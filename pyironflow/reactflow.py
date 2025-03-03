from pyiron_workflow import Workflow
from pyiron_workflow.node import Node
from pyironflow.wf_extensions import (
    get_nodes,
    get_edges,
    get_node_from_path,
    dict_to_node,
    dict_to_edge,
    create_macro
)
from pyiron_workflow.mixin.run import ReadinessError

import anywidget
import pathlib
import traitlets
import os
from typing import Literal
from dataclasses import dataclass
from enum import Enum
import json
import traceback
import sys
from contextlib import contextmanager
from IPython.core import ultratb
import inspect
from pygments import highlight
from pygments.lexers import PythonLexer
from pygments.formatters import TerminalFormatter


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
    sys.excepthook = ultratb.FormattedTB(mode="Verbose", color_scheme='Neutral')
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
    if hasattr(node, 'node_function'):
        code = inspect.getsource(node.node_function)
    elif hasattr(node, 'graph_creator'):
        code = inspect.getsource(node.graph_creator)
    elif hasattr(node, 'dataclass'):
        code = inspect.getsource(node.dataclass)
    else:
        code = 'Function to extract code not implemented!'

    return highlight(code, PythonLexer(), TerminalFormatter())


class GlobalCommand(Enum):
    RUN = "run"
    SAVE = "save"
    LOAD = "load"
    DELETE = "delete"


@dataclass
class NodeCommand:
    """Specifies a command to run a node or selection of them."""
    command: Literal["source", "run", "delete_node", "macro"]
    node: str


def parse_command(com: str) -> GlobalCommand | NodeCommand:
    """Parses commands from GUI into the correct command class."""
    print('command: ', com)
    if 'executed at' in com:
        return GlobalCommand(com.split(' ')[0])

    command_name, node_name = com.split(':')
    node_name = node_name.split('-')[0].strip()
    return NodeCommand(command_name, node_name)


class ReactFlowWidget(anywidget.AnyWidget):
    path = pathlib.Path(__file__).parent / "static"
    _esm = path / "widget.js"
    _css = path / "widget.css"
    nodes = traitlets.Unicode('[]').tag(sync=True)
    edges = traitlets.Unicode('[]').tag(sync=True)
    selected_nodes = traitlets.Unicode('[]').tag(sync=True)
    selected_edges = traitlets.Unicode('[]').tag(sync=True)
    commands = traitlets.Unicode('[]').tag(sync=True)


class PyironFlowWidget:
    def __init__(self, root_path='../pyiron_nodes/pyiron_nodes', wf: Workflow = Workflow(label='workflow'), log=None, out_widget=None):
        self.log = log
        self.out_widget = out_widget
        self.accordion_widget = None
        self.tree_widget = None
        self.gui = ReactFlowWidget()
        self.wf = wf
        self.root_path = root_path

        self.gui.observe(self.on_value_change, names='commands')

        self.update()

    def on_value_change(self, change):
        from IPython.display import display

        def display_return_value(func):
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

        self.out_widget.clear_output()

        error_message = ""

        with FormattedTB():
            try:
                self.wf = self.get_workflow()
            except Exception as error:
                print("Error:", error)
                error_message = error

        if 'done' in change['new']:
            return

        with self.out_widget:
            import warnings

            with warnings.catch_warnings():
                warnings.simplefilter("ignore")

                command = parse_command(change['new'])
                match command:
                    case GlobalCommand():
                        global_command = command
                        command = ''
                    case NodeCommand():
                        global_command = ''
                if command != '' and command.command != 'macro' and command.node != '':
                    if command.node not in self.wf.children:
                        return
                    node = self.wf.children[command.node]
                    # print(change['new'], command, node.label)
                    if self.accordion_widget is not None:
                        self.accordion_widget.selected_index = 1
                    if command.command == 'source':
                        print(highlight_node_source(node))
                    elif command.command == 'run':
                        self.out_widget.clear_output()

                        if error_message:
                            print("Error:", error_message)

                        display_return_value(node.pull)
                    elif command.command == 'delete_node':
                        self.wf.remove_child(command.node)

                elif command != "" and command.command == 'macro' and command.node != '':
                    if self.accordion_widget is not None:
                        self.accordion_widget.selected_index = 1
                    create_macro(self.get_selected_workflow(), command.node, self.root_path)
                    if self.tree_widget is not None:
                        self.tree_widget.update_tree()

                elif global_command == GlobalCommand.RUN:
                    if self.accordion_widget is not None:
                        self.accordion_widget.selected_index = 1
                    self.out_widget.clear_output()

                    display_return_value(self.wf.run)

                elif global_command == GlobalCommand.SAVE:
                    if self.accordion_widget is not None:
                        self.accordion_widget.selected_index = 1
                    temp_label = self.wf.label
                    self.wf.label = temp_label + "-save"
                    self.wf.save()
                    self.wf.label = temp_label
                    print("Successfully saved in " + temp_label + "-save")

                elif global_command == GlobalCommand.LOAD:
                    if self.accordion_widget is not None:
                        self.accordion_widget.selected_index = 1
                    temp_label = self.wf.label
                    self.wf.label = temp_label + "-save"
                    try:
                        self.wf.load()
                        self.wf.label = temp_label
                        self.update()
                        print("Successfully loaded from " + temp_label + "-save")
                    except:
                        self.wf.label = temp_label
                        self.update()
                        print("Save file " + temp_label + "-save" + " not found!")

                elif global_command == GlobalCommand.DELETE:
                    if self.accordion_widget is not None:
                        self.accordion_widget.selected_index = 1
                    temp_label = self.wf.label
                    self.wf.label = temp_label + "-save"
                    self.wf.delete_storage()
                    self.wf.label = temp_label
                    print("Deleted " + temp_label + "-save")

                else:
                    print("Command not yet implemented")


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
            self.log.append_stdout(f'add_node (reactflow): {node}, {label} \n')
            if label in self.wf.child_labels:
                self.wf.strict_naming = False

            self.wf.add_child(node(label=label))

            self.update()

    def get_workflow(self):
        workflow_label = self.wf.label

        wf = Workflow(workflow_label)
        dict_nodes = json.loads(self.gui.nodes)
        for dict_node in dict_nodes:
            node = dict_to_node(dict_node)
            wf.add_child(node)
            # wf.add_child(node(label=node.label))

        nodes = wf.children
        dict_edges = json.loads(self.gui.edges)
        for dict_edge in dict_edges:
            dict_to_edge(dict_edge, nodes)

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
