from pyiron_workflow import Workflow
from pyironflow.wf_extensions import (
    get_nodes,
    get_edges,
    get_node_from_path,
    dict_to_node,
    dict_to_edge,
    create_macro
)
from pyironflow.mixin.run import ReadinessError

import anywidget
import pathlib
import traitlets
import os
import json
import traceback

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
            try:
                out = self.wf.run()
                display(out)
            except ReadinessError as err:
                display(err.args[0])
            except Exception as e:
                print("Error:", e)
                sys.excepthook(*sys.exc_info())
            finally:
                self.update_status()

        self.out_widget.clear_output()

        import sys
        from IPython.core import ultratb

        error_message = ""

        sys_excepthook = sys.excepthook
        sys.excepthook = ultratb.FormattedTB(mode="Verbose", color_scheme='Neutral')

        try:
            self.wf = self.get_workflow()
        except Exception as error:
            print("Error:", error)
            error_message = error

        sys.excepthook = sys_excepthook

        if 'done' in change['new']:
            return

        with self.out_widget:
            import warnings

            with warnings.catch_warnings():
                warnings.simplefilter("ignore")

                print('command: ', change['new'])
                command = ''
                node_name = ''
                global_command = ''
                if 'executed at' not in change['new']:
                    command, node_name = change['new'].split(':')
                    node_name = node_name.split('-')[0].strip()
                else:
                    global_command_string = change['new'].split(' ')
                    global_command = global_command_string[0]
                # print (f'node {node_name} not in wf {self.wf._children.keys()}: ', node_name not in self.wf._children)
                if command != '' and command != 'macro' and node_name != '':
                    node_name = node_name.split('-')[0].strip()
                    if node_name not in self.wf._children:
                        return
                    node = self.wf._children[node_name]
                    # print(change['new'], command, node.label)
                    if self.accordion_widget is not None:
                        self.accordion_widget.selected_index = 1
                    if command == 'source':
                        import inspect
                        from pygments import highlight
                        from pygments.lexers import Python2Lexer
                        from pygments.formatters import TerminalFormatter

                        if hasattr(node, 'node_function'):
                            code = inspect.getsource(node.node_function)
                        elif hasattr(node, 'graph_creator'):
                            code = inspect.getsource(node.graph_creator)
                        elif hasattr(node, 'dataclass'):
                            code = inspect.getsource(node.dataclass)
                        else:
                            code = 'Function to extract code not implemented!'

                        print(highlight(code, Python2Lexer(), TerminalFormatter()))

                    elif command == 'run':
                        self.out_widget.clear_output()

                        if error_message:
                            print("Error:", error_message)

                        import sys
                        from IPython.core import ultratb

                        sys_excepthook = sys.excepthook
                        sys.excepthook = ultratb.FormattedTB(mode="Verbose", color_scheme='Neutral')
                        display_return_value(node.pull)
                        sys.excepthook = sys_excepthook
                    elif command == 'delete_node':
                        self.wf.remove_child(node_name)

                elif command == 'macro' and node_name != '':
                    if self.accordion_widget is not None:
                        self.accordion_widget.selected_index = 1
                    create_macro(self.get_selected_workflow(), node_name, self.root_path)
                    if self.tree_widget is not None:
                        self.tree_widget.update_tree()

                elif global_command == 'run':
                    if self.accordion_widget is not None:
                        self.accordion_widget.selected_index = 1
                    self.out_widget.clear_output()

                    import sys
                    from IPython.core import ultratb

                    sys_excepthook = sys.excepthook
                    sys.excepthook = ultratb.FormattedTB(mode="Verbose", color_scheme='Neutral')
                    display_return_value(self.wf.run)
                    sys.excepthook = sys_excepthook

                elif global_command == 'save':
                    if self.accordion_widget is not None:
                        self.accordion_widget.selected_index = 1
                    temp_label = self.wf.label
                    self.wf.label = temp_label + "-save"
                    self.wf.save()
                    self.wf.label = temp_label
                    print("Successfully saved in " + temp_label + "-save")

                elif global_command == 'load':
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

                elif global_command == 'delete':
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

        nodes = wf._children
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

        nodes = wf._children
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
