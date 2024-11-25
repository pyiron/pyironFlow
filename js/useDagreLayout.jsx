import dagre from '@dagrejs/dagre';


export const getLayoutedElements = (nodes, edges, direction = 'LR') => {
  const nodeWidth = 172;
  const nodeHeight = 100;

  const dagreGraph = new dagre.graphlib.Graph().setDefaultEdgeLabel(() => ({}));
  dagreGraph.setGraph({ rankdir: direction });

  nodes.forEach(node => {
      dagreGraph.setNode(node.id, { width: nodeWidth, height: nodeHeight });
  });

  edges.forEach(edge => {
      dagreGraph.setEdge(edge.source, edge.target);
  });

  dagre.layout(dagreGraph);

  const layoutedNodes = nodes.map(node => {
    const { x, y } = dagreGraph.node(node.id);
    return { ...node, position: { x: x - nodeWidth / 2, y: y - nodeHeight / 2 } };
  });    

  return { nodes: layoutedNodes, edges };
}; 