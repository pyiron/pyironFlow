import unittest

import flowrep as fr
import pyiron_workflow as pwf

from pyironflow import PyironFlow
from pyironflow.wf_extensions import (
    _get_port_default,
    get_edges,
    get_node_dict,
    get_nodes,
)


@fr.atomic("signal")
def relu(x: float, bias: float = 0.5) -> float:
    return max(0.0, x - bias)


@fr.atomic("sum")
def add(a: float, b: float) -> float:
    return a + b


@fr.workflow
def my_workflow(x):
    y = relu(x)
    z = relu(y)
    added = add(y, z)
    return added


class TestMacroNode(unittest.TestCase):
    def setUp(self):
        self.wf = pwf.node(my_workflow)

    def test_get_nodes_returns_three_nodes(self):
        nodes = get_nodes(self.wf)
        self.assertEqual(len(nodes), 3)

    def test_get_nodes_no_none_ids(self):
        nodes = get_nodes(self.wf)
        for n in nodes:
            self.assertIsNotNone(n["id"])

    def test_get_edges_no_none_source_or_target(self):
        """Boundary edges (source/target == None) must be filtered out."""
        edges = get_edges(self.wf)
        for e in edges:
            self.assertIsNotNone(e["source"], "edge source must not be None")
            self.assertIsNotNone(e["target"], "edge target must not be None")

    def test_get_edges_internal_connections(self):
        """Edges between internal nodes should be present."""
        edges = get_edges(self.wf)
        # relu_0 -> relu_1, relu_0 -> add_0, relu_1 -> add_0
        self.assertEqual(len(edges), 3)

    def test_pyironflow_init_does_not_raise(self):
        """PyironFlow([macro_node]) must not raise AttributeError."""
        pf = PyironFlow([self.wf])
        self.assertIsInstance(pf, PyironFlow)


class TestRegularWorkflow(unittest.TestCase):
    def setUp(self):
        self.wf = pwf.Workflow("test_regular")
        self.wf.n1 = pwf.node(relu, x=0.2)
        self.wf.n2 = pwf.node(relu, x=-0.5)
        self.wf.accumulate = pwf.node(
            add,
            a=self.wf.n1.outputs.signal,
            b=self.wf.n2.outputs.signal,
        )

    def test_get_nodes_contains_user_nodes(self):
        node_ids = [n["id"] for n in get_nodes(self.wf)]
        self.assertIn("n1", node_ids)
        self.assertIn("n2", node_ids)
        self.assertIn("accumulate", node_ids)

    def test_get_edges_internal_connections(self):
        edges = get_edges(self.wf)
        internal = [e for e in edges if e["source"] in ("n1", "n2")]
        self.assertEqual(len(internal), 2)

    def test_get_edges_no_const_edges(self):
        edges = get_edges(self.wf)
        for e in edges:
            self.assertFalse((e["source"] or "").startswith("_const_"))
            self.assertFalse((e["target"] or "").startswith("_const_"))


class TestNodeDictHasNoValues(unittest.TestCase):
    def setUp(self):
        self.wf = pwf.Workflow("no_values")
        self.wf.n1 = pwf.node(relu)
        self.wf.n2 = pwf.node(relu)
        self.wf.acc = pwf.node(
            add, a=self.wf.n1.outputs.signal, b=self.wf.n2.outputs.signal
        )

    def test_value_fields_are_gone(self):
        data = get_node_dict(self.wf.nodes["n1"], wf=self.wf)["data"]
        self.assertNotIn("target_values", data)
        self.assertNotIn("source_values", data)

    def test_unfilled_marks_input_with_no_default_and_no_edge(self):
        data = get_node_dict(self.wf.nodes["n1"], wf=self.wf)["data"]
        flags = dict(zip(data["target_labels"], data["target_unfilled"], strict=True))
        self.assertTrue(flags["x"], "x has no default and nothing feeds it")
        self.assertFalse(flags["bias"], "bias has a default")

    def test_unfilled_is_false_when_an_edge_feeds_the_port(self):
        data = get_node_dict(self.wf.nodes["acc"], wf=self.wf)["data"]
        self.assertEqual([False, False], data["target_unfilled"])

    def test_port_default_is_scraped_from_the_live_node(self):
        node = self.wf.nodes["n1"]
        self.assertEqual(0.5, _get_port_default(node, "bias"))
        self.assertIsNone(_get_port_default(node, "x"))


if __name__ == "__main__":
    unittest.main()
