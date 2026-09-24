import React, { memo, useEffect } from "react";
import { Handle, useUpdateNodeInternals, useStore, NodeToolbar, useNodesState, Panel, useNodeConnections } from "@xyflow/react";
import { useModel } from "@anywidget/react";
import { UpdateDataContext } from './widget.jsx';  // import the context
import PortEntry, { canEnterValue, LockButton } from "./portEntry.jsx";
import { now } from "./commands.js";

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

    // Derived every render: a node whose port count changes has to grow a row for it.
    const num_handles = Math.max(data.source_labels.length, data.target_labels.length);
    const handleRows = Array.from({ length: num_handles });

    const model = useModel();
    const actions = React.useContext(UpdateDataContext);

    const incoming = useNodeConnections({ handleType: "target" });
    const fedHandles = new Set(incoming.map((c) => c.targetHandle));

//    console.log('nodes', nodes)


    /*
     * React Flow reads handle positions out of `node.internals.handleBounds`, a cache it
     * fills from a ResizeObserver and refills only when the node's measured size changes.
     * Our size depends on nothing but the port count, and widget.jsx hands React Flow
     * nodes that already carry `measured` -- so a node can end up claiming to be measured
     * while holding no handle bounds at all, and then nothing ever re-measures it:
     * `useNodeObserver` re-observes only when `isInitialized` changes, and it stays
     * stuck at false. Such a node draws fine, but every handle on it is invisible to
     * `getHandle`, so no edge touching it is rendered and no drag can start from it.
     *
     * Force a re-measure whenever this node holds no bounds, and whenever the port
     * labels change -- bounds that survive a rename or a reorder are stale, which fails
     * the same way. `updateNodeInternals` finds the node by `[data-id="<id>"]`, so a
     * label carrying a quote or a bracket would silently miss; pyiron labels are Python
     * identifiers, so that does not arise.
     */
    const hasHandleBounds = useStore(
        (state) => !!state.nodeLookup.get(id)?.internals.handleBounds,
    );
    const portLabels = [...data.target_labels, "->", ...data.source_labels].join("\u0000");

    useEffect(() => {
        if (hasHandleBounds) {
            return undefined;
        }
        /*
         * React runs a child's effects before its parent's, so on the widget's first
         * paint this runs before React Flow has put its own container in the store --
         * and a re-measure asked for before then is silently dropped. So ask again on
         * the following frames; `hasHandleBounds` flips as soon as one lands, which
         * re-runs this effect and cancels the rest.
         */
        let frame = 0;
        let attempts = 0;
        const askToMeasure = () => {
            updateNodeInternals(id);
            attempts += 1;
            if (attempts < 5) {
                frame = requestAnimationFrame(askToMeasure);
            }
        };
        askToMeasure();
        return () => cancelAnimationFrame(frame);
    }, [hasHandleBounds, id, updateNodeInternals]);

    useEffect(() => {
        updateNodeInternals(id);
    }, [portLabels, id, updateNodeInternals]);

       const pullFunction = () => {
        // pull on the node
        console.log('pull: ', data.label)
        model.set("commands", `pull: ${data.label} ${now()}`);
        model.save_changes();
    }

    // outputFunction and sourceFunction lifted to widget.jsx to be used by ContextMenu.jsx

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
                              data-testid={`port-in-${label}`}
                              title={'Data Types: ' + data.target_types_raw[index]}>
                    <span style={{ marginLeft: '5px' }}>
                        {label}
                        {unfilled && <span style={{ color: 'red' }} data-testid="port-required"> *</span>}
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
            {handleRows.map((_, index) => (
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
      </NodeToolbar>        
    </div>
  );
});      
