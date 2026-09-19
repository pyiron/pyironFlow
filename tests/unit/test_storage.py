import contextlib
import json
import os
import pathlib
import pickle
import shutil
import tempfile
import threading
import unittest
import unittest.mock

import bagofholding as boh
import flowrep as fr
import ipywidgets as widgets
import pydantic
import pyiron_workflow as pwf
from pyiron_workflow import execution, flowcontrollers
from pyiron_workflow.atomic_node import Atomic
from pyiron_workflow.dag import Macro

from pyironflow import storage
from pyironflow.reactflow import PyironFlowWidget
from pyironflow.wf_extensions import TransientInputs, get_edges


@fr.atomic("signal")
def relu(x: float, bias: float = 0.0) -> float:
    return max(0.0, x - bias)


@fr.atomic("out")
def boom(x: float) -> float:
    raise RuntimeError("boom")


@fr.workflow("y")
def chained(x: float) -> float:
    a = relu(x)
    b = relu(a)
    return b


@fr.workflow("ys")
def looped(xs: list[float]) -> list[float]:
    ys = []
    for x in xs:
        y = relu(x)
        ys.append(y)
    return ys


def _finished_run():
    wf = pwf.Workflow("saved")
    wf.n1 = pwf.node(relu)
    wf.set_inputs_to_unconnected_child_input()
    wf.set_outputs_to_unconnected_child_output()
    return wf.run(n1__x=1.0)


def _failed_run():
    wf = pwf.Workflow("failed")
    wf.n1 = pwf.node(boom)
    wf.set_inputs_to_unconnected_child_input()
    wf.set_outputs_to_unconnected_child_output()
    caught = []
    config = execution.RunConfig(
        exception_hooks=[lambda _dir, run, _err: caught.append(run)]
    )
    with contextlib.suppress(RuntimeError):
        wf.run(config, n1__x=1.0)
    return caught[0]


def _load(path, fmt):
    if fmt is storage.RunFormat.PICKLE:
        with path.open("rb") as f:
            return pickle.load(f)
    return boh.H5Bag(str(path)).load()


class _TempDirCase(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)


class TestResolvePath(_TempDirCase):
    def setUp(self):
        super().setUp()
        previous = os.getcwd()
        os.chdir(self.tmp)
        self.addCleanup(os.chdir, previous)

    def test_a_relative_path_resolves_against_the_cwd(self):
        self.assertEqual(
            self.tmp / "a" / "b.json", storage.resolve_path("a/b", ".json")
        )

    def test_parent_references_are_resolved(self):
        self.assertEqual(
            self.tmp.parent / "up.json", storage.resolve_path("../up", ".json")
        )

    def test_an_existing_matching_extension_is_kept(self):
        self.assertEqual(self.tmp / "b.json", storage.resolve_path("b.json", ".json"))

    def test_another_suffix_still_gets_the_extension(self):
        self.assertEqual(self.tmp / "run.v2.h5", storage.resolve_path("run.v2", ".h5"))

    def test_surrounding_whitespace_is_ignored(self):
        self.assertEqual(self.tmp / "b.json", storage.resolve_path("  b  ", ".json"))

    def test_home_is_expanded(self):
        self.assertEqual(
            pathlib.Path("~/x.json").expanduser().resolve(),
            storage.resolve_path("~/x", ".json"),
        )

    def test_an_absolute_path_is_kept(self):
        target = self.tmp / "abs" / "c.pckl"
        self.assertEqual(target, storage.resolve_path(str(target), ".pckl"))

    def test_a_blank_path_is_refused(self):
        with self.assertRaises(storage.StorageError) as caught:
            storage.resolve_path("   ", ".json")
        self.assertIn("Enter a file path", str(caught.exception))

    def test_a_blank_path_can_use_a_default_name(self):
        self.assertEqual(
            self.tmp / "workflow.json",
            storage.resolve_path("   ", ".json", default="workflow"),
        )

    def test_a_blank_path_refuses_a_blank_default_name(self):
        with self.assertRaises(storage.StorageError) as caught:
            storage.resolve_path("   ", ".json", default="   ")
        self.assertIn("Enter a file path", str(caught.exception))


class TestCheckWritable(_TempDirCase):
    def test_a_new_file_in_an_existing_directory_is_fine(self):
        storage.check_writable(self.tmp / "new.json", False, False)

    def test_an_existing_file_is_refused_without_overwrite(self):
        target = self.tmp / "there.json"
        target.write_text("{}")
        with self.assertRaises(storage.StorageError) as caught:
            storage.check_writable(target, False, False)
        self.assertIn("Overwrite existing", str(caught.exception))

    def test_an_existing_file_is_fine_with_overwrite(self):
        target = self.tmp / "there.json"
        target.write_text("{}")
        storage.check_writable(target, False, True)

    def test_a_directory_is_refused(self):
        with self.assertRaises(storage.StorageError) as caught:
            storage.check_writable(self.tmp, True, True)
        self.assertIn("is a directory", str(caught.exception))

    def test_a_missing_directory_is_refused_without_create_dirs(self):
        with self.assertRaises(storage.StorageError) as caught:
            storage.check_writable(self.tmp / "no" / "x.json", False, False)
        self.assertIn("Create missing directories", str(caught.exception))

    def test_a_missing_directory_is_fine_with_create_dirs_and_nothing_is_made(self):
        storage.check_writable(self.tmp / "no" / "x.json", True, False)
        self.assertFalse((self.tmp / "no").exists())

    def test_a_file_in_the_way_of_the_directories_is_refused(self):
        (self.tmp / "blocker").write_text("")
        with self.assertRaises(storage.StorageError) as caught:
            storage.check_writable(self.tmp / "blocker" / "x.json", True, True)
        self.assertIn("is a file", str(caught.exception))


class TestRunFormat(unittest.TestCase):
    def test_extensions(self):
        self.assertEqual(".pckl", storage.RunFormat.PICKLE.extension)
        self.assertEqual(".h5", storage.RunFormat.H5.extension)


class TestSaveRun(_TempDirCase):
    def test_a_finished_run_round_trips(self):
        for fmt in storage.RunFormat:
            with self.subTest(fmt=fmt):
                path = self.tmp / f"finished{fmt.extension}"
                storage.save_run(_finished_run(), path, fmt, False, False)
                self.assertEqual({"n1__signal": 1.0}, dict(_load(path, fmt).outputs))

    def test_a_failed_run_round_trips(self):
        for fmt in storage.RunFormat:
            with self.subTest(fmt=fmt):
                path = self.tmp / f"failed{fmt.extension}"
                storage.save_run(_failed_run(), path, fmt, False, False)
                self.assertEqual(execution.RunStatus.FAILED, _load(path, fmt).status)

    def test_missing_directories_are_created_on_request(self):
        path = self.tmp / "deep" / "er" / "run.pckl"
        storage.save_run(_finished_run(), path, storage.RunFormat.PICKLE, True, False)
        self.assertTrue(path.is_file())

    def test_an_existing_file_is_kept_without_overwrite(self):
        path = self.tmp / "run.pckl"
        path.write_bytes(b"keep")
        with self.assertRaises(storage.StorageError):
            storage.save_run(
                _finished_run(), path, storage.RunFormat.PICKLE, False, False
            )
        self.assertEqual(b"keep", path.read_bytes())

    def test_overwrite_replaces_the_file(self):
        path = self.tmp / "run.pckl"
        storage.save_run(_finished_run(), path, storage.RunFormat.PICKLE, False, False)
        storage.save_run(_failed_run(), path, storage.RunFormat.PICKLE, False, True)
        self.assertEqual(
            execution.RunStatus.FAILED, _load(path, storage.RunFormat.PICKLE).status
        )

    def test_a_failed_serialization_leaves_no_file(self):
        for fmt in storage.RunFormat:
            with self.subTest(fmt=fmt):
                run = _finished_run()
                run.run_dir = threading.Lock()  # cannot be pickled or bagged
                with self.assertRaises(storage.StorageError) as caught:
                    storage.save_run(
                        run, self.tmp / f"bad{fmt.extension}", fmt, False, False
                    )
                self.assertIsInstance(caught.exception.__cause__, TypeError)
                self.assertEqual([], list(self.tmp.iterdir()))


def _edges(wf):
    return [
        (e["source"], e["sourceHandle"], e["target"], e["targetHandle"])
        for e in get_edges(wf)
    ]


def _two_relus(label="trip"):
    wf = pwf.Workflow(label)
    wf.n1 = pwf.node(relu)
    wf.n2 = pwf.node(relu, x=wf.n1.outputs.signal)
    return wf


class TestToLabel(unittest.TestCase):
    def test_labels(self):
        for stem, label in (
            ("ok", "ok"),
            ("my-bar", "my_bar"),
            ("x.v2", "x_v2"),
            ("2026 run", "wf_2026_run"),
            ("class", "class_"),
            ("inputs", "inputs_"),
        ):
            with self.subTest(stem=stem):
                self.assertEqual(label, storage.to_label(stem))

    def test_falls_back_when_nothing_valid_can_be_made(self):
        with unittest.mock.patch.object(storage, "_LABEL_ADAPTER") as adapter:
            adapter.validate_python.side_effect = ValueError("no")
            self.assertEqual(storage.DEFAULT_LABEL, storage.to_label("anything"))


class TestExportRecipe(unittest.TestCase):
    def test_used_exposes_undefaulted_and_typed_ports_and_leaves_no_io(self):
        wf = _two_relus()
        recipe = storage.export_recipe(wf, {"n2__bias": 0.5})
        self.assertEqual(["n1__x", "n2__bias"], recipe.inputs)
        self.assertEqual(["n2__signal"], recipe.outputs)
        self.assertEqual([], list(wf.inputs))
        self.assertEqual([], list(wf.outputs))

    def test_the_mode_is_passed_through(self):
        recipe = storage.export_recipe(_two_relus(), {}, TransientInputs.UNCONNECTED)
        self.assertEqual(["n1__x", "n1__bias", "n2__bias"], recipe.inputs)

    def test_a_recipe_error_is_reported_and_leaves_no_io(self):
        wf = _two_relus()
        with (
            unittest.mock.patch.object(
                pwf.Workflow,
                "recipe",
                new_callable=unittest.mock.PropertyMock,
                side_effect=ValueError("nope"),
            ),
            self.assertRaises(storage.RecipeInvalidError) as caught,
        ):
            storage.export_recipe(wf, {})
        message = str(caught.exception)
        self.assertIn("not currently a valid flowrep recipe", message)
        self.assertIn("nope", message)
        self.assertIsInstance(caught.exception.__cause__, ValueError)
        self.assertEqual([], list(wf.inputs))
        self.assertEqual([], list(wf.outputs))


class TestWriteAndReadRecipe(_TempDirCase):
    def test_write_then_read_round_trips(self):
        recipe = storage.export_recipe(_two_relus(), {})
        path = self.tmp / "sub" / "trip.json"
        storage.write_recipe(recipe, path, True, False)
        self.assertEqual("workflow", json.loads(path.read_text())["type"])
        self.assertEqual(recipe, storage.read_recipe(path))

    def test_write_refuses_an_existing_file_without_overwrite(self):
        path = self.tmp / "trip.json"
        path.write_text("keep")
        with self.assertRaises(storage.StorageError):
            storage.write_recipe(
                storage.export_recipe(_two_relus(), {}), path, False, False
            )
        self.assertEqual("keep", path.read_text())

    def test_read_reports_a_missing_file(self):
        with self.assertRaises(storage.StorageError) as caught:
            storage.read_recipe(self.tmp / "nope.json")
        self.assertIn("No such file", str(caught.exception))

    def test_read_reports_invalid_json(self):
        path = self.tmp / "bad.json"
        path.write_text("{foo")
        with self.assertRaises(storage.StorageError) as caught:
            storage.read_recipe(path)
        self.assertIn("is not a flowrep recipe", str(caught.exception))

    def test_read_reports_json_that_is_not_a_recipe(self):
        path = self.tmp / "other.json"
        path.write_text('{"foo": 1}')
        with self.assertRaises(storage.StorageError) as caught:
            storage.read_recipe(path)
        self.assertIn("is not a flowrep recipe", str(caught.exception))


class TestRecipeToGuiWorkflow(_TempDirCase):
    def test_a_workflow_without_a_reference_loses_its_io_but_keeps_its_edges(self):
        source = _two_relus("source")
        source.set_inputs_to_unconnected_child_input()
        source.set_outputs_to_unconnected_child_output()
        wf = storage.recipe_to_gui_workflow(source.recipe, "my-flow")
        self.assertIsInstance(wf, pwf.Workflow)
        self.assertEqual("my_flow", wf.label)
        self.assertEqual(["n1", "n2"], list(wf.nodes))
        self.assertEqual([("n1", "signal", "n2", "x")], _edges(wf))
        self.assertEqual([], list(wf.inputs))
        self.assertEqual([], list(wf.outputs))
        self.assertEqual(0, len(wf.undo_stack))
        self.assertEqual(0, len(wf.redo_stack))

    def test_a_workflow_with_a_reference_is_wrapped_as_a_macro(self):
        wf = storage.recipe_to_gui_workflow(pwf.node(chained).recipe, "stem")
        self.assertEqual("stem", wf.label)
        self.assertEqual(["chained"], list(wf.nodes))
        self.assertIsInstance(wf.nodes["chained"], Macro)
        self.assertEqual([], list(wf.inputs))
        self.assertEqual(0, len(wf.undo_stack))

    def test_an_atomic_recipe_is_wrapped(self):
        wf = storage.recipe_to_gui_workflow(pwf.node(relu).recipe, "stem")
        self.assertEqual(["relu"], list(wf.nodes))
        self.assertIsInstance(wf.nodes["relu"], Atomic)

    def test_a_flow_control_recipe_is_wrapped_under_the_stem_label(self):
        (for_each,) = pwf.node(looped).recipe.nodes.values()
        wf = storage.recipe_to_gui_workflow(for_each, "loop")
        self.assertEqual(["loop"], list(wf.nodes))
        self.assertIsInstance(wf.nodes["loop"], flowcontrollers.ForEach)

    def test_an_unimportable_reference_is_reported(self):
        data = json.loads(pwf.node(relu).recipe.model_dump_json())
        data["reference"]["info"]["module"] = "not_a_module_xyz"
        recipe = pydantic.TypeAdapter(fr.schemas.RecipeDiscrimination).validate_python(
            data
        )
        with self.assertRaises(storage.StorageError) as caught:
            storage.recipe_to_gui_workflow(recipe, "stem")
        self.assertIn("not_a_module_xyz.relu", str(caught.exception))
        self.assertIsInstance(caught.exception.__cause__, ModuleNotFoundError)

    def test_export_then_import_reproduces_the_graph(self):
        path = self.tmp / "trip.json"
        storage.write_recipe(
            storage.export_recipe(_two_relus(), {}), path, False, False
        )
        wf = storage.recipe_to_gui_workflow(storage.read_recipe(path), path.stem)
        self.assertEqual("trip", wf.label)
        self.assertEqual(["n1", "n2"], list(wf.nodes))
        self.assertEqual([("n1", "signal", "n2", "x")], _edges(wf))

    def test_a_nested_workflow_without_a_reference_survives_the_gui(self):
        """Its `import_path` is None, so the GUI must reuse the live node by id."""
        inner = pwf.Workflow("inner")
        inner.a = pwf.node(relu)
        inner.set_inputs_to_unconnected_child_input()
        inner.set_outputs_to_unconnected_child_output()
        outer = pwf.Workflow("outer")
        outer.m = pwf.node(inner.recipe)
        outer.b = pwf.node(relu, x=outer.m.outputs["a__signal"])
        recipe = storage.export_recipe(outer, {})

        wf = storage.recipe_to_gui_workflow(recipe, "outer")
        widget = PyironFlowWidget(
            wf=wf, log=widgets.Output(), out_widget=widgets.Output()
        )
        before = {label: id(node) for label, node in widget.wf.nodes.items()}
        widget.wf = widget.get_workflow()
        after = {label: id(node) for label, node in widget.wf.nodes.items()}
        self.assertEqual(before, after)
        self.assertEqual([("m", "a__signal", "b", "x")], _edges(widget.wf))


if __name__ == "__main__":
    unittest.main()
