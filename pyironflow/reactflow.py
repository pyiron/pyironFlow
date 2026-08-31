import inspect
import json
import pathlib
import sys
from contextlib import contextmanager
from dataclasses import dataclass
from enum import Enum
from typing import Literal

import anywidget
import traitlets
from IPython.core import ultratb
from pygments import highlight
from pygments.formatters import TerminalFormatter
from pygments.lexers import PythonLexer
from pyiron_workflow import Workflow
from pyiron_workflow.constructors import atomictype2node
from pyiron_workflow.dag import Macro
from pyiron_workflow.datatypes import Node

from pyironflow.wf_extensions import (
    NODE_WIDTH,
    _is_const_node,
    apply_node_values,
    create_macro,
    dict_to_edge,
    dict_to_node,
    get_edges,
    get_node_from_path,
    get_nodes,
)

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

_CHANNEL_CONNECTION_REGEX = r".*/[^/]+/(.*)\.\w+ = (.*); /[^/]+/(.*)\.\w+ = (.*)$"
_CHANNEL_TYPE_REGEX = r"^The channel /[^/]/([^\w]+) cannot take the value .* not compliant with the type hint (.*)$"


@contextmanager
def FormattedTB():
    sys_excepthook = sys.excepthook
    sys.excepthook = ultratb.FormattedTB(mode="Verbose", theme_name="Neutral")
    yield
    sys.excepthook = sys_excepthook


def highlight_node_source(node: Node) -> str:
    """Extract and highlight source code of a node.

    Supported node types are Atomic nodes (function-based) and Macro nodes.

    Args:
        node (pyiron_workflow.datatypes.Node): node to extract source from

    Returns:
        highlighted source code.
    """
    try:
        recipe = getattr(node, "recipe", None)
        if recipe is not None and hasattr(recipe, "fully_qualified_name"):
            fqn = recipe.fully_qualified_name
            module_path, _, name = fqn.rpartition(".")
            import importlib as _importlib

            module = _importlib.import_module(module_path)
            obj = getattr(module, name)
            code = inspect.getsource(obj)
        elif isinstance(node, Macro):
            code = inspect.getsource(type(node))
        else:
            return "Function to extract code not implemented!"
        return highlight(code, PythonLexer(), TerminalFormatter())
    except OSError as e:
        if e.args[0] == "could not find class definition":
            return "Could not locate source code."
        raise


class GlobalCommand(Enum):
    """Types of commands pertaining to the full workflow."""

    RUN = "run"
    SAVE = "save"
    LOAD = "load"
    DELETE = "delete"

    def handle(self, widget: "PyironFlowWidget"):
        """Execute command on widget."""
        match self:
            case GlobalCommand.RUN:
                widget.select_output_widget()
                widget.out_widget.clear_output()
                widget.display_return_value(widget.wf.run)
                widget.update_status()

            case GlobalCommand.SAVE:
                widget.select_output_widget()
                print("Save/load is not supported in this version of pyiron_workflow.")

            case GlobalCommand.LOAD:
                widget.select_output_widget()
                print("Save/load is not supported in this version of pyiron_workflow.")

            case GlobalCommand.DELETE:
                widget.select_output_widget()
                print(
                    "Storage deletion is not supported in this version of pyiron_workflow."
                )


@dataclass
class NodeCommand:
    """Specifies a command to run a node or selection of them."""

    command: Literal["source", "pull", "push", "delete_node", "macro", "reset"]
    node: str


def parse_command(com: str) -> GlobalCommand | NodeCommand:
    """Parses commands from GUI into the correct command class."""
    print("command: ", com)
    if "executed at" in com:
        return GlobalCommand(com.split(" ")[0])

    command_name, node_name = com.split(":")
    node_name = node_name.split("-")[0].strip()
    return NodeCommand(command_name, node_name)


class ReactFlowWidget(anywidget.AnyWidget):
    path = pathlib.Path(__file__).parent / "static"
    _esm = path / "widget.js"
    _css = path / "widget.css"
    nodes = traitlets.Unicode("[]").tag(sync=True)
    edges = traitlets.Unicode("[]").tag(sync=True)
    selected_nodes = traitlets.Unicode("[]").tag(sync=True)
    selected_edges = traitlets.Unicode("[]").tag(sync=True)
    commands = traitlets.Unicode("[]").tag(sync=True)
    # position and size of the current view on the graph in JS space
    view = traitlets.Unicode("{}").tag(sync=True)


@contextmanager
def GentleError(out, log):
    """Catch various exception from workflows and try to print nicer messages.

    Args:
        out: widget for "normal" output immediately visible to user
        log: widget for "logging" output only visible after a click
    """
    try:
        try:
            yield
        except Exception as err:
            with out:
                print(f"Error: {err}")
            with log:
                sys.excepthook(*sys.exc_info())
    except Exception as e:
        print("Error:", e)
        with log:
            sys.excepthook(*sys.exc_info())
    finally:
        pass


class PyironFlowWidget:
    def __init__(
        self,
        root_path: None | str | pathlib.Path = None,
        wf: Workflow = None,
        log=None,
        out_widget=None,
        reload_node_library=False,
    ):
        if root_path is None:
            root_path = str(pathlib.Path(__file__).parent / "pyiron_nodes/pyiron_nodes")
        if wf is None:
            wf = Workflow("workflow")
        self.log = log
        self.out_widget = out_widget
        self.accordion_widget = None
        self.tree_widget = None
        self.gui = ReactFlowWidget(layout={"height": "100%"})
        self.wf = wf
        self.root_path = root_path
        self.reload_node_library = reload_node_library

        self.gui.observe(self.on_value_change, names="commands")

        self.update()

    def select_output_widget(self):
        """Makes sure output widget is visible if accordion is set."""
        if self.accordion_widget is not None:
            self.accordion_widget.selected_index = 1

    def display_return_value(self, func):
        from IPython.display import display

        with FormattedTB(), GentleError(self.out_widget, self.log):
            display(func())

    def on_value_change(self, change):

        self.out_widget.clear_output()

        error_message = ""

        with FormattedTB(), GentleError(self.out_widget, self.log):
            try:
                self.wf = self.get_workflow()
            except Exception as error:
                error_message = error
                raise

        if "done" in change["new"]:
            return

        import warnings

        with self.out_widget, warnings.catch_warnings(action="ignore"):
            match parse_command(change["new"]):
                case GlobalCommand() as command:
                    command.handle(self)
                case NodeCommand("macro", node_name):
                    self.select_output_widget()
                    create_macro(
                        self.get_selected_workflow(), node_name, self.root_path
                    )
                    if self.tree_widget is not None:
                        self.tree_widget.update_tree()

                case NodeCommand(command, node_name):
                    if node_name not in self.wf.nodes:
                        return
                    node = self.wf.nodes[node_name]
                    self.select_output_widget()
                    match command:
                        case "reset":
                            self.wf = self.get_workflow()
                            self.update_status()
                        case "source":
                            print(highlight_node_source(node))
                        case "pull":
                            if error_message:
                                print(f"Could not pull on node {node_name}!")
                            else:
                                self.display_return_value(node.pull)
                            self.update_status()
                        case "push":
                            if error_message:
                                print(f"Could not push from node {node_name}!")
                            else:
                                print(
                                    "Push is not supported in this version of pyiron_workflow."
                                )
                            self.update_status()
                        case "output":
                            if error_message:
                                print(f"Could fetch outputs from node {node_name}!")
                            else:
                                from IPython.display import display

                                for out_label in node.outputs:
                                    print(out_label + ":")
                                    # get value from last run
                                    val = None
                                    if self.wf.last_run is not None:
                                        node_data = self.wf.last_run.result.nodes.get(
                                            node_name
                                        )
                                        if node_data is not None:
                                            out_port_data = node_data.output_ports.get(
                                                out_label
                                            )
                                            if out_port_data is not None:
                                                val = out_port_data.value
                                    display(val)
                                    print()
                            self.update_status()
                        case "delete_node":
                            self.wf.remove_node(node_name)
                        case command:
                            print(f"ERROR: unknown command: {command}!")
                case unknown:
                    print(f"Command not yet implemented: {unknown}")

    def update(self):
        nodes = get_nodes(self.wf)
        edges = get_edges(self.wf)
        self.gui.nodes = json.dumps(nodes)
        self.gui.edges = json.dumps(edges)

    def update_status(self):
        self.wf = self.get_workflow()
        actual_nodes = get_nodes(self.wf)
        actual_edges = get_edges(self.wf)
        self.gui.nodes = json.dumps(actual_nodes)
        self.gui.edges = json.dumps(actual_edges)

    @property
    def react_flow_widget(self):
        return self.gui

    def place_new_node(self):
        """Find a suitable location in UI space for the newly added node.

        Exact layouting not required as this can be done in UI, but newly added
        nodes should be visible to the user and not completely overlap.

        FIXME: Probably this is better handled completely in UI by elk.
        """
        view = json.loads(self.gui.view)
        if view == {}:
            position = [0, 0]
        else:
            position = [
                -view["x"] + 0.1 * view["height"],
                -view["y"] + 0.9 * view["height"],
            ]

        def blocked():
            for node in self.wf.nodes.values():
                if _is_const_node(node.label):
                    continue
                if hasattr(node, "position"):
                    if node.position == tuple(position):
                        return True
            return False

        while blocked():
            position[0] += NODE_WIDTH + 10

        return tuple(position)

    def add_node(self, node_path, label):
        self.wf = self.get_workflow()
        func = get_node_from_path(node_path, log=self.log)
        if func is None:
            return
        node = atomictype2node(func, label)
        node.position = self.place_new_node()
        self.log.append_stdout(f"add_node (reactflow): {node}, {label} \n")
        self.wf.add_node(node)
        self.update()

    def get_workflow(self):
        wf = self.wf
        dict_nodes = json.loads(self.gui.nodes)
        for dict_node in dict_nodes:
            node = dict_to_node(
                dict_node, dict(wf.nodes), wf=wf, reload=self.reload_node_library
            )
            if node is None:
                continue
            if node not in wf.nodes.values():
                # New node appeared in GUI with the same name but different id –
                # user removed and added something in place.
                if node.label in wf.nodes:
                    wf.remove_node(node.label)
                wf.add_node(node)
            apply_node_values(node, wf)

        dict_edges = json.loads(self.gui.edges)
        for dict_edge in dict_edges:
            dict_to_edge(dict_edge, dict(wf.nodes), wf)

        return wf

    def get_selected_workflow(self):
        wf = Workflow("temp_workflow")
        dict_nodes = json.loads(self.gui.selected_nodes)
        node_labels = []
        for dict_node in dict_nodes:
            node = dict_to_node(dict_node, {}, wf=wf)
            if node is None:
                continue
            wf.add_node(node)
            apply_node_values(node, wf)
            node_labels.append(dict_node["data"]["label"])
        print("\nSelected nodes:")
        print(node_labels)

        dict_edges = json.loads(self.gui.selected_edges)
        subset_dict_edges = []
        edge_labels = []
        for edge in dict_edges:
            if edge["source"] in node_labels and edge["target"] in node_labels:
                subset_dict_edges.append(edge)
                edge_labels.append(edge["id"])
        print("\nSelected edges:")
        print(edge_labels)

        for dict_edge in subset_dict_edges:
            dict_to_edge(dict_edge, dict(wf.nodes), wf)

        return wf
