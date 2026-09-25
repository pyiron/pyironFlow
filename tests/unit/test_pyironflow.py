import json
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

import flowrep as fr
import pyiron_workflow as pwf
from pyiron_workflow.constructors import macro2workflow

from pyironflow import PyironFlow
from pyironflow.wf_extensions import get_nodes


@fr.atomic("signal")
def relu(x: float, bias: float = 0.0) -> float:
    return max(0.0, x - bias)


@fr.atomic("sum")
def add(a: float, b: float) -> float:
    return a + b


class TestVersion(unittest.TestCase):
    def test_instance(self):
        wf = pwf.Workflow("minimal_demo")
        wf.n1 = pwf.node(relu, x=0.2)
        wf.n2 = pwf.node(relu, x=-0.5)
        wf.accumulate = pwf.node(
            add,
            a=wf.n1.outputs.signal,
            b=wf.n2.outputs.signal,
        )
        wf.n3 = pwf.node(relu, x=wf.accumulate.outputs.sum)

        pf = PyironFlow([wf])

        self.assertIsInstance(pf, PyironFlow)


@fr.workflow
def has_own_io(x):
    y = relu(x)
    return y


class TestWorkflowValidation(unittest.TestCase):
    def test_rejects_a_macro(self):
        macro = pwf.node(has_own_io)
        with self.assertRaises(TypeError) as caught:
            PyironFlow([macro])
        self.assertIn("macro2workflow", str(caught.exception))

    def test_rejects_a_workflow_with_its_own_io(self):
        wf = macro2workflow(pwf.node(has_own_io))
        with self.assertRaises(ValueError) as caught:
            PyironFlow([wf])
        message = str(caught.exception)
        self.assertIn("wf.remove_input('x')", message)
        self.assertIn("wf.remove_output('y')", message)

    def test_names_the_offending_entry(self):
        clean = pwf.Workflow("clean")
        wf = macro2workflow(pwf.node(has_own_io))
        with self.assertRaises(ValueError) as caught:
            PyironFlow([clean, wf])
        self.assertIn("wf_list[1]", str(caught.exception))

    def test_accepts_a_workflow_with_no_io(self):
        wf = pwf.Workflow("clean")
        wf.n1 = pwf.node(relu)
        self.assertIsInstance(PyironFlow([wf]), PyironFlow)

    def test_accepts_the_default_empty_list(self):
        self.assertIsInstance(PyironFlow(), PyironFlow)

    def test_rejects_a_workflow_with_only_input(self):
        wf = pwf.Workflow("only_in")
        wf.n1 = pwf.node(relu)
        wf.set_inputs_to_unconnected_child_input(build_for_defaults=True)
        input_label = next(iter(wf.inputs))
        with self.assertRaises(ValueError) as caught:
            PyironFlow([wf])
        message = str(caught.exception)
        self.assertIn(input_label, message)
        self.assertIn(f"wf.remove_input({input_label!r})", message)
        self.assertNotIn("output", message)

    def test_rejects_a_workflow_with_only_output(self):
        wf = pwf.Workflow("only_out")
        wf.n1 = pwf.node(relu, x=0.1)
        wf.set_outputs_to_unconnected_child_output()
        output_label = next(iter(wf.outputs))
        with self.assertRaises(ValueError) as caught:
            PyironFlow([wf])
        message = str(caught.exception)
        self.assertIn(output_label, message)
        self.assertIn(f"wf.remove_output({output_label!r})", message)
        self.assertNotIn("input", message)

    def test_rejects_something_that_is_neither_workflow_nor_macro(self):
        with self.assertRaises(TypeError) as caught:
            PyironFlow(["not a workflow"])
        message = str(caught.exception)
        self.assertIn("str", message)
        self.assertNotIn("macro2workflow", message)


class TestClose(unittest.TestCase):
    def test_close_releases_the_node_library_path(self):
        saved = list(sys.path)
        self.addCleanup(sys.path.__setitem__, slice(None), saved)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            flow = PyironFlow(root_path=str(root))
            self.assertIn(str(root), sys.path)
            flow.close()
            self.assertNotIn(str(root), sys.path)


def _with_node(label):
    wf = pwf.Workflow(label)
    wf.n1 = pwf.node(relu)
    return wf


class TestAddWorkflow(unittest.TestCase):
    def _flow(self, wf_list=None):
        flow = PyironFlow(wf_list)
        self.addCleanup(flow.close)
        return flow

    def test_appends_and_selects_a_new_tab(self):
        flow = self._flow([_with_node("first")])
        second = _with_node("second")
        widget = flow.add_workflow(second)
        self.assertEqual(2, len(flow.wf_widgets))
        self.assertEqual([flow.workflows[0], second], flow.workflows)
        self.assertEqual(1, flow.tab.selected_index)
        self.assertIs(widget, flow.active_widget)
        self.assertIs(widget.gui, flow.tab.children[1])
        self.assertEqual(("first", "second"), flow.tab.titles)

    def test_replaces_an_empty_active_tab(self):
        flow = self._flow()
        new = _with_node("new")
        widget = flow.add_workflow(new)
        self.assertEqual([widget], flow.wf_widgets)
        self.assertEqual([new], flow.workflows)
        self.assertEqual((widget.gui,), flow.tab.children)
        self.assertEqual(("new",), flow.tab.titles)
        self.assertEqual(0, flow.tab.selected_index)

    def test_a_node_drawn_only_in_the_gui_counts_as_not_empty(self):
        flow = self._flow()
        flow.active_widget.gui.nodes = json.dumps(get_nodes(_with_node("elsewhere")))
        flow.add_workflow(_with_node("new"))
        self.assertEqual(2, len(flow.wf_widgets))

    def test_the_new_widget_is_wired_like_the_first(self):
        flow = self._flow([_with_node("first")])
        widget = flow.add_workflow(_with_node("second"))
        self.assertIs(flow.accordion, widget.accordion_widget)
        self.assertIs(flow._tree_view, widget.tree_widget)
        self.assertIs(flow.out_log, widget.log)
        self.assertIs(flow.out_widget, widget.out_widget)

    def test_the_node_library_follows_the_selected_tab(self):
        flow = self._flow([_with_node("first")])
        widget = flow.add_workflow(_with_node("second"))
        self.assertIs(widget, flow._tree_view.flow_widget)
        flow.tab.selected_index = 0
        self.assertIs(flow.wf_widgets[0], flow._tree_view.flow_widget)

    def test_a_workflow_with_io_is_refused(self):
        flow = self._flow([_with_node("first")])
        wf = macro2workflow(pwf.node(has_own_io))
        with self.assertRaises(ValueError):
            flow.add_workflow(wf)
        self.assertEqual(1, len(flow.wf_widgets))


class _FlowCase(unittest.TestCase):
    def _flow(self, wf_list=None):
        flow = PyironFlow(wf_list)
        self.addCleanup(flow.close)
        return flow


class TestUniqueLabel(_FlowCase):
    def test_a_free_label_is_kept(self):
        self.assertEqual("new", self._flow([_with_node("first")]).unique_label("new"))

    def test_a_taken_label_gets_the_first_free_suffix(self):
        flow = self._flow([_with_node("first"), _with_node("first_1")])
        self.assertEqual("first_2", flow.unique_label("first"))


class TestRenameWorkflow(_FlowCase):
    def setUp(self):
        self.flow = self._flow([_with_node("first"), _with_node("second")])
        self.widget = self.flow.wf_widgets[1]

    def test_rename_updates_workflow_gui_and_tab(self):
        self.flow.rename_workflow(self.widget, "renamed")
        self.assertEqual("renamed", self.widget.wf.label)
        self.assertEqual("renamed", self.widget.gui.label)
        self.assertEqual(("first", "renamed"), self.flow.tab.titles)

    def test_the_same_name_changes_nothing(self):
        self.flow.rename_workflow(self.widget, "second")
        self.assertEqual(("first", "second"), self.flow.tab.titles)

    def test_an_invalid_name_is_refused(self):
        with self.assertRaises(ValueError) as caught:
            self.flow.rename_workflow(self.widget, "not valid")
        self.assertIn("not a valid workflow name", str(caught.exception))
        self.assertEqual("second", self.widget.wf.label)
        self.assertEqual(("first", "second"), self.flow.tab.titles)

    def test_another_tabs_name_is_refused(self):
        with self.assertRaises(ValueError) as caught:
            self.flow.rename_workflow(self.widget, "first")
        self.assertIn("already named", str(caught.exception))
        self.assertEqual("second", self.widget.gui.label)


class TestCloseWorkflow(_FlowCase):
    def _close(self, flow, widget):
        with unittest.mock.patch.object(
            widget.gui, "close", wraps=widget.gui.close
        ) as closed:
            flow.close_workflow(widget)
        closed.assert_called_once_with()

    def test_closing_a_middle_tab_selects_its_right_neighbour(self):
        flow = self._flow([_with_node(label) for label in ("a", "b", "c")])
        flow.tab.selected_index = 1
        middle = flow.wf_widgets[1]
        self._close(flow, middle)
        self.assertEqual(["a", "c"], [wf.label for wf in flow.workflows])
        self.assertNotIn(middle, flow.wf_widgets)
        self.assertEqual(("a", "c"), flow.tab.titles)
        self.assertEqual(1, flow.tab.selected_index)
        self.assertIs(flow.wf_widgets[1], flow._tree_view.flow_widget)

    def test_closing_the_last_tab_selects_the_new_last(self):
        flow = self._flow([_with_node(label) for label in ("a", "b")])
        flow.tab.selected_index = 1
        self._close(flow, flow.wf_widgets[1])
        self.assertEqual(("a",), flow.tab.titles)
        self.assertEqual(0, flow.tab.selected_index)
        self.assertIs(flow.wf_widgets[0], flow.active_widget)

    def test_closing_the_only_tab_leaves_a_fresh_empty_workflow(self):
        flow = self._flow([_with_node("only")])
        only = flow.wf_widgets[0]
        self._close(flow, only)
        (replacement,) = flow.wf_widgets
        self.assertIsNot(only, replacement)
        self.assertEqual("workflow", replacement.wf.label)
        self.assertEqual([], list(replacement.wf.nodes))
        self.assertEqual(("workflow",), flow.tab.titles)
        self.assertIs(flow, replacement.flow)
        self.assertIs(replacement, flow._tree_view.flow_widget)

    def test_widgets_know_their_flow(self):
        flow = self._flow([_with_node("first")])
        self.assertIs(flow, flow.wf_widgets[0].flow)


class TestAccordion(unittest.TestCase):
    def test_tabs_in_order(self):
        flow = PyironFlow()
        self.addCleanup(flow.close)
        self.assertEqual(
            ("Node Library", "Files", "Output", "Logging Info"), flow.accordion.titles
        )
        self.assertIs(flow.files_panel.gui, flow.accordion.children[1])


class TestSplitter(unittest.TestCase):
    def _flow(self, **kwargs) -> PyironFlow:
        flow = PyironFlow(**kwargs)
        self.addCleanup(flow.close)
        return flow

    def test_sits_between_the_accordion_and_the_tabs(self):
        flow = self._flow()
        self.assertEqual((flow.accordion, flow.splitter, flow.tab), flow.gui.children)

    def test_starts_at_the_requested_ratio(self):
        flow = self._flow(flow_widget_ratio=0.7)
        self.assertEqual(0.7, flow.splitter.ratio)
        self.assertEqual("30.0%", flow.accordion.layout.width)

    def test_the_requested_ratio_is_clamped(self):
        self.assertEqual(0.95, self._flow(flow_widget_ratio=2.0).splitter.ratio)
        self.assertEqual(0.05, self._flow(flow_widget_ratio=-1.0).splitter.ratio)

    def test_moving_the_splitter_resizes_the_accordion(self):
        flow = self._flow()
        flow.splitter.ratio = 0.6
        self.assertEqual("40.0%", flow.accordion.layout.width)

    def test_the_tabs_take_the_remaining_width(self):
        flow = self._flow()
        self.assertEqual("1 1 auto", flow.tab.layout.flex)
        self.assertEqual("0 0 auto", flow.accordion.layout.flex)
