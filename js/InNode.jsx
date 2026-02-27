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

    const renderLabel = (label) => {

        return (
            <div style={{ fontWeight: "normal", marginTop: "0px", textAlign: "center", fontSize: '8px' }}>
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
          style={{ top: 5 + 16 * index}}
        />
      );
    }

    const renderInputHandle = (data, index) => {   
        const label = data.target_labels[index]
        
        return (
           <>
                <div style={{ height: 8, fontSize: '8px', textAlign: 'center' }}>
                    <span style={{ marginLeft: '5px' }}>{`${label}`}</span> 

                </div>
                {renderCustomHandle('left', 'target', index, label)}
            </>
        );
    }

    const renderOutputHandle = (data, index) => {
        const label = data.source_labels[index]
        
        return (
           <>
                <div style={{ height: 8, fontSize: '8px', textAlign: 'center' }}>
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
        {handles.map((_, index) => (
            <div style={{ display: "flex", justifyContent: "center", alignItems: "center" }}>
                <div>
                    {index < data.target_labels.length && 
                        renderInputHandle(data, index)}
                </div>

                <div>
                    {index < data.source_labels.length && 
                        renderOutputHandle(data, index)}
                </div>
            </div>
        ))}
    </div>     
  );
});      