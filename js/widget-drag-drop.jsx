// does not work (Error: [React Flow]: Seems like you have not used zustand provider as an ancestor.)
// It is likely a limitation of anywidget (only a single react tree)
// ipyreact should be able to overcome it

import React, { useCallback, useState } from 'react';
import { createRender, useModel } from "@anywidget/react";
import {
  ReactFlow, 
  Controls, 
  MiniMap,
  Background, 
  useNodesState,
  useEdgesState,
  useReactFlow,
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


const nodeTypes = { textUpdater: TextUpdaterNode, customNode: CustomNode };


const render = createRender(() => {
// function render({ model, el }) {
  const model = useModel();
  // console.log("model: ", model);
  const initialNodes = JSON.parse(model.get("nodes")) 
  const initialEdges = JSON.parse(model.get("edges"))    

  const [nodes, setNodes] = useState(initialNodes);
  const [edges, setEdges] = useState(initialEdges);
  const { screenToFlowPosition } = useReactFlow();  

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

  const onDragOver = useCallback((event) => {
    event.preventDefault();
    event.dataTransfer.dropEffect = 'move';
  }, []);

  const onDrop = useCallback(
    (event) => {
      event.preventDefault();

      console.log(event)  
      const type = event.dataTransfer.getData('application/reactflow');

      // check if the dropped element is valid
      if (typeof type === 'undefined' || !type) {
        return;
      }

      // project was renamed to screenToFlowPosition
      // and you don't need to subtract the reactFlowBounds.left/top anymore
      // details: https://reactflow.dev/whats-new/2023-11-10
      const position = screenToFlowPosition({
        x: event.clientX,
        y: event.clientY,
      });
      const newNode = {
        id: getId(),
        type,
        position,
        data: { label: `${type} node` },
      };

      setNodes((nds) => nds.concat(newNode));
    },
    [screenToFlowPosition],
  );    


  // el.appendChild(
  return (    
    <div style={{ position: "relative", height: "400px", width: "100%" }}>
      <ReactFlow 
          nodes={nodes} 
          edges={edges}
          // onNodesChange={onNodesChange}
          // onEdgesChange={onEdgesChange}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onConnect={onConnect}
          onDrop={onDrop}
          onDragOver={onDragOver}
          nodeTypes={nodeTypes}
          fitView
          style={rfStyle}>
        <Background variant="dots" gap={12} size={1} />
        <MiniMap />  
        <Controls />
      </ReactFlow>
    </div>
  );
});

export default { render };