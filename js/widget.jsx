import React, { useCallback, useState, useEffect, createContext   } from 'react';
import { createRender, useModel } from "@anywidget/react";
import ELK from 'elkjs/lib/elk.bundled.js';
import {
  ReactFlow, 
  Controls, 
  MiniMap,
  Background, 
  applyEdgeChanges,
  applyNodeChanges,  
  addEdge,
  useOnSelectionChange,

} from '@xyflow/react';
import '@xyflow/react/dist/style.css';


import TextUpdaterNode from './TextUpdaterNode.jsx';
import CustomNode from './CustomNode.jsx';

import './text-updater-node.css';

const rfStyle = {
  backgroundColor: '#B8CEFF',
};

export const UpdateDataContext = createContext(null);


// const nodeTypes = { textUpdater: TextUpdaterNode, customNode: CustomNode };

function SelectionDisplay() {
  const [selectedNodes, setSelectedNodes] = useState([]);
  const [selectedEdges, setSelectedEdges] = useState([]);
 
  // the passed handler has to be memoized, otherwise the hook will not work correctly
  const onChange = useCallback(({ nodes, edges }) => {
    setSelectedNodes(nodes.map((node) => node.id));
    setSelectedEdges(edges.map((edge) => edge.id));
  }, []);
 
  useOnSelectionChange({
    onChange,
  });
 
  return (
    <div>
      <p>Selected nodes: {selectedNodes.join(', ')}</p>
      <p>Selected edges: {selectedEdges.join(', ')}</p>
    </div>
  );
}


const render = createRender(() => {
  const model = useModel();
  // console.log("model: ", model);
  const initialNodes = JSON.parse(model.get("nodes")) 
  const initialEdges = JSON.parse(model.get("edges"))    

  const [nodes, setNodes] = useState(initialNodes);
  const [edges, setEdges] = useState(initialEdges); 

  const selectedNodes = [];
  const selectedEdges = [];

  const nodeTypes = {
    textUpdater: TextUpdaterNode, 
    customNode: CustomNode,
  };


  const updateData = (nodeLabel, handleIndex, newValue) => {
      setNodes(prevNodes =>
        prevNodes.map((node, idx) => {
          console.log('updatedDataNodes: ', nodeLabel, handleIndex, newValue, node.id);  
          if (node.id !== nodeLabel) {
            return node;
          }
  
          // This line assumes that node.data.target_values is an array
          const updatedTargetValues = [...node.data.target_values];
          updatedTargetValues[handleIndex] = newValue;
          console.log('updatedData2: ', updatedTargetValues); 
  
          return {
            ...node,
            data: {
              ...node.data,
              target_values: updatedTargetValues,
            }
          };
        }),
      );
  };

    // for test only, can be later removed
    useEffect(() => {
      console.log('nodes_test:', nodes);
      model.set("nodes", JSON.stringify(nodes)); // TODO: maybe better do it via command changeValue(nodeID, handleID, value)
      model.save_changes()
    }, [nodes]);
   
  model.on("change:nodes", () => {
      const new_nodes = model.get("nodes")
      // console.log("load nodes: ", new_nodes);

      setNodes(JSON.parse(new_nodes));
      }); 

  model.on("change:edges", () => {
      const new_edges = model.get("edges")
      setEdges(JSON.parse(new_edges));
      });     

    

    
  const onNodesChange = useCallback(
    (changes) => {
      setNodes((nds) => {
        const new_nodes = applyNodeChanges(changes, nds); 
        console.log('onNodesChange: ', changes, new_nodes);
        for (const i in changes) {
            if (Object.hasOwn(changes[i], 'selected')) {
              if (changes[i].selected){
                for (const k in nodes){
                  if (nodes[k].id == changes[i].id) {
                    selectedNodes.push(nodes[k]);
                  }  

                }
              }
              else{
                for (const j in selectedNodes){
                  if (selectedNodes[j].id == changes[i].id) {
                //const index = selectedNodes[j].indexOf(changes[i].id);
                    selectedNodes.splice(j, 1); 
                  }  
                }
              }
            }
        }
        console.log('selectedNodes:', selectedNodes); 
        console.log('nodes:', nodes); 
        model.set("nodes", JSON.stringify(new_nodes));
        model.set("selected_nodes", JSON.stringify(selectedNodes));
        model.save_changes();
        
            
        
        return new_nodes;
      });
    },
    [setNodes],
  );
    
  const onEdgesChange = useCallback(
    (changes) => {
        setEdges((eds) => {
            const new_edges = applyEdgeChanges(changes, eds);
            for (const i in changes) {
              if (Object.hasOwn(changes[i], 'selected')) {
                if (changes[i].selected){
                  for (const k in new_edges){
                    if (new_edges[k].id == changes[i].id) {
                      selectedEdges.push(new_edges[k]);
                    }   
                  }
                }
                else{
                  for (const j in selectedEdges){
                    if (selectedEdges[j].id == changes[i].id) {
                      selectedEdges.splice(j, 1); 
                    }  
                  }
                }
              }
            }
            for (const n in selectedEdges){
                var filterResult = new_edges.filter((edge) => edge.id === selectedEdges[n].id);
                if (filterResult == []){
                    selectedEdges.splice(n, 1);
                }
            }
                
            console.log('selectedEdges:', selectedEdges); 
            console.log('edges:', new_edges);
            model.set("edges", JSON.stringify(new_edges));
            model.set("selected_edges", JSON.stringify(selectedEdges));
            model.save_changes();
            return new_edges;            
      });
    },
    [setEdges],
  );

  const onConnect = useCallback(
    (params) => {
        setEdges((eds) => {
            const new_edges = addEdge(params, eds);
            model.set("edges", JSON.stringify(new_edges));
            model.save_changes();
            return new_edges;            
      });
    },
    [setEdges],
  ); 


  const deleteNode = (id) => {
    // direct output of node to output widget
    console.log('output: ', id)
    if (model) {
      model.set("commands", `delete_node: ${id} - ${new Date().getTime()}`);
      model.save_changes();
    } else {
      console.error('model is undefined');
    }
  }

  const onNodesDelete = useCallback(
    (deleted) => {  
      console.log('onNodesDelete: ', deleted)
      deleteNode(deleted[0].id)
    });

  const setPosition = useCallback(
  (pos) =>
   setNodes((nodes) =>
     nodes.map((node) => ({
          ...node,
          data: { ...node.data, toolbarPosition: pos },
        })),
      ),
    [setNodes],
  );  
    
  const forceToolbarVisible = useCallback((enabled) =>
    setNodes((nodes) =>
      nodes.map((node) => ({
        ...node,
        data: { ...node.data, forceToolbarVisible: enabled },
      })),
    ),
  );    
  

  return (    
    <div style={{ position: "relative", height: "400px", width: "100%" }}>
      <UpdateDataContext.Provider value={updateData}> 
        <ReactFlow 
            nodes={nodes} 
            edges={edges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onConnect={onConnect}
            onNodesDelete={onNodesDelete}
            nodeTypes={nodeTypes}
            fitView
            style={rfStyle}>
          <Background variant="dots" gap={12} size={1} />
          <MiniMap />  
          <Controls />
            
        </ReactFlow>
      </UpdateDataContext.Provider>
    </div>
  );
});

export default { render };