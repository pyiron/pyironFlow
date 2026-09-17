import React, { memo, useEffect, useState } from "react";
import { Handle, useUpdateNodeInternals, NodeToolbar, useNodesState, Panel, useNodeConnections } from "@xyflow/react";
import { useModel } from "@anywidget/react";
import { UpdateDataContext } from './widget.jsx';  // import the context
import PortEntry, { canEnterValue, LockButton } from "./portEntry.jsx";

/**
 * Author: Joerg Neugebauer
 * Copyright: Copyright 2024, Max-Planck-Institut for Sustainable Materials GmbH - Computational Materials Design (CM) Department
 * Version: 0.2
 * Maintainer: 
 * Email: 
 * Status: development 
 * Date: Aug 1, 2024
 */

export default memo(({ id, data, node_status }) => {
    const updateNodeInternals = useUpdateNodeInternals();
//    const [nodes, setNodes, onNodesChange] = useNodesState([]);

    const num_handles = Math.max(data.source_labels.length, data.target_labels.length);
    const [handles, setHandles] = useState(Array(num_handles).fill({}));

    const model = useModel();
    const actions = React.useContext(UpdateDataContext);

    const incoming = useNodeConnections({ handleType: "target" });
    const fedHandles = new Set(incoming.map((c) => c.targetHandle));

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

    const renderInputHandle = (data, index) => {
        const label = data.target_labels[index];
        const entryKind = data.target_types[index];
        const entries = data.target_values ?? {};
        const errors = data.target_errors ?? {};
        const lockedPorts = data.target_locked ?? {};
        const locked = lockedPorts[label] ?? null;
        const hasEntry = Object.prototype.hasOwnProperty.call(entries, label);
        const hasError = Object.prototype.hasOwnProperty.call(errors, label);
        const entered = hasEntry || hasError;
        const text = hasError ? errors[label].text : (hasEntry ? entries[label] : "");
        const error = hasError ? errors[label].message : null;
        const fallback = data.target_defaults?.[index] ?? null;
        const fed = fedHandles.has(label);
        // A locked port shows its value even when its hint earns no entry widget: the
        // user has to see the constant before deciding to delete it.
        const showEntry = !fed && (canEnterValue(entryKind) || locked !== null);
        const canLock = !locked && (hasEntry || fallback !== null) && !hasError;
        const unfilled = !fed && !locked && !data.target_has_default?.[index] && !hasEntry;

        return (
           <>
                <div style={{ height: 16, fontSize: '10px', display: 'flex', alignItems: 'center', flexDirection: 'row-reverse', justifyContent: 'flex-end' }}
                              title={'Data Types: ' + data.target_types_raw[index]}>
                    <span style={{ marginLeft: '5px' }}>
                        {label}
                        {unfilled && <span style={{ color: 'red' }}> *</span>}
                    </span>
                    {showEntry && (
                        <LockButton
                            locked={locked}
                            canLock={canLock}
                            onLock={() => actions.lock(id, label)}
                            onUnlock={() => actions.unlock(id, label)}
                        />
                    )}
                    {showEntry && (
                        <PortEntry
                            entryKind={entryKind}
                            options={data.target_literal_values[index]}
                            entered={entered}
                            text={text}
                            error={error}
                            fallback={fallback}
                            locked={locked}
                            onCommit={(next) => actions.commit(id, label, next)}
                        />
                    )}
                </div>
                {renderCustomHandle('left', 'target', index, label)}
            </>
        );
    }

    const renderOutputHandle = (data, index) => {
        const label = data.source_labels[index]
        
        return (
           <>
                <div style={{ height: 16, fontSize: '10px', textAlign: 'right' }} title={'Data Types: ' + data.source_types_raw[index]}>
                    {`${label}`}
                </div>
                {renderCustomHandle('right', 'source', index, label)}
            </>
        );
    }

  return (
    <div>
        
        {renderLabel(data.label, data.failed, data.running, data.ready, data.cache_hit)}

        <div>
            {handles.map((_, index) => (
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
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
