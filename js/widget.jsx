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
  //backgroundColor: '#B8CEFF',
  backgroundColor: '#dce1ea',
  //backgroundColor: 'white',
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

  const [macroName, setMacroName] = useState('custom_macro');


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
        for (const i in changes) {
          if (Object.hasOwn(changes[i], 'selected')) {
            if (changes[i].selected){
              for (const k in new_nodes){
                if (new_nodes[k].id == changes[i].id) {
                  selectedNodes.push(new_nodes[k]);
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

  const macroFunction = (userInput) => {
    console.log('macro: ', userInput);
    if (model) {
      model.set("commands", `macro: ${userInput}`);
      model.save_changes();
    } else {
      console.error('model is undefined');
    }
  }

  const runFunction = () => {
    console.log('run_workflow');
    if (model) {
      model.set("commands", `run_workflow`);
      model.save_changes();
    } else {
      console.error('model is undefined');
    }
  }

  return (    
    <div style={{ position: "relative", height: "800px", width: "100%" }}>
      <UpdateDataContext.Provider value={updateData}> 
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
          <button
            style={{position: "absolute", left: "10px", top: "10px", zIndex: "4"}}
            onClick={() => runFunction()}
          >
            Run Workflow
          </button>
          <button
            style={{position: "absolute", left: "120px", top: "10px", zIndex: "4"}}
            /*onClick={() => macroFunction(macroName)}*/
          >
            Save Workflow
          </button>
          <button
            style={{position: "absolute", left: "230px", top: "10px", zIndex: "4"}}
            /*onClick={() => macroFunction(macroName)}*/
          >
            Load Workflow
          </button>
        </ReactFlow>
      </UpdateDataContext.Provider>
    </div>
  );
});

export default { render };
