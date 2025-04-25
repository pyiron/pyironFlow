from contextlib import contextmanager
import pathlib
from typing import Literal
from dataclasses import dataclass
from enum import Enum
import json
import sys
import inspect
import re

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
    NODE_WIDTH
)
from pyiron_workflow.channels import ChannelConnectionError
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

_CHANNEL_CONNECTION_REGEX = '.*/[^/]+/(.*)\.type_hint = (.*); /[^/]+/(.*)\.type_hint = (.*)$'
_CHANNEL_TYPE_REGEX = \
    "^The channel /[^/]/([^\w]+) cannot take the value .* not compliant with the type hint (.*)$"


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
                widget.update_status()

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
        except ReadinessError as err:
            with out:
                print("The following node require inputs before you can run the graph:")
                def clean(s):
                    if s.startswith("inputs."):
                        s = s[len("inputs."):]
                    return s.replace("__", ".")
                unready_channels = [clean(k) for k, v in err.readiness_dict.items()
                                        if not v and k not in ("ready", "running", "failed")]
                print(*unready_channels, sep='\n')
            with log:
                sys.excepthook(*sys.exc_info())
        except ChannelConnectionError as err:
            with out:
                groups = re.match(_CHANNEL_CONNECTION_REGEX, err.args[0]).groups()
                if groups is not None and len(groups) == 4:
                    leftchannel, lefttype, rightchannel, righttype = groups
                    print(f"Error: Cannot connect {leftchannel} to {rightchannel}!\n"
                            f"Their types do not match {lefttype} != {righttype}.")
                else:
                    print("Error: Could not connect some edges because of type mismatch!")
            with log:
                sys.excepthook(*sys.exc_info())
        except TypeError as err:
            with out:
                groups = re.match(_CHANNEL_TYPE_REGEX, err.args[0])
                if groups is not None and len(groups) == 2:
                    channel, typehint = groups
                    print(f"Channel {channel} connected to wrong type! Should be {typehint}.")
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
                            self.wf.failed = False
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
                                self.display_return_value(node.push)
                            self.update_status()
                        case "output":
                            if error_message:
                                print(f"Could fetch outputs from node {node_name}!")
                            else:
                                for out in node.outputs:
                                    print(out.label + ":")
                                    display(out.value)
                                    print("")
                            self.update_status()
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
                    -view['x'] + 0.1 * view['height'],
                    -view['y'] + 0.9 * view['height'],
            ]

        def blocked():
            for node in self.wf.children.values():
                if 'position' in dir(node):
                    if node.position == tuple(position):
                        return True
            return False
        while blocked():
            position[0] += NODE_WIDTH + 10

        return tuple(position)

    def add_node(self, node_path, label):
        self.wf = self.get_workflow()
        node = get_node_from_path(node_path, log=self.log)
        node.position = self.place_new_node()
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
