import React, { useCallback, useState, useEffect, createContext, useSelection } from 'react';
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
import CustomMacroNode from './CustomMacroNode.jsx';
import MacroSubNode from './MacroSubNode.jsx';
import ghostNode from './ghostNode.jsx'
import {getLayoutedNodes2}  from './useElkLayout';

import { initialNodes } from './nodes';

import './text-updater-node.css';

/**
 * Author: Joerg Neugebauer
 * Copyright: Copyright 2024, Max-Planck-Institut for Sustainable Materials GmbH - Computational Materials Design (CM) Department
 * Version: 0.2
 * Maintainer: 
 * Email: 
 * Status: development 
 * Date: Aug 1, 2024
 */


const rfStyle = {
  backgroundColor: '#B8CEFF',
  //backgroundColor: '#dce1ea',
  //backgroundColor: 'white',
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

  const selectedNodes = [];
  const selectedEdges = [];

  const nodeTypes = {
    textUpdater: TextUpdaterNode, 
    customNode: CustomNode,
    macroSubNode: MacroSubNode,
    customMacroNode: CustomMacroNode,
    ghostNode: ghostNode,
  };

  const layoutNodes = async () => {
    const layoutedNodes = await getLayoutedNodes2(nodes, edges);
    setNodes(layoutedNodes);
    // setTimeout(() => fitView(), 0);
  };
  
  useEffect(() => {
    layoutNodes();

      const new_nodes = model.get("nodes")
      // console.log("load nodes: ", new_nodes);

      //setNodes(JSON.parse(new_nodes));

      const updatedNodes = JSON.parse(new_nodes).map(node => ({
        ...node,
        //data: { ...node.data, onMessage: layoutSingleMacro},
        data: { ...node.data, onMessage: layoutMacroSubflow},  
      }));
      // console.log('updatedNodes', updatedNodes);
      setNodes(updatedNodes);
    
  }, [setNodes]);
    


  const sleep = ms => new Promise(r => setTimeout(r, ms));

  const [macroName, setMacroName] = useState('custom_macro');

  const [currentDateTime, setCurrentDateTime] = useState(() => {
    const currentTime = new Date();
    return currentTime.toLocaleString();
  });

  useEffect(() => {
    const intervalId = setInterval(() => {
     const currentTime = new Date();
     setCurrentDateTime(currentTime.toLocaleString());
    }, 1000); // update every second
   
    return () => {
     clearInterval(intervalId);
    };
   }, []);

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


    const layoutAllMacros = async () => {
      console.log("Rearrange all Macros: "); 
      const macroNodes = nodes.filter(node => node.type == 'customMacroNode');
      var layoutedNodes = [];
      for (const id of macroNodes) {
        layoutedNodes = layoutedNodes.concat(layoutMacroSubflow(id)); 
        
        }
      console.log("Rearrange all Macros: ", layoutedNodes); 
    }

    const waitForLayout = async (id) => {
      await sleep(2000);
      console.log("Waited two seconds");  
      layoutNodes();
    };

    const layoutMacroSubflow = async (id) => {
      console.log("Rearrange this: ", id);
      const filteredEdges = edges.filter(edge => edge.parent == id);
      const filteredNodes = nodes.filter(node => node.parentId === id);
      const layoutedNodes = await getLayoutedNodes2(filteredNodes, filteredEdges);
      return layoutedNodes;
    };
    
    const layoutSingleMacro = async (id) => {
      const layoutedNodes = await layoutMacroSubflow(id)
      const restEdges = edges.filter(edge => edge.parent != id); 
      const restNodes = nodes.filter(node => node.parentId != id);

      const allNodes = restNodes.concat(layoutedNodes);  
      setNodes(allNodes);
      // setTimeout(() => fitView(), 0);
    };

    const handleNodeMessage = useCallback((nodeId, message) => {
      alert(`Node ${nodeId} says: ${message}`);
    }, []);
   
  model.on("change:nodes", () => {
      const new_nodes = model.get("nodes")
      // console.log("load nodes: ", new_nodes);

      //setNodes(JSON.parse(new_nodes));

      const updatedNodes = JSON.parse(new_nodes).map(node => ({
        ...node,
        data: { ...node.data, onMessage: layoutSingleMacro },
      }));
      // console.log('updatedNodes', updatedNodes);
      setNodes(updatedNodes);

  }); 

  model.on("change:edges", () => {
      const new_edges = model.get("edges")
      setEdges(JSON.parse(new_edges));
      });     

    model.on("change:rearrange", () => {
      layoutNodes();
      });     


  const nodeSelection = useCallback(
    (nodes) => {
      const selectedNodes = nodes.filter(node => node.selected === true);
      console.log('nodes where selection == true: ', selectedNodes);
      return selectedNodes;
  });


  const edgeSelection = useCallback(
    (edges) => {
      const selectedEdges = edges.filter(edges => edges.selected === true);
      console.log('edges where selection == true: ', selectedEdges);
    return selectedEdges;
  });


    
  const onNodesChange = useCallback(
    (changes) => {
      setNodes((nds) => {
        const new_nodes = applyNodeChanges(changes, nds);
        nodeSelection(new_nodes);
        console.log('nodes:', nodes);
        model.set("nodes", JSON.stringify(new_nodes));
        model.set("selected_nodes", JSON.stringify(nodeSelection(new_nodes)));
        model.save_changes();
        return new_nodes;
      });
    },
    [setNodes],

      // ----------------- arrange here
  );
    
  const onEdgesChange = useCallback(
    (changes) => {
      setEdges((eds) => {
        const new_edges = applyEdgeChanges(changes, eds);
        edgeSelection(new_edges);
        console.log('edges:', new_edges);
        model.set("edges", JSON.stringify(new_edges));
        model.set("selected_edges", JSON.stringify(edgeSelection(new_edges)));
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




    

  const macroFunction = (userInput) => {
    console.log('macro: ', userInput);
    if (model) {
      model.set("commands", `macro: ${userInput}`);
      model.save_changes();
    } else {
      console.error('model is undefined');
    }
  }

  
    
  return (    
    <div style={{ position: "relative", height: "800px", width: "100%" }}>
      <UpdateDataContext.Provider value={updateData}>
        <button onClick={() => layoutNodes()}>Rearrange</button>

        <ReactFlow 
            nodes={nodes} 
            edges={edges.map((edge) => ({ ...edge, style: { stroke: 'black', 'strokeWidth': 1 } }))}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onConnect={onConnect}
            onNodesDelete={onNodesDelete}
            nodeTypes={nodeTypes}
            fitView
            style={rfStyle}
            /*debugMode={true}*/
        >
          <div style={{ position: "absolute", right: "10px", top: "10px", zIndex: "4", fontSize: "12px"}}>
            <label style={{display: "block"}}>Macro class name:</label>
            <input
              value={macroName}
              onChange={(evt) => setMacroName(evt.target.value)}
            />
          </div>
          <Background variant="dots" gap={20} size={2} />
          <MiniMap />  
          <Controls />
          <button
            style={{position: "absolute", right: "100px", top: "50px", zIndex: "4"}}
            onClick={() => macroFunction(macroName)}
          >
            Create Macro
          </button>
        </ReactFlow>
      </UpdateDataContext.Provider>
    </div>
  );
});

export default { render };
