import React, { memo, useEffect, useState } from "react";
import { Handle, useUpdateNodeInternals, NodeToolbar, useNodesState, } from "@xyflow/react";
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

export default memo(({ data }) => {
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

       const runFunction = () => {
        // run the node
        console.log('run: ', data.label)
        model.set("commands", `run: ${data.label} - ${new Date().getTime()}`);
        model.save_changes();
    }

    const outputFunction = () => {
        // direct output of node to output widget
        console.log('output: ', data.label)
        model.set("commands", `output: ${data.label}`);
        model.save_changes();
    }

    const sourceFunction = () => {
        // show source code of node
        console.log('source: ', data.label) 
        model.set("commands", `source: ${data.label}`);
        model.save_changes();        
    } 

    
    const renderLabel = (label) => {
        return (
            <div style={{ fontWeight: "normal", marginBottom: "0.3em", textAlign: "center" }}>
                {label}
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
        const value = data.target_values[index]       
        const [inputValue, setInputValue] = useState(value); 
        const context = React.useContext(UpdateDataContext); 
        // console.log('input type: ', data)

        const inputTypeMap = {
            'str': 'text',
            'int': 'text',
            'float': 'text',
            'bool': 'checkbox'
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
                return 'red'; // please remember to use a proper CSS color or RGB code
            } else {
                return 'white';
            }
        }
        
        return (
           <>
                <div style={{ height: 16, fontSize: '10px', display: 'flex', alignItems: 'center', flexDirection: 'row-reverse', justifyContent: 'flex-end' }}>
                    <span style={{ marginLeft: '5px' }}>{`${label}`}</span> 
                    {editValue 
                    ? <input 
                        type={currentInputType}
                        checked={currentInputType === 'checkbox' ? inputValue : undefined}
                        value={currentInputType !== 'checkbox' ? inputValue : undefined}
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
                            width: '15px', 
                            height: '10px', 
                            fontSize: '6px',
                            backgroundColor: getBackgroundColor(value, inp_type)
                        }} 
                    /> 
                    : '' 
                    } 
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


  return (
    <div>
        
        {renderLabel(data.label)}

        <div>
            {handles.map((_, index) => (
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                    {index < data.target_labels.length && 
                        renderInputHandle(data, index, true)}

                    {index < data.source_labels.length && 
                        renderOutputHandle(data, index)}
                </div>
            ))}
        </div>
      <NodeToolbar
        isVisible={data.forceToolbarVisible || undefined}
        position={data.toolbarPosition}
      >
          <button onClick={runFunction}>Run</button>
          <button onClick={sourceFunction}>Source</button>
      </NodeToolbar>        
    </div>
  );
});      