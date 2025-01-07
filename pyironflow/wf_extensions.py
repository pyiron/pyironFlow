from pyiron_workflow.type_hinting import type_hint_to_tuple
from pyiron_workflow.channels import NotData
from pyironflow.themes import get_color
import importlib
import typing
import warnings
import typing

def get_import_path(obj):
    module = obj.__module__ if hasattr(obj, "__module__") else obj.__class__.__module__
    # name = obj.__name__ if hasattr(obj, "__name__") else obj.__class__.__name__
    name = obj.__name__ if "__name__" in dir(obj) else obj.__class__.__name__
    qualname = obj.__qualname__ if "__qualname__" in dir(obj) else obj.__class__.__qualname__

    warnings.simplefilter('error', UserWarning)
    if qualname != name:
        warnings.warn("Node __name__ does not match __qualname__ which may lead to unexpected behavior. To avoid this, ensure the node is NOT nested inside subclasses within the module.")

    path = f"{module}.{name}"
    if path == "numpy.ndarray":
        path = "numpy.array"
    return path

def dict_to_node(dict_node):
    data = dict_node['data']
    node = get_node_from_path(data['import_path'])(label=dict_node['id'])
    if 'position' in dict_node:
        x, y = dict_node['position'].values()
        node.position = (x, y)
        # print('position exists: ', node.label, node.position)
    else:
        print('no position: ', node.label)
    if 'target_values' in data:
        target_values = data['target_values']
        target_labels = data['target_labels']
        for k, v in zip(target_labels, target_values):
            if v not in ('NonPrimitive', 'NotData'):
                node.inputs[k] = v

    return node

def dict_to_edge(dict_edge, nodes):
    out = nodes[dict_edge['source']].outputs[dict_edge['sourceHandle']]
    inp = nodes[dict_edge['target']].inputs[dict_edge['targetHandle']]
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
            value = 'NotData'
        elif not is_primitive(value):
            value = 'NonPrimitive'

        values.append(value)

    return values

def _get_generic_type(t):
    non_none_types = [arg for arg in t.__args__ if arg is not type(None)]
    return float if float in non_none_types else non_none_types[0]


def _get_type_name(t):
    primitive_types = (bool, str, int, float, type(None))
    if t is None:
        return 'None'
    elif t in primitive_types:
        return t.__name__
    else:
        return 'NonPrimitive'


def get_node_types(node_io):
    node_io_types = list()
    for k in node_io.channel_dict:
        type_hint = node_io[k].type_hint
        if isinstance(type_hint, typing._UnionGenericAlias):
            type_hint = _get_generic_type(type_hint)

        node_io_types.append(_get_type_name(type_hint))
    return node_io_types


def get_node_position(node, max_x, node_width=240, y0=100, x_spacing=20):
    if 'position' in dir(node):
        x, y = node.position
        # if isinstance(x, str):
        #     x, y = 0, 0
    else:
        x = max_x + node_width + x_spacing
        y = y0

    return {'x': x, 'y': y}


def get_node_dict(node, max_x, key=None):
    node_width = 240
    n_inputs = len(list(node.inputs.channel_dict.keys()))
    n_outputs = len(list(node.outputs.channel_dict.keys()))
    if n_outputs > n_inputs:
        node_height = 30 + (16*n_outputs) + 10
    else:
        node_height = 30 + (16*n_inputs) + 10
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
            'target_types': get_node_types(node.inputs),
            'source_values': get_node_values(node.outputs.channel_dict),
            'source_types': get_node_types(node.outputs),
        },
        'position': get_node_position(node, max_x),
        'type': 'customNode',
        'style': {'border': '1px black solid',
                  'padding': 5,
                  'background': get_color(node=node, theme='light'),
                  'borderRadius': '10px',
                  'width': f'{node_width}px',
                  'width_unitless': node_width,
                  'height': f'{node_height}px',
                  'height_unitless': node_height},
        'targetPosition': 'left',
        'sourcePosition': 'right'
    }


def get_nodes(wf):
    nodes = []
    x_coords = []
    max_x = 0
    for i, (k, v) in enumerate(wf.children.items()):
        if 'position' in dir(v):
            x_coords.append(v.position[0])
            if len(x_coords) > 0:
                max_x = max(x_coords)
    for i, (k, v) in enumerate(wf.children.items()):
        nodes.append(get_node_dict(v, max_x, key=k))
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
        edge_dict["style"] = {'strokeWidth': 2, 'stroke': 'black',}

        edges.append(edge_dict)
    return edges

def get_input_types_from_hint(node_input: dict):

    new_type = ""

    for listed_type in list(type_hint_to_tuple(node_input.type_hint)):
        if listed_type == None:
            listed_type = type(None)
        if listed_type.__name__ != "NoneType":
            new_type = new_type + listed_type.__name__ + "|"

    new_type = new_type[:-1]    

    for listed_type in list(type_hint_to_tuple(node_input.type_hint)):
        if listed_type == None:
            listed_type = type(None)
        if listed_type.__name__ == "NoneType":
            if new_type != "":
                new_type = ": Optional[" + new_type + "]"

    return new_type

def create_macro(wf = dict, name = str, root_path='../pyiron_nodes/pyiron_nodes'):

    imports = list("")
    var_def = ""

    file = open(root_path + '/' + name + '.py', 'w')

    for i, (k, v) in enumerate(wf.children.items()):
        rest, n = get_import_path(v).rsplit('.', 1)
        new_import = "    from " + rest + " import " + n
        imports.append(new_import)
        list_inputs = list(v.inputs.channel_dict.keys())

        for j in list(v.inputs):
            if ((v.label + "__" + j.label) in list(wf.inputs.channel_dict.keys())):
                if str(j) == ("NOT_DATA" or "None"):
                    value = "None"
                elif type(j.value) == str:
                    value = "'" + j.value + "'"
                else:
                    value = str(j.value)
                var_def = var_def + v.label + "_" + j.label + get_input_types_from_hint(j)+ " = " + value + ", "

    var_def = var_def[:-2]    

    count = 0
    new_list = list("")
    for ic, (out, inp) in enumerate(wf.graph_as_dict["edges"]["data"].keys()):
        out_node, out_port = out.split('/')[2].split('.')
        inp_node, inp_port = inp.split('/')[2].split('.')
        new_list.append([out_node, inp_node, inp_port])


    file.write(
'''from pyiron_workflow import as_function_node, as_macro_node
from typing import Optional

@as_macro_node()
def ''' + name + '''(self, ''' + var_def + '''):
''')
    for j in imports:
        file.write(j + "\n")

    for i, (k, v) in enumerate(wf.children.items()):
        rest, n = get_import_path(v).rsplit('.', 1)
        file.write("    self." + v.label + " = " +  n + "()\n") 
    
    for i, (k, v) in enumerate(wf.children.items()):
        rest, n = get_import_path(v).rsplit('.', 1)
    
        node_def =""
    
        for j in list(wf.inputs.channel_dict.keys()):
            node_label, input_label =j.rsplit('__', 1)
            if v.label == node_label: 
                node_def = node_def + input_label + " = " + node_label + "_" + input_label+ ", "
        
        for p in new_list:
            if v.label == p[1]:
                node_def = node_def + p[2] + " = self."+ p[0] + ", "
        node_def = node_def[:-2]
        file.write("    self." + v.label + ".set_input_values" + "(" + node_def + ")\n") 
    
    rest_list = []
    for items in list(wf.outputs.channel_dict.keys()):
        rest, n = items.rsplit('__', 1)
        rest_list.append(rest)

    out_str = "    return "
    for strs in rest_list:
        out_str = out_str + "self." + strs + ", "

    file.write(out_str)
    print("\nSuccessfully created macro: " + root_path + '/' + name + '.py')
    file.close()

    return