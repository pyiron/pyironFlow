import React, { useCallback, useState, useEffect, createContext } from 'react';
import { createRender, useModel } from "@anywidget/react";
import ELK from 'elkjs/lib/elk.bundled.js';
import {
  ReactFlow, 
  Controls, 
  MiniMap,
  Background, 
  applyEdgeChanges,
  applyNodeChanges,  
  addEdge,} from '@xyflow/react';
import '@xyflow/react/dist/style.css';


import TextUpdaterNode from './TextUpdaterNode.jsx';
import CustomNode from './CustomNode.jsx';

import './text-updater-node.css';

const rfStyle = {
  backgroundColor: '#B8CEFF',
};

export const UpdateDataContext = createContext(null);


// const nodeTypes = { textUpdater: TextUpdaterNode, customNode: CustomNode };


const render = createRender(() => {
  const model = useModel();
  // console.log("model: ", model);
  const initialNodes = JSON.parse(model.get("nodes")) 
  const initialEdges = JSON.parse(model.get("edges"))    

  const [nodes, setNodes] = useState(initialNodes);
  const [edges, setEdges] = useState(initialEdges); 


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
        model.set("nodes", JSON.stringify(new_nodes));
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
            model.set("edges", JSON.stringify(new_edges));
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