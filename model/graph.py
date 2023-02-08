from model.topdown_gru import ConvGRUTopDownCell
import torch
from torch import nn
import torch.nn.functional as F

#def conv_output_size(input_size, kernel_size, stride=1):
#    padding = kernel_size[0] // 2
#    return ((input_size - kernel_size) // stride) + 1

class Node:
    def __init__(self, index, input_nodes, output_nodes, input_size = (28, 28), input_dim = 1, hidden_dim = 10, kernel_size = (3,3)):
        self.index = index
        self.in_nodes_indices = input_nodes #nodes passing values into current node #contains Node index (int)
        self.out_nodes_indices = output_nodes #nodes being passed with values from current node #contains Node index (int)
        self.in_strength = [] #connection strengths of in_nodes
        self.out_strength = [] #connection strength of out_nodes
        self.rank_list = [-1] #default value. if the Node end up with only -1 as its rank_list element, then 


        #cell params
        self.input_size = input_size #Height and width of input tensor as (height, width).
        self.input_dim = input_dim
        self.hidden_dim = hidden_dim
        self.kernel_size = kernel_size 

    def __eq__(self, other): 
        return self.index == other.index


class Graph(object):
    """ 
    A brain architecture graph object, directed by default. 
    
    :param connections (n x n)
        directed binary matrix of connections row --> column 
    :param connection_strength
    """
    def __init__(self, connections, conn_strength, 
                 input_node_indices, output_node_index, 
                 input_node_params = [(1, 28, 28, 3, 3)], 
                 output_size = 10, 
                 directed=True, dtype = torch.cuda.FloatTensor, 
                 topdown = True, bias = False):
        self.input_node_indices = input_node_indices
        self.output_node_index = output_node_index
        self.input_node_params = input_node_params #a list of length len(input_node_indices), each consist of a list of 3: c,h,w 
        self.conn = connections #adjacency matrix
        self.conn_strength = conn_strength
        self.directed = directed #flag for whether the connections are directed 
        self.num_node = connections.shape[0]
        self.max_rank = -1
        self.num_edge = 0 #assuming directed edge. Will need to change if graph is undirected
        self.topdown = topdown
        self.nodes = self.generate_node_list(connections, input_node_params) #a list of Node object
        self.dtype = dtype 
        self.bias = bias
        self.output_size = output_size
        #self.nodes[output_node].dist = 0
        #self.max_length = self.find_longest_path_length()
        for input_node in self.input_node_indices:
            self.rank_node(self.nodes[input_node],self.nodes[self.output_node_index], 0, 0)

        # for node in range (self.num_node):
            
        #     print(self.nodes[node].rank_list)



    def generate_node_list(self,connections, input_node_params):
        nodes = []
        # initialize node list
        for n in range(self.num_node):
            input_nodes = torch.nonzero(connections[:, n])
            output_nodes = torch.nonzero(connections[n, :])
            input_dim = input_node_params[n][0]
            input_size = (input_node_params[n][1], input_node_params[n][2])
            kernel_size = (input_node_params[n][3], input_node_params[n][4])
            
            node = Node(n, input_nodes, output_nodes, input_dim=input_dim, input_size=input_size)
            nodes.append(node)
            
        return nodes
    
    def rank_node(self, current_node, output_node_index, rank_val, num_pass):
        ''' ranks each node in the graph'''
        current_node.rank_list.append(rank_val)
        rank_val = rank_val + 1
        for node in current_node.out_nodes_indices:
            num_pass = num_pass + 1
            if (current_node == output_node_index and num_pass == self.num_edge):
                self.max_rank = current_node.rank.max()
                return
            else:
                self.rank_node(self.nodes[node], output_node_index, rank_val, num_pass)

    def build_architecture(self):
        architecture = Architecture(self).cuda().float()
        return architecture

    def find_feedforward_cells(self, node):
        return self.nodes[node].in_nodes_indices

    def find_feedback_cells(self, node, t):
        return self.nodes[node].out_nodes_indices
        # if ((t+1) in self.nodes[n].rank_list):
        #     in_nodes.append(n)
        # return in_nodes

    def find_longest_path_length(self): #TODO: 
        return 42
        #I think this is not needed but we'll see

class Architecture(nn.Module):
    def __init__(self, graph, input_sizes, img_channel_dims, rep=1):
        '''
        :param graph (Grapph object)
            object containing architecture graph
        :param img_sizes (list of tuples)
            list of input sizes (height, width) per node. If a node doesn't receive an outside input, it's (0, 0)
        :param img_channel_dims (list of ints)
            list of input dimension sizes per node. If a node doesn't receive an outside input, it's 0
        
        '''
        super(Architecture, self).__init__()

        self.graph = graph
        self.rep = rep # repetition, i.e how many times to view the sequence in full
        
        
        cell_list = []
        for node in range(graph.num_node):
            cell_list.append(ConvGRUTopDownCell(input_size=((graph.nodes[node].input_size[0], graph.nodes[node].input_size[1])), 
                                         input_dim=graph.nodes[node].input_dim, 
                                         hidden_dim = graph.nodes[node].hidden_dim,
                                         kernel_size=graph.nodes[node].kernel_size,
                                         bias=graph.bias,
                                         dtype=graph.dtype))
        self.cell_list = nn.ModuleList(cell_list)
        
        #this is some disgusting line of code
        # Mashbayar: don't worry, does this look better?
        h, w = self.graph.nodes[self.graph.output_node_index].input_size
        self.fc1 = nn.Linear(h * w * self.graph.nodes[self.graph.output_node_index].hidden_dim, 100) 
        self.fc2 = nn.Linear(100, self.graph.output_size)
        

        # PROJECTIONS FOR INPUT
        #assuming all cells have the same input dim and the same hidden dim
        #input_conv_list = []
        #for input in range(len(self.graph.input_node_indices)):
        #    input_conv_list.append(nn.Conv2d(in_channels= self.graph.nodes[self.graph.input_node_indices[input]].input_dim,
        #                        out_channels= self.graph.nodes[self.graph.input_node_indices[input]].hidden_dim,
        #                        kernel_size=3,
        #                        padding=1,
        #                        device = 'cuda'))
        #self.input_conv_list = nn.ModuleList(input_conv_list)
        
        # PROJECTIONS FOR BOTTOM-UP INTERLAYER CONNECTIONS
        bottomup_projections = []
        
        for node in range(graph.num_node):
            # dimensions of ALL bottom-up inputs to current node
            #all_input_h = sum([conv_output_size(graph.nodes[i.item()].input_size[0], graph.nodes[i.item()].kernel_size[0]) 
            #                   for i in self.graph.nodes[node].in_nodes_indices]) + input_sizes[node][0]
            #all_input_w = sum([conv_output_size(graph.nodes[i.item()].input_size[1], graph.nodes[i.item()].kernel_size[1]) 
            #                  for i in self.graph.nodes[node].in_nodes_indices]) + input_sizes[node][1]
            
            all_input_h = sum([graph.nodes[i.item()].input_size[0] for i in self.graph.nodes[node].in_nodes_indices]) + input_sizes[node][0]
            all_input_w = sum([graph.nodes[i.item()].input_size[1] for i in self.graph.nodes[node].in_nodes_indices]) + input_sizes[node][1]
            all_input_dim = sum([graph.nodes[i.item()].hidden_dim for i in self.graph.nodes[node].in_nodes_indices]) + img_channel_dims[node]
            
            target_h, target_w = graph.nodes[node].input_size
            
            proj = nn.Linear(all_input_dim*all_input_h*all_input_w, graph.nodes[node].input_dim*target_h*target_w)
            bottomup_projections.append(proj)
        self.bottomup_projections = nn.ModuleList(bottomup_projections)
        
        
        # PROJECTIONS FOR TOPDOWN INTERLAYER CONNECTIONS
        topdown_gru_proj = []
        for node in range(self.graph.num_node):
            # dimensions of ALL top-down inputs to current node
            #all_input_h = sum([conv_output_size(graph.nodes[i.item()].input_size[0], graph.nodes[i.item()].kernel_size[0]) 
            #                   for i in self.graph.nodes[node].out_nodes_indices]) + input_sizes[node][0]
            #all_input_w = sum([conv_output_size(graph.nodes[i.item()].input_size[1], graph.nodes[i.item()].kernel_size[1]) 
            #                   for i in self.graph.nodes[node].out_nodes_indices]) + input_sizes[node][1]
            
            all_input_h = sum([graph.nodes[i.item()].input_size[0] for i in self.graph.nodes[node].out_nodes_indices])
            all_input_w = sum([graph.nodes[i.item()].input_size[1] for i in self.graph.nodes[node].out_nodes_indices])
            all_input_dim = sum([graph.nodes[i.item()].input_dim for i in self.graph.nodes[node].out_nodes_indices])
            
            # dimensions accepted by current node
            target_h, target_w = graph.nodes[node].input_size
            target_c = graph.nodes[node].hidden_dim + graph.nodes[node].input_dim
            
            proj = nn.Linear(all_input_dim*all_input_h*all_input_w, target_c*target_h*target_w)
            topdown_gru_proj.append(proj)
        self.topdown_projections = nn.ModuleList(topdown_gru_proj)

    def forward(self, all_inputs):
        """
        :param a list of tensor of size n, each consisting a input_tensor: (b, t, c, h, w). 
            n as the number of input signals. Order should correspond to self.graph.input_node_indices
        :param topdown: size (b,hidden,h,w) 
        :return: label 
        """
        #find the time length of the longest input signal + enough extra time for the last input to go through all nodes
        seq_len = max([i.shape[1] for i in all_inputs])
        process_time = seq_len + self.graph.num_node - 1
        batch_size = all_inputs[0].shape[0]
        hidden_states = self._init_hidden(batch_size=batch_size)
        hidden_states_prev = self._init_hidden(batch_size=batch_size)
        #time = seq_len * self.rep
        
        # Each time you look at the sequence
        for rep in range(self.rep):
            
            # For each image
            for t in range(process_time):

                # Go through each node and see if anything should be processed
                for node in range(self.graph.num_node):

                    # input size is same for all bottomup and topdown input for ease of combining inputs
                    c = self.graph.nodes[node].input_dim
                    h, w = self.graph.nodes[node].input_size

                    ########################################
                    # Find bottomup inputs
                    bottomup = []

                    # direct stimuli if node receives it + the sequence isn't done
                    if node in self.graph.input_node_indices and (t < seq_len):
                        inp = all_inputs[self.graph.input_node_indices.index(node)]
                        bottomup.append(inp[:, t, :, :, :].flatten(start_dim=1))
                        #bottomup.append(inp[:, t, :, :, :])

                    # bottom-up input from other nodes
                    for i, bottomup_node in enumerate(self.graph.nodes[node].in_nodes_indices):
                        bottomup.append(hidden_states_prev[bottomup_node].flatten(start_dim=1))
                        #bottomup.append(hidden_states[bottomup_node])
                    
                    # if there's no new info, skip rest of loop
                    if not bottomup or torch.count_nonzero(torch.cat(bottomup, dim=1)) == 0:   
                        continue
                    
                    # else concatenate all inputs and project to correct size
                    bottomup = torch.cat(bottomup, dim=1)
                    bottomup = self.bottomup_projections[node](bottomup).reshape(batch_size, c, h, w)
                    
                    ##################################
                    # Find topdown inputs, assumes every feedforward connection out of node has feedback
                    # Note there's no external topdown input
                    topdown = []

                    for i, topdown_node in enumerate(self.graph.nodes[node].out_nodes_indices):
                        topdown.append(hidden_states_prev[topdown_node].flatten(start_dim=1))
                        #print(topdown[0].shape)
                    
                    if not topdown or torch.count_nonzero(torch.cat(topdown, dim=1)) == 0:
                        topdown = None
                    else:
                        topdown = self.topdown_projections[node](torch.cat(topdown, dim=1))
                        topdown = topdown.reshape(batch_size, self.graph.nodes[node].input_dim + self.graph.nodes[node].hidden_dim, h, w)
                    
                    #################################################
                    # Finally, pass to layer
                    h = self.cell_list[node](bottomup, hidden_states[node], topdown)
                    hidden_states[node] = h
                hidden_states_prev = hidden_states

        pred = self.fc1(F.relu(torch.flatten(hidden_states[self.graph.output_node_index], start_dim=1)))
        pred = self.fc2(F.relu(pred))
          
        return pred

    def _init_hidden(self, batch_size):
        init_states = []
        for i in range(self.graph.num_node):
            init_states.append(self.cell_list[i].init_hidden(batch_size))
        return init_states