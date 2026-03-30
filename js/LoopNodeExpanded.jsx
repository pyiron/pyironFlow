import React, { memo, useEffect, useState, useRef } from "react";
import { Handle, useUpdateNodeInternals, NodeToolbar, useNodesState, Panel} from "@xyflow/react";
import { useModel } from "@anywidget/react";
import { UpdateDataContext } from './widget.jsx';  // import the context

/**
 * Author: Joerg Neugebauer
 * Copyright: Copyright 2024, Max-Planck-Institut for Sustainable Materials GmbH - Computational Materials Design (CM) Department
 * Version: 0.2
 * Maintainer: 
 * Email: 
 * Status: development 
 * Date: Aug 1, 2024
 */

export default memo(({ data, node_status, id, position }) => {
    const updateNodeInternals = useUpdateNodeInternals();
//    const [nodes, setNodes, onNodesChange] = useNodesState([]);    
    
    const num_handles = Math.max(data.source_labels.length, data.target_labels.length);
    const [handles, setHandles] = useState(Array(num_handles).fill({}));
    
    const model = useModel();   
    const context = React.useContext(UpdateDataContext); 

    const edgesRef = useRef(data.edges);

//    console.log('nodes', nodes)


    useEffect(() => {
        handles.map((_, index) => {
          updateNodeInternals(`handle-${index}`);
        });
    }, [handles]);   

    useEffect(() => {
      edgesRef.current = data.edges; // Update the ref when the prop changes
    }, [data.edges]);

/*
     useEffect(() => {
       const interval = setInterval(() => {
         console.log('Running logic every 0,2s', edgesRef.current);
         console.log('only edges', data.edges);
         const parents = [
             ...new Set(
               edgesRef.current
                .filter((edge) => edge.type == "macroSubEdge")
                .map ((edge) => edge.parent)
             )
           ];
          console.log('Parents: ', parents);  
         if (data.onMessage) {
           if (parents.includes(id)) {
             data.onMessage(id);
             clearInterval(interval);
             return;
           }
           else {

           };
          model.set("timestamp", Date.now());
         };
           
       }, 200);

    return () => clearInterval(interval);
         
    }, []);

*/

    

       const pullFunction = () => {
        // pull on the node
        console.log('pull: ', data.label)
        model.set("commands", `pull: ${data.label} - ${new Date().getTime()}`);
        model.save_changes();
    }

    const pushFunction = () => {
        // push from the node
        console.log('push: ', data.label)
        model.set("commands", `push: ${data.label} - ${new Date().getTime()}`);
        model.save_changes();
    }

    // outputFunction and sourceFunction lifted to widget.jsx to be used by ContextMenu.jsx

    const resetFunction = () => {
        // reset state and cache of node
        console.log('reset: ', data.label) 
        model.set("commands", `reset: ${data.label}`);
        model.save_changes();        
    }

    const collapseFunction = () => {
        // show source code of node
        console.log('collapse ', data.label) 
        model.set("commands", `collapse: ${data.label}`);
        model.save_changes(); 
    }

    const sortFunction = () => {
        // reset state and cache of node
        console.log('sort: ', data.label) 
        data.onSort(id);
    }

    const buildViewFunction = () => {
        // show source code of node
        console.log('build_view ', data.label) 
        model.set("commands", `build_view: ${data.label}`);
        model.save_changes(); 
    }

    const loopViewFunction = () => {
        // show source code of node
        console.log('loop_view ', data.label) 
        model.set("commands", `loop_view: ${data.label}`);
        model.save_changes(); 
    }

    
    
    const renderLabel = (label, failed, running, ready, cache_hit) => {
        let status = '';

        if (failed === "True") {
            status = '🟥   ';
        } else if (running === "True") {
            status = '🟨   ';
        } else if ((ready === "True") && (cache_hit === "False")) {
            status = '🟦   ';
        } else if ((ready === "True") && (cache_hit === "True")) {
            status = '🟩   ';
        } else {
            status = '⬜   ';
        }

        return (
            <div style={{ fontWeight: "normal", marginBottom: "0.3em", textAlign: "center" }}>
                {status + label}
            </div>
        );
    }

    
    const renderCustomHandle = (position, type, index, label) => {
      return (
        <Handle
          key={`${position}-${index}`}
          type={type}
          position={position}
          id={label}
          style={{ top: 30 + 16 * index}}
        />
      );
    }

    const renderInputHandle = (data, index, editValue = false) => {   
        const label = data.target_labels[index]
        const inp_type = data.target_types[index]
        const literal_type = data.target_literal_types[index]
        const value = data.target_values[index]       
        const [inputValue, setInputValue] = useState(value); 
        const context = React.useContext(UpdateDataContext); 
        // console.log('input type: ', data)

        const inputTypeMap = {
            'str': 'text',
            'int': 'text',
            'float': 'text',
            'bool': 'checkbox',
            '_LiteralGenericAlias': 'dropdown'
        };

        const convertInput = (value, inp_type) => {
            switch(inp_type) {
                case 'int':
                    // Check if value can be converted to an integer
                    const intValue = parseInt(value, 10);
                    return isNaN(intValue) ? value : intValue;
                case 'float':
                    // Check if value can be converted to a float
                    const floatValue = parseFloat(value);
                    return isNaN(floatValue) ? value : floatValue;
                case 'bool':
                    return value; 
                default:
                    return value;  // if inp_type === 'str' or anything else unexpected, returns the original string
            }
        }                           
      
        const currentInputType = inputTypeMap[inp_type] || 'text';
                
        if (inp_type === 'NonPrimitive' || inp_type === 'None') {
            editValue = false;
        }

        const getBackgroundColor = (value, inp_type) => {            
            if (value === null) {
                return 'grey';
            } else if (value === 'NotData') {
                return '#FFD740'
            } else {
                return 'white';
            }
        }
        
        return (
           <>

                {renderCustomHandle('left', 'target', index, label)}
            </>
        );
    }

    const renderOutputHandle = (data, index) => {
        const label = data.source_labels[index]
        
        return (
           <>
                {renderCustomHandle('right', 'source', index, label)}
            </>
        );
    }

      const onChange = (evt) => {
        setSimpleOption(evt.target.value); // without type assertions
      };

  return (
    <div>
        
        {renderLabel(data.label, data.failed, data.running, data.ready, data.cache_hit)}

        <div>
            {handles.map((_, index) => (
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                    <div>
                        {index < data.target_labels.length && 
                            renderInputHandle(data, index, true)}
                    </div>

                    <div>
                        {index < data.source_labels.length && 
                            renderOutputHandle(data, index)}
                    </div>
                </div>
            ))}
        </div>
      <NodeToolbar
        isVisible={data.forceToolbarVisible || undefined}
        position={data.toolbarPosition}
      >
          <button onClick={pullFunction} title="Run all connected upstream nodes and this node">Pull</button>
          <button onClick={pushFunction} title="Run this node and all connected downstream nodes">Push</button>
          <button onClick={resetFunction} title="Reset this node by clearing its cache">Reset</button>
          <button onClick={collapseFunction} title="Collapse this Macro">Collapse</button>
          <button onClick={buildViewFunction} title="Show the blueprint of this Loop">View Blueprint</button>
          <button onClick={loopViewFunction} title="Show the internals of this Loop">View Control-Flow</button>
      </NodeToolbar>        
    </div>
  );
});      
