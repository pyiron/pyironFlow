import contextlib
import html
import io
import json
import pathlib
import pickle
import shutil
import tempfile
import types
import unittest
import unittest.mock

import bagofholding as boh
import flowrep as fr
import pyiron_workflow as pwf
from pyiron_workflow.execution import RunStatus

from pyironflow import PyironFlow, storage
from pyironflow.files_panel import FileAction, FilesPanel
from pyironflow.reactflow import AccordionTab
from pyironflow.wf_extensions import TransientInputs


@fr.atomic("signal")
def relu(x: float, bias: float = 0.0) -> float:
    return max(0.0, x - bias)


@fr.atomic("out")
def nested_param(b__c: float) -> float:
    return b__c


@fr.atomic("out")
def plain_param(c: float) -> float:
    return c


@fr.atomic("out")
def maybe_fail(x: float, fail: bool = False) -> float:
    if fail:
        raise RuntimeError("boom")
    return x


def _quietly(fn):
    with (
        contextlib.redirect_stdout(io.StringIO()),
        contextlib.redirect_stderr(io.StringIO()),
    ):
        return fn()


def _type_value(widget, node_label, port_label, value):
    """Enter *value* into a port's field the way the browser would report it."""
    nodes = json.loads(widget.gui.nodes)
    for node in nodes:
        if node["id"] == node_label:
            node["data"]["target_values"][port_label] = value
    widget.gui.nodes = json.dumps(nodes)


class TestConstruction(unittest.TestCase):
    def test_does_not_touch_active_widget_or_accordion(self):
        stand_in = types.SimpleNamespace()  # no .active_widget, no .accordion
        panel = FilesPanel(stand_in)
        self.assertEqual(FileAction.EXPORT, panel.action.value)


class _PanelCase(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        wf = pwf.Workflow("first")
        wf.n1 = pwf.node(relu)
        self.flow = self._flow([wf])
        self.panel = self.flow.files_panel

    def _flow(self, wf_list=None):
        flow = PyironFlow(wf_list)
        self.addCleanup(flow.close)
        return flow

    def _actions(self, panel=None):
        return [value for _, value in (panel or self.panel).action.options]

    def _run(self, flow=None):
        widget = (flow or self.flow).active_widget
        _type_value(widget, "n1", "x", 1.0)
        widget.wf = widget.get_workflow()
        _quietly(lambda: widget.run_workflow(widget.wf))

    def _go(self, action, path, panel=None):
        panel = panel or self.panel
        panel.action.value = action
        panel.path.value = str(path)
        panel.go.click()
        return panel.status.value


class TestActions(_PanelCase):
    def test_save_is_unavailable_without_a_run(self):
        self.assertEqual([FileAction.EXPORT, FileAction.IMPORT], self._actions())

    def test_save_appears_after_a_run(self):
        self._run()
        self.assertIn(FileAction.SAVE, self._actions())

    def test_save_follows_the_selected_tab(self):
        self._run()
        self.panel.action.value = FileAction.SAVE
        second = pwf.Workflow("second")
        second.n1 = pwf.node(relu)
        self.flow.add_workflow(second)
        self.assertNotIn(FileAction.SAVE, self._actions())
        self.assertEqual(FileAction.EXPORT, self.panel.action.value)
        self.flow.tab.selected_index = 0
        self.assertIn(FileAction.SAVE, self._actions())

    def test_a_refresh_keeps_the_selected_action(self):
        self._run()
        self.panel.action.value = FileAction.IMPORT
        second = pwf.Workflow("second")
        second.n1 = pwf.node(relu)
        self.flow.add_workflow(second)
        self.assertEqual(FileAction.IMPORT, self.panel.action.value)

    def test_controls_shown_per_action(self):
        self._run()
        shown = {
            FileAction.EXPORT: {"export_inputs", "create_dirs", "overwrite"},
            FileAction.IMPORT: set(),
            FileAction.SAVE: {"run_format", "run_info", "create_dirs", "overwrite"},
        }
        optional = {
            "export_inputs",
            "run_format",
            "run_info",
            "create_dirs",
            "overwrite",
        }
        for action, visible in shown.items():
            self.panel.action.value = action
            for name in optional:
                with self.subTest(action=action, control=name):
                    display = getattr(self.panel, name).layout.display
                    self.assertEqual(name in visible, display != "none")

    def test_run_info_describes_the_cached_run(self):
        self._run()
        self.panel.action.value = FileAction.SAVE
        self.assertIn("first", self.panel.run_info.value)
        self.assertIn("finished", self.panel.run_info.value)

    def test_run_info_reflects_a_later_run_without_reselecting_save(self):
        wf = pwf.Workflow("flaky")
        wf.n1 = pwf.node(maybe_fail)
        flow = self._flow([wf])
        panel = flow.files_panel
        widget = flow.active_widget

        _type_value(widget, "n1", "x", 1.0)
        widget.wf = widget.get_workflow()
        _quietly(lambda: widget.run_workflow(widget.wf))
        panel.action.value = FileAction.SAVE
        self.assertIn("(finished,", panel.run_info.value)

        _type_value(widget, "n1", "fail", True)
        widget.wf = widget.get_workflow()
        _quietly(lambda: widget.run_workflow(widget.wf))

        self.assertIn("(failed,", panel.run_info.value)
        self.assertNotIn("(finished,", panel.run_info.value)

    def test_open_selects_the_action_and_the_files_tab(self):
        self.panel.open("import")
        self.assertEqual(FileAction.IMPORT, self.panel.action.value)
        self.assertEqual(AccordionTab.FILES.index, self.flow.accordion.selected_index)

    def test_opening_save_without_a_run_explains(self):
        self.panel.open(FileAction.SAVE)
        self.assertIn("no run to save", self.panel.status.value)
        self.assertEqual(AccordionTab.FILES.index, self.flow.accordion.selected_index)


class TestExport(_PanelCase):
    def _inputs(self, name="out.json"):
        return json.loads((self.tmp / name).read_text())["inputs"]

    def test_export_writes_the_recipe(self):
        _type_value(self.flow.active_widget, "n1", "bias", 0.5)
        status = self._go(FileAction.EXPORT, self.tmp / "out")
        self.assertIn(str(self.tmp / "out.json"), status)
        self.assertEqual(["n1__x", "n1__bias"], self._inputs())

    def test_export_uses_the_chosen_mode(self):
        _type_value(self.flow.active_widget, "n1", "bias", 0.5)
        self.panel.export_inputs.value = TransientInputs.UNDEFAULTED
        self._go(FileAction.EXPORT, self.tmp / "out")
        self.assertEqual(["n1__x"], self._inputs())

    def test_an_invalid_graph_writes_nothing_and_logs(self):
        wf = pwf.Workflow("clash")
        wf.a = pwf.node(nested_param)
        wf.a__b = pwf.node(plain_param)
        flow = self._flow([wf])
        flow.files_panel.create_dirs.value = True
        status = self._go(
            FileAction.EXPORT, self.tmp / "sub" / "out", panel=flow.files_panel
        )
        self.assertIn("not currently a valid flowrep recipe", status)
        self.assertFalse((self.tmp / "sub").exists())
        self.assertGreater(len(flow.out_log.outputs), 0)

    def test_an_existing_file_needs_overwrite(self):
        target = self.tmp / "out.json"
        target.write_text("keep")
        status = self._go(FileAction.EXPORT, target)
        self.assertIn("already exists", status)
        self.assertEqual("keep", target.read_text())
        self.panel.overwrite.value = True
        self._go(FileAction.EXPORT, target)
        self.assertEqual("workflow", json.loads(target.read_text())["type"])

    def test_a_blank_path_is_reported(self):
        self.assertIn("Enter a file path", self._go(FileAction.EXPORT, "  "))


class TestImport(_PanelCase):
    def _write(self, name):
        wf = pwf.Workflow("source")
        wf.n1 = pwf.node(relu)
        path = self.tmp / f"{name}.json"
        storage.write_recipe(storage.export_recipe(wf, {}), path, False, False)
        return path

    def test_import_opens_a_new_tab(self):
        path = self._write("second_flow")
        status = self._go(FileAction.IMPORT, self.tmp / "second_flow")
        self.assertIn("Imported", status)
        self.assertEqual(2, len(self.flow.wf_widgets))
        self.assertEqual("second_flow", self.flow.active_widget.wf.label)
        self.assertEqual(["n1"], list(self.flow.active_widget.wf.nodes))
        self.assertTrue(path.is_file())

    def test_import_into_an_empty_tab_replaces_it(self):
        self._write("into_empty")
        flow = self._flow()
        self._go(FileAction.IMPORT, self.tmp / "into_empty", panel=flow.files_panel)
        self.assertEqual(1, len(flow.wf_widgets))
        self.assertEqual("into_empty", flow.active_widget.wf.label)

    def test_a_missing_file_is_reported(self):
        self.assertIn("No such file", self._go(FileAction.IMPORT, self.tmp / "nope"))

    def test_an_unexpected_error_is_reported_and_logged(self):
        self._write("boom")
        with unittest.mock.patch.object(
            storage, "read_recipe", side_effect=RuntimeError("kaboom")
        ):
            status = self._go(FileAction.IMPORT, self.tmp / "boom")
        self.assertIn("Error: kaboom", status)
        self.assertGreater(len(self.flow.out_log.outputs), 0)

    def test_importing_the_same_recipe_twice_gets_distinct_names(self):
        self._write("dup")
        self._go(FileAction.IMPORT, self.tmp / "dup")
        status = self._go(FileAction.IMPORT, self.tmp / "dup")
        # `_report` HTML-escapes the message, so the literal quotes from `!r`
        # come through as entities.
        self.assertIn(html.escape("'dup_1'"), status)
        self.assertEqual(("first", "dup", "dup_1"), self.flow.tab.titles)


class TestSaveRun(_PanelCase):
    def test_save_as_pickle(self):
        self._run()
        self._go(FileAction.SAVE, self.tmp / "r")
        with (self.tmp / "r.pckl").open("rb") as f:
            self.assertEqual(RunStatus.FINISHED, pickle.load(f).status)

    def test_save_as_h5(self):
        self._run()
        self.panel.action.value = FileAction.SAVE
        self.panel.run_format.value = storage.RunFormat.H5
        self._go(FileAction.SAVE, self.tmp / "r")
        loaded = boh.H5Bag(str(self.tmp / "r.h5")).load()
        self.assertEqual(RunStatus.FINISHED, loaded.status)

    def test_save_without_a_cached_run_is_reported(self):
        self._run()
        self.panel.action.value = FileAction.SAVE
        self.flow.active_widget.last_run = None
        self.panel.path.value = str(self.tmp / "r")
        self.panel.go.click()
        self.assertIn("no run to save", self.panel.status.value)
        self.assertFalse((self.tmp / "r.pckl").exists())


if __name__ == "__main__":
    unittest.main()
