from pyiron_workflow import Workflow
from pyiron_workflow.channels import NotData

import anywidget
import pathlib
import traitlets
import os
import json
import importlib


class ReactFlowWidget(anywidget.AnyWidget):
    _esm = pathlib.Path(__file__).parent / "static" / "widget.js"
    _css = pathlib.Path(__file__).parent / "static" / "widget.css"
    nodes = traitlets.Unicode('[]').tag(sync=True)
    edges = traitlets.Unicode('[]').tag(sync=True)
    commands = traitlets.Unicode('[]').tag(sync=True)


def get_import_path(obj):
    module = obj.__module__ if hasattr(obj, "__module__") else obj.__class__.__module__
    name = obj.__name__ if hasattr(obj, "__name__") else obj.__class__.__name__
    path = f"{module}.{name}"
    if path == "numpy.ndarray":
        path = "numpy.array"
    return path


def dict_to_node(dict_node):
    data = dict_node['data']
    node = get_node_from_path(data['import_path'])
    node.label = dict_node['id']
    # TODO: add values
    return node


def dict_to_edge(dict_edge, nodes):
    out = nodes[dict_edge['source']].outputs[dict_edge['sourceHandle']]
    inp = nodes[dict_edge['target']].inputs[dict_edge['targetHandle']]
    inp.connect(out)

    return True


def get_workflow(wf_widget):
    workflow_label = wf_widget.wf.label

    wf = Workflow(workflow_label)
    dict_nodes = json.loads(wf_widget.gui.nodes)
    for dict_node in dict_nodes:
        node = dict_to_node(dict_node)
        wf.add_child(node(label=node.label))

    nodes = wf._children
    dict_edges = json.loads(wf_widget.gui.edges)
    for dict_edge in dict_edges:
        dict_to_edge(dict_edge, nodes)

    return wf


def is_primitive(obj):
    primitives = (bool, str, int, float, type(None))
    return isinstance(obj, primitives)


def get_node_values(channel_dict):
    values = list()
    for k, v in channel_dict.items():
        value = v.value
        if isinstance(value, NotData):
            value = 'NotData'
        elif not is_primitive(value):
            value = 'NonPrimitive'

        values.append(value)

    return values


def get_node_dict(node, id_num, key=None):
    node_width = 200
    label = node.label
    if (node.label != key) and (key is not None):
        label = f'{node.label}: {key}'
    return {
        'id': node.label,
        'data': {
            'label': label,
            'source_labels': list(node.outputs.channel_dict.keys()),
            'target_labels': list(node.inputs.channel_dict.keys()),
            'import_path': get_import_path(node),
            'target_values': get_node_values(node.inputs.channel_dict),
            'source_values': get_node_values(node.outputs.channel_dict),
        },
        'position': {'x': id_num * (node_width + 30), 'y': 100},
        'type': 'customNode',
        'style': {'border': '1px black solid',
                  'padding': 5,
                  'background': node.color,  # '#1999',
                  'border-radius': '10px',
                  'width': f'{node_width}px'},
        'targetPosition': 'left',
        'sourcePosition': 'right'
    }


def get_nodes(wf):
    nodes = []
    for i, (k, v) in enumerate(wf.children.items()):
        nodes.append(get_node_dict(v, id_num=i, key=k))
    return nodes


def get_node_from_path(import_path, log=None):
    # Split the path into module and object part
    module_path, _, name = import_path.rpartition(".")
    # Import the module
    try:
        module = importlib.import_module(module_path)
    except ModuleNotFoundError as e:
        log.append_stderr(e)
        return None
    # Get the object
    object_from_path = getattr(module, name)
    return object_from_path


def get_edges(wf):
    edges = []
    for ic, (out, inp) in enumerate(wf.graph_as_dict["edges"]["data"].keys()):
        out_node, out_port = out.split('/')[2].split('.')
        inp_node, inp_port = inp.split('/')[2].split('.')

        edge_dict = dict()
        edge_dict["source"] = out_node
        edge_dict["sourceHandle"] = out_port
        edge_dict["target"] = inp_node
        edge_dict["targetHandle"] = inp_port
        edge_dict["id"] = ic

        edges.append(edge_dict)
    return edges


class PyironFlowWidget:
    def __init__(self, wf: Workflow = Workflow(label='workflow'), log=None, out_widget=None):
        self.log = log
        self.out_widget = out_widget
        self.gui = ReactFlowWidget()
        self.wf = wf

        self.gui.observe(self.on_value_change, names='commands')

        self.update()

    def on_value_change(self, change):
        from IPython.display import display
        self.out_widget.clear_output()
        self.wf = self.get_workflow()

        with self.out_widget:
            command, node_name = change['new'].split(':')
            node = self.wf._children[node_name.strip()]
            # print(change['new'], command, node.label)
            if command == 'source':
                import inspect
                from pygments import highlight
                from pygments.lexers import Python2Lexer
                from pygments.formatters import TerminalFormatter

                code = inspect.getsource(node.node_function)
                print(highlight(code, Python2Lexer(), TerminalFormatter()))

            elif command == 'run':
                out = node.pull()
                display(out)
            elif command == 'output':
                keys = list(node.outputs.channel_dict.keys())
                display(node.outputs.channel_dict[keys[0]].value)

    def update(self):
        nodes = get_nodes(self.wf)
        edges = get_edges(self.wf)
        self.gui.nodes = json.dumps(nodes)
        self.gui.edges = json.dumps(edges)

    @property
    def react_flow_widget(self):
        return self.gui

    def add_node(self, node_path, label):
        node = get_node_from_path(node_path, log=self.log)
        if node is not None:
            self.log.append_stdout(f'add_node: {node} \n')
            self.wf.add_child(node(label=label))

            self.update()

    def get_workflow(self):
        workflow_label = self.wf.label

        wf = Workflow(workflow_label)
        dict_nodes = json.loads(self.gui.nodes)
        for dict_node in dict_nodes:
            node = dict_to_node(dict_node)
            wf.add_child(node(label=node.label))

        nodes = wf._children
        dict_edges = json.loads(self.gui.edges)
        for dict_edge in dict_edges:
            dict_to_edge(dict_edge, nodes)

        return wf
