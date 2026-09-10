import typing
import unittest

import flowrep as fr
import pyiron_workflow as pwf

from pyironflow import PyironFlow
from pyironflow.wf_extensions import (
    PORT_HEIGHT_PLAIN,
    _get_port_default,
    get_edges,
    get_node_dict,
    get_nodes,
    get_port_dict,
    get_port_hint,
    is_port_element,
    parse_port_element_id,
    port_element_id,
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


class TestPortElements(unittest.TestCase):
    def setUp(self):
        self.wf = pwf.Workflow("ports")
        self.wf.n1 = pwf.node(relu)
        self.wf.set_io_to_unconnected_child_io(
            remove_existing=True, build_for_defaults=True
        )

    def test_input_element_shape(self):
        port = self.wf.inputs["n1__x"]
        element = get_port_dict(port, "input", allow_value_entry=True)
        self.assertEqual("input::n1__x", element["id"])
        self.assertEqual("portNode", element["type"])
        data = element["data"]
        self.assertEqual("input", data["variant"])
        self.assertEqual("n1__x", data["label"])
        self.assertEqual("float", data["hint"])
        self.assertEqual("float", data["entry_kind"])
        self.assertTrue(data["allow_value_entry"])
        self.assertEqual(["n1__x"], data["source_labels"])
        self.assertEqual([], data["target_labels"])

    def test_output_element_mirrors_the_input_one(self):
        port = self.wf.outputs["n1__signal"]
        element = get_port_dict(port, "output")
        self.assertEqual("output::n1__signal", element["id"])
        data = element["data"]
        self.assertEqual("output", data["variant"])
        self.assertEqual([], data["source_labels"])
        self.assertEqual(["n1__signal"], data["target_labels"])
        self.assertFalse(data["allow_value_entry"])

    def test_seeded_value_is_carried_through(self):
        port = self.wf.inputs["n1__bias"]
        element = get_port_dict(port, "input", allow_value_entry=True, value=0.5)
        self.assertEqual(0.5, element["data"]["value"])

    def test_position_defaults_and_overrides(self):
        port = self.wf.inputs["n1__x"]
        self.assertEqual({"x": 0, "y": 0}, get_port_dict(port, "input")["position"])
        self.assertEqual(
            {"x": 5, "y": 7},
            get_port_dict(port, "input", position={"x": 5, "y": 7})["position"],
        )

    def test_id_round_trip(self):
        self.assertEqual(
            ("input", "n1__x"), parse_port_element_id(port_element_id("input", "n1__x"))
        )

    def test_is_port_element(self):
        port = self.wf.inputs["n1__x"]
        self.assertTrue(is_port_element(get_port_dict(port, "input")))
        self.assertFalse(is_port_element(get_node_dict(self.wf.nodes["n1"], self.wf)))

    def test_style_uses_min_height_not_height(self):
        """A fixed height pins the box; minHeight lets it grow to fit wrapped text."""
        port = self.wf.inputs["n1__x"]
        style = get_port_dict(port, "input")["style"]
        self.assertIn("minHeight", style)
        self.assertNotIn("height", style)

    def test_short_label_gets_plain_height_estimate(self):
        port = self.wf.inputs["n1__x"]
        style = get_port_dict(port, "input")["style"]
        self.assertEqual(PORT_HEIGHT_PLAIN, style["height_unitless"])

    def test_long_label_estimate_grows_for_wrapped_lines(self):
        long_label = "a_label_long_enough_to_wrap_across_three_separate_lines"
        wf = pwf.Workflow("ports_long_label")
        wf.create_input(long_label)
        short_style = get_port_dict(self.wf.inputs["n1__x"], "input")["style"]
        long_style = get_port_dict(wf.inputs[long_label], "input")["style"]
        self.assertGreater(
            long_style["height_unitless"], short_style["height_unitless"]
        )

    def test_entry_field_still_adds_height_over_no_entry(self):
        port = self.wf.inputs["n1__x"]
        no_entry = get_port_dict(port, "input", allow_value_entry=False)
        with_entry = get_port_dict(port, "input", allow_value_entry=True)
        self.assertGreater(
            with_entry["style"]["height_unitless"],
            no_entry["style"]["height_unitless"],
        )


class TestPortHint(unittest.TestCase):
    def test_plain_class(self):
        wf = pwf.Workflow("hint_plain")
        wf.n1 = pwf.node(relu)
        wf.create_input_for(wf.nodes["n1"].inputs["x"], label="x")
        self.assertEqual("float", get_port_hint(wf.inputs["x"]))

    def test_no_hint(self):
        wf = pwf.Workflow("hint_none")
        wf.create_input("bare")
        self.assertEqual("None", get_port_hint(wf.inputs["bare"]))

    def test_parametrised_hints_keep_their_parameters(self):
        """__name__ would collapse these to "Literal" and "dict"."""
        wf = pwf.Workflow("hint_param")
        wf.create_input("choice", type_hint=typing.Literal["bfgs", "cg"])
        wf.create_input("table", type_hint=dict[str, int])
        wf.create_input("maybe", type_hint=int | None)
        self.assertEqual("Literal['bfgs', 'cg']", get_port_hint(wf.inputs["choice"]))
        self.assertEqual("dict[str, int]", get_port_hint(wf.inputs["table"]))
        self.assertEqual("int | None", get_port_hint(wf.inputs["maybe"]))


if __name__ == "__main__":
    unittest.main()
