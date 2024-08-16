import React, { memo, useEffect, useState } from "react";
import { Handle, useUpdateNodeInternals, NodeToolbar, useNodesState, } from "@xyflow/react";
import { useModel } from "@anywidget/react";


export default memo(({ data }) => {
      const updateNodeInternals = useUpdateNodeInternals();
      const [nodes, setNodes, onNodesChange] = useNodesState([]);    
      
      const num_handles = Math.max(data.source_labels.length, data.target_labels.length);
      const [handles, setHandles] = useState(Array(num_handles).fill({}));
    
      const model = useModel();      
    
      useEffect(() => {
        handles.map((_, index) => {
          updateNodeInternals(`handle-${index}`);
        });
      }, [handles]);

       const runFunction = () => {
        // run the node
        console.log('run: ', data.label)
        model.set("commands", `run: ${data.label}`);
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
        const value = data.target_values[index]       
        const [inputValue, setInputValue] = useState(value); 
        
        return (
           <>
                <div style={{ height: 16, fontSize: '10px', display: 'flex', alignItems: 'center', flexDirection: 'row-reverse', justifyContent: 'flex-end' }}>
                    <span style={{ marginLeft: '5px' }}>{`${label}`}</span> 
                    {editValue 
                        ? <input 
                              type="text"
                              value={inputValue}
                              onChange={e => setInputValue(e.target.value)} // onChange={data.onChange(label, index)}
                              style={{ width: '15px', height: '10px', fontSize: '6px' }} 
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
          <button onClick={outputFunction}>Output</button>
          <button onClick={sourceFunction}>Source</button>
      </NodeToolbar>        
    </div>
  );
});      