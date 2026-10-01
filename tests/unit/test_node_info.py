import re
import unittest

import flowrep as fr
import ipywidgets as widgets
import pyiron_workflow as pwf
from pyiron_workflow.execution import RunStatus

from pyironflow import node_info, reactflow

QUERIED = re.compile(r"^Queried @ \d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\n$")


@fr.atomic("signal")
def relu(x: float, bias: float = 0.0) -> float:
    return max(0.0, x - bias)


@fr.atomic("out")
def boom(x: float) -> float:
    raise RuntimeError("boom")


def _texts(out: widgets.Output) -> list[str]:
    return [
        o["text"] if o["output_type"] == "stream" else o["data"]["text/plain"]
        for o in out.outputs
    ]


class TestNodeInfoPanel(unittest.TestCase):
    def setUp(self):
        wf = pwf.Workflow("info")
        wf.n1 = pwf.node(relu)
        self.widget = reactflow.PyironFlowWidget(
            wf=wf, log=widgets.Output(), out_widget=widgets.Output()
        )
        self.panel = node_info.NodeInfoPanel()

    def test_starts_empty_and_collapsed(self):
        self.assertEqual("", self.panel.header.value)
        self.assertEqual("", self.panel.status.value)
        self.assertEqual((), self.panel.last_input.outputs)
        self.assertEqual((), self.panel.last_output.outputs)
        self.assertEqual((), self.panel.source.outputs)
        self.assertIsNone(self.panel.last_input_section.selected_index)
        self.assertIsNone(self.panel.last_output_section.selected_index)
        self.assertIsNone(self.panel.source_section.selected_index)

    def test_stacks_header_last_input_last_output_and_source(self):
        self.assertEqual(
            (
                self.panel.title,
                self.panel.executor_row,
                self.panel.last_input_section,
                self.panel.last_output_section,
                self.panel.source_section,
            ),
            self.panel.gui.children,
        )
        self.assertEqual(
            (self.panel.status, self.panel.header), self.panel.title.children
        )
        self.assertEqual(("Last Input",), self.panel.last_input_section.titles)
        self.assertEqual(("Last Output",), self.panel.last_output_section.titles)
        self.assertEqual(("Source",), self.panel.source_section.titles)
        self.assertIn("node-info-header", self.panel.header._dom_classes)

    def test_show_before_any_run(self):
        self.panel.show(self.widget, "n1")
        self.assertEqual("n1", self.panel.header.value)
        queried, *rest = _texts(self.panel.last_output)
        self.assertRegex(queried, QUERIED)
        self.assertEqual(["n1 has not been run yet.\n"], rest)
        queried, *rest = _texts(self.panel.last_input)
        self.assertRegex(queried, QUERIED)
        self.assertEqual(["n1 has not been run yet.\n"], rest)

    def test_show_after_a_run(self):
        self.widget._port_cache["n1__x"] = 3.0
        self.widget.run_workflow(self.widget.wf)
        self.panel.show(self.widget, "n1")
        self.assertEqual("3.0", _texts(self.panel.last_output)[-1])
        queried, *shown = _texts(self.panel.last_input)
        self.assertRegex(queried, QUERIED)
        # Headers then values, per port; the untyped bias shows the default it ran on
        self.assertEqual(["3.0", "0.0"], shown[1::2])
        self.assertIn("x:", str(self.panel.last_input.outputs))
        self.assertIn("bias:", str(self.panel.last_input.outputs))

    def test_show_a_node_outside_the_last_run(self):
        self.widget.wf.n2 = pwf.node(relu, x=self.widget.wf.n1.outputs.signal)
        self.widget._port_cache["n1__x"] = 3.0
        self.widget.pull_workflow(self.widget.wf.nodes["n1"])
        self.panel.show(self.widget, "n2")
        self.assertEqual(
            "n2 was not part of the last run.\n", _texts(self.panel.last_output)[-1]
        )
        self.assertEqual(
            "n2 was not part of the last run.\n", _texts(self.panel.last_input)[-1]
        )

    def test_show_the_source(self):
        self.panel.show(self.widget, "n1")
        queried, source = _texts(self.panel.source)
        self.assertRegex(queried, QUERIED)
        self.assertIn("relu", source)

    def test_show_never_touches_global_output(self):
        self.panel.show(self.widget, "n1")
        self.assertEqual((), self.widget.out_widget.outputs)

    def test_show_replaces_what_was_there(self):
        self.panel.show(self.widget, "n1")
        self.panel.show(self.widget, "n1")
        self.assertEqual(2, len(self.panel.last_input.outputs))
        self.assertEqual(2, len(self.panel.last_output.outputs))
        self.assertEqual(2, len(self.panel.source.outputs))

    def test_clear(self):
        self.panel.show(self.widget, "n1")
        self.panel.clear()
        self.assertEqual("", self.panel.header.value)
        self.assertEqual((), self.panel.last_input.outputs)
        self.assertEqual((), self.panel.last_output.outputs)
        self.assertEqual((), self.panel.source.outputs)

    def test_expand_opens_only_what_is_flagged(self):
        self.panel.expand(last_input=False, last_output=True, source=False)
        self.assertIsNone(self.panel.last_input_section.selected_index)
        self.assertEqual(0, self.panel.last_output_section.selected_index)
        self.assertIsNone(self.panel.source_section.selected_index)
        self.panel.expand(last_input=True, last_output=False, source=False)
        self.assertEqual(0, self.panel.last_input_section.selected_index)

    def test_expand_leaves_unflagged_sections_as_the_user_set_them(self):
        self.panel.source_section.selected_index = 0
        self.panel.last_input_section.selected_index = 0
        self.panel.last_output_section.selected_index = None
        self.panel.expand(last_input=False, last_output=False, source=False)
        self.assertEqual(0, self.panel.last_input_section.selected_index)
        self.assertIsNone(self.panel.last_output_section.selected_index)
        self.assertEqual(0, self.panel.source_section.selected_index)


class TestNodeInfoStatus(unittest.TestCase):
    def setUp(self):
        wf = pwf.Workflow("info")
        wf.n1 = pwf.node(relu)
        wf.n2 = pwf.node(relu)
        self.widget = reactflow.PyironFlowWidget(
            wf=wf, log=widgets.Output(), out_widget=widgets.Output()
        )
        self.widget._port_cache["n1__x"] = 1.0
        self.panel = node_info.NodeInfoPanel()

    def _pull(self, label):
        self.widget.pull_workflow(self.widget.wf.nodes[label])

    def test_a_node_never_run_is_white(self):
        self.panel.show(self.widget, "n1")
        self.assertEqual(node_info.NOT_RUN, self.panel.status.value)

    def test_a_finished_node_is_green(self):
        self._pull("n1")
        self.panel.show(self.widget, "n1")
        self.assertEqual("🟩", self.panel.status.value)

    def test_a_node_outside_the_latest_pull_is_white(self):
        self._pull("n1")
        self.panel.show(self.widget, "n2")
        self.assertEqual(node_info.NOT_RUN, self.panel.status.value)

    def test_a_failed_node_is_red(self):
        self.widget.wf.n_boom = pwf.node(boom)
        self.widget._port_cache["n_boom__x"] = 1.0
        with self.assertRaises(RuntimeError):
            self._pull("n_boom")
        self.panel.show(self.widget, "n_boom")
        self.assertEqual("🟥", self.panel.status.value)

    def test_the_status_is_a_snapshot(self):
        self.panel.show(self.widget, "n1")
        self._pull("n1")
        self.assertEqual(node_info.NOT_RUN, self.panel.status.value)

    def test_clear_blanks_the_status(self):
        self.panel.show(self.widget, "n1")
        self.panel.clear()
        self.assertEqual("", self.panel.status.value)

    def test_running_has_a_symbol(self):
        self.assertEqual("🟨", node_info.STATUS_SYMBOLS[RunStatus.RUNNING])


class TestExecutorDropdown(unittest.TestCase):
    def setUp(self):
        self.chosen = []
        self.panel = node_info.NodeInfoPanel(on_executor_chosen=self.chosen.append)
        wf = pwf.Workflow("info")
        wf.n1 = pwf.node(relu)
        self.widget = reactflow.PyironFlowWidget(
            wf=wf, log=widgets.Output(), out_widget=widgets.Output()
        )

    def test_labelled_in_the_header(self):
        label, dropdown = self.panel.executor_row.children
        self.assertEqual(node_info.EXECUTOR_LABEL, label.value)
        self.assertIs(self.panel.executor, dropdown)

    def test_cleared_it_is_disabled_and_empty(self):
        self.assertTrue(self.panel.executor.disabled)
        self.assertEqual((), self.panel.executor.options)

    def test_show_lists_none_names_and_create_new(self):
        self.panel.show(self.widget, "n1", ["a", "b"], "b")
        self.assertFalse(self.panel.executor.disabled)
        self.assertEqual(
            (node_info.NO_EXECUTOR, "a", "b", node_info.CREATE_NEW),
            self.panel.executor.options,
        )
        self.assertEqual("b", self.panel.executor.value)
        self.assertEqual([], self.chosen)  # showing is not choosing

    def test_show_without_an_executor_selects_none(self):
        self.panel.show(self.widget, "n1", ["a"], None)
        self.assertEqual(node_info.NO_EXECUTOR, self.panel.executor.value)

    def test_show_defaults_to_no_executors(self):
        self.panel.show(self.widget, "n1")
        self.assertEqual(
            (node_info.NO_EXECUTOR, node_info.CREATE_NEW), self.panel.executor.options
        )
        self.assertEqual(node_info.NO_EXECUTOR, self.panel.executor.value)

    def test_a_user_choice_is_reported(self):
        self.panel.show(self.widget, "n1", ["a"], None)
        self.panel.executor.value = "a"
        self.panel.executor.value = node_info.NO_EXECUTOR
        self.assertEqual(["a", node_info.NO_EXECUTOR], self.chosen)

    def test_revert_restores_the_last_real_choice_quietly(self):
        self.panel.show(self.widget, "n1", ["a", "b"], "a")
        self.panel.executor.value = "b"
        self.panel.executor.value = node_info.CREATE_NEW
        self.panel.revert()
        self.assertEqual("b", self.panel.executor.value)
        self.assertEqual(["b", node_info.CREATE_NEW], self.chosen)

    def test_revert_straight_after_show_restores_what_was_shown(self):
        self.panel.show(self.widget, "n1", ["a"], "a")
        self.panel.executor.value = node_info.CREATE_NEW
        self.panel.revert()
        self.assertEqual("a", self.panel.executor.value)

    def test_clear_disables_it_again(self):
        self.panel.show(self.widget, "n1", ["a"], "a")
        self.panel.clear()
        self.assertTrue(self.panel.executor.disabled)
        self.assertEqual((), self.panel.executor.options)
        self.assertEqual([], self.chosen)

    def test_the_default_callback_ignores_choices(self):
        panel = node_info.NodeInfoPanel()
        panel.show(self.widget, "n1", ["a"], None)
        panel.executor.value = "a"  # does not raise
        self.assertEqual("a", panel.executor.value)


if __name__ == "__main__":
    unittest.main()
