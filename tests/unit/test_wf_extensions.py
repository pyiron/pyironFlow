import typing
import unittest

import flowrep as fr
import ipywidgets as widgets
import pyiron_workflow as pwf

from pyironflow import PyironFlow, datamodel
from pyironflow.reactflow import PyironFlowWidget
from pyironflow.wf_extensions import (
    LOCKED_TEXT_MAX,
    LOCKED_TITLE_MAX,
    NO_DEFAULT,
    TransientInputs,
    _get_port_default,
    _port_default_value,
    cached_run_kwargs,
    create_dangling_output,
    create_transient_input,
    edge_id,
    extract_locks,
    fed_input_ports,
    get_edges,
    get_node_cached_values,
    get_node_defaults,
    get_node_has_defaults,
    get_node_locked,
    get_nodes,
    invalid_entries,
    is_constant,
    missing_required_input,
    port_cache_key,
    prune_uncached_input,
    rebuild_constants,
    transient_io,
    validate_constants,
)


@fr.atomic("signal")
def relu(x: float, bias: float = 0.0) -> float:
    return max(0.0, x - bias)


@fr.atomic("sum")
def add(a: float, b: float) -> float:
    return a + b


@fr.atomic("saw")
def optional(o: int | None) -> str:
    return "none" if o is None else "int"


@fr.atomic("out")
def tabulate(
    rows: tuple[int, ...] = (1, 2),
    scale: float = 1.0,
    mode: typing.Literal["a", "b"] = "a",
    flag: bool = False,
) -> int:
    return sum(rows) * int(scale) * (2 if flag else 1) * len(mode)


@fr.atomic("out")
def containers(
    grid: list[list[int]] = [[1, 2]],  # noqa: B006
    table: dict[str, float] = {"a": 1.0},  # noqa: B006
    mixed: int | str = 1,
    flag: bool = False,
    choice: typing.Literal["a", 1] = "a",
    opaque: tuple[int, int] = (1, 2),
) -> int:
    return len(grid) + len(table) + len(str(mixed)) + int(flag) + len(str(choice))


@fr.atomic("out")
def boom(x: float) -> float:
    raise RuntimeError("boom")


@fr.atomic("out")
def nested_param(b__c: float) -> float:
    """A port whose label collides with another node's under ``port_cache_key``.

    Paired with ``plain_param`` on a node labeled ``a__b``, a node labeled ``a`` with
    this port both key to ``a__b__c``, so creating a cached terminal input for the
    second one raises.
    """
    return b__c


@fr.atomic("out")
def plain_param(c: float) -> float:
    return c


@fr.workflow
def my_workflow(x):
    y = relu(x)
    z = relu(y)
    added = add(y, z)
    return added


def _constant(value, label):
    """A flowrep constant node, the thing this GUI draws as a locked port."""
    return pwf.schemas.Constant.from_value(value, label)


class TestIsConstant(unittest.TestCase):
    def test_true_for_a_constant(self):
        self.assertTrue(is_constant(_constant(1.0, "c")))

    def test_false_for_an_atomic(self):
        self.assertFalse(is_constant(pwf.node(relu)))


class TestValidateConstants(unittest.TestCase):
    def test_passes_a_graph_with_no_constants(self):
        wf = pwf.Workflow("plain")
        wf.n1 = pwf.node(relu)
        self.assertIsNone(validate_constants(wf))

    def test_passes_a_connected_constant(self):
        wf = pwf.Workflow("connected")
        wf.n1 = pwf.node(relu)
        c = _constant(2.5, "c")
        wf.add_node(c)
        wf.connect(c.outputs["constant"], wf.n1.inputs["bias"])
        self.assertIsNone(validate_constants(wf))

    def test_raises_on_a_dangling_constant(self):
        wf = pwf.Workflow("dangling")
        wf.n1 = pwf.node(relu)
        wf.add_node(_constant(2.5, "loose"))
        with self.assertRaises(ValueError) as caught:
            validate_constants(wf)
        message = str(caught.exception)
        self.assertIn("loose", message, "the message must name the offending node")
        self.assertIn("remove_node", message, "the message must carry the fix")

    def test_names_every_dangling_constant(self):
        wf = pwf.Workflow("two_dangling")
        wf.n1 = pwf.node(relu)
        wf.add_node(_constant(1.0, "loose_a"))
        wf.add_node(_constant(2.0, "loose_b"))
        with self.assertRaises(ValueError) as caught:
            validate_constants(wf)
        self.assertIn("loose_a", str(caught.exception))
        self.assertIn("loose_b", str(caught.exception))


class TestExtractLocks(unittest.TestCase):
    def test_empty_without_constants(self):
        wf = pwf.Workflow("plain")
        wf.n1 = pwf.node(relu)
        self.assertEqual(extract_locks(wf), {})

    def test_one_key_per_constant(self):
        wf = pwf.Workflow("one")
        wf.n1 = pwf.node(relu)
        c = _constant(2.5, "c")
        wf.add_node(c)
        wf.connect(c.outputs["constant"], wf.n1.inputs["bias"])
        self.assertEqual(extract_locks(wf), {port_cache_key("n1", "bias"): 2.5})

    def test_one_key_per_target_of_a_shared_constant(self):
        """A constant feeding two ports becomes two locks, which is the lossy split."""
        wf = pwf.Workflow("shared")
        wf.n1 = pwf.node(relu)
        wf.n2 = pwf.node(relu)
        c = _constant(2.5, "c")
        wf.add_node(c)
        wf.connect(c.outputs["constant"], wf.n1.inputs["bias"])
        wf.connect(c.outputs["constant"], wf.n2.inputs["bias"])
        self.assertEqual(
            extract_locks(wf),
            {
                port_cache_key("n1", "bias"): 2.5,
                port_cache_key("n2", "bias"): 2.5,
            },
        )

    def test_carries_a_container_value(self):
        wf = pwf.Workflow("container")
        wf.n1 = pwf.node(containers)
        c = _constant([[1, 2], [3]], "c")
        wf.add_node(c)
        wf.connect(c.outputs["constant"], wf.n1.inputs["grid"])
        self.assertEqual(
            extract_locks(wf), {port_cache_key("n1", "grid"): [[1, 2], [3]]}
        )

    def test_rejects_a_dangling_constant(self):
        wf = pwf.Workflow("dangling")
        wf.n1 = pwf.node(relu)
        wf.add_node(_constant(2.5, "loose"))
        with self.assertRaises(ValueError):
            extract_locks(wf)

    def test_ignores_an_edge_between_two_ordinary_nodes(self):
        """A non-constant source must not be mistaken for a lock."""
        wf = pwf.Workflow("mixed")
        wf.n1 = pwf.node(relu)
        wf.n2 = pwf.node(relu)
        wf.connect(wf.n2.outputs["signal"], wf.n1.inputs["bias"])
        c = _constant(2.5, "c")
        wf.add_node(c)
        wf.connect(c.outputs["constant"], wf.n2.inputs["bias"])
        self.assertEqual(extract_locks(wf), {port_cache_key("n2", "bias"): 2.5})

    def test_ignores_a_workflow_boundary_edge(self):
        """An edge from the workflow's own input has no node to be a constant."""
        wf = pwf.Workflow("boundary")
        wf.n1 = pwf.node(relu)
        wf.create_input_for(wf.n1.inputs["x"], label="n1__x")
        c = _constant(2.5, "c")
        wf.add_node(c)
        wf.connect(c.outputs["constant"], wf.n1.inputs["bias"])
        self.assertEqual(extract_locks(wf), {port_cache_key("n1", "bias"): 2.5})


class TestPyironFlowRejectsDanglingConstants(unittest.TestCase):
    def test_init_refuses(self):
        wf = pwf.Workflow("dangling")
        wf.n1 = pwf.node(relu)
        wf.add_node(_constant(2.5, "loose"))
        with self.assertRaises(ValueError) as caught:
            PyironFlow([wf])
        self.assertIn("loose", str(caught.exception))

    def test_init_accepts_a_connected_constant(self):
        wf = pwf.Workflow("connected")
        wf.n1 = pwf.node(relu)
        c = _constant(2.5, "c")
        wf.add_node(c)
        wf.connect(c.outputs["constant"], wf.n1.inputs["bias"])
        self.assertIsInstance(PyironFlow([wf]), PyironFlow)


class TestRebuildConstants(unittest.TestCase):
    def setUp(self):
        self.wf = pwf.Workflow("rebuilt")
        self.wf.n1 = pwf.node(relu)

    def _constants(self):
        return {
            label: node.recipe.constant
            for label, node in self.wf.nodes.items()
            if is_constant(node)
        }

    def _edges(self):
        return {
            (e.source.node, e.source.port, e.target.node, e.target.port)
            for e in self.wf.edges
        }

    def test_creates_one_constant_per_locked_port(self):
        rebuild_constants(self.wf, {port_cache_key("n1", "bias"): 2.5})
        self.assertEqual(self._constants(), {"n1_bias_constant_0": 2.5})
        self.assertEqual(
            self._edges(), {("n1_bias_constant_0", "constant", "n1", "bias")}
        )

    def test_is_idempotent(self):
        locked = {port_cache_key("n1", "bias"): 2.5}
        rebuild_constants(self.wf, locked)
        rebuild_constants(self.wf, locked)
        self.assertEqual(self._constants(), {"n1_bias_constant_0": 2.5})
        self.assertEqual(len(self._edges()), 1)

    def test_removes_a_constant_whose_lock_is_gone(self):
        rebuild_constants(self.wf, {port_cache_key("n1", "bias"): 2.5})
        rebuild_constants(self.wf, {})
        self.assertEqual(self._constants(), {})
        self.assertEqual(self._edges(), set())

    def test_updates_a_changed_value(self):
        rebuild_constants(self.wf, {port_cache_key("n1", "bias"): 2.5})
        rebuild_constants(self.wf, {port_cache_key("n1", "bias"): 4.0})
        self.assertEqual(self._constants(), {"n1_bias_constant_0": 4.0})

    def test_uniquifies_against_a_label_collision(self):
        self.wf.n1_bias_constant_0 = pwf.node(relu)
        rebuild_constants(self.wf, {port_cache_key("n1", "bias"): 2.5})
        self.assertEqual(self._constants(), {"n1_bias_constant_1": 2.5})

    def test_skips_a_key_whose_node_is_gone(self):
        rebuild_constants(self.wf, {port_cache_key("absent", "bias"): 2.5})
        self.assertEqual(self._constants(), {})

    def test_skips_a_key_whose_port_is_gone(self):
        rebuild_constants(self.wf, {port_cache_key("n1", "absent"): 2.5})
        self.assertEqual(self._constants(), {})

    def test_skips_a_port_fed_by_a_real_edge(self):
        """Two edges into one input port is not a graph flowrep will accept."""
        self.wf.n2 = pwf.node(relu)
        self.wf.connect(self.wf.n2.outputs["signal"], self.wf.n1.inputs["bias"])
        rebuild_constants(self.wf, {port_cache_key("n1", "bias"): 2.5})
        self.assertEqual(self._constants(), {})
        self.assertEqual(self._edges(), {("n2", "signal", "n1", "bias")})

    def test_splits_a_shared_constant_on_the_way_back_out(self):
        self.wf.n2 = pwf.node(relu)
        c = _constant(2.5, "c")
        self.wf.add_node(c)
        self.wf.connect(c.outputs["constant"], self.wf.n1.inputs["bias"])
        self.wf.connect(c.outputs["constant"], self.wf.n2.inputs["bias"])
        rebuild_constants(self.wf, extract_locks(self.wf))
        self.assertEqual(
            self._constants(),
            {"n1_bias_constant_0": 2.5, "n2_bias_constant_0": 2.5},
        )

    def test_a_rebuilt_graph_runs(self):
        rebuild_constants(self.wf, {port_cache_key("n1", "bias"): 2.5})
        self.wf.create_input_for(self.wf.n1.inputs["x"], label="n1__x")
        self.wf.set_outputs_to_unconnected_child_output(remove_existing=True)
        run = self.wf.run(n1__x=5.0)
        self.assertEqual(run.outputs["n1__signal"], 2.5)


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

    def test_pyironflow_init_rejects_a_macro(self):
        """A Macro has IO of its own, which pyironFlow would overwrite."""
        with self.assertRaises(TypeError):
            PyironFlow([self.wf])


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

    def test_edge_id_format(self):
        self.assertEqual(edge_id("n1", "signal", "n2", "x"), "n1.signal->n2.x")

    def test_get_edges_ids_name_their_ports(self):
        ids = {e["id"] for e in get_edges(self.wf)}
        self.assertEqual(ids, {"n1.signal->accumulate.a", "n2.signal->accumulate.b"})


class TestPortCache(unittest.TestCase):
    def test_key_matches_pyiron_workflow_naming(self):
        """The key must be the label pyiron_workflow gives the matching port."""
        wf = pwf.Workflow("keys")
        wf.n1 = pwf.node(relu)
        wf.set_inputs_to_unconnected_child_input(build_for_defaults=True)
        self.assertIn(port_cache_key("n1", "x"), wf.inputs)

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
            [None, "1.0", "'a'", "False"],
            data["target_defaults"],
            msg="rows defaults to a tuple, which cannot be displayed in a field",
        )

    def test_has_default_reports_the_non_primitive_default(self):
        """The two fields differ exactly where a default exists but cannot be shown."""
        data = self._data(get_nodes(self.wf), "kinds")
        self.assertEqual([True, True, True, True], data["target_has_default"])

    def test_required_port_has_neither(self):
        data = self._data(get_nodes(self.wf), "required")
        self.assertEqual([None, "0.0"], data["target_defaults"])
        self.assertEqual([False, True], data["target_has_default"])

    def test_values_come_from_the_cache(self):
        cache = {"required__x": 2.5}
        data = self._data(get_nodes(self.wf, port_cache=cache), "required")
        self.assertEqual({"x": "2.5"}, data["target_values"])

    def test_an_uncached_port_is_absent_from_the_values(self):
        data = self._data(get_nodes(self.wf), "required")
        self.assertEqual({}, data["target_values"])

    def test_output_values_are_gone(self):
        data = self._data(get_nodes(self.wf), "required")
        self.assertNotIn("source_values", data)

    def test_helpers_agree_with_the_serialized_fields(self):
        node = self.wf.nodes["kinds"]
        self.assertEqual([None, "1.0", "'a'", "False"], get_node_defaults(node))
        self.assertEqual([True, True, True, True], get_node_has_defaults(node))
        self.assertEqual({}, get_node_cached_values(node, {}))


class TestSerializedEntryFields(unittest.TestCase):
    def setUp(self):
        self.wf = pwf.Workflow("serialize")
        self.wf.n1 = pwf.node(containers)
        self.data = get_nodes(self.wf)[0]["data"]
        self.index = {label: i for i, label in enumerate(self.data["target_labels"])}

    def _field(self, name, port):
        return self.data[name][self.index[port]]

    def test_entry_kinds(self):
        for port, expected in [
            ("grid", "text"),
            ("table", "text"),
            ("mixed", "text"),
            ("flag", "checkbox"),
            ("choice", "dropdown"),
            ("opaque", "none"),
        ]:
            with self.subTest(port=port):
                self.assertEqual(expected, self._field("target_types", port))

    def test_defaults_are_rendered_text(self):
        self.assertEqual("[[1, 2]]", self._field("target_defaults", "grid"))
        self.assertEqual("{'a': 1.0}", self._field("target_defaults", "table"))

    def test_a_default_that_is_not_jsonable_is_dropped(self):
        self.assertIsNone(self._field("target_defaults", "opaque"))

    def test_dropdown_options_are_rendered(self):
        self.assertEqual(["'a'", "1"], self._field("target_literal_values", "choice"))

    def test_literal_types_are_gone(self):
        self.assertNotIn("target_literal_types", self.data)

    def test_cached_values_are_rendered_text(self):
        cache = {"n1__grid": [[1, 2], [3]], "n1__mixed": "42"}
        data = get_nodes(self.wf, port_cache=cache)[0]["data"]
        self.assertEqual(
            {"grid": "[[1, 2], [3]]", "mixed": "'42'"}, data["target_values"]
        )

    def test_invalid_entries_are_sent_with_their_text_and_message(self):
        invalid = {
            "n1__grid": datamodel.InvalidEntry(
                "[1, 2", "[1, 2 is not a Python literal."
            )
        }
        data = get_nodes(self.wf, invalid=invalid)[0]["data"]
        self.assertEqual(
            {"grid": {"text": "[1, 2", "message": "[1, 2 is not a Python literal."}},
            data["target_errors"],
        )


class _StubLiveNode:
    def __init__(self, input_ports):
        self.input_ports = input_ports


class _StubPortData:
    def __init__(self, default):
        self.default = default


class _StubPort:
    def __init__(self, type_hint):
        self.type_hint = type_hint


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
            inputs = {"x": _StubPort(float)}

            def generate_flowrep_live_node(self):
                return _StubLiveNode({"x": _StubPortData(float("inf"))})

        self.assertIsNone(_get_port_default(Node(), "x"))


class TestPortDefaultValue(unittest.TestCase):
    def test_returns_the_value_not_the_text(self):
        node = pwf.node(relu)
        self.assertEqual(_port_default_value(node, "bias"), 0.0)

    def test_sentinel_when_there_is_no_default(self):
        node = pwf.node(relu)
        self.assertIs(_port_default_value(node, "x"), NO_DEFAULT)

    def test_sentinel_for_a_hint_with_no_entry_field(self):
        node = pwf.node(containers)
        self.assertIs(_port_default_value(node, "opaque"), NO_DEFAULT)

    def test_a_none_default_is_a_value_not_an_absence(self):
        """The whole reason `NO_DEFAULT` is a sentinel and not just `None`."""

        class Node:
            inputs = {"x": _StubPort(int | None)}

            def generate_flowrep_live_node(self):
                return _StubLiveNode({"x": _StubPortData(None)})

        result = _port_default_value(Node(), "x")
        self.assertIsNone(result)
        self.assertIsNot(result, NO_DEFAULT)

    def test_the_sentinel_reprs_legibly(self):
        self.assertEqual(repr(NO_DEFAULT), "<NO DEFAULT>")


class TestGetNodeLocked(unittest.TestCase):
    def test_empty_when_nothing_is_locked(self):
        self.assertEqual(get_node_locked(pwf.node(relu), {}), {})

    def test_releasable_port(self):
        node = pwf.node(relu)
        locked = {port_cache_key(node.label, "bias"): 2.5}
        self.assertEqual(
            get_node_locked(node, locked),
            {"bias": {"text": "2.5", "full": "2.5", "releasable": True}},
        )

    def test_non_releasable_port_gets_a_repr(self):
        node = pwf.node(containers)
        locked = {port_cache_key(node.label, "opaque"): [1, 2]}
        entry_ = get_node_locked(node, locked)["opaque"]
        self.assertFalse(entry_["releasable"])
        self.assertEqual(entry_["text"], "[1, 2]")

    def test_clips_the_field_text(self):
        node = pwf.node(containers)
        big = [list(range(50)) for _ in range(50)]
        locked = {port_cache_key(node.label, "grid"): big}
        shown = get_node_locked(node, locked)["grid"]
        self.assertEqual(len(shown["text"]), LOCKED_TEXT_MAX)
        self.assertTrue(shown["text"].endswith("…"))

    def test_clips_the_tooltip_text(self):
        node = pwf.node(containers)
        big = [list(range(500)) for _ in range(50)]
        locked = {port_cache_key(node.label, "grid"): big}
        shown = get_node_locked(node, locked)["grid"]
        self.assertEqual(len(shown["full"]), LOCKED_TITLE_MAX)
        self.assertTrue(shown["full"].endswith("…"))

    def test_short_values_agree(self):
        node = pwf.node(relu)
        shown = get_node_locked(node, {port_cache_key(node.label, "bias"): 2.5})["bias"]
        self.assertEqual(shown["text"], shown["full"])

    def test_only_locked_ports_appear(self):
        node = pwf.node(relu)
        locked = {port_cache_key(node.label, "bias"): 2.5}
        self.assertEqual(set(get_node_locked(node, locked)), {"bias"})


class TestConstantsAreHiddenFromTheGui(unittest.TestCase):
    def setUp(self):
        self.wf = pwf.Workflow("hidden")
        self.wf.n1 = pwf.node(relu)
        c = _constant(2.5, "c")
        self.wf.add_node(c)
        self.wf.connect(c.outputs["constant"], self.wf.n1.inputs["bias"])

    def test_get_nodes_omits_the_constant(self):
        self.assertEqual([n["id"] for n in get_nodes(self.wf)], ["n1"])

    def test_get_edges_omits_the_constant_edge(self):
        self.assertEqual(get_edges(self.wf), [])

    def test_get_nodes_emits_target_locked(self):
        locked = extract_locks(self.wf)
        node = get_nodes(self.wf, locked=locked)[0]
        self.assertEqual(
            node["data"]["target_locked"],
            {"bias": {"text": "2.5", "full": "2.5", "releasable": True}},
        )

    def test_target_locked_is_empty_without_locks(self):
        node = get_nodes(self.wf)[0]
        self.assertEqual(node["data"]["target_locked"], {})


class TestInvalidEntries(unittest.TestCase):
    def setUp(self):
        self.wf = pwf.Workflow("invalid")
        self.wf.n1 = pwf.node(relu)

    def test_a_recorded_error_on_an_unfed_port_is_reported(self):
        invalid = {"n1__x": datamodel.InvalidEntry("[1", "[1 is not a Python literal.")}
        self.assertEqual(
            [("n1", "x", "[1 is not a Python literal.")],
            invalid_entries(self.wf, {}, invalid),
        )

    def test_a_cached_value_that_no_longer_fits_is_reported(self):
        found = invalid_entries(self.wf, {"n1__x": "not a float"}, {})
        self.assertEqual(1, len(found))
        self.assertEqual(("n1", "x"), found[0][:2])

    def test_a_good_cache_reports_nothing(self):
        self.assertEqual([], invalid_entries(self.wf, {"n1__x": 1.0}, {}))

    def test_a_fed_port_is_not_reported(self):
        wf = pwf.Workflow("fed")
        wf.n1 = pwf.node(relu, x=0.5)
        invalid = {"n1__x": datamodel.InvalidEntry("[1", "nope")}
        self.assertEqual([], invalid_entries(wf, {}, invalid))


class TestCachedRunKwargs(unittest.TestCase):
    def test_an_int_is_promoted_for_a_float_port(self):
        wf = pwf.Workflow("promote")
        wf.n1 = pwf.node(relu)
        cache = {"n1__x": 2}
        with transient_io(wf, cache, TransientInputs.USED):
            kwargs = cached_run_kwargs(wf, cache)
        self.assertEqual(2.0, kwargs["n1__x"])
        self.assertIs(float, type(kwargs["n1__x"]))


class TestRunTimeIO(unittest.TestCase):
    def setUp(self):
        self.wf = pwf.Workflow("runtime")
        self.wf.n1 = pwf.node(relu)
        self.wf.n2 = pwf.node(relu, x=-0.5)
        self.wf.acc = pwf.node(
            add, a=self.wf.n1.outputs.signal, b=self.wf.n2.outputs.signal
        )
        self.cache = {
            "n1__x": 1.0,
            "n1__bias": 0.25,
        }

    def test_used_creates_ports_for_cached_and_undefaulted_values(self):
        created = create_transient_input(self.wf, self.cache, TransientInputs.USED)
        self.assertEqual(["n1__x", "n1__bias"], created)
        self.assertEqual(["n1__x", "n1__bias"], list(self.wf.inputs))

    def test_skips_a_port_that_an_edge_already_feeds(self):
        """A cached value on a port that has since been wired up is ignored."""
        cache = dict(self.cache)
        cache["n2__x"] = 9.0
        created = create_transient_input(self.wf, cache, TransientInputs.USED)
        self.assertNotIn("n2__x", created)

    def test_skips_a_cached_value_for_a_node_that_is_gone(self):
        cache = {"deleted__x": 1.0}
        created = create_transient_input(self.wf, cache, TransientInputs.USED)
        self.assertEqual(["n1__x"], created)

    def test_output_exposes_the_unconsumed_child_output(self):
        self.assertEqual(["acc__sum"], create_dangling_output(self.wf))

    def test_missing_lists_the_unfed_undefaulted_uncached_port(self):
        self.assertEqual([("n1", "x")], missing_required_input(self.wf, {}))

    def test_nothing_missing_once_the_value_is_cached(self):
        self.assertEqual([], missing_required_input(self.wf, self.cache))

    def test_run_kwargs_promote_an_int_to_a_float(self):
        """A text field yields 2 where the float-hinted port wanted 2.0."""
        create_transient_input(self.wf, {"n1__x": 2}, TransientInputs.USED)
        kwargs = cached_run_kwargs(self.wf, {"n1__x": 2})
        self.assertIsInstance(kwargs["n1__x"], float)

    def test_run_leaves_the_workflow_as_it_found_it(self):
        created_input = create_transient_input(
            self.wf, self.cache, TransientInputs.USED
        )
        created_output = create_dangling_output(self.wf)
        run = self.wf.run(**cached_run_kwargs(self.wf, self.cache))
        self.wf.remove_input(*created_input)
        self.wf.remove_output(*created_output)
        self.assertEqual({"acc__sum": 0.75}, run.outputs)
        self.assertEqual([], list(self.wf.inputs))
        self.assertEqual([], list(self.wf.outputs))

    def test_pull_agrees_with_run(self):
        """A value typed into a defaulted port must reach a pull, not just a run."""
        pulled = self.wf.nodes["acc"].pulled_workflow(True, True)
        prune_uncached_input(pulled, self.cache)
        self.assertEqual([], missing_required_input(pulled, self.cache))
        run = pulled.run(**cached_run_kwargs(pulled, self.cache))
        self.assertEqual(0.75, run.outputs["sum"])

    def test_prune_drops_only_the_defaulted_uncached_port(self):
        pulled = self.wf.nodes["acc"].pulled_workflow(True, True)
        self.assertIn("n2__bias", pulled.inputs)
        removed = prune_uncached_input(pulled, self.cache)
        self.assertEqual(["n2__bias"], removed)
        self.assertIn("n1__x", pulled.inputs)

    def test_prune_drops_a_port_wired_to_nothing(self):
        """A terminal input with no destination cannot affect a run and must not
        linger, unlike a port whose only destination is the workflow's own output,
        which genuinely still needs a value and so is kept by the `all(...)` branch."""
        create_transient_input(self.wf, self.cache, TransientInputs.USED)
        (edge,) = [e for e in self.wf.edges if e.source.port == "n1__x"]
        self.wf.remove_edge(edge)
        removed = prune_uncached_input(self.wf, {})
        self.assertIn("n1__x", removed)
        self.assertNotIn("n1__x", self.wf.inputs)


class TestTransientInputs(unittest.TestCase):
    """Which unconnected ports each mode exposes, and that the IO is transient."""

    def setUp(self):
        self.wf = pwf.Workflow("modes")
        self.wf.n1 = pwf.node(relu)  # x undefaulted, bias defaulted
        self.wf.n2 = pwf.node(relu)  # nothing typed
        self.wf.n3 = pwf.node(relu, x=self.wf.n1.outputs.signal)  # x connected
        self.cache = {"n1__x": 1.0, "n1__bias": 0.5, "n3__x": 9.0}

    def test_used_is_undefaulted_plus_cached(self):
        self.assertEqual(
            ["n1__x", "n1__bias", "n2__x"],
            create_transient_input(self.wf, self.cache, TransientInputs.USED),
        )

    def test_unconnected_is_every_unconnected_port(self):
        self.assertEqual(
            ["n1__x", "n1__bias", "n2__x", "n2__bias", "n3__bias"],
            create_transient_input(self.wf, self.cache, TransientInputs.UNCONNECTED),
        )

    def test_undefaulted_ignores_the_cache(self):
        self.assertEqual(
            ["n1__x", "n2__x"],
            create_transient_input(self.wf, self.cache, TransientInputs.UNDEFAULTED),
        )

    def test_an_unknown_mode_is_rejected(self):
        with self.assertRaises(AssertionError):
            create_transient_input(self.wf, {}, "bogus")  # type: ignore[arg-type]

    def test_every_mode_yields_a_valid_recipe_and_leaves_no_io(self):
        for mode in TransientInputs:
            with self.subTest(mode=mode):
                with transient_io(self.wf, self.cache, mode) as wf:
                    self.assertIs(self.wf, wf)
                    self.assertIsInstance(wf.recipe, fr.schemas.WorkflowRecipe)
                    self.assertEqual(["n2__signal", "n3__signal"], list(wf.outputs))
                self.assertEqual([], list(self.wf.inputs))
                self.assertEqual([], list(self.wf.outputs))

    def test_io_is_removed_when_the_body_raises(self):
        with (
            self.assertRaises(RuntimeError),
            transient_io(self.wf, self.cache, TransientInputs.USED),
        ):
            raise RuntimeError("inside")
        self.assertEqual([], list(self.wf.inputs))
        self.assertEqual([], list(self.wf.outputs))

    def test_undo_and_redo_history_are_restored(self):
        self.wf.n4 = pwf.node(relu)
        self.wf.undo()
        undo_before = list(self.wf.undo_stack)
        redo_before = list(self.wf.redo_stack)
        self.assertGreater(len(redo_before), 0)
        with transient_io(self.wf, self.cache, TransientInputs.UNCONNECTED):
            pass
        self.assertEqual(undo_before, list(self.wf.undo_stack))
        self.assertEqual(redo_before, list(self.wf.redo_stack))


def _captured(widget, fn):
    """Run *fn* on a cleared output widget and return what it shows there.

    Printed text reads as itself, an HTML header as its markup, and a displayed
    value as its ``repr``.
    """
    widget.out_widget.outputs = ()
    fn()
    return [
        (
            o["text"]
            if o["output_type"] == "stream"
            else o["data"].get("text/html", o["data"]["text/plain"])
        )
        for o in widget.out_widget.outputs
    ]


class TestRunWorkflow(unittest.TestCase):
    """Widget-level coverage of ``run_workflow``: missing input, success, failure."""

    def setUp(self):
        self.wf = pwf.Workflow("run_widget")
        self.wf.n1 = pwf.node(relu)  # x required, bias defaulted
        self.widget = PyironFlowWidget(
            wf=self.wf, log=widgets.Output(), out_widget=widgets.Output()
        )

    def _run(self):
        return _captured(self.widget, lambda: self.widget.run_workflow(self.widget.wf))

    def test_aborts_and_creates_no_port_when_a_required_value_is_missing(self):
        seen_error = self._run()[0]
        self.assertIn("n1.x", seen_error)
        self.assertEqual([], list(self.widget.wf.inputs))

    def test_a_successful_run_reports_outputs_and_leaves_the_workflow_clean(self):
        self.widget._port_cache["n1__x"] = 1.0
        seen = self._run()
        self.assertIn("n1__signal", seen[0])
        self.assertEqual([], list(self.widget.wf.inputs))
        self.assertEqual([], list(self.widget.wf.outputs))

    def test_a_typed_value_on_a_defaulted_port_changes_the_result(self):
        self.widget._port_cache["n1__x"] = 1.0
        first = self._run()
        self.assertIn("n1__signal", first[0])
        self.assertAlmostEqual(1.0, float(first[1]))

        self.widget._port_cache["n1__bias"] = 0.5
        second = self._run()
        self.assertIn("n1__signal", second[0])
        self.assertAlmostEqual(0.5, float(second[1]))

    def test_a_raise_during_the_run_still_leaves_the_workflow_clean(self):
        self.wf.n_boom = pwf.node(boom)
        self.widget._port_cache["n1__x"] = 1.0
        self.widget._port_cache["n_boom__x"] = 1.0
        with self.assertRaises(RuntimeError):
            self._run()
        self.assertEqual([], list(self.widget.wf.inputs))
        self.assertEqual([], list(self.widget.wf.outputs))

    def test_a_raise_during_port_creation_still_leaves_the_workflow_clean(self):
        """Finding 1: a cache-key collision must not leave a dangling terminal port.

        A node ``a`` with a port ``b__c`` and a node ``a__b`` with a port ``c`` both
        key to ``a__b__c``, so the second ``create_input_for`` call raises while the
        first port is already attached, mid-loop inside `create_transient_input` --
        before it can return anything describing what it built.
        """
        wf = pwf.Workflow("collide")
        wf.a = pwf.node(nested_param)
        wf.a__b = pwf.node(plain_param)
        widget = PyironFlowWidget(
            wf=wf, log=widgets.Output(), out_widget=widgets.Output()
        )
        widget._port_cache["a__b__c"] = 1.0

        with self.assertRaises(ValueError):
            _captured(widget, lambda: widget.run_workflow(widget.wf))

        self.assertEqual([], list(widget.wf.inputs))
        self.assertEqual([], list(widget.wf.outputs))

    def test_run_does_not_grow_the_undo_stack(self):
        """A run's own port bookkeeping must not appear in the user's undo history."""
        self.widget._port_cache["n1__x"] = 1.0
        before = len(self.widget.wf.undo_stack)
        self._run()
        self.assertEqual(before, len(self.widget.wf.undo_stack))

    def test_run_does_not_clear_the_redo_stack(self):
        self.wf.n2 = pwf.node(tabulate)  # no required input, so the run still fires
        self.wf.undo()
        self.assertGreater(len(self.wf.redo_stack), 0)
        before = list(self.wf.redo_stack)

        self.widget._port_cache["n1__x"] = 1.0
        self._run()

        self.assertEqual(before, list(self.wf.redo_stack))

    def test_undo_stack_unchanged_when_the_run_raises(self):
        self.wf.n_boom = pwf.node(boom)
        self.widget._port_cache["n1__x"] = 1.0
        self.widget._port_cache["n_boom__x"] = 1.0
        before = len(self.widget.wf.undo_stack)

        with self.assertRaises(RuntimeError):
            self._run()

        self.assertEqual(before, len(self.widget.wf.undo_stack))

    def test_undo_immediately_after_a_run_does_not_restore_terminal_io(self):
        self.widget._port_cache["n1__x"] = 1.0
        self._run()

        self.wf.undo()

        self.assertEqual([], list(self.wf.inputs))
        self.assertEqual([], list(self.wf.outputs))

    def test_undo_after_a_run_on_a_saturated_stack_restores_no_terminal_io(self):
        """Regression: a full undo_stack must not let the run's own diffs survive.

        `undo_stack` is a bounded `deque` (`maxlen` defaults to 10). Once it is
        already full of real user edits, the run's four pushes would evict genuine
        entries one for one rather than growing the stack, so a length-based
        truncation of the stack (comparing lengths before and after) never fires:
        the run's diffs are left on top, and a real user edit is lost underneath.
        """
        wf = pwf.Workflow("saturated")
        wf.n1 = pwf.node(relu)  # x required, cached below
        for i in range(wf.undo_stack.maxlen):
            # Every input of `tabulate` has a default, so this never trips the
            # missing-input check and each assignment is one real, undoable edit.
            setattr(wf, f"filler_{i}", pwf.node(tabulate))
        self.assertEqual(wf.undo_stack.maxlen, len(wf.undo_stack))
        before = list(wf.undo_stack)

        widget = PyironFlowWidget(
            wf=wf, log=widgets.Output(), out_widget=widgets.Output()
        )
        widget._port_cache["n1__x"] = 1.0
        _captured(widget, lambda: widget.run_workflow(widget.wf))

        self.assertEqual([], list(wf.inputs))
        self.assertEqual([], list(wf.outputs))
        self.assertEqual(before, list(wf.undo_stack))

        wf.undo()

        self.assertEqual([], list(wf.inputs))
        self.assertEqual([], list(wf.outputs))


class TestPullWorkflow(unittest.TestCase):
    """Widget-level coverage of ``pull_workflow``, agreeing with an equivalent run."""

    def test_pull_aborts_when_a_required_value_is_missing(self):
        wf = pwf.Workflow("pull_widget_missing")
        wf.n1 = pwf.node(relu)
        widget = PyironFlowWidget(
            wf=wf, log=widgets.Output(), out_widget=widgets.Output()
        )
        seen_error = _captured(
            widget, lambda: widget.pull_workflow(widget.wf.nodes["n1"])
        )[0]
        self.assertIn("n1.x", seen_error)

    def test_pull_agrees_with_the_equivalent_run(self):
        wf = pwf.Workflow("pull_widget")
        wf.n1 = pwf.node(relu)
        wf.n2 = pwf.node(relu, x=-0.5)
        wf.acc = pwf.node(add, a=wf.n1.outputs.signal, b=wf.n2.outputs.signal)
        widget = PyironFlowWidget(
            wf=wf, log=widgets.Output(), out_widget=widgets.Output()
        )
        widget._port_cache["n1__x"] = 1.0
        widget._port_cache["n1__bias"] = 0.25

        seen_run = _captured(widget, lambda: widget.run_workflow(widget.wf))
        self.assertIn("acc__sum", seen_run[0])
        self.assertAlmostEqual(0.75, float(seen_run[1]))

        seen_pull = _captured(
            widget, lambda: widget.pull_workflow(widget.wf.nodes["acc"])
        )
        self.assertIn("sum", seen_pull[0])
        self.assertAlmostEqual(0.75, float(seen_pull[1]))


if __name__ == "__main__":
    unittest.main()


class TestNoneIsAValue(unittest.TestCase):
    """``None`` is a value a user can enter, distinct from entering nothing.

    `PortCache` absence is the only marker for "nothing entered", which is what
    leaves ``None`` free to mean the user typed ``None``, on a port whose hint admits
    it. The cache is written only by `PyironFlowWidget.commit_entry`; this class
    covers how a stored ``None`` renders and behaves once it is there.
    """

    def test_a_stored_none_survives_serialization(self):
        """The rendered text for a stored ``None`` is the literal word, not JSON null.

        ``get_node_cached_values`` now renders every cached value as text (see
        ``wf_extensions.get_node_cached_values``), so a cached ``None`` becomes the
        text ``"None"`` rather than surviving as JSON ``null``. The cache holds
        ``None`` itself; only the wire carries the text ``"None"``, and
        ``PyironFlowWidget.commit_entry`` is what parses text back into a value.
        """
        wf = pwf.Workflow("noneround")
        wf.n1 = pwf.node(relu)
        cache = {"n1__x": None}
        data = next(n["data"] for n in get_nodes(wf, port_cache=cache))
        self.assertEqual({"x": "None"}, data["target_values"])

    def test_an_uncached_port_is_absent_rather_than_null(self):
        wf = pwf.Workflow("noneround")
        wf.n1 = pwf.node(relu)
        data = next(n["data"] for n in get_nodes(wf, port_cache={}))
        self.assertEqual({}, data["target_values"])

    def test_a_typed_none_reaches_the_run_kwargs(self):
        """A ``float`` port cannot hold ``None``; only a hint that admits it can.

        ``cached_run_kwargs`` now re-checks every value against its port's hint
        (`entry.coerce`), so this uses ``optional``'s ``int | None`` port rather than
        ``relu``'s plain ``float`` one, which could never hold ``None`` in practice:
        `entry.parse` would have rejected it long before it reached the cache.
        """
        wf = pwf.Workflow("nonerun")
        wf.n1 = pwf.node(optional)
        wf.create_input_for(wf.nodes["n1"].inputs["o"], label="n1__o")
        self.assertEqual({"n1__o": None}, cached_run_kwargs(wf, {"n1__o": None}))

    def test_an_uncached_port_contributes_no_kwarg(self):
        wf = pwf.Workflow("nonerun")
        wf.n1 = pwf.node(relu)
        wf.create_input_for(wf.nodes["n1"].inputs["x"], label="n1__x")
        self.assertEqual({}, cached_run_kwargs(wf, {}))

    def test_a_typed_none_reaches_the_node_that_runs(self):
        """End to end: a cached None must arrive at the function, not its absence."""
        wf = pwf.Workflow("noneend")
        wf.n1 = pwf.node(optional)
        widget = PyironFlowWidget(
            wf=wf, log=widgets.Output(), out_widget=widgets.Output()
        )
        widget._port_cache["n1__o"] = None
        created_input = create_transient_input(
            wf, widget._port_cache, TransientInputs.USED
        )
        create_dangling_output(wf)
        run = wf.run(**cached_run_kwargs(wf, widget._port_cache))
        wf.remove_input(*created_input)
        wf.remove_output(*list(wf.outputs))
        self.assertEqual({"n1__saw": "none"}, run.outputs)

    def test_a_typed_none_counts_as_cached_for_port_creation(self):
        """A None entry must still build a terminal port, or the value cannot arrive."""
        wf = pwf.Workflow("noneport")
        wf.n1 = pwf.node(relu)
        self.assertEqual(
            ["n1__x"],
            create_transient_input(wf, {"n1__x": None}, TransientInputs.USED),
        )
