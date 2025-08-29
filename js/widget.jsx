import React, { useCallback, useState, useEffect, createContext, useRef, useSelection } from 'react';
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
import { ReactFlowProvider } from '@xyflow/react';


import TextUpdaterNode from './TextUpdaterNode.jsx';
import CustomNode from './CustomNode.jsx';
import {getLayoutedNodes2}  from './useElkLayout';

import './text-updater-node.css';
import './widget.css';
import './ContextMenu.css';
import ContextMenu from './ContextMenu';

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
  // reference to the DOM element containing the UI
  const reactFlowWrapper = useRef(null);
  const model = useModel();

  const initialNodes = JSON.parse(model.get("nodes"))
  const initialEdges = JSON.parse(model.get("edges"))

  const [nodes, setNodes] = useState(initialNodes);
  const [edges, setEdges] = useState(initialEdges); 

  const selectedNodes = [];
  const selectedEdges = [];

  const [menu, setMenu] = useState(null);
  const ref = useRef(null);

  const nodeTypes = {
    textUpdater: TextUpdaterNode, 
    customNode: CustomNode,
  };

  const layoutNodes = async () => {
    const layoutedNodes = await getLayoutedNodes2(nodes, edges);
    setNodes(layoutedNodes);
    // setTimeout(() => fitView(), 0);
  };

  const outputFunction = (data) => {
    // direct output of node to output widget
    console.log('output: ', data.label)
    model.set("commands", `output: ${data.label}`);
    model.save_changes();
}

const sourceFunction = (data) => {
    // show source code of node
    console.log('source: ', data.label) 
    model.set("commands", `source: ${data.label}`);
    model.save_changes();        
}

  const onNodeContextMenu = useCallback(
    (event, node) => {
      // Prevent native context menu from showing
      event.preventDefault();
 
      const wrapperRect = reactFlowWrapper.current.getBoundingClientRect();
    setMenu({
      id: node.id,
      top: event.clientY - wrapperRect.top,  // relative to wrapper top
      left: event.clientX - wrapperRect.left, // relative to wrapper left
      data: node.data
      });
    },
  );

  const onPaneClick = useCallback(() => setMenu(null), [setMenu]);
  
  useEffect(() => {
    layoutNodes();
  }, [setNodes]);

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
   
  model.on("change:nodes", () => {
      const new_nodes = model.get("nodes")
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
        var selectionChanged = false;
        for (const i in changes) {
          if (Object.hasOwn(changes[i], 'selected')) {
            if (changes[i].selected){
              for (const k in new_nodes){
                if (new_nodes[k].id == changes[i].id) {
                  selectedNodes.push(new_nodes[k]);
                  selectionChanged = true;
                }
              }
            }
            else{
              for (const j in selectedNodes){
                if (selectedNodes[j].id == changes[i].id) {
                  selectedNodes.splice(j, 1); 
                  selectionChanged = true;
                }
              }
            }
          }
        }
        if (selectionChanged) {
          console.log('selectedNodes:', selectedNodes); 
          model.set("selected_nodes", JSON.stringify(selectedNodes));
          model.save_changes()
        }
        return new_nodes;
      });
    },
    [setNodes],
  );

  const onNodeDragStop = useCallback(
    (event, node, event_nodes) => {
      // communicates updated positions to python backend, can probably be cut
      // in the future
      model.set("nodes", JSON.stringify(nodes));
      model.save_changes();
    },
    [nodes]
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

  function getOS() {
    var userAgent = window.navigator.userAgent;
    if (/Mac/.test(userAgent)) {
        return 'Mac OS';
    } else if (/Win/.test(userAgent)) {
        return 'Windows';
    } else if (/Linux/.test(userAgent)) {
        return 'Linux';
    }
    return 'Unknown OS';
  }

  var os = getOS();
  var macrobuttonStyle = {position: "absolute", zIndex: "4"};

  if (os === "Windows") {
    macrobuttonStyle = { ...macrobuttonStyle, right: "80px", top: "50px" }
  } else if (os === "Linux") {
    macrobuttonStyle = { ...macrobuttonStyle, right: "100px", top: "50px" }
  } else if (os === "Mac OS") {
    macrobuttonStyle = { ...macrobuttonStyle, right: "100px", top: "50px" }
  }

  // const macroFunction = (userInput) => {
  //   console.log('macro: ', userInput);
  //   if (model) {
  //     model.set("commands", `macro: ${userInput}`);
  //     model.save_changes();
  //   } else {
  //     console.error('model is undefined');
  //   }
  // }

  const runFunction = (dateTime) => {
    console.log('run executed at ', dateTime);
    if (model) {
      model.set("commands", `run executed at ${dateTime}`);
      model.save_changes();
    } else {
      console.error('model is undefined');
    }
  }

  const saveFunction = (dateTime) => {
    console.log('save executed at ', dateTime);
    if (model) {
      model.set("commands", `save executed at ${dateTime}`);
      model.save_changes();
    } else {
      console.error('model is undefined');
    }
  }

  const loadFunction = (dateTime) => {
    console.log('load executed at ', dateTime);
    if (model) {
      model.set("commands", `load executed at ${dateTime}`);
      model.save_changes();
    } else {
      console.error('model is undefined');
    }
  }

  const deleteFunction = (dateTime) => {
    console.log('delete executed at ', dateTime);
    if (model) {
      model.set("commands", `delete executed at ${dateTime}`);
      model.save_changes();
    } else {
      console.error('model is undefined');
    }
  }

  // whenever the user stops panning update the model with the current location
  // and size, so the backend knows where to place new nodes
  // BUG: When the component resizes due to the browser changing the viewport
  // this is not triggered, but it listens only panning events by the user
  // useOnViewportChange may be another option
  const onMoveEnd = useCallback( (event, viewport) => {
    if (!reactFlowWrapper.current) return;

    const bounds = reactFlowWrapper.current.getBoundingClientRect();
    model.set("view", JSON.stringify({
      x: viewport.x/viewport.zoom,
      y: viewport.y/viewport.zoom,
      width: bounds.width/viewport.zoom,
      height: bounds.height/viewport.zoom
    }));
    model.save_changes();
  }, [model, reactFlowWrapper]);

  return (
    <ReactFlowProvider>
    <div ref={reactFlowWrapper} style={{ position: "relative", height: "100%", width: "100%" }}>
      <UpdateDataContext.Provider value={updateData}> 
        <ReactFlow 
            nodes={nodes} 
            edges={edges}
            onNodesChange={onNodesChange}
            onNodeDragStop={onNodeDragStop}
            onEdgesChange={onEdgesChange}
            onConnect={onConnect}
            onNodesDelete={onNodesDelete}
            onMoveEnd={onMoveEnd}
            nodeTypes={nodeTypes}
            onPaneClick={onPaneClick}
            onNodeContextMenu={onNodeContextMenu}
            fitView
            style={rfStyle}
            /*debugMode={true}*/
        >
      {/*
          <div style={{ position: "absolute", right: "10px", top: "10px", zIndex: "4", fontSize: "12px"}}>
            <label style={{display: "block"}}>Macro class name:</label>
            <input
              value={macroName}
              onChange={(evt) => setMacroName(evt.target.value)}
            />
          </div>
          */}
          <Background variant="dots" gap={20} size={2} />
          <MiniMap />
          <Controls />
      {/*
          <button
            style={macrobuttonStyle}
            onClick={() => macroFunction(macroName)}
          >
            Create Macro
          </button>
          */}
          <div
            style={{position: "absolute", left: "1rem", top: "1rem", zIndex: "4"}}
          >
          <button
            onClick={() => runFunction(currentDateTime)}
            title="Run all nodes in the workflow"
          >
            Run
          </button>
          <button
            onClick={() => saveFunction(currentDateTime)}
            title="Save the current state of the workflow to a file"
          >
            Save
          </button>
          <button
            onClick={() => loadFunction(currentDateTime)}
            title="Load the previously saved state of the workflow"
          >
            Load
          </button>
          <button
            onClick={() => deleteFunction(currentDateTime)}
            title="Delete the save file of the workflow"
          >
            Delete
          </button>
          </div>
          <a
            href="https://github.com/pyiron/pyironFlow/blob/main/docs/user_guide.md" target="_blank"
            style={{position: "absolute", right: "1rem", top: "1rem", zIndex: "4"}}
          >
          <button title="Documentation, launches in a new tab">Help</button>
          </a>
          <button
            style={{position: "absolute", right: "130px", bottom: "170px", zIndex: "4"}}
            onClick={layoutNodes}
            title="Automatically (re-)layout the nodes"
          >
            Reset Layout
          </button>
        </ReactFlow>
        {menu && <ContextMenu onOutput={outputFunction} onSource={sourceFunction} onClick={onPaneClick} {...menu} />}
      </UpdateDataContext.Provider>
    </div>
    </ReactFlowProvider>
  );
});

export default { render };
