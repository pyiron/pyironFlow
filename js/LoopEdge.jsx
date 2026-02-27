import React from 'react';
import { BaseEdge, BezierEdge, EdgeLabelRenderer, MarkerType} from '@xyflow/react';
 
export default function SelfConnecting({ id, sourceX, sourceY, targetX, targetY}) {

  const radiusX = (sourceX - targetX) * 0.6;
  const radiusY = 50;
  const edgePath = `M ${sourceX - 2} ${sourceY} A ${radiusX} ${radiusY} 0 1 0 ${
    targetX + 2
  } ${targetY}`;
  const markerEndType = MarkerType.ArrowClosed
  //             transform: `translate(-50%, -50%) translate(${radiusX}px,${radiusY}px)`,
  //return <BaseEdge path={edgePath} markerEnd={markerEnd} />;
  return (
    <>
      <BaseEdge path={edgePath} markerEnd={markerEndType} color="blue" />
      <EdgeLabelRenderer>
        <div
          style={{
            transform: `translate(${radiusX}px,${radiusY + sourceY} px)`,
            color: "blue" ,
          }}
          className="edge-label-renderer__loop-edge nodrag nopan"
        >
          {"loop"}
        </div>
      </EdgeLabelRenderer>
    </>
  );

}
