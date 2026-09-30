import unittest
from pathlib import Path

from pyironflow import entry, pyironflow_std, treeview

EXPECTED = {
    "input_int": (int, entry.EntryKind.TEXT, 3),
    "input_float": (float, entry.EntryKind.TEXT, 1.5),
    "input_str": (str, entry.EntryKind.TEXT, "hi"),
    "input_bool": (bool, entry.EntryKind.CHECKBOX, True),
}


class TestPyironflowStd(unittest.TestCase):
    def setUp(self):
        file = Path(pyironflow_std.__file__)
        self.definitions = {d.name: d for d in treeview.list_definitions(file)}

    def test_library_lists_exactly_the_atomic_inputs(self):
        self.assertEqual(
            {name: d.kind for name, d in self.definitions.items()},
            {name: treeview.NodeKind.ATOMIC for name in EXPECTED},
        )

    def test_each_node_passes_its_typed_value_through(self):
        for name, (hint, kind, value) in EXPECTED.items():
            with self.subTest(name=name):
                node = treeview.instantiate(self.definitions[name], f"{name}_0")
                self.assertEqual(list(node.inputs), ["x"])
                self.assertEqual(list(node.outputs), ["x"])
                self.assertIs(node.inputs.x.type_hint, hint)
                self.assertEqual(entry.entry_kind(node.inputs.x.type_hint), kind)
                run = node.run(x=value)
                self.assertEqual(run.result.output_ports["x"].value, value)
