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

# What js/commands.js `now()` stamps a command with; note the colons.
STAMP = "9/21/2026, 10:15:03 AM #3"


@fr.atomic("signal")
def relu(x: float, bias: float = 0.0) -> float:
    return max(0.0, x - bias)


@fr.atomic("out")
def boom(x: float) -> float:
    raise RuntimeError("boom")


@fr.atomic("out")
def nothing() -> None:
    return None


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


def _shown(widget: reactflow.PyironFlowWidget) -> list[str]:
    """What reached the output widget, one entry per output.

    Printed text reads as itself, HTML as its markup, and any other displayed object
    as its ``repr``.
    """
    return [
        (
            o["text"]
            if o["output_type"] == "stream"
            else o["data"].get("text/html", o["data"]["text/plain"])
        )
        for o in widget.out_widget.outputs
    ]


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


@fr.atomic("out")
def opaque_node(pair: tuple[int, int] = (1, 2), scale: float = 1.0) -> int:
    return sum(pair) * int(scale)


def _constant(value, label):
    return pwf.schemas.Constant.from_value(value, label)


def _locked_widget():
    """A widget whose `n1.bias` arrives already fed by a constant."""
    wf = pwf.Workflow("locked")
    wf.n1 = pwf.node(relu)
    c = _constant(2.5, "c")
    wf.add_node(c)
    wf.connect(c.outputs["constant"], wf.n1.inputs["bias"])
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
        with self.assertRaises(RuntimeError):
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
        with (
            unittest.mock.patch.object(
                pwf.Workflow, "run", side_effect=RuntimeError("early")
            ),
            self.assertRaises(RuntimeError),
        ):
            self._run()
        self.assertIs(first, self.widget.last_run)
        self.assertTrue(self.widget.gui.has_run)

    def test_a_failure_before_any_run_exists_with_nothing_cached(self):
        self.widget._port_cache["n1__x"] = 1.0
        with (
            unittest.mock.patch.object(
                pwf.Workflow, "run", side_effect=RuntimeError("early")
            ),
            self.assertRaises(RuntimeError),
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
                command, argument = reactflow.parse_command(f"{name} executed at now")
                self.assertEqual(name, command.value)
                self.assertIsNone(argument)

    def test_the_argument_is_the_text_after_as(self):
        self.assertEqual(
            (reactflow.GlobalCommand.RENAME, "abandoned"),
            reactflow.parse_command("rename executed at now as abandoned"),
        )

    def test_retired_commands_no_longer_parse(self):
        for name in ("load", "delete"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                reactflow.parse_command(f"{name} executed at now")

    def test_file_commands_open_the_panel(self):
        widget = _widget(pwf.Workflow("commands"))
        widget.files_panel = unittest.mock.Mock()
        reactflow.GlobalCommand.IMPORT.handle(widget)
        widget.files_panel.open.assert_called_once_with("import")

    def test_file_commands_explain_themselves_without_a_panel(self):
        widget = _widget(pwf.Workflow("commands"))
        reactflow.GlobalCommand.SAVE.handle(widget)
        self.assertIn("needs the full PyironFlow GUI", _shown(widget)[-1])

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
        reactflow.GlobalCommand.RENAME.handle(widget, "bad name")
        self.assertEqual(["Cannot rename: nope\n"], _shown(widget))

    def test_tab_commands_explain_themselves_without_a_flow(self):
        widget = _widget(pwf.Workflow("commands"))
        for command in (reactflow.GlobalCommand.RENAME, reactflow.GlobalCommand.CLOSE):
            with self.subTest(command=command):
                command.handle(widget, "x")
                self.assertIn("needs the full PyironFlow GUI", _shown(widget)[-1])

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


class TestNodeCommands(unittest.TestCase):
    def setUp(self):
        wf = pwf.Workflow("node_commands")
        wf.n1 = pwf.node(relu)
        self.widget = _widget(wf)

    def test_node_commands_parse(self):
        for name in ("source", "pull", "output", "delete_node"):
            with self.subTest(name=name):
                command, node_name = reactflow.parse_command(f"{name}: n1 @ {STAMP}")
                self.assertEqual(name, command.value)
                self.assertEqual("n1", node_name)

    def test_a_timestamp_is_optional(self):
        self.assertEqual(
            (reactflow.NodeCommand.OUTPUT, "n1"), reactflow.parse_command("output: n1")
        )

    def test_labels_survive_awkward_characters(self):
        for label in ("my-node", "a @ b", "x:y"):
            with self.subTest(label=label):
                self.assertEqual(
                    (reactflow.NodeCommand.PULL, label),
                    reactflow.parse_command(f"pull: {label} @ {STAMP}"),
                )

    def test_unknown_node_commands_do_not_parse(self):
        with self.assertRaises(ValueError):
            reactflow.parse_command(f"frobnicate: n1 @ {STAMP}")

    def test_a_missing_node_is_ignored(self):
        reactflow.NodeCommand.DELETE_NODE.handle(self.widget, "nope")
        self.assertEqual(["n1"], list(self.widget.wf.nodes))
        self.assertEqual([], _shown(self.widget))

    def test_delete_removes_the_node(self):
        reactflow.NodeCommand.DELETE_NODE.handle(self.widget, "n1")
        self.assertEqual([], list(self.widget.wf.nodes))

    def test_node_commands_show_the_output_tab(self):
        accordion = widgets.Accordion(
            children=[widgets.Output(), widgets.Output(), widgets.Output()]
        )
        self.widget.accordion_widget = accordion
        reactflow.NodeCommand.OUTPUT.handle(self.widget, "n1")
        self.assertEqual(reactflow.AccordionTab.OUTPUT.index, accordion.selected_index)
        self.assertEqual(["n1 has not been run yet.\n"], _shown(self.widget))


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


class TestPreflight(unittest.TestCase):
    def test_a_run_refuses_while_an_entry_is_invalid(self):
        widget, _ = _entry_widget()
        widget.commit_entry("n1", "grid", "[[1, 2")
        _quietly(lambda: widget.run_workflow(widget.wf))
        self.assertIsNone(widget.last_run)
        self.assertEqual([], list(widget.wf.inputs))
        self.assertEqual([], list(widget.wf.outputs))

    def test_a_cleared_defaulted_port_runs_on_its_default(self):
        wf = pwf.Workflow("defaults")
        wf.n1 = pwf.node(relu)
        widget = _widget(wf)
        widget.commit_entry("n1", "x", "1.0")
        widget.commit_entry("n1", "bias", "0.25")
        _quietly(lambda: widget.run_workflow(widget.wf))
        self.assertEqual(0.75, widget.last_run.outputs["n1__signal"])
        widget.commit_entry("n1", "bias", "")
        _quietly(lambda: widget.run_workflow(widget.wf))
        self.assertEqual(1.0, widget.last_run.outputs["n1__signal"])

    def test_a_container_value_runs_end_to_end(self):
        widget, _ = _entry_widget()
        widget.commit_entry("n1", "grid", "[[1, 2], [3]]")
        _quietly(lambda: widget.run_workflow(widget.wf))
        self.assertEqual(2, widget.last_run.outputs["n1__out"])

    def test_a_stale_cached_value_refuses_a_run(self):
        """A value cached before a hint change no longer fits its port.

        Unlike a freshly rejected entry, the key stays in ``_port_cache`` (only
        ``commit_entry`` pops it), so ``missing_required_input`` sees a value and
        does not fire; this exercises `invalid_entries`'s own rejection instead.
        """
        wf = pwf.Workflow("stale")
        wf.n1 = pwf.node(relu)
        widget = _widget(wf)
        widget._port_cache["n1__x"] = "not a float"
        widget.run_workflow(widget.wf)
        self.assertIsNone(widget.last_run)
        self.assertIn("n1.x", _shown(widget)[0])
        self.assertEqual([], list(widget.wf.inputs))
        self.assertEqual([], list(widget.wf.outputs))

    def test_a_stale_cached_value_refuses_a_pull(self):
        wf = pwf.Workflow("stale_pull")
        wf.n1 = pwf.node(relu)
        widget = _widget(wf)
        widget._port_cache["n1__x"] = "not a float"
        widget.pull_workflow(widget.wf.nodes["n1"])
        self.assertIsNone(widget.last_run)
        self.assertIn("n1.x", _shown(widget)[0])


class TestLockExtractionOnInit(unittest.TestCase):
    def test_constants_become_locks(self):
        widget, _ = _locked_widget()
        self.assertEqual(
            widget.locked, {wf_extensions.port_cache_key("n1", "bias"): 2.5}
        )

    def test_the_constant_is_normalized_to_a_canonical_label(self):
        widget, _ = _locked_widget()
        self.assertIn("n1_bias_constant_0", widget.wf.nodes)
        self.assertNotIn("c", widget.wf.nodes)

    def test_a_shared_constant_is_split_at_construction(self):
        wf = pwf.Workflow("shared")
        wf.n1 = pwf.node(relu)
        wf.n2 = pwf.node(relu)
        c = _constant(2.5, "c")
        wf.add_node(c)
        wf.connect(c.outputs["constant"], wf.n1.inputs["bias"])
        wf.connect(c.outputs["constant"], wf.n2.inputs["bias"])
        widget = _widget(wf)
        self.assertEqual(
            set(widget.locked),
            {
                wf_extensions.port_cache_key("n1", "bias"),
                wf_extensions.port_cache_key("n2", "bias"),
            },
        )
        self.assertIn("n1_bias_constant_0", widget.wf.nodes)
        self.assertIn("n2_bias_constant_0", widget.wf.nodes)

    def test_the_constant_is_not_drawn(self):
        widget, _ = _locked_widget()
        self.assertEqual([n["id"] for n in json.loads(widget.gui.nodes)], ["n1"])


class TestLockPort(unittest.TestCase):
    def test_locks_a_committed_entry(self):
        wf = pwf.Workflow("locking")
        wf.n1 = pwf.node(relu)
        widget = _widget(wf)
        widget.gui.send = lambda content, buffers=None: None
        widget.commit_entry("n1", "bias", "3.5")
        reply = widget.lock_port("n1", "bias")
        key = wf_extensions.port_cache_key("n1", "bias")
        self.assertIsNone(reply["error"])
        self.assertEqual(widget.locked[key], 3.5)
        self.assertNotIn(
            key, widget.port_cache, "locking moves the value out of the cache"
        )
        self.assertEqual(
            reply["locked"], {"text": "3.5", "full": "3.5", "releasable": True}
        )

    def test_locks_a_default(self):
        wf = pwf.Workflow("locking")
        wf.n1 = pwf.node(relu)
        widget = _widget(wf)
        widget.gui.send = lambda content, buffers=None: None
        reply = widget.lock_port("n1", "bias")
        self.assertIsNone(reply["error"])
        self.assertEqual(widget.locked[wf_extensions.port_cache_key("n1", "bias")], 0.0)

    def test_rejects_an_unknown_port(self):
        wf = pwf.Workflow("locking")
        wf.n1 = pwf.node(relu)
        widget = _widget(wf)
        widget.gui.send = lambda content, buffers=None: None
        self.assertIn("No such port", widget.lock_port("n1", "nope")["error"])

    def test_rejects_a_port_with_nothing_to_lock(self):
        wf = pwf.Workflow("locking")
        wf.n1 = pwf.node(relu)
        widget = _widget(wf)
        widget.gui.send = lambda content, buffers=None: None
        reply = widget.lock_port("n1", "x")  # no default, nothing entered
        self.assertIn("no value", reply["error"])
        self.assertEqual(widget.locked, {})

    def test_rejects_a_port_holding_an_invalid_entry(self):
        wf = pwf.Workflow("locking")
        wf.n1 = pwf.node(relu)
        widget = _widget(wf)
        widget.gui.send = lambda content, buffers=None: None
        widget.commit_entry("n1", "bias", "not a float")
        reply = widget.lock_port("n1", "bias")
        self.assertIsNotNone(reply["error"])
        self.assertEqual(widget.locked, {})

    def test_rejects_a_port_fed_by_an_edge(self):
        wf = pwf.Workflow("locking")
        wf.n1 = pwf.node(relu)
        wf.n2 = pwf.node(relu)
        wf.connect(wf.n2.outputs["signal"], wf.n1.inputs["bias"])
        widget = _widget(wf)
        widget.gui.send = lambda content, buffers=None: None
        self.assertIn("edge", widget.lock_port("n1", "bias")["error"])

    def test_rejects_an_already_locked_port(self):
        widget, _ = _locked_widget()
        self.assertIn("already", widget.lock_port("n1", "bias")["error"].lower())

    def test_replies_to_the_browser(self):
        widget, sent = _locked_widget()
        widget.lock_port("n1", "bias")
        self.assertEqual(sent[-1]["type"], "lock")


class TestUnlockPort(unittest.TestCase):
    def test_releasable_port_keeps_the_value_in_the_cache(self):
        widget, _ = _locked_widget()
        key = wf_extensions.port_cache_key("n1", "bias")
        reply = widget.unlock_port("n1", "bias")
        self.assertIsNone(reply["error"])
        self.assertNotIn(key, widget.locked)
        self.assertEqual(widget.port_cache[key], 2.5)
        self.assertEqual(reply["text"], "2.5")

    def test_non_releasable_port_discards_the_value(self):
        wf = pwf.Workflow("trash")
        wf.n1 = pwf.node(opaque_node)
        c = _constant([1, 2], "c")
        wf.add_node(c)
        wf.connect(c.outputs["constant"], wf.n1.inputs["pair"])
        widget = _widget(wf)
        widget.gui.send = lambda content, buffers=None: None
        key = wf_extensions.port_cache_key("n1", "pair")
        self.assertIn(key, widget.locked, "it arrives locked")
        reply = widget.unlock_port("n1", "pair")
        self.assertIsNone(reply["error"])
        self.assertNotIn(key, widget.locked)
        self.assertNotIn(key, widget.port_cache, "a trashed value goes nowhere")
        self.assertIsNone(reply["text"])

    def test_rejects_a_port_that_is_not_locked(self):
        wf = pwf.Workflow("plain")
        wf.n1 = pwf.node(relu)
        widget = _widget(wf)
        widget.gui.send = lambda content, buffers=None: None
        self.assertIsNotNone(widget.unlock_port("n1", "bias")["error"])

    def test_rejects_an_unknown_port(self):
        widget, _ = _locked_widget()
        self.assertIn("No such port", widget.unlock_port("n1", "nope")["error"])

    def test_the_constant_is_gone_after_a_sync(self):
        widget, _ = _locked_widget()
        widget.unlock_port("n1", "bias")
        wf = widget.get_workflow()
        self.assertEqual(
            [label for label, n in wf.nodes.items() if wf_extensions.is_constant(n)], []
        )


class TestCommitEntryRespectsLocks(unittest.TestCase):
    def test_refuses_a_locked_port(self):
        widget, _ = _locked_widget()
        key = wf_extensions.port_cache_key("n1", "bias")
        reply = widget.commit_entry("n1", "bias", "9.0")
        self.assertIsNotNone(reply["error"])
        self.assertEqual(widget.locked[key], 2.5, "the lock is untouched")
        self.assertNotIn(key, widget.port_cache)


class TestCustomMessageRouting(unittest.TestCase):
    def test_routes_lock(self):
        widget, _ = _locked_widget()
        widget.unlock_port("n1", "bias")
        widget._on_custom_msg(
            widget.gui, {"type": "lock", "node": "n1", "port": "bias"}, []
        )
        self.assertIn(wf_extensions.port_cache_key("n1", "bias"), widget.locked)

    def test_routes_unlock(self):
        widget, _ = _locked_widget()
        widget._on_custom_msg(
            widget.gui, {"type": "unlock", "node": "n1", "port": "bias"}, []
        )
        self.assertEqual(widget.locked, {})

    def test_ignores_an_unknown_type(self):
        widget, _ = _locked_widget()
        widget._on_custom_msg(widget.gui, {"type": "nonsense"}, [])
        self.assertEqual(len(widget.locked), 1)

    def test_ignores_a_message_that_is_not_a_dict(self):
        """The `isinstance` check is its own statement now, so it needs its own test.

        Before this task it was one short-circuiting `and`, which a dict-shaped message
        was enough to cover.
        """
        widget, sent = _locked_widget()
        widget._on_custom_msg(widget.gui, "not a dict", [])
        self.assertEqual(sent, [])
        self.assertEqual(len(widget.locked), 1)


class TestConstantRoundTrip(unittest.TestCase):
    def test_a_constant_survives_a_sync(self):
        widget, _ = _locked_widget()
        wf = widget.get_workflow()
        constants = {
            label: n.recipe.constant
            for label, n in wf.nodes.items()
            if wf_extensions.is_constant(n)
        }
        self.assertEqual(constants, {"n1_bias_constant_0": 2.5})
        self.assertIn(
            ("n1_bias_constant_0", "constant", "n1", "bias"),
            {
                (e.source.node, e.source.port, e.target.node, e.target.port)
                for e in wf.edges
            },
        )

    def test_a_locked_port_needs_no_run_time_value(self):
        widget, _ = _locked_widget()
        widget.wf = widget.get_workflow()
        self.assertEqual(
            wf_extensions.missing_required_input(widget.wf, widget.port_cache),
            [("n1", "x")],
            "bias is fed by its constant; only x is still missing",
        )

    def test_a_locked_workflow_runs(self):
        widget, _ = _locked_widget()
        widget.commit_entry("n1", "x", "5.0")
        _quietly(lambda: widget.run_workflow(widget.get_workflow()))
        self.assertIsNotNone(widget.last_run)
        self.assertEqual(widget.last_run.outputs["n1__signal"], 2.5)


class TestViewOutput(unittest.TestCase):
    """The "View Output" context-menu command reads the widget's most recent run.

    That run is whatever `_run_and_cache` last stored -- a full run or a pull -- and
    never `wf.last_run`, which a pull leaves untouched because it runs a throwaway cone.
    """

    def setUp(self):
        wf = pwf.Workflow("viewed")
        wf.n1 = pwf.node(relu)
        wf.n2 = pwf.node(relu, "n2")
        wf.n2.inputs.x = wf.n1.outputs.signal
        self.widget = _widget(wf)
        self.widget._port_cache["n1__x"] = 5.0

    @staticmethod
    def _view(widget, node_label: str) -> list[str]:
        """Drive the real command the way the browser does; return what the panel shows.

        The panel is cleared per command, and its first line echoes the command, so
        that line is dropped.
        """
        widget.gui.commands = f"output: {node_label} @ {STAMP}"
        echo, *shown = _shown(widget)
        assert echo.startswith("command: output"), echo
        return shown

    @staticmethod
    def _header(port: str) -> str:
        return f"<h3 style='margin-bottom:0.2em'>{port}:</h3>"

    def test_a_full_run_shows_the_value(self):
        self.widget.run_workflow(self.widget.wf)
        self.assertEqual([self._header("signal"), "5.0"], self._view(self.widget, "n1"))

    def test_a_pull_shows_the_value(self):
        """The regression: a pull writes only the widget's run, not `wf.last_run`."""
        self.widget.pull_workflow(self.widget.wf.nodes["n2"])
        self.assertEqual([self._header("signal"), "5.0"], self._view(self.widget, "n1"))

    def test_a_node_outside_the_pulled_cone_shows_no_value(self):
        """n2 is downstream of n1, so pulling n1 never runs it."""
        self.widget.pull_workflow(self.widget.wf.nodes["n1"])
        self.assertEqual(
            ["n2 was not part of the last run.\n"], self._view(self.widget, "n2")
        )

    def test_nothing_ran_yet_says_so(self):
        self.assertEqual(["n1 has not been run yet.\n"], self._view(self.widget, "n1"))

    def test_a_node_returning_none_is_not_confused_with_an_absent_run(self):
        """`None` is a real output value, so it must not read as "never ran"."""
        wf = pwf.Workflow("nones")
        wf.n = pwf.node(nothing)
        widget = _widget(wf)
        widget.run_workflow(widget.wf)
        self.assertEqual([self._header("out"), "None"], self._view(widget, "n"))


class TestValidateInput(unittest.TestCase):
    def setUp(self):
        wf = pwf.Workflow("validated")
        wf.n1 = pwf.node(relu)
        wf.n2 = pwf.node(relu)
        self.widget = _widget(wf)

    def _message(self):
        return self.widget._validate_current_input_for(self.widget.wf)

    def test_valid_input_gives_no_message(self):
        self.widget._port_cache["n1__x"] = 1.0
        self.widget._port_cache["n2__x"] = 2.0
        self.assertIsNone(self._message())

    def test_missing_input_is_listed(self):
        self.widget._port_cache["n1__x"] = 1.0
        message = self._message()
        self.assertIn("No value(s) for:\n    n2.x", message)
        self.assertNotIn("Invalid", message)

    def test_invalid_input_is_listed(self):
        self.widget._port_cache["n1__x"] = 1.0
        self.widget._port_cache["n2__x"] = "not a float"
        message = self._message()
        self.assertIn("Invalid value(s) for:\n    n2.x", message)
        self.assertNotIn("No value", message)

    def test_missing_and_invalid_input_are_both_listed(self):
        self.widget._port_cache["n1__x"] = "not a float"
        message = self._message()
        self.assertIn("No value(s) for:\n    n2.x", message)
        self.assertIn("Invalid value(s) for:\n    n1.x", message)


class TestSay(unittest.TestCase):
    def test_each_message_is_its_own_line(self):
        widget = _widget(pwf.Workflow("said"))
        widget._say("bare")
        widget._say("terminated\n")
        self.assertEqual(["bare\n", "terminated\n"], _shown(widget))


class TestGentleError(unittest.TestCase):
    def setUp(self):
        self.out, self.log = widgets.Output(), widgets.Output()
        self.out.append_stdout("stale\n")

    def test_clears_the_output_by_default(self):
        with reactflow.GentleError(self.out, self.log):
            pass
        self.assertEqual((), self.out.outputs)

    def test_can_keep_the_output(self):
        with reactflow.GentleError(self.out, self.log, clear=False):
            pass
        self.assertEqual("stale\n", self.out.outputs[0]["text"])

    def test_reports_an_error_and_logs_its_traceback(self):
        with reactflow.GentleError(self.out, self.log):
            raise RuntimeError("oops")
        self.assertEqual("Error: oops\n", self.out.outputs[-1]["text"])
        self.assertIn("RuntimeError: oops", self.log.outputs[-1]["text"])


class TestOnValueChange(unittest.TestCase):
    """The browser's commands, dispatched through `on_value_change`."""

    def setUp(self):
        wf = pwf.Workflow("dispatched")
        wf.n1 = pwf.node(relu)
        self.widget = _widget(wf)

    def _send(self, command: str) -> list[str]:
        self.widget.gui.commands = command
        return _shown(self.widget)

    def test_the_command_is_echoed(self):
        self.assertEqual(
            ["command: run executed at now\n"], self._send("run executed at now")[:1]
        )

    def test_a_failure_to_sync_the_workflow_is_reported_and_nothing_runs(self):
        self.widget._port_cache["n1__x"] = 1.0
        with unittest.mock.patch.object(
            self.widget, "get_workflow", side_effect=ValueError("bad graph")
        ):
            shown = self._send("run executed at now")
        self.assertEqual("Error: bad graph\n", shown[-1])
        self.assertIsNone(self.widget.last_run)

    def test_a_failed_run_is_reported(self):
        self.widget.wf.n_boom = pwf.node(boom)
        self.widget.update()
        self.widget._port_cache["n1__x"] = 1.0
        self.widget._port_cache["n_boom__x"] = 1.0
        shown = self._send("run executed at now")
        self.assertEqual("Error: boom\n", shown[-1])
        self.assertEqual(RunStatus.FAILED, self.widget.last_run.status)

    def test_an_unknown_node_command_is_reported(self):
        shown = self._send(f"frobnicate: n1 @ {STAMP}")
        self.assertEqual("Error: 'frobnicate' is not a valid NodeCommand\n", shown[-1])

    def test_a_command_for_a_missing_node_does_nothing(self):
        self.assertEqual(1, len(self._send(f"pull: nope @ {STAMP}")))

    def test_pull_shows_the_result(self):
        self.widget._port_cache["n1__x"] = 1.0
        self.assertEqual(
            ["<h3 style='margin-bottom:0.2em'>signal:</h3>", "1.0"],
            self._send(f"pull: n1 @ {STAMP}")[1:],
        )

    def test_source_is_shown(self):
        self.assertIn("relu", self._send(f"source: n1 @ {STAMP}")[-1])

    def test_delete_node_removes_the_node(self):
        self._send(f"delete_node: n1 @ {STAMP}")
        self.assertNotIn("n1", self.widget.wf.nodes)


if __name__ == "__main__":
    unittest.main()
