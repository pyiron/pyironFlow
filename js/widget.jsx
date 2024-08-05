import React, { useCallback, useState } from 'react';
import { createRender, useModel } from "@anywidget/react";
import {
  ReactFlow, 
  Controls, 
  MiniMap,
  Background, 
  useNodesState,
  useEdgesState,
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

const initialNodes = [
  {
    id: 'node-1',
    // type: 'textUpdater',
    type: 'customNode',  
    position: { x: 0, y: 0 },
    style: {
              border: '1px black solid',
              padding: 20
            },  
    data: { value: 123 },
  },
];
// we define the nodeTypes outside of the component to prevent re-renderings
// you could also use useMemo inside the component
const nodeTypes = { textUpdater: TextUpdaterNode, customNode: CustomNode };
const initialEdges = []



const render = createRender(() => {
  const model = useModel();

  const [nodes, setNodes] = useState(initialNodes);
  const [edges, setEdges] = useState(initialEdges);

  const onNodesChange = useCallback(
    (changes) => setNodes((nds) => applyNodeChanges(changes, nds)),
    [setNodes],
  );
  const onEdgesChange = useCallback(
    (changes) => setEdges((eds) => applyEdgeChanges(changes, eds)),
    [setEdges],
  );
  const onConnect = useCallback(
    (params) => setEdges((eds) => addEdge(params, eds)),
    [setEdges],
  );    


  React.useEffect(() => {
    function handle_custom_msg(msg) {
      const nodes_list = JSON.parse(msg);

      console.log("nodes_lst", nodes_list);
      setNodes(nodes_list);
    }
    model.on("msg:custom", handle_custom_msg);
    return () => model.off("msg:custom", handle_custom_msg);
  }, [model]);



  return (
    <div style={{ position: "relative", height: "400px", width: "800px" }}>
      <ReactFlow 
          nodes={nodes} 
          edges={edges}
          // onNodesChange={onNodesChange}
          // onEdgesChange={onEdgesChange}
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
    </div>
  );
});

export default { render };