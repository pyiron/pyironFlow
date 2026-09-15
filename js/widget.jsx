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
  // Close takes two clicks: the first arms it, the second closes the tab
  const [confirmClose, setConfirmClose] = useState(false);
  useEffect(() => {
    if (!confirmClose) {
      return;
    }
    const timer = setTimeout(() => setConfirmClose(false), 4000);
    return () => clearTimeout(timer);
  }, [confirmClose]);
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

  const onPaneClick = useCallback(() => {
    setMenu(null);
    setConfirmClose(false);
  }, [setMenu]);
  
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


  // target_values holds one key per port the user entered something into, keyed by port
  // label. Absence is the only marker for "nothing entered", which is what lets null
  // through as the value a user meant when they typed None. An emptied field therefore
  // drops its key rather than storing a blank.
  const updateData = (nodeLabel, portLabel, newValue) => {
      setNodes(prevNodes =>
        prevNodes.map((node) => {
          if (node.id !== nodeLabel) {
            return node;
          }

          const entered = { ...(node.data.target_values ?? {}) };
          if (newValue === "") {
            delete entered[portLabel];
          } else {
            entered[portLabel] = newValue;
          }

          return {
            ...node,
            data: {
              ...node.data,
              target_values: entered,
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
    setConfirmClose(false);
    console.log('run executed at ', dateTime);
    if (model) {
      model.set("commands", `run executed at ${dateTime}`);
      model.save_changes();
    } else {
      console.error('model is undefined');
    }
  }

  // Export, Import and Save only open the Files panel on the Python side
  const openFilesFunction = (name, dateTime) => {
    setConfirmClose(false);
    console.log(`${name} executed at `, dateTime);
    if (model) {
      model.set("commands", `${name} executed at ${dateTime}`);
      model.save_changes();
    } else {
      console.error('model is undefined');
    }
  }

  // Save stays disabled until Python holds a run to save
  const [hasRun, setHasRun] = useState(model.get("has_run"));
  useEffect(() => {
    const onHasRun = () => setHasRun(model.get("has_run"));
    model.on("change:has_run", onHasRun);
    return () => model.off("change:has_run", onHasRun);
  }, [model]);

  // The workflow's label, offered as the default when renaming
  const [label, setLabel] = useState(model.get("label"));
  useEffect(() => {
    const onLabel = () => setLabel(model.get("label"));
    model.on("change:label", onLabel);
    return () => model.off("change:label", onLabel);
  }, [model]);

  const renameFunction = (dateTime) => {
    setConfirmClose(false);
    const answer = window.prompt("New name for this workflow", label);
    const newLabel = answer === null ? "" : answer.trim();
    if (newLabel === "" || newLabel === label) {
      return;
    }
    console.log('rename executed at ', dateTime, ' as ', newLabel);
    if (model) {
      model.set("commands", `rename executed at ${dateTime} as ${newLabel}`);
      model.save_changes();
    } else {
      console.error('model is undefined');
    }
  }

  const closeFunction = (dateTime) => {
    if (!confirmClose) {
      setConfirmClose(true);
      return;
    }
    setConfirmClose(false);
    console.log('close executed at ', dateTime);
    if (model) {
      model.set("commands", `close executed at ${dateTime}`);
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
            onClick={() => openFilesFunction("export", currentDateTime)}
            title="Export the workflow recipe to a JSON file (opens the Files panel)"
          >
            Export
          </button>
          <button
            onClick={() => openFilesFunction("import", currentDateTime)}
            title="Import a workflow recipe from a JSON file into a new tab (opens the Files panel)"
          >
            Import
          </button>
          <button
            onClick={() => openFilesFunction("save", currentDateTime)}
            disabled={!hasRun}
            title={hasRun
              ? "Save the most recent run or pull to a file (opens the Files panel)"
              : "Nothing to save yet: press Run, or pull on a node, first"}
          >
            Save
          </button>
          <button
            onClick={() => renameFunction(currentDateTime)}
            title="Rename this workflow and its tab"
          >
            Rename
          </button>
          <button
            onClick={() => closeFunction(currentDateTime)}
            style={confirmClose ? {background: "#d9534f", color: "white"} : undefined}
            title={confirmClose
              ? "Click again to close this tab"
              : "Close this tab (asks for a second click)"}
          >
            {confirmClose ? "Confirm close" : "Close"}
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
