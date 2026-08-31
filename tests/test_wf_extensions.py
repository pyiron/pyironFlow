"""Tests for wf_extensions with pyiron_workflow >= 0.19."""
import pytest

flowrep = pytest.importorskip("flowrep")
pwf = pytest.importorskip("pyiron_workflow")

import flowrep as fr
import pyiron_workflow as pwf

from pyironflow.wf_extensions import get_edges, get_nodes, _is_const_node


# ---------------------------------------------------------------------------
# Simple node fixtures
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# _is_const_node
# ---------------------------------------------------------------------------

class TestIsConstNode:
    def test_none_label_returns_false(self):
        """None label (workflow boundary edge) must not raise AttributeError."""
        assert _is_const_node(None) is False

    def test_const_prefix_returns_true(self):
        assert _is_const_node("_const_n1__x") is True

    def test_regular_label_returns_false(self):
        assert _is_const_node("relu_0") is False


# ---------------------------------------------------------------------------
# get_nodes / get_edges with a @fr.workflow (Macro) node
# ---------------------------------------------------------------------------

class TestMacroNode:
    @pytest.fixture
    def wf(self):
        return pwf.node(my_workflow)

    def test_get_nodes_returns_three_nodes(self, wf):
        nodes = get_nodes(wf)
        assert len(nodes) == 3

    def test_get_nodes_no_none_ids(self, wf):
        nodes = get_nodes(wf)
        for n in nodes:
            assert n["id"] is not None

    def test_get_edges_no_none_source_or_target(self, wf):
        """Boundary edges (source/target == None) must be filtered out."""
        edges = get_edges(wf)
        for e in edges:
            assert e["source"] is not None, "edge source must not be None"
            assert e["target"] is not None, "edge target must not be None"

    def test_get_edges_internal_connections(self, wf):
        """Edges between internal nodes should be present."""
        edges = get_edges(wf)
        # relu_0 -> relu_1, relu_0 -> add_0, relu_1 -> add_0
        assert len(edges) == 3

    def test_pyironflow_init_does_not_raise(self, wf):
        """PyironFlow([macro_node]) must not raise AttributeError."""
        from pyironflow import PyironFlow

        # PyironFlow requires a display environment; we just test construction
        # raises no Python-level exception (widget rendering may be no-op).
        pf = PyironFlow([wf])
        assert pf is not None


# ---------------------------------------------------------------------------
# get_nodes / get_edges with a regular Workflow
# ---------------------------------------------------------------------------

class TestRegularWorkflow:
    @pytest.fixture
    def wf(self):
        wf = pwf.Workflow("test_regular")
        wf.n1 = pwf.node(relu, x=0.2)
        wf.n2 = pwf.node(relu, x=-0.5)
        wf.accumulate = pwf.node(add, a=wf.n1.outputs.signal, b=wf.n2.outputs.signal)
        return wf

    def test_get_nodes_count(self, wf):
        # pyiron_workflow auto-creates constant nodes for literal values (e.g. n1_x_constant_0)
        nodes = get_nodes(wf)
        node_ids = [n["id"] for n in nodes]
        # The three user-visible nodes must be present
        assert "n1" in node_ids
        assert "n2" in node_ids
        assert "accumulate" in node_ids

    def test_get_edges_count(self, wf):
        edges = get_edges(wf)
        # At minimum the two internal (node-to-node) edges must exist
        internal = [e for e in edges if e["source"] in ("n1", "n2")]
        assert len(internal) == 2

    def test_get_edges_no_const_edges(self, wf):
        edges = get_edges(wf)
        for e in edges:
            assert not (e["source"] or "").startswith("_const_")
            assert not (e["target"] or "").startswith("_const_")
