from pyiron_workflow import Workflow

from pyiron_nodes.development import hash_based_storage as hs
from pyironflow.wf_extensions import (
    get_nodes,
    get_edges,
    get_node_from_path,
    dict_to_node,
    dict_to_edge,
)

import anywidget
import pathlib
import traitlets

# import os
import json


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
    # path = pathlib.Path(os.getcwd()) / 'static'
    path = pathlib.Path(__file__).parent.parent / "static"
    _esm = path / "widget.js"
    _css = path / "widget.css"
    nodes = traitlets.Unicode("[]").tag(sync=True)
    edges = traitlets.Unicode("[]").tag(sync=True)
    commands = traitlets.Unicode("[]").tag(sync=True)


class PyironFlowWidget:
    def __init__(
        self,
        wf: Workflow = Workflow(label="workflow"),
        log=None,
        out_widget=None,
        hash_nodes=False,
    ):
        self.log = log
        self.out_widget = out_widget
        self.accordion_widget = None
        self.gui = ReactFlowWidget()
        self.wf = wf

        if hash_nodes:
            self.db = hs.create_nodes_table(echo=False)
        else:
            self.db = None

        self.gui.observe(self.on_value_change, names="commands")

        self.update()

    def on_value_change(self, change):
        from IPython.display import display

        self.out_widget.clear_output()
        self.wf = self.get_workflow()
        if "done" in change["new"]:
            return

        with self.out_widget:
            import warnings

            with warnings.catch_warnings():
                warnings.simplefilter("ignore")

                print("command: ", change["new"])
                command, node_name = change["new"].split(":")
                node_name = node_name.split("-")[0].strip()
                # print (f'node {node_name} not in wf {self.wf._children.keys()}: ', node_name not in self.wf._children)
                if node_name not in self.wf._children:
                    return
                node = self.wf._children[node_name]
                # print(change['new'], command, node.label)
                if self.accordion_widget is not None:
                    self.accordion_widget.selected_index = 1
                if command == "source":
                    import inspect
                    from pygments import highlight
                    from pygments.lexers import Python2Lexer
                    from pygments.formatters import TerminalFormatter

                    node_dir = dir(node)
                    if "dataclass" in node_dir:
                        code = node.dataclass()
                        # print(code)
                        # return
                    elif "node_function" in node_dir:
                        code = inspect.getsource(node.node_function)
                    elif "graph_creator" in node_dir:
                        code = inspect.getsource(node.graph_creator)

                    else:
                        print("Unknown node type!")
                        return

                    print(highlight(code, Python2Lexer(), TerminalFormatter()))

                elif command == "run":
                    self.out_widget.clear_output()
                    if self.db is None:
                        out = node.pull()
                    else:
                        out = hs.run_node(node, self.db).outputs.to_value_dict()

                    display(out)
                # elif command == 'output':
                #     keys = list(node.outputs.channel_dict.keys())
                #     display(node.outputs.channel_dict[keys[0]].value)
                elif command == "delete_node":
                    self.wf.remove_child(node_name)

    def update(self):
        nodes = get_nodes(self.wf)
        edges = get_edges(self.wf)
        self.gui.nodes = json.dumps(nodes)
        self.gui.edges = json.dumps(edges)

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
        workflow_label = self.wf.label

        wf = Workflow(workflow_label)
        dict_nodes = json.loads(self.gui.nodes)
        for dict_node in dict_nodes:
            node = dict_to_node(dict_node, self.log)
            wf.add_child(node)
            # wf.add_child(node(label=node.label))

        nodes = wf._children
        dict_edges = json.loads(self.gui.edges)
        for dict_edge in dict_edges:
            dict_to_edge(dict_edge, nodes)

        return wf
