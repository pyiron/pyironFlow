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
import { now } from './commands.js';
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


// Module scope on purpose. Rebuilding this object inside the component gives it a new
// identity on every render, which makes React Flow remount every node component.
const nodeTypes = { textUpdater: TextUpdaterNode, customNode: CustomNode };

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

  const layoutNodes = async () => {
    const layoutedNodes = await getLayoutedNodes2(nodes, edges);
    setNodes(layoutedNodes);
    // setTimeout(() => fitView(), 0);
  };

  const outputFunction = (data) => {
    // direct output of node to output widget
    console.log('output: ', data.label)
    model.set("commands", `output: ${data.label} ${now()}`);
    model.save_changes();
}

const sourceFunction = (data) => {
    // show source code of node
    console.log('source: ', data.label) 
    model.set("commands", `source: ${data.label} ${now()}`);
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

  // Without a handler React Flow swallows its own errors in a production build,
  // including the 008 it raises when an edge names a handle it cannot resolve --
  // which is a disappearing edge, and took a long time to find for want of this.
  const onFlowError = useCallback((code, message) => {
    console.warn(`[pyironFlow xyflow error ${code}]`, message);
  }, []);

  const [macroName, setMacroName] = useState('custom_macro');


  // The browser does no parsing: it sends the raw text and Python replies with either
  // the value rendered back, or an error to show on the field. Python owns the cache,
  // so nothing here writes a value into `nodes` on its own. Lock and unlock work the
  // same way: a message out, a reply in, no local guess at the outcome.
  const portActions = React.useMemo(() => ({
      commit: (nodeLabel, portLabel, text) => {
          model.send({ type: "entry", node: nodeLabel, port: portLabel, text });
      },
      lock: (nodeLabel, portLabel) => {
          model.send({ type: "lock", node: nodeLabel, port: portLabel });
      },
      unlock: (nodeLabel, portLabel) => {
          model.send({ type: "unlock", node: nodeLabel, port: portLabel });
      },
  }), [model]);

  useEffect(() => {
      const onMessage = (msg) => {
          if (!msg || msg.type !== "entry") return;
          setNodes(prevNodes =>
            prevNodes.map((node) => {
              if (node.id !== msg.node) return node;
              const values = { ...(node.data.target_values ?? {}) };
              const errors = { ...(node.data.target_errors ?? {}) };
              delete values[msg.port];
              delete errors[msg.port];
              if (msg.error) {
                  errors[msg.port] = { text: msg.text ?? "", message: msg.error };
              } else if (!msg.cleared) {
                  values[msg.port] = msg.text;
              }
              return {
                ...node,
                data: { ...node.data, target_values: values, target_errors: errors },
              };
            }),
          );
      };
      const onLockMessage = (msg) => {
          if (!msg || (msg.type !== "lock" && msg.type !== "unlock")) return;
          if (msg.error) return;  // the reply carries no state change to apply
          setNodes(prevNodes =>
            prevNodes.map((node) => {
              if (node.id !== msg.node) return node;
              const lockedPorts = { ...(node.data.target_locked ?? {}) };
              const values = { ...(node.data.target_values ?? {}) };
              const errors = { ...(node.data.target_errors ?? {}) };
              delete errors[msg.port];
              if (msg.type === "lock") {
                  lockedPorts[msg.port] = msg.locked;
                  delete values[msg.port];
              } else {
                  delete lockedPorts[msg.port];
                  if (msg.text === null || msg.text === undefined) {
                      delete values[msg.port];
                  } else {
                      values[msg.port] = msg.text;
                  }
              }
              return {
                ...node,
                data: {
                  ...node.data,
                  target_locked: lockedPorts,
                  target_values: values,
                  target_errors: errors,
                },
              };
            }),
          );
      };
      model.on("msg:custom", onMessage);
      model.on("msg:custom", onLockMessage);
      return () => {
          model.off("msg:custom", onMessage);
          model.off("msg:custom", onLockMessage);
      };
  }, [model]);

    // for test only, can be later removed
    useEffect(() => {
      console.log('nodes_test:', nodes);
      model.set("nodes", JSON.stringify(nodes)); // TODO: maybe better do it via command changeValue(nodeID, handleID, value)
      model.save_changes()
    }, [nodes]);
   
  // Registered once, with cleanup. These used to sit in the render body, so every
  // render added another listener that was never removed, and a single Python update
  // fanned out into as many duplicate state updates as there had been renders.
  useEffect(() => {
      const onNodes = () => {
          const parsed = JSON.parse(model.get("nodes"));
          // Merge rather than replace. React Flow v12 keeps each node's measured size
          // on the node object (`node.measured`) and hides any node that has none,
          // waiting for a resize to measure it. Python's payload is plain JSON with no
          // such field, so replacing the objects outright un-measures every node -- and
          // when the DOM element and its size have not actually changed, no resize ever
          // fires and the node stays hidden for good.
          setNodes((previous) => {
              const byId = new Map(previous.map((node) => [node.id, node]));
              return parsed.map((incoming) => {
                  const existing = byId.get(incoming.id);
                  return existing === undefined
                      ? incoming
                      : { ...existing, ...incoming, measured: existing.measured };
              });
          });
      };
      const onEdges = () => setEdges(JSON.parse(model.get("edges")));
      model.on("change:nodes", onNodes);
      model.on("change:edges", onEdges);
      return () => {
          model.off("change:nodes", onNodes);
          model.off("change:edges", onEdges);
      };
  }, [model, setNodes, setEdges]);

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

  // Must match `edge_id` in pyironflow/wf_extensions.py: an edge keeps its id when
  // Python re-sends the edges, and tests find it by that id.
  const edgeId = ({ source, sourceHandle, target, targetHandle }) =>
    `${source}.${sourceHandle}->${target}.${targetHandle}`;

  const onConnect = useCallback(
    (params) => {
        setEdges((eds) => {
            const new_edges = addEdge({ ...params, id: edgeId(params) }, eds);
            model.set("edges", JSON.stringify(new_edges));
            model.save_changes();
            return new_edges;
      });
    },
    [setEdges],
  );

  // A locked port is already fed, by the constant node the GUI draws as its value.
  // Two edges into one input port is not a graph flowrep will accept, and the padlock
  // is the way to free the port.
  const isValidConnection = useCallback(
    (connection) => {
        const target = nodes.find((n) => n.id === connection.target);
        const lockedPorts = target?.data?.target_locked ?? {};
        return !(connection.targetHandle in lockedPorts);
    },
    [nodes],
  );


  const deleteNode = (id) => {
    // direct output of node to output widget
    console.log('output: ', id)
    if (model) {
      model.set("commands", `delete_node: ${id} ${now()}`);
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

  const runFunction = () => {
    setConfirmClose(false);
    const dateTime = now()
    console.log('run ', dateTime);
    if (model) {
      model.set("commands", `run executed ${dateTime}`);
      model.save_changes();
    } else {
      console.error('model is undefined');
    }
  }

  // Export, Import and Save only open the Files panel on the Python side
  const openFilesFunction = (name) => {
    setConfirmClose(false);
    const dateTime = now()
    console.log(`${name} executed `, dateTime);
    if (model) {
      model.set("commands", `${name} executed ${dateTime}`);
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

  const renameFunction = () => {
    setConfirmClose(false);
    const dateTime = now()
    const answer = window.prompt("New name for this workflow", label);
    const newLabel = answer === null ? "" : answer.trim();
    if (newLabel === "" || newLabel === label) {
      return;
    }
    console.log('rename as ', newLabel, dateTime);
    if (model) {
      model.set("commands", `rename executed ${dateTime} as ${newLabel}`);
      model.save_changes();
    } else {
      console.error('model is undefined');
    }
  }

  const closeFunction = () => {
    if (!confirmClose) {
      setConfirmClose(true);
      return;
    }
    setConfirmClose(false);
    const dateTime = now()
    console.log('close ', dateTime);
    if (model) {
      model.set("commands", `close executed ${dateTime}`);
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
      <UpdateDataContext.Provider value={portActions}>
        <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodesChange={onNodesChange}
            onNodeDragStop={onNodeDragStop}
            onEdgesChange={onEdgesChange}
            onConnect={onConnect}
            isValidConnection={isValidConnection}
            onNodesDelete={onNodesDelete}
            onMoveEnd={onMoveEnd}
            onError={onFlowError}
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
            onClick={() => runFunction()}
            title="Run all nodes in the workflow"
          >
            Run
          </button>
          <button
            onClick={() => openFilesFunction("export")}
            title="Export the workflow recipe to a JSON file (opens the Files panel)"
          >
            Export
          </button>
          <button
            onClick={() => openFilesFunction("import")}
            title="Import a workflow recipe from a JSON file into a new tab (opens the Files panel)"
          >
            Import
          </button>
          <button
            onClick={() => openFilesFunction("save")}
            disabled={!hasRun}
            title={hasRun
              ? "Save the most recent run or pull to a file (opens the Files panel)"
              : "Nothing to save yet: press Run, or pull on a node, first"}
          >
            Save
          </button>
          <button
            onClick={() => renameFunction()}
            title="Rename this workflow and its tab"
          >
            Rename
          </button>
          <button
            onClick={() => closeFunction()}
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
