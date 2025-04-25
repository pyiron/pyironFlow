import React, { useCallback } from 'react';
import { useReactFlow } from '@xyflow/react';
 
export default function ContextMenu({
  id,
  data,
  top,
  left,
  right,
  bottom,
  onOutput,
  onSource,
  ...props
}) {

  return (
    <div
      style={{ position: 'absolute', top: top, left: left, zIndex: 1000 }}
      className="context-menu"
      {...props}
    >
      <p style={{ margin: '0.5em' }}>
        <b>node: {id}</b>
      </p>
      <button onClick={() => onOutput(data)} title="View the output(s) of this node without running it"> View Output</button>
      <button onClick={() => onSource(data)} title="View the source code of this node">View Source</button>
    </div>
  );
}