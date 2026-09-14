import ast
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

import pyiron_workflow as pwf
from ipytree import Node, Tree
from ipywidgets import Button, VBox
from pyiron_snippets import retrieve
from pyiron_workflow import datatypes

__author__ = "Joerg Neugebauer"
__copyright__ = (
    "Copyright 2024, Max-Planck-Institut for Sustainable Materials GmbH - "
    "Computational Materials Design (CM) Department"
)
__version__ = "0.2"
__maintainer__ = ""
__email__ = ""
__status__ = "development"
__date__ = "Aug 1, 2024"


# Note: available icons and types in ipytree
# - style_values = ["warning", "danger", "success", "info", "default"]
# - icons: https://fontawesome.com/v5/search?q=node&o=r (version 5) appears to work


class NodeKind(Enum):
    """What the tree view recognised a top-level definition as."""

    ATOMIC = "atomic"
    WORKFLOW = "workflow"
    DATACLASS = "dataclass"
    PLAIN = "plain"

    @property
    def icon(self) -> str:
        return _KIND_ICONS[self][0]

    @property
    def icon_style(self) -> str:
        """ipytree's icon colour."""
        return _KIND_ICONS[self][1]


_KIND_ICONS: dict[NodeKind, tuple[str, str]] = {
    NodeKind.ATOMIC: ("codepen", "danger"),
    NodeKind.WORKFLOW: ("sitemap", "info"),
    NodeKind.DATACLASS: ("table", "success"),
    NodeKind.PLAIN: ("code", "default"),
}


@dataclass(frozen=True)
class NodeDefinition:
    """A top-level function or class found by parsing a python file.

    ``factory`` marks definitions decorated by ``pyiron_workflow``'s compatibility
    decorators, whose imported object must be called to produce a node.
    """

    name: str
    path: Path
    kind: NodeKind
    factory: bool = False


NODE_DECORATORS: dict[str, tuple[NodeKind, bool]] = {
    "flowrep.atomic": (NodeKind.ATOMIC, False),
    "flowrep.tools.atomic": (NodeKind.ATOMIC, False),
    "flowrep.workflow": (NodeKind.WORKFLOW, False),
    "flowrep.tools.workflow": (NodeKind.WORKFLOW, False),
    "flowrep.dataclass": (NodeKind.DATACLASS, False),
    "flowrep.tools.dataclass": (NodeKind.DATACLASS, False),
    "pyiron_workflow.as_function_node": (NodeKind.ATOMIC, True),
    "pyiron_workflow.as_macro_node": (NodeKind.WORKFLOW, True),
}

_SCOPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)


def import_aliases(tree: ast.Module) -> dict[str, str]:
    """Map each name bound by a module-level import to its fully qualified path.

    Imports nested in module-level compound statements (``try``, ``if``, ``with``)
    count; imports inside function or class bodies do not. Relative imports are
    ignored, and a later binding of a name overwrites an earlier one.
    """
    aliases: dict[str, str] = {}
    _collect_aliases(tree.body, aliases)
    return aliases


def _collect_aliases(nodes: Iterable[ast.AST], aliases: dict[str, str]) -> None:
    for node in nodes:
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.asname is None:
                    head = alias.name.split(".")[0]
                    aliases[head] = head
                else:
                    aliases[alias.asname] = alias.name
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module is not None:
                for alias in node.names:
                    local = alias.asname or alias.name
                    aliases[local] = f"{node.module}.{alias.name}"
        elif not isinstance(node, _SCOPES):
            _collect_aliases(ast.iter_child_nodes(node), aliases)


def resolve_decorator(decorator: ast.expr, aliases: dict[str, str]) -> str | None:
    """Fully qualified dotted path of a decorator, or ``None`` if it has no such form.

    A called decorator resolves as its callee; the leading name is expanded through
    *aliases*.
    """
    target = decorator.func if isinstance(decorator, ast.Call) else decorator
    parts: list[str] = []
    while isinstance(target, ast.Attribute):
        parts.insert(0, target.attr)
        target = target.value
    if not isinstance(target, ast.Name):
        return None
    return ".".join([aliases.get(target.id, target.id), *parts])


def list_definitions(file: Path, log=None) -> list[NodeDefinition]:
    """Top-level functions and classes of *file*, classified by their decorators.

    Undecorated definitions (or ones with only unrecognised decorators) are ``PLAIN``
    and are skipped when private. A file that does not parse yields nothing, with a
    message appended to *log* when one is given.
    """
    try:
        tree = ast.parse(file.read_text())
    except SyntaxError as error:
        if log is not None:
            log.append_stderr(f"Could not parse {file}: {error}\n")
        return []

    aliases = import_aliases(tree)
    definitions = []
    for statement in tree.body:
        if not isinstance(statement, (ast.FunctionDef, ast.ClassDef)):
            continue
        kind, factory = _classify(statement, aliases)
        if kind is NodeKind.PLAIN and statement.name.startswith("_"):
            continue
        definitions.append(NodeDefinition(statement.name, file, kind, factory))
    return definitions


def _classify(
    definition: ast.FunctionDef | ast.ClassDef, aliases: dict[str, str]
) -> tuple[NodeKind, bool]:
    for decorator in definition.decorator_list:
        resolved = resolve_decorator(decorator, aliases)
        if resolved is not None and resolved in NODE_DECORATORS:
            return NODE_DECORATORS[resolved]
    return NodeKind.PLAIN, False


def module_location(file: Path) -> tuple[str, Path | None]:
    """Dotted module name for *file*, and a directory it needs on ``sys.path``.

    A file inside a package is named from the outermost directory of its unbroken
    chain of ``__init__.py``-carrying parents; that package must already be
    importable, so no directory is returned. A file whose own directory is not a
    package is a loose script, importable by its stem from its directory.
    """
    file = file.resolve()
    if not (file.parent / "__init__.py").exists():
        return file.stem, file.parent
    parts = [file.stem]
    directory = file.parent
    while (directory / "__init__.py").exists():
        parts.insert(0, directory.name)
        directory = directory.parent
    return ".".join(parts), None


def import_definition(definition: NodeDefinition) -> Any:
    """Import the object *definition* names, appending a loose script's directory
    to ``sys.path`` first if it is not already there."""
    module, sys_path_entry = module_location(definition.path)
    if sys_path_entry is not None and str(sys_path_entry) not in sys.path:
        sys.path.append(str(sys_path_entry))
    return retrieve.import_from_string(f"{module}.{definition.name}")


def instantiate(definition: NodeDefinition, label: str) -> datatypes.Node:
    """Import *definition* and build a node from it labelled *label*.

    ``pyiron_workflow`` compatibility factories are called to get their node, which
    ``pyiron_workflow.node`` then copies under *label*. Import and parsing errors
    propagate.
    """
    obj = import_definition(definition)
    return pwf.node(obj() if definition.factory else obj, label)


def get_rel_path_for_last_occurrence(path: Path, relpath_start: str) -> int:
    assert relpath_start in path.parts
    # Reverse the list and find the first (last in original list) occurrence
    reversed_parts = path.parts[::-1]  # this does not modify the original list
    last_occurrence = len(path.parts) - 1 - reversed_parts.index(relpath_start)

    rel_path = Path(*path.parts[last_occurrence:])
    rel_path_no_ext = rel_path.with_suffix("")
    return rel_path_no_ext


class TreeView:
    def __init__(self, root_path: str | Path, flow_widget=None, log=None):
        """
        This function generates and returns a tree view of nodes starting from the
        root_path directory.

        Args:
            root_path (str | Path): root directory path from which the tree starts.
        """
        import copy

        self.path = copy.copy(root_path)
        if isinstance(self.path, str):
            self.path = Path(root_path)

        self.flow_widget = flow_widget
        self.log = log  # logging widget

        self.refresh_button = Button(
            description="Refresh", disabled=False, button_style="info"
        )

        self.tree = Tree(stripes=True)
        self.add_nodes(self.tree, parent_node=self.path)

        self.refresh_button.on_click(self.update_tree)
        # the following flag is needed since handle click sends two signals,
        # the first repeats the last one from the previous click
        self._handle_click_is_last_event = True

        self.gui = VBox([self.refresh_button, self.tree])

    def update_tree(self, b=None):
        for tree_nodes in self.tree.nodes:
            self.tree.remove_node(tree_nodes)
        self.add_nodes(self.tree, parent_node=self.path)

    def handle_click(self, event):
        """
        This function handles click events by adding nodes to the selected object
        if it does not already have any nodes.

        Args:
            event (dict): dictionary representing the event object.

        Note:
            The event object should include the owner of the event (the object
            that was clicked), and the owner should have a 'nodes' property (a
            list of nodes) and a 'path' property (the path to the node).
        """
        if not self._handle_click_is_last_event:
            self._handle_click_is_last_event = True
            return
        self._handle_click_is_last_event = False

        selected_node = event["owner"]

        if isinstance(selected_node.path, NodeDefinition):
            selected_node.on_click(selected_node)
        elif (len(selected_node.nodes)) == 0:
            self.add_nodes(selected_node, selected_node.path)

    def on_click(self, node):
        import os

        path = os.path.join(
            get_rel_path_for_last_occurrence(node.path.path, "pyiron_nodes"),
            node.path.name,
        )
        path_str = str(path).replace(os.sep, ".")
        if self.flow_widget is not None:
            self.flow_widget.add_node(str(path_str), node.path.name)

    def add_nodes(self, tree, parent_node):
        """
        This function adds child nodes to a parent node in a tree. It assumes
        the input is an Abstract Syntax Tree (AST). It creates new nodes based
        on the attributes of the parent node, updates icon style based on the
        type of node and finally adds child nodes to the parent.

        Args:
            tree (Tree): Abstract Syntax Tree
            parent_node (Node): node of the AST to which child nodes must be
                added

        """

        for node in self.list_nodes(parent_node):
            name_lst = node.name.split(".")
            if len(name_lst) > 1:
                if name_lst[-1] == "py":
                    node_tree = Node(name_lst[0])
                    node_tree.icon = "archive"  # 'file'
                    node_tree.icon_style = "success"
                else:
                    continue
            else:
                node_tree = Node(node.name)
                if isinstance(node, NodeDefinition):
                    node_tree.icon = node.kind.icon
                    node_tree.icon_style = node.kind.icon_style
                else:
                    node_tree.icon = "folder"  # 'info', 'copy', 'archive'
                    node_tree.icon_style = "warning"

            node_tree.path = node
            tree.add_node(node_tree)
            if self.on_click is not None:
                node_tree.on_click = self.on_click

            node_tree.observe(self.handle_click, "selected")

    def list_nodes(self, node: Path):
        """
        Return a list of child directories and python files of a given Path' node'.
        Child directories and python files starting with '.' or '_' are excluded.

        Args:
            node (Path): A directory or a python file.

        Returns:
            nodes (list[Path]): List of child directories and python files. For
                python file 'node', list_definitions(node) is called and the
                definitions are added.
        """
        node_path = node

        nodes = []
        if node.is_dir():
            for child in node_path.iterdir():
                if (
                    child.is_dir()
                    and not child.name.startswith(".")
                    and not child.name.startswith("_")
                ):
                    nodes.append(child)

            for child in node_path.glob("*.py"):
                if not child.name.startswith(".") and not child.name.startswith("_"):
                    nodes.append(child)

        elif node.is_file():
            for child in list_definitions(node, log=self.log):
                nodes.append(child)

        return nodes
