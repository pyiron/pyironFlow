import unittest

import flowrep as fr
import pyiron_workflow as pwf

from pyironflow import PyironFlow
from pyironflow.wf_extensions import _is_const_node, get_edges, get_nodes


@fr.atomic("signal")
def relu(x: float, bias: float = 0.0) -> float:
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


class TestIsConstNode(unittest.TestCase):
    def test_none_label_returns_false(self):
        """None label (workflow boundary edge) must not raise AttributeError."""
        self.assertFalse(_is_const_node(None))

    def test_const_prefix_returns_true(self):
        self.assertTrue(_is_const_node("_const_n1__x"))

    def test_regular_label_returns_false(self):
        self.assertFalse(_is_const_node("relu_0"))


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


if __name__ == "__main__":
    unittest.main()
