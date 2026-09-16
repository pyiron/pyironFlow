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


@fr.atomic("out")
def grid_node(grid: list[list[int]], scale: float = 1.0) -> int:
    return len(grid) * int(scale)


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


def _entry_widget():
    wf = pwf.Workflow("entries")
    wf.n1 = pwf.node(grid_node)
    widget = _widget(wf)
    sent = []
    widget.gui.send = lambda content, buffers=None: sent.append(content)
    return widget, sent


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

    def test_a_run_refreshes_a_wired_files_panel(self):
        self.widget.files_panel = unittest.mock.Mock()
        self.widget._port_cache["n1__x"] = 1.0
        self._run()
        self.widget.files_panel.refresh.assert_called_once()


class TestGlobalCommands(unittest.TestCase):
    def test_file_commands_parse(self):
        for name in ("run", "export", "import", "save", "rename", "close"):
            with self.subTest(name=name):
                command = _quietly(
                    lambda name=name: reactflow.parse_command(f"{name} executed at now")
                )
                self.assertEqual(name, command.value)

    def test_retired_commands_no_longer_parse(self):
        for name in ("load", "delete"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                _quietly(
                    lambda name=name: reactflow.parse_command(f"{name} executed at now")
                )

    def test_file_commands_open_the_panel(self):
        widget = _widget(pwf.Workflow("commands"))
        widget.files_panel = unittest.mock.Mock()
        reactflow.GlobalCommand.IMPORT.handle(widget)
        widget.files_panel.open.assert_called_once_with("import")

    def test_file_commands_explain_themselves_without_a_panel(self):
        widget = _widget(pwf.Workflow("commands"))
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            reactflow.GlobalCommand.SAVE.handle(widget)
        self.assertIn("needs the full PyironFlow GUI", buffer.getvalue())

    def test_port_cache_is_the_widget_cache(self):
        widget = _widget(pwf.Workflow("commands"))
        self.assertIs(widget._port_cache, widget.port_cache)

    def test_command_argument_is_the_text_after_as(self):
        self.assertEqual(
            "abandoned",
            reactflow.command_argument(
                "rename executed at 9/15/2026, 1:20:33 PM as abandoned"
            ),
        )
        self.assertIsNone(reactflow.command_argument("close executed at now"))

    def test_rename_and_close_go_to_the_flow(self):
        widget = _widget(pwf.Workflow("commands"))
        widget.flow = unittest.mock.Mock()
        reactflow.GlobalCommand.RENAME.handle(widget, "renamed")
        widget.flow.rename_workflow.assert_called_once_with(widget, "renamed")
        reactflow.GlobalCommand.CLOSE.handle(widget)
        widget.flow.close_workflow.assert_called_once_with(widget)

    def test_a_refused_rename_is_explained(self):
        widget = _widget(pwf.Workflow("commands"))
        widget.flow = unittest.mock.Mock()
        widget.flow.rename_workflow.side_effect = ValueError("nope")
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            reactflow.GlobalCommand.RENAME.handle(widget, "bad name")
        self.assertIn("Cannot rename: nope", buffer.getvalue())

    def test_tab_commands_explain_themselves_without_a_flow(self):
        widget = _widget(pwf.Workflow("commands"))
        for command in (reactflow.GlobalCommand.RENAME, reactflow.GlobalCommand.CLOSE):
            with self.subTest(command=command):
                buffer = io.StringIO()
                with contextlib.redirect_stdout(buffer):
                    command.handle(widget, "x")
                self.assertIn("needs the full PyironFlow GUI", buffer.getvalue())

    def test_a_command_containing_done_is_not_dropped(self):
        """Nothing sends "done"; the old substring check swallowed such commands."""
        widget = _widget(pwf.Workflow("commands"))
        widget.flow = unittest.mock.Mock()
        _quietly(
            lambda: setattr(
                widget.gui, "commands", "rename executed at now as abandoned"
            )
        )
        widget.flow.rename_workflow.assert_called_once_with(widget, "abandoned")

    def test_the_gui_carries_the_workflow_label(self):
        self.assertEqual("labelled", _widget(pwf.Workflow("labelled")).gui.label)


class TestCommitEntry(unittest.TestCase):
    def test_a_valid_commit_caches_the_value_and_replies_with_rendered_text(self):
        widget, sent = _entry_widget()
        reply = widget.commit_entry("n1", "grid", "[[1, 2], [3]]")
        self.assertEqual([[1, 2], [3]], widget.port_cache["n1__grid"])
        self.assertEqual("[[1, 2], [3]]", reply["text"])
        self.assertIsNone(reply["error"])
        self.assertEqual([reply], sent)

    def test_a_float_port_replies_with_the_normalized_value(self):
        widget, _ = _entry_widget()
        self.assertEqual("2.0", widget.commit_entry("n1", "scale", "2")["text"])
        self.assertEqual(2.0, widget.port_cache["n1__scale"])

    def test_an_invalid_commit_records_the_error_and_drops_the_value(self):
        widget, _ = _entry_widget()
        widget.commit_entry("n1", "grid", "[[1, 2], [3]]")
        reply = widget.commit_entry("n1", "grid", "[[1, 2")
        self.assertNotIn("n1__grid", widget.port_cache)
        self.assertEqual("[[1, 2", widget._invalid_entries["n1__grid"].text)
        self.assertIsNotNone(reply["error"])
        self.assertEqual("[[1, 2", reply["text"])

    def test_a_blank_commit_clears_both_the_value_and_the_error(self):
        widget, _ = _entry_widget()
        widget.commit_entry("n1", "scale", "2")
        widget.commit_entry("n1", "grid", "[[1, 2")
        self.assertTrue(widget.commit_entry("n1", "scale", "")["cleared"])
        self.assertTrue(widget.commit_entry("n1", "grid", "  ")["cleared"])
        self.assertEqual({}, dict(widget.port_cache))
        self.assertEqual({}, widget._invalid_entries)

    def test_an_unknown_node_or_port_changes_nothing(self):
        widget, _ = _entry_widget()
        for node, port in [("nope", "grid"), ("n1", "nope")]:
            with self.subTest(node=node, port=port):
                reply = widget.commit_entry(node, port, "1")
                self.assertIsNotNone(reply["error"])
        self.assertEqual({}, dict(widget.port_cache))
        self.assertEqual({}, widget._invalid_entries)

    def test_a_custom_message_routes_to_commit_entry(self):
        widget, sent = _entry_widget()
        widget._on_custom_msg(
            widget.gui,
            {"type": "entry", "node": "n1", "port": "scale", "text": "3"},
            [],
        )
        self.assertEqual(3.0, widget.port_cache["n1__scale"])
        self.assertEqual(1, len(sent))

    def test_an_unknown_message_type_is_ignored(self):
        widget, sent = _entry_widget()
        widget._on_custom_msg(widget.gui, {"type": "something_else"}, [])
        self.assertEqual([], sent)

    def test_a_committed_value_survives_a_redraw(self):
        widget, _ = _entry_widget()
        widget.commit_entry("n1", "grid", "[[1, 2], [3]]")
        widget.update()
        data = json.loads(widget.gui.nodes)[0]["data"]
        self.assertEqual({"grid": "[[1, 2], [3]]"}, data["target_values"])

    def test_a_rejected_entry_survives_a_redraw(self):
        widget, _ = _entry_widget()
        widget.commit_entry("n1", "grid", "[[1, 2")
        widget.update()
        data = json.loads(widget.gui.nodes)[0]["data"]
        self.assertEqual("[[1, 2", data["target_errors"]["grid"]["text"])

    def test_the_nodes_traitlet_no_longer_writes_the_cache(self):
        widget, _ = _entry_widget()
        nodes = json.loads(widget.gui.nodes)
        nodes[0]["data"]["target_values"]["scale"] = "9.0"
        widget.gui.nodes = json.dumps(nodes)
        widget.wf = widget.get_workflow()
        self.assertEqual({}, dict(widget.port_cache))


if __name__ == "__main__":
    unittest.main()
