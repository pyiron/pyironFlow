import os
import pathlib
import shutil
import tempfile
import unittest

import flowrep as fr
import pyiron_workflow as pwf

from pyironflow import entry, pyironflow_std, storage, treeview

INPUTS = {
    "input_int": (int, entry.EntryKind.TEXT, 3),
    "input_float": (float, entry.EntryKind.TEXT, 1.5),
    "input_str": (str, entry.EntryKind.TEXT, "hi"),
    "input_bool": (bool, entry.EntryKind.CHECKBOX, True),
}
LOADERS = ("load_result", "browse_paths")


@fr.atomic("signal")
def relu(x: float) -> float:
    return max(0.0, x)


def _definitions():
    file = pathlib.Path(pyironflow_std.__file__)
    return {d.name: d for d in treeview.list_definitions(file)}


class TestPyironflowStd(unittest.TestCase):
    def setUp(self):
        self.definitions = _definitions()

    def test_library_lists_exactly_the_std_nodes_as_atomic(self):
        self.assertEqual(
            {name: d.kind for name, d in self.definitions.items()},
            {name: treeview.NodeKind.ATOMIC for name in (*INPUTS, *LOADERS)},
        )

    def test_each_input_passes_its_typed_value_through(self):
        for name, (hint, kind, value) in INPUTS.items():
            with self.subTest(name=name):
                node = treeview.instantiate(self.definitions[name], f"{name}_0")
                self.assertEqual(list(node.inputs), ["x"])
                self.assertEqual(list(node.outputs), ["x"])
                self.assertIs(node.inputs.x.type_hint, hint)
                self.assertEqual(entry.entry_kind(node.inputs.x.type_hint), kind)
                run = node.run(x=value)
                self.assertEqual(run.result.output_ports["x"].value, value)


class TestLoaders(unittest.TestCase):
    """Runs of `relu` saved as ``run.pckl`` and ``run.h5`` in the working directory."""

    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        previous = os.getcwd()
        os.chdir(self.tmp)
        self.addCleanup(os.chdir, previous)
        self.definitions = _definitions()
        wf = pwf.Workflow("saved")
        wf.n1 = pwf.node(relu)
        wf.set_inputs_to_unconnected_child_input()
        wf.set_outputs_to_unconnected_child_output()
        run = wf.run(n1__x=2.0)
        for fmt in storage.RunFormat:
            storage.save_run(run, self.tmp / f"run{fmt.extension}", fmt, False, False)

    def _node(self, name):
        return treeview.instantiate(self.definitions[name], f"{name}_0")

    def test_the_format_port_is_a_dropdown_of_every_load_format(self):
        for name in LOADERS:
            with self.subTest(name=name):
                hint = self._node(name).inputs.format.type_hint
                self.assertEqual(entry.EntryKind.DROPDOWN, entry.entry_kind(hint))
                self.assertEqual(
                    set(storage.LoadFormat), set(entry._literal_members(hint))
                )

    def test_each_format_option_parses_back_to_its_load_format(self):
        """The GUI shows options as text and sends the chosen text back."""
        hint = self._node("load_result").inputs.format.type_hint
        self.assertEqual(
            list(storage.LoadFormat),
            [entry.parse(text, hint) for text in entry.options(hint)],
        )

    def test_browse_paths_lists_the_outputs(self):
        for fmt in storage.RunFormat:
            with self.subTest(fmt=fmt):
                run = self._node("browse_paths").run(file=f"run{fmt.extension}")
                self.assertEqual(
                    ["n1.outputs.signal", "outputs.n1__signal"], run.outputs.paths
                )

    def test_load_result_loads_relative_to_the_working_directory(self):
        for fmt in storage.RunFormat:
            with self.subTest(fmt=fmt):
                run = self._node("load_result").run(
                    file=f"run{fmt.extension}", lexical_path="n1/outputs.signal"
                )
                self.assertEqual(2.0, run.outputs.value)

    def test_a_chosen_format_finds_the_file_without_its_extension(self):
        run = self._node("load_result").run(
            file="run", lexical_path="outputs.n1__signal", format=storage.LoadFormat.H5
        )
        self.assertEqual(2.0, run.outputs.value)

    def test_a_plain_string_format_is_accepted(self):
        run = self._node("browse_paths").run(file="run.h5", format="h5")
        self.assertIn("n1.outputs.signal", run.outputs.paths)

    def test_a_loader_survives_recipe_export_and_import(self):
        """Recipes carry the enum-hinted port, and whether it has a default, not values."""
        wf = pwf.Workflow("trip")
        wf.lr = self._node("load_result")
        cache = {"lr__file": "run.h5", "lr__lexical_path": "outputs.n1__signal"}
        recipe = storage.export_recipe(wf, cache)
        path = self.tmp / "trip.json"
        storage.write_recipe(recipe, path, False, False)
        read = storage.read_recipe(path)
        self.assertEqual(recipe, read)
        rebuilt = storage.recipe_to_gui_workflow(read, "trip")
        self.assertEqual(["lr"], list(rebuilt.nodes))
        self.assertTrue(rebuilt.nodes["lr"].inputs.format.has_default)
