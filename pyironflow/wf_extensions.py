"""
Provide functions that are needed for pyironFlow, but that should be provided by 
pyiron_workflows in the end.
"""

from pyiron_workflow.channels import NotData
from pyironflow.themes import get_color
import importlib
import typing


def get_import_path(obj):
    module = obj.__module__ if hasattr(obj, "__module__") else obj.__class__.__module__
    # name = obj.__name__ if hasattr(obj, "__name__") else obj.__class__.__name__
    name = obj.__name__ if "__name__" in dir(obj) else obj.__class__.__name__
    path = f"{module}.{name}"
    if path == "numpy.ndarray":
        path = "numpy.array"
    return path


def dict_to_node(dict_node, log):
    data = dict_node["data"]
    node = get_node_from_path(data["import_path"], log=log)(label=dict_node["id"])
    if "position" in dict_node:
        x, y = dict_node["position"].values()
        node.position = (x, y)
        # print('position exists: ', node.label, node.position)
    else:
        print("no position: ", node.label)
    if "target_values" in data:
        target_values = data["target_values"]
        target_labels = data["target_labels"]
        for k, v in zip(target_labels, target_values):
            if v not in ("NonPrimitive", "NotData"):
                node.inputs[k] = v

    return node


def dict_to_edge(dict_edge, nodes):
    out = nodes[dict_edge["source"]].outputs[dict_edge["sourceHandle"]]
    inp = nodes[dict_edge["target"]].inputs[dict_edge["targetHandle"]]
    inp.connect(out)

    return True


def is_primitive(obj):
    primitives = (bool, str, int, float, type(None))
    return isinstance(obj, primitives)


def get_node_values(channel_dict):
    values = list()
    for k, v in channel_dict.items():
        value = v.value
        if isinstance(value, NotData):
            value = "NotData"
        elif not is_primitive(value):
            value = "NonPrimitive"

        values.append(value)

    return values


def _get_generic_type(t):
    non_none_types = [arg for arg in t.__args__ if arg is not type(None)]
    return float if float in non_none_types else non_none_types[0]


def _get_type_name(t):
    primitive_types = (bool, str, int, float, type(None))
    if t is None:
        return "None"
    elif t in primitive_types:
        return t.__name__
    else:
        return "NonPrimitive"


def get_node_types(node_io):
    node_io_types = list()
    for k in node_io.channel_dict:
        type_hint = node_io[k].type_hint
        if isinstance(type_hint, typing._UnionGenericAlias):
            type_hint = _get_generic_type(type_hint)

        node_io_types.append(_get_type_name(type_hint))
    return node_io_types


def get_node_position(node, id_num, node_width=200, y0=100, x_spacing=30):
    if "position" in dir(node):
        x, y = node.position
        # if isinstance(x, str):
        #     x, y = 0, 0
    else:
        x = id_num * (node_width + x_spacing)
        y = y0

    return {"x": x, "y": y}


def get_node_dict(node, id_num, key=None):
    node_width = 200
    label = node.label
    if (node.label != key) and (key is not None):
        label = f"{node.label}: {key}"
    return {
        "id": node.label,
        "data": {
            "label": label,
            "source_labels": list(node.outputs.channel_dict.keys()),
            "target_labels": list(node.inputs.channel_dict.keys()),
            "import_path": get_import_path(node),
            "target_values": get_node_values(node.inputs.channel_dict),
            "target_types": get_node_types(node.inputs),
            "source_values": get_node_values(node.outputs.channel_dict),
            "source_types": get_node_types(node.outputs),
        },
        "position": get_node_position(node, id_num),
        "type": "customNode",
        "style": {
            "border": "1px black solid",
            "padding": 5,
            "background": get_color(node=node, theme="light"),
            "borderRadius": "10px",
            "width": f"{node_width}px",
        },
        "targetPosition": "left",
        "sourcePosition": "right",
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
        out_node, out_port = out.split("/")[2].split(".")
        inp_node, inp_port = inp.split("/")[2].split(".")

        edge_dict = dict()
        edge_dict["source"] = out_node
        edge_dict["sourceHandle"] = out_port
        edge_dict["target"] = inp_node
        edge_dict["targetHandle"] = inp_port
        edge_dict["id"] = ic
        edge_dict["style"] = {
            "strokeWidth": 2,
            "stroke": "black",
        }

        edges.append(edge_dict)
    return edges
