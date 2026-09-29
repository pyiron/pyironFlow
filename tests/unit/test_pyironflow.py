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
from pyironflow.reactflow import AccordionTab
from pyironflow.wf_extensions import extract_locks, get_nodes


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
    def test_a_workflow_with_designed_io_is_wrapped_keeping_it(self):
        wf = macro2workflow(pwf.node(has_own_io))
        (wrapper,) = PyironFlow([wf]).workflows
        self.assertEqual("has_own_io", wrapper.label)
        child = wrapper.nodes["has_own_io"]
        self.assertIsNot(wf, child)
        self.assertEqual(["x"], list(child.inputs))
        self.assertEqual(["y"], list(child.outputs))
        self.assertIsNone(wf.owner)

    def test_accepts_a_workflow_with_no_io(self):
        wf = pwf.Workflow("clean")
        wf.n1 = pwf.node(relu)
        self.assertIsInstance(PyironFlow([wf]), PyironFlow)

    def test_accepts_the_default_empty_list(self):
        self.assertIsInstance(PyironFlow(), PyironFlow)

    def test_a_workflow_with_automatic_io_is_shown_directly_without_it(self):
        for build in (
            lambda wf: wf.set_io_to_unconnected_child_io(build_for_defaults=True),
            lambda wf: wf.set_inputs_to_unconnected_child_input(),
            lambda wf: wf.set_outputs_to_unconnected_child_output(),
        ):
            wf = _with_node("auto")
            build(wf)
            with self.subTest(io=(list(wf.inputs), list(wf.outputs))):
                io = (list(wf.inputs), list(wf.outputs))
                undo_depth = len(wf.undo_stack)
                (shown,) = PyironFlow([wf]).workflows
                self.assertIsNot(wf, shown)
                self.assertEqual(["n1"], list(shown.nodes))
                self.assertFalse(shown.inputs or shown.outputs)
                self.assertEqual(io, (list(wf.inputs), list(wf.outputs)))
                self.assertEqual(undo_depth, len(wf.undo_stack))

    def test_rejects_something_that_is_neither_node_nor_recipe(self):
        with self.assertRaises(TypeError) as caught:
            PyironFlow([pwf.Workflow("clean"), "not a workflow"])
        message = str(caught.exception)
        self.assertIn("wf_list[1]", message)
        self.assertIn("str", message)


class TestWrapping(unittest.TestCase):
    def _flow(self, wf_list):
        flow = PyironFlow(wf_list)
        self.addCleanup(flow.close)
        return flow

    def test_a_node_becomes_the_sole_child_of_a_workflow_named_for_it(self):
        node = pwf.node(relu, "rectifier", x=0.3)
        (wf,) = self._flow([node]).workflows
        self.assertIsInstance(wf, pwf.Workflow)
        self.assertEqual("rectifier", wf.label)
        self.assertIsNot(node, wf.nodes["rectifier"])
        self.assertIsNone(node.owner)
        self.assertEqual({"rectifier__x": 0.3}, extract_locks(wf))

    def test_a_macro_is_wrapped_rather_than_refused(self):
        macro = pwf.node(has_own_io, "macro")
        (wf,) = self._flow([macro]).workflows
        self.assertIsInstance(wf.nodes["macro"], type(macro))
        self.assertIsNot(macro, wf.nodes["macro"])

    def test_a_node_owned_elsewhere_is_copied_out_of_it(self):
        owner = pwf.Workflow("owner")
        owner.n1 = pwf.node(relu)
        (wf,) = self._flow([owner.n1]).workflows
        self.assertEqual(["n1"], list(wf.nodes))
        self.assertIs(owner, owner.n1.owner)

    def test_a_node_waiting_on_a_connection_is_refused(self):
        with self.assertRaises(ValueError):
            PyironFlow([pwf.node(relu, "r", x=pwf.node(relu, "source"))])

    def test_wrapper_labels_are_unique_among_the_tabs(self):
        flow = self._flow(
            [_with_node("relu"), pwf.node(relu, "relu"), pwf.node(relu, "relu")]
        )
        self.assertEqual(
            ["relu", "relu_1", "relu_2"], [wf.label for wf in flow.workflows]
        )

    def test_a_recipe_with_a_reference_becomes_a_child_named_for_it(self):
        (wf,) = self._flow([has_own_io.flowrep_recipe]).workflows
        self.assertEqual("has_own_io", wf.label)
        self.assertEqual(["has_own_io"], list(wf.nodes))

    def test_a_workflow_recipe_without_a_reference_is_opened_directly(self):
        source = pwf.Workflow("source")
        source.n1 = pwf.node(relu, x=0.1)
        (wf,) = self._flow([source.recipe]).workflows
        self.assertEqual("workflow", wf.label)
        self.assertIn("n1", wf.nodes)
        self.assertFalse(wf.inputs or wf.outputs)

    def test_add_workflow_wraps_a_node_under_a_free_label(self):
        flow = self._flow([_with_node("relu")])
        widget = flow.add_workflow(pwf.node(relu, "relu"))
        self.assertEqual("relu_1", widget.wf.label)
        self.assertEqual(["relu", "relu_1"], [wf.label for wf in flow.workflows])


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
        self.assertEqual([flow.workflows[0], widget.wf], flow.workflows)
        self.assertEqual(1, flow.tab.selected_index)
        self.assertIs(widget, flow.active_widget)
        self.assertIs(widget.gui, flow.tab.children[1])
        self.assertEqual(("first", "second"), flow.tab.titles)

    def test_replaces_an_empty_active_tab(self):
        flow = self._flow()
        new = _with_node("new")
        widget = flow.add_workflow(new)
        self.assertEqual([widget], flow.wf_widgets)
        self.assertEqual([widget.wf], flow.workflows)
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

    def test_something_that_is_neither_node_nor_recipe_is_refused(self):
        flow = self._flow([_with_node("first")])
        with self.assertRaises(TypeError) as caught:
            flow.add_workflow("not a workflow")
        self.assertIn("the item is a str", str(caught.exception))
        self.assertEqual(1, len(flow.wf_widgets))

    def test_a_workflow_with_designed_io_is_wrapped_under_a_free_label(self):
        flow = self._flow([_with_node("has_own_io")])
        wf = macro2workflow(pwf.node(has_own_io))
        widget = flow.add_workflow(wf)
        self.assertEqual("has_own_io_1", widget.wf.label)
        self.assertIsNot(wf, widget.wf.nodes["has_own_io"])
        self.assertEqual(["x"], list(widget.wf.nodes["has_own_io"].inputs))


class _FlowCase(unittest.TestCase):
    def _flow(self, wf_list=None):
        flow = PyironFlow(wf_list)
        self.addCleanup(flow.close)
        return flow


class TestGetWorkflow(_FlowCase):
    def test_returns_the_selected_tab_synced_from_the_browser(self):
        flow = self._flow([_with_node("first"), pwf.Workflow("second")])
        flow.tab.selected_index = 1
        flow.active_widget.gui.nodes = json.dumps(get_nodes(_with_node("drawn")))
        wf = flow.get_workflow()
        self.assertIs(flow.workflows[1], wf)
        self.assertEqual(["n1"], list(wf.nodes))


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
            ("Node Library", "Files", "Global Output", "Node Info", "Logging Info"),
            flow.accordion.titles,
        )
        self.assertIs(flow.files_panel.gui, flow.accordion.children[1])
        self.assertIs(flow.out_widget, flow.accordion.children[2])
        self.assertIs(flow.node_info.gui, flow.accordion.children[3])
        self.assertIs(flow.out_log, flow.accordion.children[4])


class TestNodeInfoSelection(_FlowCase):
    def setUp(self):
        self.flow = self._flow([_with_node("first"), _with_node("second")])
        self.widget = self.flow.wf_widgets[0]
        self.widget.wf.n2 = pwf.node(relu)
        self.widget.update()

    def _select(self, *labels, widget=None):
        widget = self.widget if widget is None else widget
        widget.gui.selected_nodes = json.dumps(
            [n for n in get_nodes(widget.wf) if n["id"] in labels]
        )

    def _open(self):
        self.flow.accordion.selected_index = AccordionTab.NODE_INFO.index

    @property
    def _header(self):
        return self.flow.node_info.header.value

    def test_one_node_selected_while_open_is_shown(self):
        self._open()
        self._select("n1")
        self.assertEqual("n1", self._header)
        self.assertNotEqual((), self.flow.node_info.output.outputs)

    def test_changing_the_single_selection_follows_it(self):
        self._open()
        self._select("n1")
        self._select("n2")
        self.assertEqual("n2", self._header)

    def test_selection_while_closed_builds_nothing(self):
        self._select("n1")
        self.assertEqual("", self._header)
        self.assertEqual((), self.flow.node_info.output.outputs)

    def test_opening_builds_the_selected_node(self):
        self._select("n1")
        self._open()
        self.assertEqual("n1", self._header)

    def test_opening_without_a_target_stays_empty(self):
        self._open()
        self.assertEqual("", self._header)

    def test_zero_or_many_selected_clears(self):
        self._open()
        for labels in ((), ("n1", "n2")):
            with self.subTest(labels=labels):
                self._select("n1")
                self._select(*labels)
                self.assertEqual("", self._header)
                self.assertEqual((), self.flow.node_info.output.outputs)

    def test_selection_does_not_move_focus(self):
        self.flow.accordion.selected_index = AccordionTab.FILES.index
        self._select("n1")
        self.assertEqual(AccordionTab.FILES.index, self.flow.accordion.selected_index)

    def test_selection_does_not_touch_the_sections(self):
        self.flow.node_info.source_section.selected_index = None
        self._open()
        self._select("n1")
        self.assertIsNone(self.flow.node_info.source_section.selected_index)

    def test_selection_on_an_inactive_tab_is_ignored(self):
        self._open()
        self._select("n1", widget=self.flow.wf_widgets[1])
        self.assertEqual("", self._header)
        self.assertIsNone(self.flow._node_info_target)

    def test_switching_tabs_clears_and_forgets(self):
        self._open()
        self._select("n1")
        self.flow.tab.selected_index = 1
        self.assertEqual("", self._header)
        self.flow.tab.selected_index = 0
        self.assertEqual("", self._header)

    def test_an_unknown_label_is_no_target(self):
        self._open()
        self.widget.gui.selected_nodes = json.dumps([{"id": "ghost"}])
        self.assertEqual("", self._header)

    def test_node_deleted_clears_its_own_target(self):
        self._open()
        self._select("n1")
        self.flow.node_deleted(self.widget, "n2")
        self.assertEqual("n1", self._header)
        self.flow.node_deleted(self.widget, "n1")
        self.assertEqual("", self._header)
        self.assertIsNone(self.flow._node_info_target)

    def _rename(self, old, new):
        self.widget.gui.commands = f"rename_node: {old} @ now as {new}"

    def test_renaming_the_target_follows_it(self):
        self._open()
        self._select("n1")
        self._rename("n1", "first_node")
        self.assertEqual("first_node", self._header)
        self.assertEqual((self.widget, "first_node"), self.flow._node_info_target)

    def test_renaming_another_node_leaves_the_target(self):
        self._open()
        self._select("n1")
        self._rename("n2", "second_node")
        self.assertEqual("n1", self._header)

    def test_grouping_the_target_clears_it(self):
        self._open()
        self._select("n1", "n2")
        self.flow.show_node_info(self.widget, "n1", source=False)
        self.widget.gui.commands = "group executed @ now as pair"
        self.assertEqual("", self._header)
        self.assertIsNone(self.flow._node_info_target)

    def test_ungrouping_the_target_clears_it(self):
        self.widget.wf.g = pwf.Workflow("g")
        self.widget.wf.g.a = pwf.node(relu)
        self.widget.wf.g.set_io_to_unconnected_child_io()
        self.widget.update()
        self._open()
        self._select("g")
        self.widget.gui.commands = "ungroup_node: g @ now"
        self.assertEqual("", self._header)
        self.assertIsNone(self.flow._node_info_target)

    def test_a_target_deleted_behind_its_back_clears_on_refresh(self):
        self._open()
        self._select("n1")
        self.widget.wf.remove_node("n1")
        self.flow._refresh_node_info()
        self.assertEqual("", self._header)
        self.assertIsNone(self.flow._node_info_target)


class TestShowNodeInfo(_FlowCase):
    def setUp(self):
        self.flow = self._flow([_with_node("first")])
        self.widget = self.flow.wf_widgets[0]

    def test_focuses_node_info_and_builds(self):
        self.flow.show_node_info(self.widget, "n1", source=True)
        self.assertEqual(
            AccordionTab.NODE_INFO.index, self.flow.accordion.selected_index
        )
        self.assertEqual("n1", self.flow.node_info.header.value)
        self.assertEqual(0, self.flow.node_info.output_section.selected_index)
        self.assertEqual(0, self.flow.node_info.source_section.selected_index)

    def test_source_false_leaves_source_alone(self):
        self.flow.show_node_info(self.widget, "n1", source=False)
        self.assertIsNone(self.flow.node_info.source_section.selected_index)

    def test_info_while_node_info_is_open_rebuilds(self):
        self.flow.show_node_info(self.widget, "n1", source=True)
        with unittest.mock.patch.object(
            self.flow.node_info, "show", wraps=self.flow.node_info.show
        ) as shown:
            self.flow.show_node_info(self.widget, "n1", source=True)
        shown.assert_called_once_with(self.widget, "n1")


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
