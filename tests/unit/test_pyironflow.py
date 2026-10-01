import json
import sys
import tempfile
import types
import unittest
import unittest.mock
from pathlib import Path

import flowrep as fr
import pyiron_workflow as pwf
from pyiron_workflow.constructors import macro2workflow

from pyironflow import PyironFlow, executors, executors_lib, node_info, pyironflow_std
from pyironflow import pyironflow as pyironflow_module
from pyironflow.reactflow import AccordionTab
from pyironflow.wf_extensions import extract_locks, get_nodes
from tests.unit.executor_fixtures import clashing_creators, extra_creators


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
            flow = PyironFlow(library_roots=str(root))
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
            (
                "Node Library",
                "Files",
                "Global Output",
                "Node Info",
                "Executors",
                "Logging Info",
            ),
            flow.accordion.titles,
        )
        self.assertIs(flow.files_panel.gui, flow.accordion.children[1])
        self.assertIs(flow.out_widget, flow.accordion.children[2])
        self.assertIs(flow.node_info.gui, flow.accordion.children[3])
        self.assertIs(flow.executors_panel.gui, flow.accordion.children[4])
        self.assertIs(flow.out_log, flow.accordion.children[5])


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
        self.assertNotEqual((), self.flow.node_info.last_output.outputs)

    def test_changing_the_single_selection_follows_it(self):
        self._open()
        self._select("n1")
        self._select("n2")
        self.assertEqual("n2", self._header)

    def test_selection_while_closed_builds_nothing(self):
        self._select("n1")
        self.assertEqual("", self._header)
        self.assertEqual((), self.flow.node_info.last_output.outputs)

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
                self.assertEqual((), self.flow.node_info.last_output.outputs)

    def test_selection_does_not_move_focus(self):
        self.flow.accordion.selected_index = AccordionTab.FILES.index
        self._select("n1")
        self.assertEqual(AccordionTab.FILES.index, self.flow.accordion.selected_index)

    def test_selection_does_not_touch_the_sections(self):
        self.flow.node_info.source_section.selected_index = None
        self.flow.node_info.last_input_section.selected_index = 0
        self._open()
        self._select("n1")
        self.assertIsNone(self.flow.node_info.source_section.selected_index)
        self.assertEqual(0, self.flow.node_info.last_input_section.selected_index)

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
        self.flow.show_node_info(self.widget, "n1", last_input=False, source=False)
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
        self.flow.show_node_info(self.widget, "n1", last_input=True, source=True)
        self.assertEqual(
            AccordionTab.NODE_INFO.index, self.flow.accordion.selected_index
        )
        self.assertEqual("n1", self.flow.node_info.header.value)
        self.assertEqual(0, self.flow.node_info.last_input_section.selected_index)
        self.assertEqual(0, self.flow.node_info.last_output_section.selected_index)
        self.assertEqual(0, self.flow.node_info.source_section.selected_index)

    def test_false_flags_leave_their_sections_alone(self):
        self.flow.show_node_info(self.widget, "n1", last_input=False, source=False)
        self.assertIsNone(self.flow.node_info.last_input_section.selected_index)
        self.assertIsNone(self.flow.node_info.source_section.selected_index)
        self.assertEqual(0, self.flow.node_info.last_output_section.selected_index)

    def test_info_while_node_info_is_open_rebuilds(self):
        self.flow.show_node_info(self.widget, "n1", last_input=True, source=True)
        with unittest.mock.patch.object(
            self.flow.node_info, "show", wraps=self.flow.node_info.show
        ) as shown:
            self.flow.show_node_info(self.widget, "n1", last_input=True, source=True)
        shown.assert_called_once_with(self.widget, "n1", [], None)


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


class TestLibraryPaths(unittest.TestCase):
    def test_none_is_no_roots(self):
        self.assertEqual(pyironflow_module._as_library_paths(None), [])

    def test_str_is_one_path(self):
        self.assertEqual(
            pyironflow_module._as_library_paths("some/dir"), [Path("some/dir")]
        )

    def test_pathlike_is_one_path(self):
        self.assertEqual(
            pyironflow_module._as_library_paths(Path("a.py")), [Path("a.py")]
        )

    def test_package_module_is_its_directory(self):
        self.assertEqual(
            pyironflow_module._as_library_paths(fr),
            [Path(fr.__file__).parent],
        )

    def test_plain_module_is_its_file(self):
        self.assertEqual(
            pyironflow_module._as_library_paths(pyironflow_std),
            [Path(pyironflow_std.__file__)],
        )

    def test_mixed_iterable_keeps_order(self):
        self.assertEqual(
            pyironflow_module._as_library_paths(["x", Path("y.py"), pyironflow_std]),
            [Path("x"), Path("y.py"), Path(pyironflow_std.__file__)],
        )

    def test_generator_of_roots(self):
        self.assertEqual(
            pyironflow_module._as_library_paths(p for p in ["x", "y"]),
            [Path("x"), Path("y")],
        )

    def test_rejected_values(self):
        for bad in (3, [["nested"]], [3], types.ModuleType("no_file")):
            with self.subTest(bad=bad), self.assertRaises(TypeError):
                pyironflow_module._as_library_paths(bad)


class TestLibraryRoots(unittest.TestCase):
    STD = [Path(fr.std.__file__), Path(pyironflow_std.__file__)]

    def _roots(self, **kwargs) -> list[Path]:
        flow = PyironFlow(**kwargs)
        self.addCleanup(flow.close)
        return flow._tree_view.roots

    def test_standard_roots_come_first(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(
                self._roots(library_roots=[tmp, pyironflow_std]),
                [*self.STD, Path(tmp), Path(pyironflow_std.__file__)],
            )

    def test_default_is_the_working_directory(self):
        self.assertEqual(self._roots(), [*self.STD, Path(".")])

    def test_none_leaves_only_the_standard_roots(self):
        self.assertEqual(self._roots(library_roots=None), self.STD)

    def test_root_path_is_a_deprecated_alias(self):
        with self.assertWarns(DeprecationWarning):
            roots = self._roots(root_path=None)
        self.assertEqual(roots, self.STD)

    def test_root_path_and_library_roots_together_raise(self):
        with self.assertRaises(TypeError):
            PyironFlow(library_roots=None, root_path=None)


def _two_node_flow(**kwargs) -> PyironFlow:
    wf = pwf.Workflow("wf")
    wf.n1 = pwf.node(relu)
    wf.n2 = pwf.node(relu)
    return PyironFlow([wf], library_roots=None, **kwargs)


def _focus(flow: PyironFlow, label: str) -> None:
    flow.show_node_info(flow.active_widget, label, last_input=False, source=False)


class TestExecutorCreatorsKwarg(unittest.TestCase):
    def test_the_library_is_always_first(self):
        library = list(executors.find_creators([executors_lib]))
        for given, extra in [
            (None, []),
            (extra_creators, ["tagged_thread_pool"]),
            ([extra_creators], ["tagged_thread_pool"]),
        ]:
            with self.subTest(given=given):
                flow = _two_node_flow(executor_creators=given)
                self.addCleanup(flow.close)
                self.assertEqual([*library, *extra], list(flow.executors.creators))
                self.assertEqual(
                    [*library, *extra], list(flow.executors_panel.creator.options)
                )

    def test_a_clash_fails_construction(self):
        with self.assertRaisesRegex(ValueError, "defined by both"):
            _two_node_flow(executor_creators=clashing_creators)

    def test_widgets_share_the_registry(self):
        flow = _two_node_flow()
        self.addCleanup(flow.close)
        self.assertIs(flow.executors, flow.active_widget.executors)
        added = flow.add_workflow(pwf.Workflow("other"))
        self.assertIs(flow.executors, added.executors)


class TestExternalExecutors(unittest.TestCase):
    def test_adopted_on_construction_and_add_workflow(self):
        wf = pwf.Workflow("wf")
        wf.n1 = pwf.node(relu)
        first = executors_lib.thread_pool_executor_instructions()
        wf.n1.executor = first
        flow = PyironFlow([wf], library_roots=None)
        self.addCleanup(flow.close)
        self.assertEqual("external_0", flow.executors.name_of(first))
        other = pwf.Workflow("other")
        other.m = pwf.node(relu)
        second = executors_lib.thread_pool_executor_instructions()
        other.m.executor = second
        flow.add_workflow(other)
        self.assertEqual("external_1", flow.executors.name_of(second))
        self.assertEqual(
            ("external_0", "external_1"), flow.executors_panel.browse.options
        )


class TestNodeInfoExecutor(unittest.TestCase):
    def setUp(self):
        self.flow = _two_node_flow()
        self.addCleanup(self.flow.close)
        self.made = self.flow.executors.create(
            "made", "thread_pool_executor_instructions", {}
        )
        self.flow.executors_panel.refresh()
        _focus(self.flow, "n1")
        self.dropdown = self.flow.node_info.executor

    def _node(self, label):
        return self.flow.active_widget.wf.nodes[label]

    def _create_from_panel(self, name="fresh"):
        panel = self.flow.executors_panel
        panel.creator.value = "thread_pool_executor_instructions"
        panel.name.value = name
        # A click handler's exception is only logged, so a logged warning is a failure
        with self.assertNoLogs(level="WARNING"):
            panel.create_button.click()
        return self.flow.executors.created[name]

    def test_the_dropdown_offers_the_registry(self):
        self.assertEqual(
            (node_info.NO_EXECUTOR, "made", node_info.CREATE_NEW),
            self.dropdown.options,
        )
        self.assertEqual(node_info.NO_EXECUTOR, self.dropdown.value)

    def test_the_dropdown_shows_the_nodes_executor(self):
        self._node("n2").executor = self.made.value
        _focus(self.flow, "n2")
        self.assertEqual("made", self.dropdown.value)

    def test_choosing_sets_and_clears_the_executor(self):
        self.dropdown.value = "made"
        self.assertIs(self.made.value, self._node("n1").executor)
        self.dropdown.value = node_info.NO_EXECUTOR
        self.assertIsNone(self._node("n1").executor)

    def test_create_new_redirects_to_executors(self):
        self.dropdown.value = node_info.CREATE_NEW
        self.assertEqual(node_info.NO_EXECUTOR, self.dropdown.value)
        self.assertEqual(
            AccordionTab.EXECUTORS.index, self.flow.accordion.selected_index
        )
        self.assertEqual(0, self.flow.executors_panel.create_section.selected_index)

    def test_create_applies_to_the_pending_node_and_returns(self):
        self.dropdown.value = node_info.CREATE_NEW
        fresh = self._create_from_panel()
        self.assertIs(fresh.value, self._node("n1").executor)
        self.assertEqual(
            AccordionTab.NODE_INFO.index, self.flow.accordion.selected_index
        )
        self.assertEqual("n1", self.flow.node_info.header.value)
        self.assertEqual("fresh", self.dropdown.value)

    def test_the_pending_node_is_used_once(self):
        self.dropdown.value = node_info.CREATE_NEW
        self._create_from_panel("first")
        self.flow.accordion.selected_index = AccordionTab.EXECUTORS.index
        self._create_from_panel("second")
        self.assertIs(
            self.flow.executors.created["first"].value, self._node("n1").executor
        )

    def test_create_without_a_pending_node_stays_put(self):
        self.flow.accordion.selected_index = AccordionTab.EXECUTORS.index
        self._create_from_panel()
        self.assertIsNone(self._node("n1").executor)
        self.assertEqual(
            AccordionTab.EXECUTORS.index, self.flow.accordion.selected_index
        )

    def test_a_new_executor_is_offered_in_node_info(self):
        self._create_from_panel()
        self.flow.accordion.selected_index = AccordionTab.NODE_INFO.index
        self.assertIn("fresh", self.dropdown.options)

    def test_the_pending_node_is_dropped_when_the_target_changes(self):
        self.dropdown.value = node_info.CREATE_NEW
        _focus(self.flow, "n2")
        self._create_from_panel()
        self.assertIsNone(self._node("n1").executor)
        self.assertIsNone(self._node("n2").executor)

    def test_the_pending_node_is_dropped_when_the_tab_changes(self):
        self.dropdown.value = node_info.CREATE_NEW
        self.flow.add_workflow(pwf.Workflow("other"))
        self.flow.tab.selected_index = 0
        self._create_from_panel()
        self.assertIsNone(self._node("n1").executor)

    def test_the_pending_node_follows_a_rename(self):
        self.dropdown.value = node_info.CREATE_NEW
        self.flow.active_widget.rename_node("n1", "renamed")
        fresh = self._create_from_panel()
        self.assertIs(fresh.value, self._node("renamed").executor)

    def test_create_after_the_target_was_deleted_applies_nowhere(self):
        self.dropdown.value = node_info.CREATE_NEW
        widget = self.flow.active_widget
        widget.wf.remove_node("n1")
        self.flow.node_deleted(widget, "n1")
        self._create_from_panel()
        self.assertIn("fresh", self.flow.executors.created)
        self.assertIsNone(self._node("n2").executor)

    def test_create_after_the_node_vanished_unannounced_applies_nowhere(self):
        self.dropdown.value = node_info.CREATE_NEW
        self.flow.active_widget.wf.remove_node("n1")
        self._create_from_panel()
        self.assertIn("fresh", self.flow.executors.created)

    def test_choosing_without_a_target_does_nothing(self):
        self.flow._node_info_target = None
        self.flow._on_executor_chosen("made")
        self.assertIsNone(self._node("n1").executor)

    def test_delete_clears_the_node_and_the_dropdown(self):
        self.dropdown.value = "made"
        panel = self.flow.executors_panel
        panel.browse.value = "made"
        panel.delete_button.click()
        panel.delete_button.click()
        self.assertIsNone(self._node("n1").executor)
        self.assertEqual({}, self.flow.executors.created)
        self.flow.accordion.selected_index = AccordionTab.NODE_INFO.index
        self.assertEqual(node_info.NO_EXECUTOR, self.dropdown.value)
        self.assertNotIn("made", self.dropdown.options)


class TestCloseShutsExecutorsDown(unittest.TestCase):
    def test_close(self):
        flow = _two_node_flow()
        made = flow.executors.create("t", "thread_pool_executor", {})
        flow.close()
        self.assertEqual({}, flow.executors.created)
        with self.assertRaises(RuntimeError):
            made.value.submit(int)
