import re
import unittest

import flowrep as fr
import ipywidgets as widgets
import pyiron_workflow as pwf

from pyironflow import node_info, reactflow

QUERIED = re.compile(r"^Queried @ \d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\n$")


@fr.atomic("signal")
def relu(x: float, bias: float = 0.0) -> float:
    return max(0.0, x - bias)


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
        self.assertEqual((), self.panel.output.outputs)
        self.assertEqual((), self.panel.source.outputs)
        self.assertIsNone(self.panel.output_section.selected_index)
        self.assertIsNone(self.panel.source_section.selected_index)

    def test_stacks_header_output_and_source(self):
        self.assertEqual(
            (self.panel.header, self.panel.output_section, self.panel.source_section),
            self.panel.gui.children,
        )
        self.assertEqual(("Output",), self.panel.output_section.titles)
        self.assertEqual(("Source",), self.panel.source_section.titles)
        self.assertIn("node-info-header", self.panel.header._dom_classes)

    def test_show_before_any_run(self):
        self.panel.show(self.widget, "n1")
        self.assertEqual("n1", self.panel.header.value)
        queried, *rest = _texts(self.panel.output)
        self.assertRegex(queried, QUERIED)
        self.assertEqual(["n1 has not been run yet.\n"], rest)

    def test_show_after_a_run(self):
        self.widget._port_cache["n1__x"] = 3.0
        self.widget.run_workflow(self.widget.wf)
        self.panel.show(self.widget, "n1")
        self.assertEqual("3.0", _texts(self.panel.output)[-1])

    def test_show_a_node_outside_the_last_run(self):
        self.widget.wf.n2 = pwf.node(relu, x=self.widget.wf.n1.outputs.signal)
        self.widget._port_cache["n1__x"] = 3.0
        self.widget.pull_workflow(self.widget.wf.nodes["n1"])
        self.panel.show(self.widget, "n2")
        self.assertEqual(
            "n2 was not part of the last run.\n", _texts(self.panel.output)[-1]
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
        self.assertEqual(2, len(self.panel.output.outputs))
        self.assertEqual(2, len(self.panel.source.outputs))

    def test_clear(self):
        self.panel.show(self.widget, "n1")
        self.panel.clear()
        self.assertEqual("", self.panel.header.value)
        self.assertEqual((), self.panel.output.outputs)
        self.assertEqual((), self.panel.source.outputs)

    def test_expand_opens_only_what_is_flagged(self):
        self.panel.expand(output=True, source=False)
        self.assertEqual(0, self.panel.output_section.selected_index)
        self.assertIsNone(self.panel.source_section.selected_index)

    def test_expand_leaves_unflagged_sections_as_the_user_set_them(self):
        self.panel.source_section.selected_index = 0
        self.panel.output_section.selected_index = None
        self.panel.expand(output=False, source=False)
        self.assertIsNone(self.panel.output_section.selected_index)
        self.assertEqual(0, self.panel.source_section.selected_index)


if __name__ == "__main__":
    unittest.main()
