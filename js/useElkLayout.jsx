import { useEffect } from 'react';
import ELK from 'elkjs/lib/elk.bundled.js';
import {  useNodesInitialized, useReactFlow } from '@xyflow/react';
// import { saveAs } from 'file-saver';

 
// elk layouting options can be found here:
// https://www.eclipse.org/elk/reference/algorithms/org-eclipse-elk-layered.html

 
// uses elkjs to give each node a layouted position
export const getLayoutedNodes2 = async (nodes, edges) => {
  const layoutOptions = {
    'elk.algorithm': 'layered',
    'elk.direction': 'RIGHT',
    'elk.layered.spacing.edgeNodeBetweenLayers': '40',
    'elk.spacing.nodeNode': '40',
    'elk.layered.nodePlacement.strategy': 'SIMPLE',
  };
   
  console.log("nodes layout: ", nodes); 
  console.log("edges layout: ", edges); 
  const elk = new ELK();

  const graph = {
    id: 'root',
    layoutOptions,
    children: nodes.map((n) => {
      const targetPorts = n.data.target_labels.map((label) => ({
        id: `${n.id}_in_${label}`,
 
        // ⚠️ it's important to let elk know on which side the port is
        // in this example targets are on the left (WEST) and sources on the right (EAST)
        properties: {
          side: 'WEST',
        },
      }));
 
      const sourcePorts = n.data.source_labels.map((label) => ({
        id: `${n.id}_out_${label}`,
        properties: {
          side: 'EAST',
        },
      }));
 
      return {
        id: n.id,
        width: n.style.width_unitless ?? 240,
        height: n.style.height_unitless ?? 100,
        // ⚠️ we need to tell elk that the ports are fixed, in order to reduce edge crossings
        properties: {
          'org.eclipse.elk.portConstraints': 'FIXED_ORDER',
        //  'org.eclipse.elk.layered.portSortingStrategy': 'UP_DOWN',
        },
        // we are also passing the id, so we can also handle edges without a sourceHandle or targetHandle option
        ports: [ ...targetPorts.reverse(), ...sourcePorts.reverse()],
      };
    }),
    edges: edges.map((e) => ({
      id: e.id,   
      sources: [`${e.source}_out_${e.sourceHandle}`],
      targets: [`${e.target}_in_${e.targetHandle}`],
    })),
  };

  // const blob = new Blob([JSON.stringify(graph)], {type: "text/plain;charset=utf-8"});
  // saveAs(blob, 'output.json');
 
  console.log("Graph: ", graph);
  const layoutedGraph = await elk.layout(graph);
  console.log("layoutedGraph: ", layoutedGraph);
 
  const layoutedNodes = nodes.map((node) => {
    const layoutedNode = layoutedGraph.children?.find(
      (lgNode) => lgNode.id === node.id,
    );
 
    return {
      ...node,
      position: {
        x: layoutedNode?.x ?? 0,
        y: layoutedNode?.y ?? 0,
      },
    };
  });
  console.log("layoutedGraphNodes: ", layoutedNodes);
 
  return layoutedNodes;
};

export default function useLayoutNodes() {
    const nodesInitialized = useNodesInitialized();
    const { getNodes, getEdges, setNodes, fitView } = useReactFlow();
   
    useEffect(() => {
      if (nodesInitialized) {
        const layoutNodes = async () => {
          const layoutedNodes = await getLayoutedNodes(
            getNodes(),
            getEdges(),
          );
   
          setNodes(layoutedNodes);
          setTimeout(() => fitView(), 0);
        };
   
        layoutNodes();
      }
    }, [nodesInitialized, getNodes, getEdges, setNodes, fitView]);
   
    return null;
  }