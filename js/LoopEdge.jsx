import React from 'react';
import { BaseEdge, BezierEdge, EdgeLabelRenderer, MarkerType} from '@xyflow/react';
 
export default function SelfConnecting({ id, sourceX, sourceY, targetX, targetY, ...props}) {

  const radiusX = (sourceX - targetX) * 0.6;
  const radiusY = 50;
  const edgePath = `M ${sourceX - 2} ${sourceY} A ${radiusX} ${radiusY} 0 1 0 ${
    targetX + 2
  } ${targetY}`; 
  //             transform: `translate(-50%, -50%) translate(${radiusX}px,${radiusY}px)`,
  //return <BaseEdge path={edgePath} markerEnd={markerEnd} />;
  return (
    <>
      <BaseEdge 
          path={edgePath}      
          style={{
            stroke: 'blue', 
            strokeWidth: 2,
          }} 
        />
    </>
  );
}
