import ast
import contextlib
import importlib
import io
import json
import os
import sys
import tempfile
import textwrap
import unittest
import warnings
from pathlib import Path

import flowrep as fr
import ipywidgets as widgets
import pyiron_workflow as pwf
from pyiron_snippets import retrieve
from pyiron_workflow import datatypes

from pyironflow import reactflow, treeview

NODES_SOURCE = """
import functools

import flowrep as fr
import pyiron_workflow
from flowrep import workflow as wfd
from pyiron_workflow import as_function_node as fn

try:
    from flowrep import tools
except ImportError:
    tools = None


@fr.atomic
def add(x: int = 1, y: int = 2) -> int:
    s = x + y
    return s


@fn("z")
def legacy(x: int = 1):
    z = x + 1
    return z


@pyiron_workflow.as_macro_node("out")
def legacy_macro(self, x: int = 1):
    self.a = legacy(x=x)
    return self.a


@wfd
def twice(x: int = 1):
    a = add(x, x)
    b = add(a, a)
    return b


@tools.dataclass
class Record:
    a: int = 1


@fr.atomic
def _hidden_atomic(x: int = 0) -> int:
    return x


@functools.cache
def cached(x):
    return x


def plain(x):
    return x


class Plain:
    def __init__(self, a: int = 0):
        self.a = a

    def method(self):
        return self.a


def _private(x):
    return x


async def coroutine(x):
    return x


def unparseable(*args):
    return args
"""

LOOSE_SOURCE = """
import flowrep as fr


@fr.atomic
def loose_add(a: int = 1, b: int = 1) -> int:
    total = a + b
    return total
"""


def _write(root: Path, relative: str, source: str) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(source))
    return path


def _aliases(source: str) -> dict[str, str]:
    return treeview.import_aliases(ast.parse(textwrap.dedent(source)))


def _first_decorator(source: str) -> ast.expr:
    definition = ast.parse(textwrap.dedent(source)).body[0]
    assert isinstance(definition, ast.FunctionDef)
    return definition.decorator_list[0]


class _FixtureFiles(unittest.TestCase):
    """Writes an importable package and a loose script, and undoes any import of them."""

    PACKAGE = "pyironflow_tv_fixture_pkg"
    LOOSE = "pyironflow_tv_loose"

    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory())).resolve()
        _write(self.root, f"{self.PACKAGE}/__init__.py", "")
        _write(self.root, f"{self.PACKAGE}/sub/__init__.py", "")
        self.nodes_file = _write(
            self.root, f"{self.PACKAGE}/sub/nodes.py", NODES_SOURCE
        )
        self.loose_file = _write(self.root, f"loose/{self.LOOSE}.py", LOOSE_SOURCE)
        importlib.invalidate_caches()

        saved_path = list(sys.path)
        self.addCleanup(self._restore_imports, saved_path)
        self.enterContext(warnings.catch_warnings())
        warnings.simplefilter("ignore")

    @staticmethod
    def _restore_imports(saved_path: list[str]) -> None:
        sys.path[:] = saved_path
        for name in [m for m in sys.modules if m.startswith("pyironflow_tv_")]:
            del sys.modules[name]


class TestImportAliases(unittest.TestCase):
    def test_plain_import_binds_the_top_package(self):
        self.assertEqual(_aliases("import a.b.c"), {"a": "a"})

    def test_aliased_import_binds_the_full_path(self):
        self.assertEqual(_aliases("import a.b.c as x"), {"x": "a.b.c"})

    def test_from_imports(self):
        self.assertEqual(
            _aliases("from a.b import c\nfrom a.b import d as x"),
            {"c": "a.b.c", "x": "a.b.d"},
        )

    def test_relative_imports_are_ignored(self):
        self.assertEqual(_aliases("from . import c\nfrom .m import d"), {})

    def test_imports_in_module_level_blocks_count(self):
        source = """
        try:
            import a as x
        except ImportError:
            pass
        if True:
            from b import c
        """
        self.assertEqual(_aliases(source), {"x": "a", "c": "b.c"})

    def test_imports_inside_functions_and_classes_are_ignored(self):
        source = """
        def f():
            import a

        async def g():
            import b

        class C:
            import c
        """
        self.assertEqual(_aliases(source), {})

    def test_later_bindings_win_in_source_order(self):
        source = """
        try:
            import a as x
        except ImportError:
            pass
        import b as x
        """
        self.assertEqual(_aliases(source), {"x": "b"})


class TestResolveDecorator(unittest.TestCase):
    def test_bare_unaliased_name(self):
        decorator = _first_decorator("@atomic\ndef f(): pass")
        self.assertEqual(treeview.resolve_decorator(decorator, {}), "atomic")

    def test_attribute_chain_with_aliased_head(self):
        decorator = _first_decorator("@fr.tools.atomic\ndef f(): pass")
        self.assertEqual(
            treeview.resolve_decorator(decorator, {"fr": "flowrep"}),
            "flowrep.tools.atomic",
        )

    def test_called_decorator(self):
        decorator = _first_decorator("@fn('z')\ndef f(): pass")
        self.assertEqual(
            treeview.resolve_decorator(
                decorator, {"fn": "pyiron_workflow.as_function_node"}
            ),
            "pyiron_workflow.as_function_node",
        )

    def test_unsupported_expressions_resolve_to_none(self):
        for source in (
            "@registry['x']\ndef f(): pass",
            "@(lambda f: f)\ndef f(): pass",
        ):
            with self.subTest(source=source):
                decorator = _first_decorator(source)
                self.assertIsNone(treeview.resolve_decorator(decorator, {}))


class TestListDefinitions(_FixtureFiles):
    def test_definitions_in_source_order_with_kinds(self):
        found = [
            (d.name, d.kind, d.factory)
            for d in treeview.list_definitions(self.nodes_file)
        ]
        self.assertEqual(
            found,
            [
                ("add", treeview.NodeKind.ATOMIC, False),
                ("legacy", treeview.NodeKind.ATOMIC, True),
                ("legacy_macro", treeview.NodeKind.WORKFLOW, True),
                ("twice", treeview.NodeKind.WORKFLOW, False),
                ("Record", treeview.NodeKind.DATACLASS, False),
                ("_hidden_atomic", treeview.NodeKind.ATOMIC, False),
                ("cached", treeview.NodeKind.PLAIN, False),
                ("plain", treeview.NodeKind.PLAIN, False),
                ("Plain", treeview.NodeKind.PLAIN, False),
                ("unparseable", treeview.NodeKind.PLAIN, False),
            ],
        )

    def test_definitions_point_at_their_file(self):
        paths = {d.path for d in treeview.list_definitions(self.nodes_file)}
        self.assertEqual(paths, {self.nodes_file})

    def test_unparseable_file_yields_nothing_and_logs(self):
        broken = _write(self.root, "broken.py", "def broken(:\n")
        log = widgets.Output()
        self.assertEqual(treeview.list_definitions(broken, log=log), [])
        self.assertEqual(len(log.outputs), 1)
        self.assertEqual(log.outputs[0]["name"], "stderr")
        self.assertIn(str(broken), log.outputs[0]["text"])

    def test_unparseable_file_without_log(self):
        broken = _write(self.root, "broken.py", "def broken(:\n")
        self.assertEqual(treeview.list_definitions(broken), [])


class TestNodeKind(unittest.TestCase):
    def test_icons_are_distinct_from_each_other_and_from_folders_and_files(self):
        pairs = [(kind.icon, kind.icon_style) for kind in treeview.NodeKind]
        self.assertEqual(len(set(pairs)), len(pairs))
        self.assertNotIn(("folder", "warning"), pairs)
        self.assertNotIn(("archive", "success"), pairs)


class TestNodeDecorators(unittest.TestCase):
    def test_every_path_imports_the_public_decorator(self):
        expected = {
            "flowrep.atomic": fr.atomic,
            "flowrep.tools.atomic": fr.atomic,
            "flowrep.workflow": fr.workflow,
            "flowrep.tools.workflow": fr.workflow,
            "flowrep.dataclass": fr.dataclass,
            "flowrep.tools.dataclass": fr.dataclass,
            "pyiron_workflow.as_function_node": pwf.as_function_node,
            "pyiron_workflow.as_macro_node": pwf.as_macro_node,
        }
        self.assertEqual(set(treeview.NODE_DECORATORS), set(expected))
        for path, decorator in expected.items():
            with self.subTest(path=path):
                self.assertIs(retrieve.import_from_string(path), decorator)


class TestTreeDisplay(_FixtureFiles):
    def setUp(self):
        super().setUp()
        self.tree_view = treeview.TreeView(
            root_path=self.nodes_file.parent, log=widgets.Output()
        )
        (self.file_node,) = self.tree_view.tree.nodes
        self.tree_view.add_nodes(self.file_node, self.file_node.path)
        self.items = {item.name: item for item in self.file_node.nodes}

    def test_definitions_are_drawn_with_their_kind_icons(self):
        kinds = {d.name: d.kind for d in treeview.list_definitions(self.nodes_file)}
        drawn = {
            name: (item.icon, item.icon_style) for name, item in self.items.items()
        }
        self.assertEqual(
            drawn, {name: (kind.icon, kind.icon_style) for name, kind in kinds.items()}
        )

    def test_handle_click_routes_definitions_to_on_click(self):
        seen = []
        item = self.items["plain"]
        item.on_click = seen.append
        self.tree_view.handle_click({"owner": item})
        self.assertEqual(seen, [item])


class TestTreeNavigation(_FixtureFiles):
    """Exercises TreeView navigation left untouched by this task, for coverage."""

    def setUp(self):
        super().setUp()
        self.tree_view = treeview.TreeView(
            root_path=self.root / self.PACKAGE, log=widgets.Output()
        )

    def test_update_tree_rebuilds_from_root(self):
        (folder_node,) = self.tree_view.tree.nodes
        self.tree_view.update_tree()
        (rebuilt,) = self.tree_view.tree.nodes
        self.assertEqual(rebuilt.name, folder_node.name)

    def test_handle_click_ignores_the_repeated_event(self):
        (folder_node,) = self.tree_view.tree.nodes
        self.tree_view._handle_click_is_last_event = False
        self.tree_view.handle_click({"owner": folder_node})
        self.assertTrue(self.tree_view._handle_click_is_last_event)
        self.assertEqual(len(folder_node.nodes), 0)

    def test_handle_click_expands_a_folder_node(self):
        (folder_node,) = self.tree_view.tree.nodes
        self.tree_view.handle_click({"owner": folder_node})
        self.assertEqual(len(folder_node.nodes), 1)


class TestModuleLocation(_FixtureFiles):
    def test_file_in_a_package(self):
        self.assertEqual(
            treeview.module_location(self.nodes_file),
            (f"{self.PACKAGE}.sub.nodes", None),
        )

    def test_loose_script(self):
        self.assertEqual(
            treeview.module_location(self.loose_file),
            (self.LOOSE, self.loose_file.parent),
        )

    def test_unresolved_paths_climb_correctly(self):
        indirect = self.root / self.PACKAGE / "sub" / ".." / "sub" / "nodes.py"
        self.assertEqual(
            treeview.module_location(indirect),
            (f"{self.PACKAGE}.sub.nodes", None),
        )


class TestImportDefinition(_FixtureFiles):
    def test_loose_script_directory_is_appended_once(self):
        definition = treeview.NodeDefinition(
            "loose_add", self.loose_file, treeview.NodeKind.ATOMIC
        )
        self.assertEqual(treeview.import_definition(definition).__name__, "loose_add")
        treeview.import_definition(definition)
        self.assertEqual(sys.path[-1], str(self.loose_file.parent))
        self.assertEqual(sys.path.count(str(self.loose_file.parent)), 1)

    def test_package_import_leaves_sys_path_alone(self):
        sys.path.insert(0, str(self.root))
        before = list(sys.path)
        definition = treeview.NodeDefinition(
            "add", self.nodes_file, treeview.NodeKind.ATOMIC
        )
        self.assertEqual(treeview.import_definition(definition).__name__, "add")
        self.assertEqual(sys.path, before)


class TestInstantiate(_FixtureFiles):
    def setUp(self):
        super().setUp()
        sys.path.insert(0, str(self.root))
        self.definitions = {
            d.name: d for d in treeview.list_definitions(self.nodes_file)
        }

    def test_every_node_kind(self):
        expected = {
            "add": (["x", "y"], ["s"]),
            "legacy": (["x"], ["z"]),
            "legacy_macro": (["x"], ["out"]),
            "twice": (["x"], ["b"]),
            "Record": (["a"], ["instance"]),
            "_hidden_atomic": (["x"], ["x"]),
            "plain": (["x"], ["x"]),
            "Plain": (["a"], ["instance"]),
        }
        for name, (inputs, outputs) in expected.items():
            with self.subTest(name=name):
                node = treeview.instantiate(self.definitions[name], f"{name}_7")
                self.assertIsInstance(node, datatypes.Node)
                self.assertEqual(node.label, f"{name}_7")
                self.assertEqual(list(node.inputs), inputs)
                self.assertEqual(list(node.outputs), outputs)

    def test_loose_script(self):
        (definition,) = treeview.list_definitions(self.loose_file)
        node = treeview.instantiate(definition, "loose_add_0")
        self.assertEqual(node.label, "loose_add_0")
        self.assertEqual(list(node.outputs), ["total"])

    def test_plain_definition_flowrep_cannot_parse_raises(self):
        with self.assertRaises(ValueError):
            treeview.instantiate(self.definitions["unparseable"], "unparseable_0")


class TestAddingFromTree(_FixtureFiles):
    def setUp(self):
        super().setUp()
        sys.path.insert(0, str(self.root))
        self.widget = reactflow.PyironFlowWidget(
            wf=pwf.Workflow("tree"), log=widgets.Output(), out_widget=widgets.Output()
        )
        self.tree_view = treeview.TreeView(
            root_path=self.nodes_file.parent,
            flow_widget=self.widget,
            log=self.widget.log,
        )
        (file_node,) = self.tree_view.tree.nodes
        self.tree_view.add_nodes(file_node, file_node.path)
        self.items = {item.name: item for item in file_node.nodes}

    def _click(self, name: str, tree_view: treeview.TreeView | None = None) -> str:
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(buffer):
            (tree_view or self.tree_view).on_click(self.items[name])
        return buffer.getvalue()

    def _drawn_ids(self) -> list[str]:
        return [d["id"] for d in json.loads(self.widget.gui.nodes)]

    def test_each_click_adds_a_uniquely_labelled_node(self):
        self._click("add")
        self._click("add")
        self.assertEqual(list(self.widget.wf.nodes), ["add_0", "add_1"])
        self.assertEqual(self._drawn_ids(), ["add_0", "add_1"])

    def test_factory_definition_is_added(self):
        self._click("legacy")
        self.assertEqual(list(self.widget.wf.nodes), ["legacy_0"])
        self.assertEqual(list(self.widget.wf.nodes["legacy_0"].outputs), ["z"])

    def test_failed_add_leaves_the_graph_unchanged(self):
        self._click("add")
        printed = self._click("unparseable")
        self.assertEqual(list(self.widget.wf.nodes), ["add_0"])
        self.assertEqual(self._drawn_ids(), ["add_0"])
        self.assertIn("Error:", printed)

    def test_handle_click_adds_the_definition(self):
        with contextlib.redirect_stdout(io.StringIO()):
            self.tree_view.handle_click({"owner": self.items["plain"]})
        self.assertEqual(list(self.widget.wf.nodes), ["plain_0"])

    def test_click_without_a_flow_widget_does_nothing(self):
        detached = treeview.TreeView(
            root_path=self.nodes_file.parent, log=widgets.Output()
        )
        self._click("add", tree_view=detached)
        self.assertEqual(list(self.widget.wf.nodes), [])

    def test_failed_add_shows_the_output_tab(self):
        accordion = widgets.Accordion(
            children=[widgets.Output(), widgets.Output(), widgets.Output()]
        )
        self.widget.accordion_widget = accordion
        self._click("unparseable")
        self.assertEqual(accordion.selected_index, reactflow.AccordionTab.OUTPUT.index)

    def test_successful_add_leaves_the_accordion_alone(self):
        accordion = widgets.Accordion(
            children=[widgets.Output(), widgets.Output(), widgets.Output()]
        )
        self.widget.accordion_widget = accordion
        self._click("add")
        self.assertIsNone(accordion.selected_index)


class TestSysPath(_FixtureFiles):
    def _tree_view(self, root: Path) -> treeview.TreeView:
        return treeview.TreeView(root_path=root, log=widgets.Output())

    def test_import_root_of_a_plain_directory(self):
        self.assertEqual(
            treeview.import_root(self.loose_file.parent), self.loose_file.parent
        )

    def test_import_root_of_a_package(self):
        self.assertEqual(treeview.import_root(self.nodes_file.parent), self.root)

    def test_missing_root_is_added_and_close_removes_it(self):
        entry = str(self.loose_file.parent)
        tree_view = self._tree_view(self.loose_file.parent)
        self.assertEqual(sys.path.count(entry), 1)
        tree_view.close()
        self.assertNotIn(entry, sys.path)
        tree_view.close()
        self.assertNotIn(entry, sys.path)

    def test_package_root_path_adds_its_import_root(self):
        tree_view = self._tree_view(self.root / self.PACKAGE)
        self.assertIn(str(self.root), sys.path)
        tree_view.close()
        self.assertNotIn(str(self.root), sys.path)

    def test_entry_already_present_is_left_alone(self):
        entry = str(self.loose_file.parent)
        sys.path.append(entry)
        tree_view = self._tree_view(self.loose_file.parent)
        self.assertEqual(sys.path.count(entry), 1)
        tree_view.close()
        self.assertIn(entry, sys.path)

    def test_relative_entry_for_the_same_directory_counts(self):
        sys.path.append(os.path.relpath(self.loose_file.parent))
        before = list(sys.path)
        tree_view = self._tree_view(self.loose_file.parent)
        self.assertEqual(sys.path, before)
        tree_view.close()
        self.assertEqual(sys.path, before)

    def test_tree_view_makes_its_root_importable(self):
        self._tree_view(self.loose_file.parent)
        imported = retrieve.import_from_string(f"{self.LOOSE}.loose_add")
        self.assertEqual(imported.__name__, "loose_add")


if __name__ == "__main__":
    unittest.main()
