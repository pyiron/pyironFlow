import React, { useCallback } from 'react';
import { Handle, Position } from '@xyflow/react';

const handleStyle = { right: 0, top: 10 }; //, width: 12, height: 12  };

function TextUpdaterNode({ data, isConnectable }) {
  const onChange = useCallback((evt) => {
    console.log(evt.target.value);
  }, []);

  return (
    <div className="text-updater-node">
      <Handle
        type="target"
        position={Position.Left}
        isConnectable={isConnectable}>
          <div className="handle-text-left">target</div>
      </Handle>
      <div>
        <label htmlFor="text">Text:</label>
        <input id="text" name="text" onChange={onChange} className="nodrag" />
      </div>
      <Handle
        type="source"
        position={Position.Right}  
        id="a"
        style={handleStyle}
        isConnectable={isConnectable}>
          <div className="handle-text-right">source a</div>
      </Handle>
          
      <Handle
        type="source"
        position={Position.Right}
        id="b"
        isConnectable={isConnectable}>
          <div className="handle-text-right">source b</div>
      </Handle>
    </div>
  );
}

export default TextUpdaterNode;