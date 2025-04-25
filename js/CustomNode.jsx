import React, { memo, useEffect, useState } from "react";
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

export default memo(({ data, node_status }) => {
    const updateNodeInternals = useUpdateNodeInternals();
//    const [nodes, setNodes, onNodesChange] = useNodesState([]);    
    
    const num_handles = Math.max(data.source_labels.length, data.target_labels.length);
    const [handles, setHandles] = useState(Array(num_handles).fill({}));
    
    const model = useModel();   
    const context = React.useContext(UpdateDataContext); 

//    console.log('nodes', nodes)


    useEffect(() => {
        handles.map((_, index) => {
          updateNodeInternals(`handle-${index}`);
        });
    }, [handles]);   

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
    
    const renderLabel = (label, failed, running, ready, cache_hit) => {
        let status = '';

        if (failed === "True") {
            status = '🟥   ';
        } else if (running === "True") {
            status = '🟨   ';
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
                <div style={{ height: 16, fontSize: '10px', display: 'flex', alignItems: 'center', flexDirection: 'row-reverse', justifyContent: 'flex-end' }}>
                    <span style={{ marginLeft: '5px' }}>{`${label}`}</span> 
                    {editValue && (currentInputType === 'dropdown'
                    ? (
                        <select className="nodrag"
                        value={value}
                        onChange={e => {
                            const newValue = e.target.value;
                            
                            console.log('Original Value:', newValue);
                    
                            const convertedOptions = data.target_literal_values[index].map((option, idx) => ({
                              original: option,
                              converted: convertInput(option, literal_type[idx]),
                            }));

                            const selectedIndex = convertedOptions.findIndex(
                              opt => opt.converted.toString() === newValue
                            );
                    
                            const convertedValue = convertInput(newValue, literal_type[selectedIndex]);
                    
                            setInputValue(convertedValue);
                            context(data.label, index, convertedValue);
                          }}
                        style={{ width: '48px', fontSize: '6px'}}
                        >
                            <option value='' style={{ fontSize: '12px' }}>Select</option>
                            {data.target_literal_values[index].map((option, idx) => {
                                return (
                                    <option value={option} style={{ fontSize: '12px' }}>
                                    {option}
                                </option>
                            );
                        })}
                        </select> 
                ) : (
                    <input 
                        type={currentInputType}
                        checked={currentInputType === 'checkbox' ? inputValue : undefined}
                        value={currentInputType !== 'checkbox' ? (inputValue !== "NotData" ? inputValue : undefined) : undefined}
                        placeholder="NOT_DATA"
                        className="nodrag"
                        onChange={e => {
                            const newValue = currentInputType === 'checkbox' ? e.target.checked : e.target.value;
                            console.log('onChange', value, e, inputValue, newValue, index, data.label);
                            // Always update the input value
                            setInputValue(newValue);
                            context(data.label, index, newValue); 
                        }}
                        onKeyDown={e => {
                            if(e.keyCode === 13) {
                                // When Enter key is pressed, convert the input
                                const convertedValue = convertInput(inputValue, inp_type);
                                console.log('onKeyDown', value, e, inputValue, convertedValue, index, data.label);
                                context(data.label, index, convertedValue); 
                            }
                        }}
                        onBlur={() => {
                            // When the mouse leaves the textbox, convert the input
                            const convertedValue = convertInput(inputValue, inp_type);
                            context(data.label, index, convertedValue);
                        }}
                        style={{ 
                            width: '40px',
                            height: '10px', 
                            fontSize: '6px',
                            backgroundColor: getBackgroundColor(value, inp_type)
                        }} 
                    /> 
                ))} 
                </div>
                {renderCustomHandle('left', 'target', index, label)}
            </>
        );
    }

    const renderOutputHandle = (data, index) => {
        const label = data.source_labels[index]
        
        return (
           <>
                <div style={{ height: 16, fontSize: '10px', textAlign: 'right' }}>
                    {`${label}`}
                </div>
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
      </NodeToolbar>        
    </div>
  );
});      
