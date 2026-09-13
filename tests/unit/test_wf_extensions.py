import contextlib
import io
import json
import typing
import unittest

import flowrep as fr
import ipywidgets as widgets
import pyiron_workflow as pwf

from pyironflow import PyironFlow, datamodel
from pyironflow.reactflow import PyironFlowWidget
from pyironflow.wf_extensions import (
    _coerce_to_hint,
    _get_port_default,
    cached_run_kwargs,
    create_cached_input,
    create_dangling_output,
    fed_input_ports,
    get_edges,
    get_node_cached_values,
    get_node_defaults,
    get_node_has_defaults,
    get_nodes,
    harvest_port_cache,
    missing_required_input,
    port_cache_key,
    prune_uncached_input,
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


class TestRunTimeIO(unittest.TestCase):
    def setUp(self):
        self.wf = pwf.Workflow("runtime")
        self.wf.n1 = pwf.node(relu)
        self.wf.n2 = pwf.node(relu, x=-0.5)
        self.wf.acc = pwf.node(
            add, a=self.wf.n1.outputs.signal, b=self.wf.n2.outputs.signal
        )
        self.cache = {
            "n1__x": datamodel.PortCacheEntry(1.0),
            "n1__bias": datamodel.PortCacheEntry(0.25),
        }

    def test_creates_a_port_only_for_a_cached_value(self):
        created = create_cached_input(self.wf, self.cache)
        self.assertEqual(["n1__x", "n1__bias"], created)
        self.assertEqual(["n1__x", "n1__bias"], list(self.wf.inputs))

    def test_skips_a_port_that_an_edge_already_feeds(self):
        """A cached value on a port that has since been wired up is ignored."""
        cache = dict(self.cache)
        cache["n2__x"] = datamodel.PortCacheEntry(9.0)
        created = create_cached_input(self.wf, cache)
        self.assertNotIn("n2__x", created)

    def test_skips_a_cached_value_for_a_node_that_is_gone(self):
        cache = {"deleted__x": datamodel.PortCacheEntry(1.0)}
        self.assertEqual([], create_cached_input(self.wf, cache))

    def test_output_exposes_the_unconsumed_child_output(self):
        self.assertEqual(["acc__sum"], create_dangling_output(self.wf))

    def test_missing_lists_the_unfed_undefaulted_uncached_port(self):
        self.assertEqual([("n1", "x")], missing_required_input(self.wf, {}))

    def test_nothing_missing_once_the_value_is_cached(self):
        self.assertEqual([], missing_required_input(self.wf, self.cache))

    def test_run_kwargs_promote_an_int_to_a_float(self):
        """A text field yields 2 where the float-hinted port wanted 2.0."""
        create_cached_input(self.wf, {"n1__x": datamodel.PortCacheEntry(2)})
        kwargs = cached_run_kwargs(self.wf, {"n1__x": datamodel.PortCacheEntry(2)})
        self.assertIsInstance(kwargs["n1__x"], float)

    def test_run_leaves_the_workflow_as_it_found_it(self):
        created_input = create_cached_input(self.wf, self.cache)
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
        create_cached_input(self.wf, self.cache)
        (edge,) = [e for e in self.wf.edges if e.source.port == "n1__x"]
        self.wf.remove_edge(edge)
        removed = prune_uncached_input(self.wf, {})
        self.assertIn("n1__x", removed)
        self.assertNotIn("n1__x", self.wf.inputs)

    def test_coerce_to_hint_leaves_an_already_matching_value_untouched(self):
        """No promotion is needed, or possible, once the value already fits."""
        self.assertEqual(2, _coerce_to_hint(2, int))


def _captured(widget, fn):
    """Run *fn* the way GUI dispatch would and return what reached the output widget.

    Outside a live Jupyter kernel, ``ipywidgets.Output.__enter__`` is a no-op (it only
    hooks the kernel's iopub channel, which does not exist in a plain script), so a
    bare ``with widget.out_widget:`` block captures nothing on its own. ``stdout`` is
    redirected to recover the same text a Jupyter frontend would have routed into the
    output widget.
    """
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer), widget.out_widget:
        fn()
    return buffer.getvalue()


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
        text = self._run()
        self.assertIn("n1.x", text)
        self.assertEqual([], list(self.widget.wf.inputs))

    def test_a_successful_run_reports_outputs_and_leaves_the_workflow_clean(self):
        self.widget._port_cache["n1__x"] = datamodel.PortCacheEntry(1.0)
        text = self._run()
        self.assertIn("n1__signal", text)
        self.assertEqual([], list(self.widget.wf.inputs))
        self.assertEqual([], list(self.widget.wf.outputs))

    def test_a_typed_value_on_a_defaulted_port_changes_the_result(self):
        self.widget._port_cache["n1__x"] = datamodel.PortCacheEntry(1.0)
        first = self._run()
        self.assertIn("'n1__signal': 1.0", first)

        self.widget._port_cache["n1__bias"] = datamodel.PortCacheEntry(0.5)
        second = self._run()
        self.assertIn("'n1__signal': 0.5", second)

    def test_a_raise_during_the_run_still_leaves_the_workflow_clean(self):
        self.wf.n_boom = pwf.node(boom)
        self.widget._port_cache["n1__x"] = datamodel.PortCacheEntry(1.0)
        self.widget._port_cache["n_boom__x"] = datamodel.PortCacheEntry(1.0)
        self._run()
        self.assertEqual([], list(self.widget.wf.inputs))
        self.assertEqual([], list(self.widget.wf.outputs))

    def test_a_raise_during_port_creation_still_leaves_the_workflow_clean(self):
        """Finding 1: a cache-key collision must not leave a dangling terminal port.

        A node ``a`` with a port ``b__c`` and a node ``a__b`` with a port ``c`` both
        key to ``a__b__c``, so the second ``create_input_for`` call raises while the
        first port is already attached, mid-loop inside `create_cached_input` -- before
        it can return anything describing what it built.
        """
        wf = pwf.Workflow("collide")
        wf.a = pwf.node(nested_param)
        wf.a__b = pwf.node(plain_param)
        widget = PyironFlowWidget(
            wf=wf, log=widgets.Output(), out_widget=widgets.Output()
        )
        widget._port_cache["a__b__c"] = datamodel.PortCacheEntry(1.0)

        _captured(widget, lambda: widget.run_workflow(widget.wf))

        self.assertEqual([], list(widget.wf.inputs))
        self.assertEqual([], list(widget.wf.outputs))


class TestPullWorkflow(unittest.TestCase):
    """Widget-level coverage of ``pull_workflow``, agreeing with an equivalent run."""

    def test_pull_aborts_when_a_required_value_is_missing(self):
        wf = pwf.Workflow("pull_widget_missing")
        wf.n1 = pwf.node(relu)
        widget = PyironFlowWidget(
            wf=wf, log=widgets.Output(), out_widget=widgets.Output()
        )
        text = _captured(widget, lambda: widget.pull_workflow(widget.wf.nodes["n1"]))
        self.assertIn("n1.x", text)

    def test_pull_agrees_with_the_equivalent_run(self):
        wf = pwf.Workflow("pull_widget")
        wf.n1 = pwf.node(relu)
        wf.n2 = pwf.node(relu, x=-0.5)
        wf.acc = pwf.node(add, a=wf.n1.outputs.signal, b=wf.n2.outputs.signal)
        widget = PyironFlowWidget(
            wf=wf, log=widgets.Output(), out_widget=widgets.Output()
        )
        widget._port_cache["n1__x"] = datamodel.PortCacheEntry(1.0)
        widget._port_cache["n1__bias"] = datamodel.PortCacheEntry(0.25)

        run_text = _captured(widget, lambda: widget.run_workflow(widget.wf))
        self.assertIn("'acc__sum': 0.75", run_text)

        pull_text = _captured(
            widget, lambda: widget.pull_workflow(widget.wf.nodes["acc"])
        )
        self.assertIn("'sum': 0.75", pull_text)


if __name__ == "__main__":
    unittest.main()
