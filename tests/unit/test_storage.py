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
from pyironflow.wf_extensions import TransientInputs, get_edges, get_node_step


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

    def test_a_workflow_with_designed_io_is_wrapped_keeping_it(self):
        source = _two_relus("source")
        source.create_input_for(source.n1.inputs.x, label="x")
        wf = storage.recipe_to_gui_workflow(source.recipe, "my-flow")
        self.assertEqual("my_flow", wf.label)
        self.assertEqual(["my_flow"], list(wf.nodes))
        (child,) = wf.nodes.values()
        self.assertIsInstance(child, pwf.Workflow)
        self.assertEqual(["x"], list(child.inputs))
        self.assertEqual([], list(wf.inputs))
        self.assertEqual(0, len(wf.undo_stack))

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


def _designed_io_run():
    """A run of a workflow whose IO someone chose, so the GUI wraps it."""
    wf = pwf.Workflow("designed")
    wf.n1 = pwf.node(relu)
    wf.create_input_for(wf.n1.inputs.x, label="x")
    wf.set_outputs_to_unconnected_child_output()
    return wf.run(x=2.0)


def _nested_run():
    """A run with a sub-workflow and a for-each loop, so paths go several levels deep."""
    wf = pwf.Workflow("nested")
    wf.c = pwf.node(chained)
    wf.l = pwf.node(looped)
    wf.set_inputs_to_unconnected_child_input()
    wf.set_outputs_to_unconnected_child_output()
    return wf.run(c__x=2.0, l__xs=[1.0, -1.0])


def _atomic_run():
    return pwf.node(relu).run(x=3.0)


def _saved(tmp, run, name):
    """*run* saved in every format, keyed by format."""
    paths = {}
    for fmt in storage.RunFormat:
        paths[fmt] = tmp / f"{name}{fmt.extension}"
        storage.save_run(run, paths[fmt], fmt, False, False)
    return paths


def _paths(run):
    """Every lexical path in *run*, depth first."""
    return [run.lexical_path] + [path for step in run.steps for path in _paths(step)]


class TestLoadRun(_TempDirCase):
    def test_saved_runs_load_by_inferred_format(self):
        for fmt in storage.RunFormat:
            with self.subTest(fmt=fmt):
                path = self.tmp / f"finished{fmt.extension}"
                storage.save_run(_finished_run(), path, fmt, False, False)
                run = storage.load_run(path, storage.LoadFormat.INFER)
                self.assertIsInstance(run, execution.Run)
                self.assertEqual({"n1__signal": 1.0}, dict(run.outputs))
                self.assertEqual(
                    ["saved.n1"], [step.lexical_path for step in run.steps]
                )

    def test_a_forced_format_ignores_the_suffix(self):
        for fmt in storage.RunFormat:
            with self.subTest(fmt=fmt):
                path = self.tmp / f"{fmt}.dat"
                storage.save_run(_finished_run(), path, fmt, False, False)
                run = storage.load_run(path, storage.LoadFormat(fmt))
                self.assertEqual(execution.RunStatus.FINISHED, run.status)

    def test_an_unknown_suffix_cannot_be_inferred(self):
        path = self.tmp / "run.dat"
        storage.save_run(_finished_run(), path, storage.RunFormat.PICKLE, False, False)
        with self.assertRaises(storage.StorageError) as caught:
            storage.load_run(path, storage.LoadFormat.INFER)
        self.assertIn("choose", str(caught.exception))

    def test_a_missing_file_is_reported(self):
        with self.assertRaises(storage.StorageError) as caught:
            storage.load_run(self.tmp / "nope.pckl", storage.LoadFormat.INFER)
        self.assertIn("No such file", str(caught.exception))

    def test_something_other_than_a_run_is_refused(self):
        path = self.tmp / "dict.pckl"
        path.write_bytes(pickle.dumps({"not": "a run"}))
        with self.assertRaises(storage.StorageError) as caught:
            storage.load_run(path, storage.LoadFormat.INFER)
        self.assertIn("dict", str(caught.exception))

    def test_an_unreadable_file_is_reported_with_its_cause(self):
        for fmt in storage.RunFormat:
            with self.subTest(fmt=fmt):
                path = self.tmp / f"garbage{fmt.extension}"
                path.write_bytes(b"garbage")
                with self.assertRaises(storage.StorageError) as caught:
                    storage.load_run(path, storage.LoadFormat.INFER)
                self.assertIsNotNone(caught.exception.__cause__)


class TestBrowseRunOutputs(_TempDirCase):
    def test_the_result_root_is_where_a_saved_run_keeps_its_result(self):
        path = _saved(self.tmp, _finished_run(), "root")[storage.RunFormat.H5]
        bag = boh.H5Bag(str(path))
        self.assertEqual(execution.Run.__qualname__, bag["object"].qualname)
        self.assertEqual(
            fr.schemas.DagData.__qualname__,
            bag[storage.RESULT_STORAGE_ROOT].qualname,
        )

    def test_formats_agree_on_sorted_output_paths(self):
        for name, make in (("nested", _nested_run), ("atomic", _atomic_run)):
            paths = _saved(self.tmp, make(), name)
            browsed = {
                fmt: storage.browse_run_outputs(path, storage.LoadFormat.INFER)
                for fmt, path in paths.items()
            }
            with self.subTest(name=name):
                pickled = browsed[storage.RunFormat.PICKLE]
                self.assertEqual(pickled, browsed[storage.RunFormat.H5])
                self.assertEqual(sorted(pickled), pickled)
                self.assertTrue(all(p.split(".")[-2] == "outputs" for p in pickled))

    def test_nested_and_looped_outputs_are_listed(self):
        path = _saved(self.tmp, _nested_run(), "nested")[storage.RunFormat.H5]
        browsed = storage.browse_run_outputs(path, storage.LoadFormat.INFER)
        for expected in (
            "outputs.c__y",
            "c.relu_1.outputs.signal",
            "l.for_each_0.body_1.relu_0.outputs.signal",
        ):
            with self.subTest(expected=expected):
                self.assertIn(expected, browsed)

    def test_an_atomic_run_lists_only_its_own_outputs(self):
        path = _saved(self.tmp, _atomic_run(), "atomic")[storage.RunFormat.PICKLE]
        self.assertEqual(
            ["outputs.signal"],
            storage.browse_run_outputs(path, storage.LoadFormat.INFER),
        )

    def test_a_missing_file_is_reported(self):
        for fmt in storage.LoadFormat:
            with self.subTest(fmt=fmt):
                with self.assertRaises(storage.StorageError) as caught:
                    storage.browse_run_outputs(self.tmp / "nope.h5", fmt)
                self.assertIn("No such file", str(caught.exception))

    def test_an_h5_file_of_something_else_is_refused(self):
        path = self.tmp / "data.h5"
        boh.H5Bag.save(_finished_run().result, path)
        with self.assertRaises(storage.StorageError) as caught:
            storage.browse_run_outputs(path, storage.LoadFormat.INFER)
        self.assertIn("DagData", str(caught.exception))

    def test_an_unreadable_h5_file_is_reported_with_its_cause(self):
        path = self.tmp / "garbage.h5"
        path.write_bytes(b"garbage")
        with self.assertRaises(storage.StorageError) as caught:
            storage.browse_run_outputs(path, storage.LoadFormat.INFER)
        self.assertIsNotNone(caught.exception.__cause__)


def _value_at(result, path):
    """The value the live *result* holds at output *path*, walking it by hand."""
    *nodes, _, port = path.split(".")
    for label in nodes:
        result = result.nodes[label]
    return result.output_ports[port].value


class TestLoadRunOutput(_TempDirCase):
    def setUp(self):
        super().setUp()
        self.run = _nested_run()
        self.paths = _saved(self.tmp, self.run, "nested")

    def _load(self, fmt, lexical_path):
        return storage.load_run_output(
            self.paths[fmt], lexical_path, storage.LoadFormat.INFER
        )

    def test_every_browsed_path_loads_its_value_in_every_format(self):
        browsed = storage.browse_run_outputs(
            self.paths[storage.RunFormat.H5], storage.LoadFormat.INFER
        )
        for fmt in storage.RunFormat:
            for path in browsed:
                with self.subTest(fmt=fmt, path=path):
                    self.assertEqual(
                        _value_at(self.run.result, path), self._load(fmt, path)
                    )

    def test_an_atomic_run_loads_its_output(self):
        for fmt, path in _saved(self.tmp, _atomic_run(), "atomic").items():
            with self.subTest(fmt=fmt):
                self.assertEqual(
                    3.0,
                    storage.load_run_output(
                        path, "outputs.signal", storage.LoadFormat.INFER
                    ),
                )

    def test_slashes_dividers_and_whitespace_are_forgiven(self):
        clean = "l.for_each_0.body_0.relu_0.outputs.signal"
        for fmt in storage.RunFormat:
            for variant in (
                "l/for_each_0/body_0/relu_0.outputs.signal",
                "l/for_each_0.body_0/relu_0.outputs.signal",
                "  l.for_each_0.body_0.relu_0.outputs.signal  ",
                "/l/for_each_0/body_0/relu_0.outputs.signal/",
            ):
                with self.subTest(fmt=fmt, variant=variant):
                    self.assertEqual(self._load(fmt, clean), self._load(fmt, variant))

    def test_paths_that_do_not_end_at_an_output_are_refused(self):
        for fmt in storage.RunFormat:
            for path in ("c", "c.outputs", "c.inputs.x", "inputs.c__x", ""):
                with self.subTest(fmt=fmt, path=path):
                    with self.assertRaises(storage.StorageError) as caught:
                        self._load(fmt, path)
                    self.assertIn("outputs.<port>", str(caught.exception))

    def test_unknown_nodes_and_ports_are_named(self):
        for fmt in storage.RunFormat:
            for path, missing in (
                ("nope.outputs.y", "nope"),
                ("c.nope.outputs.signal", "nope"),
                ("c.outputs.nope", "nope"),
                ("c.relu_0.relu_0.outputs.signal", "relu_0"),
            ):
                with self.subTest(fmt=fmt, path=path):
                    with self.assertRaises(storage.StorageError) as caught:
                        self._load(fmt, path)
                    self.assertIn(missing, str(caught.exception))

    def test_an_output_without_data_is_an_error(self):
        for fmt, path in _saved(self.tmp, _failed_run(), "failed").items():
            with self.subTest(fmt=fmt):
                with self.assertRaises(storage.StorageError) as caught:
                    storage.load_run_output(
                        path, "outputs.n1__out", storage.LoadFormat.INFER
                    )
                self.assertIn("no data", str(caught.exception))

    def test_a_forced_format_is_used(self):
        path = self.tmp / "run.dat"
        storage.save_run(self.run, path, storage.RunFormat.H5, False, False)
        self.assertEqual(
            2.0,
            storage.load_run_output(path, "outputs.c__y", storage.LoadFormat.H5),
        )


class TestRunToGuiWorkflow(unittest.TestCase):
    def test_a_workflow_run_is_kept_as_the_last_run(self):
        run = _finished_run()
        wf, last_run = storage.run_to_gui_workflow(run, "my-run")
        self.assertEqual("my_run", wf.label)
        self.assertEqual(["n1"], list(wf.nodes))
        self.assertEqual([], list(wf.inputs))
        self.assertIs(run, last_run)

    def test_a_wrapped_run_becomes_the_only_step_of_a_parent_run(self):
        run = pwf.node(relu).run(x=1.0)
        wf, parent = storage.run_to_gui_workflow(run, "stem")
        self.assertEqual(["relu"], list(wf.nodes))
        self.assertEqual("stem", parent.lexical_path)
        self.assertEqual(["stem", "stem.relu"], _paths(parent))
        (step,) = parent.steps
        self.assertIs(run.result, step.result)
        self.assertIs(run.result, parent.result.nodes["relu"])
        self.assertEqual({"relu__signal": 1.0}, dict(parent.outputs))
        self.assertEqual(1.0, parent.result.input_ports["relu__x"].value)
        for field in ("status", "exception", "started_at", "finished_at", "run_dir"):
            with self.subTest(field=field):
                self.assertEqual(getattr(run, field), getattr(parent, field))
        self.assertIs(step, get_node_step(parent, "relu"))
        self.assertEqual("relu", run.lexical_path, msg="the loaded run is untouched")

    def test_the_child_is_labelled_after_the_run_it_came_from(self):
        wf, parent = storage.run_to_gui_workflow(_designed_io_run(), "stem")
        self.assertEqual(["designed"], list(wf.nodes))
        self.assertEqual(["stem", "stem.designed", "stem.designed.n1"], _paths(parent))
        self.assertEqual(
            {"n1__signal": 2.0}, dict(get_node_step(parent, "designed").outputs)
        )

    def test_a_failed_wrapped_run_keeps_its_failure(self):
        caught = []
        config = execution.RunConfig(
            exception_hooks=[lambda _dir, run, _err: caught.append(run)]
        )
        with contextlib.suppress(RuntimeError):
            pwf.node(boom).run(config, x=1.0)
        _, parent = storage.run_to_gui_workflow(caught[0], "stem")
        self.assertEqual(execution.RunStatus.FAILED, parent.status)
        self.assertIsInstance(parent.exception, RuntimeError)

    def test_a_saved_parent_run_loads_back_unwrapped(self):
        _, parent = storage.run_to_gui_workflow(_designed_io_run(), "stem")
        with tempfile.TemporaryDirectory() as tmp:
            for fmt in storage.RunFormat:
                with self.subTest(fmt=fmt):
                    path = pathlib.Path(tmp) / f"parent{fmt.extension}"
                    storage.save_run(parent, path, fmt, False, False)
                    loaded = storage.load_run(path, storage.LoadFormat.INFER)
                    wf, last_run = storage.run_to_gui_workflow(loaded, "again")
                    self.assertEqual(["designed"], list(wf.nodes))
                    self.assertIs(loaded, last_run)


if __name__ == "__main__":
    unittest.main()
