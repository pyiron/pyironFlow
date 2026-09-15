import contextlib
import io
import json
import unittest
import unittest.mock

import flowrep as fr
import ipywidgets as widgets
import pyiron_workflow as pwf
from pyiron_workflow.execution import RunStatus

from pyironflow import reactflow, wf_extensions


@fr.atomic("signal")
def relu(x: float, bias: float = 0.0) -> float:
    return max(0.0, x - bias)


@fr.atomic("out")
def boom(x: float) -> float:
    raise RuntimeError("boom")


def _quietly(fn):
    """Call *fn*, swallowing what GUI output and error reporting print."""
    with (
        contextlib.redirect_stdout(io.StringIO()),
        contextlib.redirect_stderr(io.StringIO()),
    ):
        return fn()


def _widget(wf: pwf.Workflow) -> reactflow.PyironFlowWidget:
    return reactflow.PyironFlowWidget(
        wf=wf, log=widgets.Output(), out_widget=widgets.Output()
    )


class TestNodeLabels(unittest.TestCase):
    def test_labels_of_workflow_nodes(self):
        wf = pwf.Workflow("labels")
        wf.n1 = pwf.node(relu)
        self.assertEqual(_widget(wf).node_labels(), {"n1"})

    def test_labels_include_nodes_only_drawn_in_the_gui(self):
        elsewhere = pwf.Workflow("elsewhere")
        elsewhere.from_gui = pwf.node(relu)
        widget = _widget(pwf.Workflow("labels"))
        widget.gui.nodes = json.dumps(wf_extensions.get_nodes(elsewhere))
        self.assertEqual(widget.node_labels(), {"from_gui"})


class TestAddNode(unittest.TestCase):
    def test_adds_places_and_draws(self):
        widget = _widget(pwf.Workflow("adding"))
        first = pwf.node(relu, "relu_0")
        second = pwf.node(relu, "relu_1")
        widget.add_node(first)
        widget.add_node(second)
        self.assertEqual(list(widget.wf.nodes), ["relu_0", "relu_1"])
        self.assertNotEqual(first.position, second.position)
        self.assertEqual(
            [d["id"] for d in json.loads(widget.gui.nodes)], ["relu_0", "relu_1"]
        )

    def test_works_without_a_log_widget(self):
        widget = _widget(pwf.Workflow("adding"))
        widget.log = None
        widget.add_node(pwf.node(relu, "relu_0"))
        self.assertEqual(list(widget.wf.nodes), ["relu_0"])


class TestPlaceNewNode(unittest.TestCase):
    def test_without_a_view_steps_down_and_cycles(self):
        widget = _widget(pwf.Workflow("placing"))
        positions = [widget.place_new_node() for _ in range(11)]
        self.assertEqual(positions, [(0, 50 * (i % 10)) for i in range(11)])

    def test_with_a_view_steps_by_a_small_fraction_of_its_height(self):
        widget = _widget(pwf.Workflow("placing"))
        widget.gui.view = json.dumps(
            {"x": -100, "y": -200, "width": 800, "height": 1000}
        )
        positions = [widget.place_new_node() for _ in range(11)]
        for i, (x, y) in enumerate(positions):
            with self.subTest(i=i):
                self.assertAlmostEqual(x, 200.0)
                self.assertAlmostEqual(y, 200.0 + 90.0 * (i % 10))

    def test_a_clash_after_a_full_cycle_shifts_sideways(self):
        widget = _widget(pwf.Workflow("placing"))
        for i in range(11):
            widget.add_node(pwf.node(relu, f"relu_{i}"))
        self.assertEqual(
            widget.wf.nodes["relu_10"].position, (wf_extensions.NODE_WIDTH + 10, 0)
        )


class TestLastRun(unittest.TestCase):
    def setUp(self):
        wf = pwf.Workflow("cached")
        wf.n1 = pwf.node(relu)  # x required
        self.widget = _widget(wf)

    def _run(self):
        _quietly(lambda: self.widget.run_workflow(self.widget.wf))

    def test_nothing_is_cached_before_a_run(self):
        self.assertIsNone(self.widget.last_run)
        self.assertFalse(self.widget.gui.has_run)

    def test_a_successful_run_is_cached(self):
        self.widget._port_cache["n1__x"] = 1.0
        self._run()
        self.assertEqual(RunStatus.FINISHED, self.widget.last_run.status)
        self.assertEqual(1.0, self.widget.last_run.outputs["n1__signal"])
        self.assertTrue(self.widget.gui.has_run)

    def test_a_failed_run_is_cached(self):
        self.widget.wf.n_boom = pwf.node(boom)
        self.widget._port_cache["n1__x"] = 1.0
        self.widget._port_cache["n_boom__x"] = 1.0
        self._run()
        self.assertEqual(RunStatus.FAILED, self.widget.last_run.status)
        self.assertIsNotNone(self.widget.last_run.exception)
        self.assertTrue(self.widget.gui.has_run)

    def test_a_pull_is_cached(self):
        self.widget._port_cache["n1__x"] = 1.0
        _quietly(lambda: self.widget.pull_workflow(self.widget.wf.nodes["n1"]))
        self.assertEqual(RunStatus.FINISHED, self.widget.last_run.status)
        self.assertEqual(1.0, self.widget.last_run.outputs["signal"])
        self.assertTrue(self.widget.gui.has_run)

    def test_missing_input_keeps_the_previous_run(self):
        self.widget._port_cache["n1__x"] = 1.0
        self._run()
        first = self.widget.last_run
        del self.widget._port_cache["n1__x"]
        self._run()
        self.assertIs(first, self.widget.last_run)
        self.assertTrue(self.widget.gui.has_run)

    def test_a_failure_before_any_run_exists_keeps_the_previous_run(self):
        self.widget._port_cache["n1__x"] = 1.0
        self._run()
        first = self.widget.last_run
        with unittest.mock.patch.object(
            pwf.Workflow, "run", side_effect=RuntimeError("early")
        ):
            self._run()
        self.assertIs(first, self.widget.last_run)
        self.assertTrue(self.widget.gui.has_run)

    def test_a_failure_before_any_run_exists_with_nothing_cached(self):
        self.widget._port_cache["n1__x"] = 1.0
        with unittest.mock.patch.object(
            pwf.Workflow, "run", side_effect=RuntimeError("early")
        ):
            self._run()
        self.assertIsNone(self.widget.last_run)
        self.assertFalse(self.widget.gui.has_run)


if __name__ == "__main__":
    unittest.main()
