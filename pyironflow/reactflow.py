from contextlib import contextmanager
import pathlib
from typing import Literal
from dataclasses import dataclass
from enum import Enum
import json
import sys
import inspect

import anywidget
import traitlets
from IPython.core import ultratb
from pygments import highlight
from pygments.lexers import PythonLexer
from pygments.formatters import TerminalFormatter

from pyiron_workflow import Workflow
from pyiron_workflow.node import Node
from pyiron_workflow.nodes.transform import DataclassNode
from pyiron_workflow.nodes.function import Function as FunctionNode
from pyiron_workflow.nodes.macro import Macro as MacroNode
from pyironflow.wf_extensions import (
    get_nodes,
    get_edges,
    get_node_from_path,
    dict_to_node,
    dict_to_edge,
    create_macro,
)
from pyiron_workflow.mixin.run import ReadinessError

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


@contextmanager
def FormattedTB():
    sys_excepthook = sys.excepthook
    sys.excepthook = ultratb.FormattedTB(mode="Verbose", color_scheme="Neutral")
    yield
    sys.excepthook = sys_excepthook


def highlight_node_source(node: Node) -> str:
    """Extract and highlight source code of a node.

    Supported node types are function node, dataclass nodes and 'graph creator'.

    Args:
        node (pyiron_workflow.node.Node): node to extract source from

    Returns:
        highlighted source code.
    """
    try:
        match node:
            case FunctionNode():
                code = inspect.getsource(node.node_function)
            case MacroNode():
                code = inspect.getsource(node.graph_creator)
            case DataclassNode():
                code = inspect.getsource(node.dataclass)
            case _:
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

    def handle(self, widget: 'PyironFlowWidget'):
        """Execute command on widget."""
        match self:
            case GlobalCommand.RUN:
                widget.select_output_widget()
                widget.out_widget.clear_output()
                widget.display_return_value(widget.wf.run)

            case GlobalCommand.SAVE:
                widget.select_output_widget()
                widget.wf.save()
                print(f"Successfully saved in {widget.wf.label}.")

            case GlobalCommand.LOAD:
                widget.select_output_widget()
                try:
                    widget.wf.load()
                    widget.update()
                    print(f"Successfully loaded from {widget.wf.label}.")
                except FileNotFoundError:
                    widget.update()
                    print(f"Save file {widget.wf.label} not found!")

            case GlobalCommand.DELETE:
                widget.select_output_widget()
                widget.wf.delete_storage()
                print(f"Deleted {widget.wf.label}.")

@dataclass
class NodeCommand:
    """Specifies a command to run a node or selection of them."""

    command: Literal["source", "run", "delete_node", "macro", "reset"]
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


class PyironFlowWidget:
    def __init__(
        self,
        root_path="../pyiron_nodes/pyiron_nodes",
        wf: Workflow = Workflow(label="workflow"),
        log=None,
        out_widget=None,
        reload_node_library=False,
    ):
        self.log = log
        self.out_widget = out_widget
        self.accordion_widget = None
        self.tree_widget = None
        self.gui = ReactFlowWidget(layout={'height': '100%'})
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
        with FormattedTB():
            try:
                display(func())
            except ReadinessError as err:
                print(err.args[0])
            except Exception as e:
                print("Error:", e)
                sys.excepthook(*sys.exc_info())
            finally:
                self.update_status()

    def on_value_change(self, change):


        self.out_widget.clear_output()

        error_message = ""

        with FormattedTB():
            try:
                self.wf = self.get_workflow()
            except Exception as error:
                print("Error:", error)
                error_message = error

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
                    if node_name not in self.wf.children:
                        return
                    node = self.wf.children[node_name]
                    self.select_output_widget()
                    match command:
                        case "reset":
                            node.failed = False
                            node.running = False
                            if node.use_cache:
                                node._cached_inputs = {}
                            self.update_status()
                        case "source":
                            print(highlight_node_source(node))
                        case "run":
                            self.out_widget.clear_output()
                            if error_message:
                                print("Error:", error_message)
                            self.display_return_value(node.pull)
                        case "delete_node":
                            self.wf.remove_child(node_name)
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
        temp_nodes = get_nodes(self.wf)
        temp_edges = get_edges(self.wf)
        self.wf = self.get_workflow()
        actual_nodes = get_nodes(self.wf)
        actual_edges = get_edges(self.wf)
        for i in range(len(actual_nodes)):
            actual_nodes[i]["data"]["failed"] = temp_nodes[i]["data"]["failed"]
            actual_nodes[i]["data"]["running"] = temp_nodes[i]["data"]["running"]
            actual_nodes[i]["data"]["ready"] = temp_nodes[i]["data"]["ready"]
        self.gui.nodes = json.dumps(actual_nodes)
        self.gui.edges = json.dumps(actual_edges)

    @property
    def react_flow_widget(self):
        return self.gui

    def add_node(self, node_path, label):
        self.wf = self.get_workflow()
        node = get_node_from_path(node_path, log=self.log)
        if node is not None:
            self.log.append_stdout(f"add_node (reactflow): {node}, {label} \n")
            if label in self.wf.child_labels:
                self.wf.strict_naming = False

            self.wf.add_child(node(label=label))

            self.update()

    def get_workflow(self):
        wf = self.wf
        dict_nodes = json.loads(self.gui.nodes)
        for dict_node in dict_nodes:
            node = dict_to_node(dict_node, wf.children, reload=self.reload_node_library)
            if node not in wf.children.values():
                # new node appeared in GUI with the same name, but different
                # id, i.e. user removed and added something in place
                if node.label in wf.children:
                    # FIXME look at replace_child
                    wf.remove_child(node.label)
                wf.add_child(node)

        dict_edges = json.loads(self.gui.edges)
        for dict_edge in dict_edges:
            dict_to_edge(dict_edge, wf.children)

        return wf

    def get_selected_workflow(self):
        wf = Workflow("temp_workflow")
        dict_nodes = json.loads(self.gui.selected_nodes)
        node_labels = []
        for dict_node in dict_nodes:
            node = dict_to_node(dict_node)
            wf.add_child(node)
            node_labels.append(dict_node["data"]["label"])
            # wf.add_child(node(label=node.label))
        print("\nSelected nodes:")
        print(node_labels)

        nodes = wf.children
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
            dict_to_edge(dict_edge, nodes)

        return wf
