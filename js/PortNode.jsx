import React, { memo, useContext } from "react";
import { Handle, Position } from "@xyflow/react";
import { UpdateNodeDataContext } from "./widget.jsx";
import PortEntry, { canEnterValue } from "./portEntry.jsx";

/**
 * One terminal port of the parent-most workflow, drawn as a rounded box:
 * the port label on top, its type hint beneath in monospace, and where the
 * hint is primitive and entry is allowed, a value field beneath that.
 *
 * The entered value is GUI-side only. Nothing feeds it to the model yet.
 */
export default memo(({ id, data }) => {
    const updateNodeData = useContext(UpdateNodeDataContext);
    const isInput = data.variant === "input";
    const showEntry =
        isInput && data.allow_value_entry && canEnterValue(data.entry_kind);

    return (
        <div className={`port-node port-node--${data.variant}`}>
            <div className="port-node__label">{data.label}</div>
            <div className="port-node__hint" title={data.hint}>
                <bdi>{data.hint}</bdi>
            </div>
            {showEntry && (
                <PortEntry
                    entryKind={data.entry_kind}
                    literalValues={data.literal_values}
                    literalTypes={data.literal_types}
                    value={data.value}
                    onCommit={(next) => updateNodeData(id, { value: next })}
                />
            )}
            <Handle
                type={isInput ? "source" : "target"}
                position={isInput ? Position.Right : Position.Left}
                id={data.label}
            />
        </div>
    );
});
