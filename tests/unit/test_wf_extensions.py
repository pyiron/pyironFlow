import json
import typing
import unittest

import flowrep as fr
import ipywidgets as widgets
import pyiron_workflow as pwf

from pyironflow import PyironFlow, datamodel
from pyironflow.reactflow import PyironFlowWidget
from pyironflow.wf_extensions import (
    _get_port_default,
    fed_input_ports,
    get_edges,
    get_node_cached_values,
    get_node_defaults,
    get_node_has_defaults,
    get_nodes,
    harvest_port_cache,
    port_cache_key,
)


@fr.atomic("signal")
def relu(x: float, bias: float = 0.0) -> float:
    return max(0.0, x - bias)


@fr.atomic("sum")
def add(a: float, b: float) -> float:
    return a + b


@fr.atomic("out")
def tabulate(
    rows: tuple[int, ...] = (1, 2),
    scale: float = 1.0,
    mode: typing.Literal["a", "b"] = "a",
    flag: bool = False,
) -> int:
    return sum(rows) * int(scale) * (2 if flag else 1) * len(mode)


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


class TestPortCache(unittest.TestCase):
    def test_key_matches_pyiron_workflow_naming(self):
        """The key must be the label pyiron_workflow gives the matching port."""
        wf = pwf.Workflow("keys")
        wf.n1 = pwf.node(relu)
        wf.set_inputs_to_unconnected_child_input(build_for_defaults=True)
        self.assertIn(port_cache_key("n1", "x"), wf.inputs)

    def test_harvest_stores_entered_values(self):
        cache = {}
        harvest_port_cache(
            [
                {
                    "id": "n1",
                    "data": {
                        "target_labels": ["x", "bias"],
                        "target_values": [1.5, None],
                    },
                }
            ],
            cache,
        )
        self.assertEqual({"n1__x": datamodel.PortCacheEntry(1.5)}, cache)

    def test_harvest_keeps_false_and_zero(self):
        """False and 0 are values a user meant, not empty fields."""
        cache = {}
        harvest_port_cache(
            [
                {
                    "id": "t1",
                    "data": {
                        "target_labels": ["flag", "scale"],
                        "target_values": [False, 0],
                    },
                }
            ],
            cache,
        )
        self.assertEqual(
            {
                "t1__flag": datamodel.PortCacheEntry(False),
                "t1__scale": datamodel.PortCacheEntry(0),
            },
            cache,
        )

    def test_harvest_clears_on_empty_string(self):
        cache = {"n1__x": datamodel.PortCacheEntry(1.5)}
        harvest_port_cache(
            [{"id": "n1", "data": {"target_labels": ["x"], "target_values": [""]}}],
            cache,
        )
        self.assertEqual({}, cache)

    def test_harvest_keeps_entries_for_absent_nodes(self):
        """A node deleted and re-added under the same label keeps what was typed."""
        cache = {"gone__x": datamodel.PortCacheEntry(7)}
        harvest_port_cache(
            [{"id": "n1", "data": {"target_labels": ["x"], "target_values": [1]}}],
            cache,
        )
        self.assertIn("gone__x", cache)

    def test_harvest_ignores_a_node_without_values(self):
        cache = {}
        harvest_port_cache([{"id": "n1", "data": {"target_labels": ["x"]}}], cache)
        self.assertEqual({}, cache)

    def test_fed_input_ports_sees_an_injected_constant(self):
        wf = pwf.Workflow("fed")
        wf.n1 = pwf.node(relu, x=0.25)
        self.assertIn(("n1", "x"), fed_input_ports(wf))
        self.assertNotIn(("n1", "bias"), fed_input_ports(wf))

    def test_fed_input_ports_ignores_terminal_input(self):
        """A port fed only from workflow input still needs a value supplied."""
        wf = pwf.Workflow("fed")
        wf.n1 = pwf.node(relu)
        wf.create_input_for(wf.nodes["n1"].inputs["x"], label="n1__x")
        self.assertNotIn(("n1", "x"), fed_input_ports(wf))


class TestSerializedInputFields(unittest.TestCase):
    def setUp(self):
        self.wf = pwf.Workflow("fields")
        self.wf.required = pwf.node(relu)
        self.wf.kinds = pwf.node(tabulate)

    def _data(self, nodes, node_id):
        return next(n["data"] for n in nodes if n["id"] == node_id)

    def test_defaults_are_none_where_there_is_no_primitive_default(self):
        data = self._data(get_nodes(self.wf), "kinds")
        self.assertEqual(
            [None, 1.0, "a", False],
            data["target_defaults"],
            msg="rows defaults to a tuple, which cannot be displayed in a field",
        )

    def test_has_default_reports_the_non_primitive_default(self):
        """The two fields differ exactly where a default exists but cannot be shown."""
        data = self._data(get_nodes(self.wf), "kinds")
        self.assertEqual([True, True, True, True], data["target_has_default"])

    def test_required_port_has_neither(self):
        data = self._data(get_nodes(self.wf), "required")
        self.assertEqual([None, 0.0], data["target_defaults"])
        self.assertEqual([False, True], data["target_has_default"])

    def test_values_come_from_the_cache(self):
        cache = {"required__x": datamodel.PortCacheEntry(2.5)}
        data = self._data(get_nodes(self.wf, port_cache=cache), "required")
        self.assertEqual([2.5, None], data["target_values"])

    def test_values_are_all_none_without_a_cache(self):
        data = self._data(get_nodes(self.wf), "required")
        self.assertEqual([None, None], data["target_values"])

    def test_output_values_are_gone(self):
        data = self._data(get_nodes(self.wf), "required")
        self.assertNotIn("source_values", data)

    def test_helpers_agree_with_the_serialized_fields(self):
        node = self.wf.nodes["kinds"]
        self.assertEqual([None, 1.0, "a", False], get_node_defaults(node))
        self.assertEqual([True, True, True, True], get_node_has_defaults(node))
        self.assertEqual([None] * 4, get_node_cached_values(node, {}))


class _StubLiveNode:
    def __init__(self, input_ports):
        self.input_ports = input_ports


class _StubPortData:
    def __init__(self, default):
        self.default = default


class TestGetPortDefault(unittest.TestCase):
    """Edge cases of ``_get_port_default`` not reached by any real node."""

    def test_none_when_live_node_generation_raises(self):
        class ExplodingNode:
            def generate_flowrep_live_node(self):
                raise RuntimeError("no live node available")

        self.assertIsNone(_get_port_default(ExplodingNode(), "x"))

    def test_none_when_port_absent_from_live_node(self):
        class Node:
            def generate_flowrep_live_node(self):
                return _StubLiveNode({})

        self.assertIsNone(_get_port_default(Node(), "x"))

    def test_none_for_a_non_finite_default(self):
        class Node:
            def generate_flowrep_live_node(self):
                return _StubLiveNode({"x": _StubPortData(float("inf"))})

        self.assertIsNone(_get_port_default(Node(), "x"))


class TestWidgetPortCacheRoundTrip(unittest.TestCase):
    """Harvest on ``get_workflow`` and replay on ``update`` round-trip a value."""

    def test_a_typed_value_survives_get_workflow_and_update(self):
        wf = pwf.Workflow("roundtrip")
        wf.n1 = pwf.node(relu)
        widget = PyironFlowWidget(
            wf=wf, log=widgets.Output(), out_widget=widgets.Output()
        )

        nodes = json.loads(widget.gui.nodes)
        nodes[0]["data"]["target_values"][0] = 2.5
        widget.gui.nodes = json.dumps(nodes)

        widget.wf = widget.get_workflow()
        self.assertEqual(datamodel.PortCacheEntry(2.5), widget._port_cache["n1__x"])

        widget.update()
        redrawn = json.loads(widget.gui.nodes)[0]["data"]["target_values"][0]
        self.assertEqual(2.5, redrawn)


if __name__ == "__main__":
    unittest.main()
