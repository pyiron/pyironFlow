from pyiron_workflow.type_hinting import type_hint_to_tuple, valid_value
from pyiron_workflow.api import NOT_DATA
from pyiron_workflow.node import Node
from pyironflow.themes import get_color
from pyiron_workflow.nodes.macro import Macro
from pyiron_workflow.nodes.while_loop import While
from pyiron_workflow.nodes.for_loop import For
from pyiron_workflow import Workflow

import importlib
import typing
import warnings
from typing import Union, get_args
import types
import math

NODE_WIDTH = 240

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

def dict_to_node(dict_node: dict, live_children: dict = None, reload=False) -> Node:
    """Convert dict spec of node back to Node object."""
    if live_children is None:
        live_children = {}
    data = dict_node['data']
    label = dict_node['id']
    node_id = data['python_object_id']
    # Check whether a node of the same label already exists in the underlying
    # workflow and whether it is the same object (by python id).  If so, return
    # that instance back so that the widget can avoid double adding the same
    # node and node data caches still work.
    if id(node := live_children.get(label, None)) != node_id:
        node = get_node_from_path(data['import_path'], reload=reload)(label=label)
    # if updating the workflow disconnect all edges here and let dict_to_edge
    # rebuild them so as to not keep edges in the underlying workflow that have
    # been removed in the GUI.
    node.inputs.disconnect()
    node.outputs.disconnect()
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
            if v not in ('NonPrimitive', 'NOT_DATA.__class__', ''):
                type_hint = node.inputs[k].type_hint
                # JS gui can return input values like 2.0 as int, breaking type hints
                # so check here if the type hint is a float, but convert only if losslessly possible
                if isinstance(v, int) and not valid_value(v, type_hint) \
                        and valid_value(float(v), type_hint) and v == float(v):
                    v = float(v)
                node.inputs[k].value = v

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
    values = []
    for k, v in channel_dict.items():
        value = v.value
        if isinstance(value, NOT_DATA.__class__):
            value = 'NOT_DATA.__class__'
        elif not is_primitive(value):
            value = 'NonPrimitive'

        # JSON does not understand nan or infinity and JSON.parse will crash
        # the react front end on encountering it
        if isinstance(value, float) and not math.isfinite(value):
            value = None
        values.append(value)

    return values

def _get_generic_type(t):
    non_none_types = [arg for arg in t.__args__ if arg is not type(None)]
    hints = {float, int, str}.intersection(non_none_types)
    if int in hints and float in hints:
        return Union[int,float]
    if int in hints:
        return int
    if float in hints:
        return float
    if str in hints:
        return str
    return non_none_types[0]


def _get_type_name(t):
    primitive_types = (bool, str, int, float, typing._LiteralGenericAlias, type(None))
    if t is None:
        return 'None'
    elif isinstance(t, (types.UnionType, typing._UnionGenericAlias)):
        return 'int-float'
    elif t in primitive_types:
        return t.__name__
    else:
        return 'NonPrimitive'


def get_node_types(node_io):
    node_io_types = list()
    for k in node_io.channel_dict:
        type_hint = node_io[k].type_hint
        if isinstance(type_hint, (types.UnionType, typing._UnionGenericAlias)):
            if all(isinstance(arg, typing._LiteralGenericAlias) for arg in get_args(type_hint)):
                type_hint = typing._LiteralGenericAlias
            elif all(not isinstance(arg, typing._LiteralGenericAlias) for arg in get_args(type_hint)):
                if all(arg is not bool for arg in get_args(type_hint)):
                    type_hint = _get_generic_type(type_hint)
                else:
                    type_hint = object
            else:
                type_hint = object
        if isinstance(type_hint, typing._LiteralGenericAlias):
            type_hint = typing._LiteralGenericAlias

        node_io_types.append(_get_type_name(type_hint))
    return node_io_types

def get_node_literal_values(node_inputs):
    node_io_literal_values = list()
    for k in node_inputs.channel_dict:
        if isinstance(node_inputs[k].type_hint, typing._LiteralGenericAlias):
            args = list(get_args(node_inputs[k].type_hint))
        elif all(isinstance(arg, typing._LiteralGenericAlias) for arg in get_args(node_inputs[k].type_hint)):
            args = []
            for arg in get_args(node_inputs[k].type_hint):
                for arg_1 in get_args(arg):
                    args.append(arg_1)
        else:
            args = None

        node_io_literal_values.append(args)
    return node_io_literal_values

def get_node_literal_types(node_inputs):
    node_io_literal_types = list()
    for k in node_inputs.channel_dict:
        if isinstance(node_inputs[k].type_hint, typing._LiteralGenericAlias):
            args = [type(arg).__name__ for arg in list(get_args(node_inputs[k].type_hint))]
        elif all(isinstance(arg, typing._LiteralGenericAlias) for arg in get_args(node_inputs[k].type_hint)):
            args = []
            for arg in get_args(node_inputs[k].type_hint):
                for arg_1 in get_args(arg):
                    args.append(type(arg_1).__name__)
        else:
            args = None

        node_io_literal_types.append(args)
    return node_io_literal_types

def get_raw_target_types(node_inputs):
    node_input_types = list()
    for k in node_inputs.channel_dict:
        type_hint = node_inputs[k].type_hint
        if isinstance(type_hint, (types.UnionType, typing._UnionGenericAlias)):
            union_types = [arg.__name__ for arg in type_hint.__args__]
            node_input_types.append(union_types)
        else:
            try:
                node_input_types.append(type_hint.__name__)
            except:
                node_input_types.append("Not Explicitly Defined")
    return node_input_types

def get_raw_source_types(node_outputs):
    node_output_types = list()
    for k in node_outputs.channel_dict:
        type_hint = node_outputs[k].type_hint
        if isinstance(type_hint, (types.UnionType, typing._UnionGenericAlias)):
            union_types = [arg.__name__ for arg in type_hint.__args__]
            node_output_types.append(union_types)
        else:
            try:
                node_output_types.append(type_hint.__name__)
            except:
                node_output_types.append("Not Explicitly Defined")
    return node_output_types


def get_node_position(node):
    if 'position' in dir(node):
        x, y = node.position
    else:
        x, y = 0, 0
    return {'x': x, 'y': y}



def get_node_dict(node, macroType, key=None):
    n_inputs = len(list(node.inputs.channel_dict.keys()))
    n_outputs = len(list(node.outputs.channel_dict.keys()))
    if n_outputs > n_inputs:
        node_height = 30 + (16*n_outputs) + 10
    else:
        node_height = 30 + (16*n_inputs) + 10

    if macroType == "expanded":
        node_width, node_height = get_macro_node_size(node)
        node_height = node_height * 100 + 80
        node_width = node_width * 200 + 390 
        #node_height = 500
        #node_width = 1300
        nodeType = 'macroNodeExpanded'
        color = 'rgba(234, 207, 159, 0.7)'

    
    elif macroType == "while_loop_expanded":
        #node_width, node_height = get_macro_node_size(node)
        temp_wf = Workflow('temp')
        temp_wf.body = node._body_node_class()
        node_width, node_height = get_macro_node_size(temp_wf.body)
        node_height = node_height * 100 + 80 + 250
        node_width = node_width * 200 + 1000
        nodeType = 'loopNodeExpanded'
        color = 'rgba(140, 86, 75, 0.7)'

    elif macroType == "for_loop_expanded":
        #node_width, node_height = get_macro_node_size(node)
        temp_wf = Workflow('temp')
        temp_wf.body = node._body_node_class()
        node_width, node_height = get_macro_node_size(temp_wf.body)
        node_height = node_height * 100 + 300
        node_width = max(node_width * 200 + 900, 1500)
        nodeType = 'loopNodeExpanded'
        color = 'rgba(140, 86, 75, 0.7)'

    elif macroType == "collapsed":
        node_width = 240
        nodeType = 'macroNode'
        color = 'rgba(234, 207, 159, 1)'

    elif macroType == "loop_collapsed":
        node_width = 240
        nodeType = 'macroNode'
        color = 'rgba(140, 86, 75, 0.7)'

    else :
        node_width = 240
        nodeType = 'customNode'
        color = get_color(node=node, theme='light')


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
            'target_types_raw': get_raw_target_types(node.inputs),
            'target_literal_values': get_node_literal_values(node.inputs),
            'target_literal_types': get_node_literal_types(node.inputs),
            'source_values': get_node_values(node.outputs.channel_dict),
            'source_types': get_node_types(node.outputs),
            'source_types_raw': get_raw_source_types(node.outputs),
            'failed': str(node.failed),
            'running': str(node.running),
            'ready': str(node.outputs.ready),
            'cache_hit': str(node.cache_hit),
            'python_object_id': id(node),
        },
        'position': get_node_position(node),
        'type': nodeType,
        'layer': 0,
        'style': {'padding': 5,
                  'background': color,
                  'borderRadius': '10px',
                  'width': f'{node_width}PX',
                  'width_unitless': node_width,
                  'height': f'{node_height}px',
                  'height_unitless': node_height},
        'targetPosition': 'left',
        'sourcePosition': 'right'
    }

def get_macro_subnode_dict(node, parentNode, key=None):
    n_inputs = len(list(node.inputs.channel_dict.keys()))
    n_outputs = len(list(node.outputs.channel_dict.keys()))
    if n_outputs > n_inputs:
        node_height = 30 + (16*n_outputs) + 10
    else:
        node_height = 30 + (16*n_inputs) + 10
    label = node.label

    layer = 1

    node_id = parentNode + "_" + label
    
    return {
        'id': node_id,
        'data': {
            'label': label,
            'source_labels': list(node.outputs.channel_dict.keys()),
            'target_labels': list(node.inputs.channel_dict.keys()),
            'import_path': get_import_path(node),
            'target_values': get_node_values(node.inputs.channel_dict),
            'target_types': get_node_types(node.inputs),
            'target_types_raw': get_raw_target_types(node.inputs),
            'target_literal_values': get_node_literal_values(node.inputs),
            'target_literal_types': get_node_literal_types(node.inputs),
            'source_values': get_node_values(node.outputs.channel_dict),
            'source_types': get_node_types(node.outputs),
            'source_types_raw': get_raw_source_types(node.outputs),
            'failed': str(node.failed),
            'running': str(node.running),
            'ready': str(node.outputs.ready),
            'cache_hit': str(node.cache_hit),
            'python_object_id': id(node),
        },
        'position': get_node_position(node),
        'type': 'subNode',
        'layer': layer,
        'style': {'padding': 5,
                  'background': get_color(node=node, theme='light'),
                  'borderRadius': '10px',
                  'width': '150px',
                  'width_unitless': 150,
                  'height': f'{node_height}px',
                  'height_unitless': node_height},
        'targetPosition': 'left',
        'sourcePosition': 'right',
        'parentId': parentNode,
        'extent': 'parent',
    }

def in_node_dict(node):

    x = len(list(node.inputs.channel_dict))*16 + 40 
    node_id = node.label + "_inputs"
    layer = 1
    
    return {
        'id': node_id,
        'data': {
            'label': "inputs",
            'source_labels': list(node.inputs.channel_dict),
            'target_labels': [],
            'import_path': '',
            'target_values': [],
            'target_types': [],
            'target_types_raw': [],
            'target_literal_values': [],
            'target_literal_types': [],
            'source_values': [],
            'source_types': [],
            'source_types_raw': [],
            'failed': 'False',
            'running': 'False',
            'ready': 'False',
            'cache_hit': 'False',
            'python_object_id': id(node),
        },
        'position': {'x': 50, 'y': 50},
        'type': 'subNode',
        'layer': layer,
        'style': {'padding': 5,
                  'background': "rgba(171, 190, 209, 1)",
                  'borderRadius': '10px',
                  'width': '100px',
                  'width_unitless': 100,
                  'height': f'{x}px',
                  'height_unitless': x},
        'targetPosition': 'left',
        'sourcePosition': 'right',
        'draggable' : False,
        'parentId': node.label,
        'extent': 'parent',
    }


def out_node_dict(node):

    x = len(list(node.outputs.channel_dict))*16 + 40 
    node_id = node.label + "_outputs"
    layer = 1
    
    return {
        'id': node_id,
        'data': {
            'label': "outputs",
            'source_labels': [],
            'target_labels': list(node.outputs.channel_dict),
            'import_path': '',
            'target_values': [],
            'target_types': [],
            'target_types_raw': [],
            'target_literal_values': [],
            'target_literal_types': [],
            'source_values': [],
            'source_types': [],
            'source_types_raw': [],
            'failed': 'False',
            'running': 'False',
            'ready': 'False',
            'cache_hit': 'False',
            'python_object_id': id(node),
        },
        'position': {'x': 700, 'y': 50},
        'type': 'subNode',
        'layer': layer,
        'style': {'padding': 5,
                  'background': "rgba(171, 190, 209, 1)",
                  'borderRadius': '10px',
                  'width': '100px',
                  'width_unitless': 100,
                  'height': f'{x}px',
                  'height_unitless': x},
        'targetPosition': 'left',
        'sourcePosition': 'right',
        'draggable' : False,
        'parentId': node.label,
        'extent': 'parent',
    }

#-----

def start_node_dict(node):

    x = 60 
    node_id = node.label + "_start"
    layer = 1
    
    return {
        'id': node_id,
        'data': {
            'label': "start",
            'source_labels': ['start'],
            'target_labels': [],
            'import_path': '',
            'target_values': [],
            'target_types': [],
            'target_types_raw': [],
            'target_literal_values': [],
            'target_literal_types': [],
            'source_values': [],
            'source_types': [],
            'source_types_raw': [],
            'failed': 'False',
            'running': 'False',
            'ready': 'False',
            'cache_hit': 'False',
            'python_object_id': id(node),
        },
        'position': {'x': 200, 'y': 200},
        'type': 'subNode',
        'layer': layer,
        'style': {'padding': 5,
                  'background': "rgba(171, 190, 209, 1)",
                  'borderRadius': '10px',
                  'width': '100px',
                  'width_unitless': 100,
                  'height': f'{x}px',
                  'height_unitless': x},
        'targetPosition': 'left',
        'sourcePosition': 'right',
        'draggable' : False,
        'parentId': node.label,
        'extent': 'parent',
    }


def end_node_dict(node):

    x = 60
    node_id = node.label + "_end"
    layer = 1
    
    return {
        'id': node_id,
        'data': {
            'label': "end",
            'source_labels': [],
            'target_labels': ['end'],
            'import_path': '',
            'target_values': [],
            'target_types': [],
            'target_types_raw': [],
            'target_literal_values': [],
            'target_literal_types': [],
            'source_values': [],
            'source_types': [],
            'source_types_raw': [],
            'failed': 'False',
            'running': 'False',
            'ready': 'False',
            'cache_hit': 'False',
            'python_object_id': id(node),
        },
        'position': {'x': 700, 'y': 300},
        'type': 'subNode',
        'layer': layer,
        'style': {'padding': 5,
                  'background': "rgba(171, 190, 209, 1)",
                  'borderRadius': '10px',
                  'width': '100px',
                  'width_unitless': 100,
                  'height': f'{x}px',
                  'height_unitless': x},
        'targetPosition': 'left',
        'sourcePosition': 'right',
        'draggable' : False,
        'parentId': node.label,
        'extent': 'parent',
    }
#-----

def get_loop_view_node_dict(node, nodeType, parentNode, key=None):

    node_width = 240
    node_height = 56
    label = node.label
    
    if (nodeType == "test"):
        sourceLabelList = ['true', 'false']
        targetLabelList = ['run'] 
        node_height = 72
        color = get_color(node=node, theme='light')
        node_id = label
    elif (nodeType == "body"):
        sourceLabelList = ['end']
        targetLabelList = ['run']
        color = 'rgba(234, 207, 159, 1)'
        node_id = label + "_body"  
    elif (nodeType == "range"):
        sourceLabelList = ['true', 'false']
        targetLabelList = ['run']
        node_height = 72
        color = 'rgba(162, 234, 159, 1)'
        label = "In Range"
        node_id = parentNode.label + "_in_range"   
    elif (nodeType == "increment"):
        sourceLabelList = ['end']
        targetLabelList = ['run']
        color = 'rgba(162, 234, 159, 1)'
        label = "Increment"
        node_id = parentNode.label + "_increment"   

        
    return {
        'id': node_id,
        'data': {
            'label': label,
            'source_labels': sourceLabelList,
            'target_labels': targetLabelList,
            'import_path': '',
            'target_values': [],
            'target_types': [],
            'target_types_raw': [],
            'target_literal_values': [],
            'target_literal_types': [],
            'source_values': [],
            'source_types': [],
            'source_types_raw': [],
            'failed': 'False',
            'running': 'False',
            'ready': 'False',
            'cache_hit': 'False',
            'python_object_id': id(node),
        },
        'position': get_node_position(node),
        'type': 'subNode',
        'layer': 1,
        'style': {'padding': 5,
                  'background': color,
                  'borderRadius': '10px',
                  'width': f'{node_width}PX',
                  'width_unitless': node_width,
                  'height': f'{node_height}px',
                  'height_unitless': node_height},
        'targetPosition': 'left',
        'sourcePosition': 'right',
        'draggable' : False,
        'parentId': parentNode.label,
        'extent': 'parent',
    }






#------------------------------------------------------------------------------------------

def get_loop_body_node_dict(node, macroType, parentNode, key=None):
    n_inputs = len(list(node.inputs.channel_dict.keys()))
    n_outputs = len(list(node.outputs.channel_dict.keys()))
    if n_outputs > n_inputs:
        node_height = 30 + (16*n_outputs) + 10
    else:
        node_height = 30 + (16*n_inputs) + 10

    source_labels = list(node.outputs.channel_dict.keys())
    target_labels = list(node.inputs.channel_dict.keys())
    node_id = node.label 
    label = node.label
    
    if macroType == "expanded":
        node_width, node_height = get_macro_node_size(node)
        node_height = node_height * 100 + 80
        node_width = node_width * 200 + 390 
        nodeType = 'macroNodeExpanded'
        color = 'rgba(234, 207, 159, 0.7)'

    elif macroType == "collapsed":
        node_width = 150
        nodeType = 'macroNode'
        color = 'rgba(234, 207, 159, 1)'

    elif macroType == "dummy_macro":
        node_width, node_height = get_macro_node_size(node)
        node_height = node_height * 100 + 100
        node_width = node_width * 240 + 390 
        nodeType = 'customNode'
        color = 'rgba(234, 207, 159, 0.7)'

    elif macroType == "dummy_macro_for1":
        node_width, node_height = get_macro_node_size(node)
        node_height = 300
        node_width = 900 
        nodeType = 'customNode'
        color = 'rgba(234, 207, 159, 0.7)'
        label = type(node).__name__
        node_id = parentNode.label + "_" + label

    elif macroType == "dummy_macro_expanded":
        node_width, node_height = get_macro_node_size(node)
        node_height = node_height * 100 + 80
        node_width = node_width * 200 + 390 
        nodeType = 'dummyMacroExpanded'
        color = 'rgba(234, 207, 159, 0.7)'


    elif macroType == "test_invert":
        node_width = 150
        nodeType = 'reverseSubNode'
        color = get_color(node=node, theme='light')
        source_labels = list(node.inputs.channel_dict.keys())
        target_labels = list(node.outputs.channel_dict.keys()) 
        n_inputs = len(list(node.outputs.channel_dict.keys()))
        n_outputs = len(list(node.inputs.channel_dict.keys()))
        label = "←" + label

    elif macroType == "control":
        node_width = 300
        node_height = 50
        nodeType = 'subNode'
        color = 'rgba(128, 128, 255, 1)'
        source_labels = []
        target_labels = []
        n_inputs = []
        n_outputs = []
        label = "Control-Flow-Representation"

    else :
        node_width = 150
        nodeType = 'customNode'
        color = get_color(node=node, theme='light')



    return {
        'id': node_id,
        'data': {
            'label': label,
            'source_labels': source_labels,
            'target_labels': target_labels,
            'import_path': get_import_path(node),
            'target_values': get_node_values(node.inputs.channel_dict),
            'target_types': get_node_types(node.inputs),
            'target_types_raw': get_raw_target_types(node.inputs),
            'target_literal_values': get_node_literal_values(node.inputs),
            'target_literal_types': get_node_literal_types(node.inputs),
            'source_values': get_node_values(node.outputs.channel_dict),
            'source_types': get_node_types(node.outputs),
            'source_types_raw': get_raw_source_types(node.outputs),
            'failed': str(node.failed),
            'running': str(node.running),
            'ready': str(node.outputs.ready),
            'cache_hit': str(node.cache_hit),
            'python_object_id': id(node),
        },
        'position': get_node_position(node),
        'type': nodeType,
        'layer': 1,
        'style': {'padding': 5,
                  'background': color,
                  'borderRadius': '10px',
                  'width': f'{node_width}PX',
                  'width_unitless': node_width,
                  'height': f'{node_height}px',
                  'height_unitless': node_height},
        'targetPosition': 'left',
        'sourcePosition': 'right',
        'parentId': parentNode.label,
        'extent': 'parent',
        'draggable' : False,
    }





def internal_loop_node_dict(node):

    x = len(list(node.outputs.channel_dict))*16 + 40 
    node_id = node.label + "_outputs"
    layer = 1
    
    return {
        'id': "loop",
        'data': {
            'label': "←loop",
            'source_labels': ["next", "now"],
            'target_labels': ["this", "last"],
            'import_path': '',
            'target_values': [],
            'target_types': [],
            'target_types_raw': [],
            'target_literal_values': [],
            'target_literal_types': [],
            'source_values': [],
            'source_types': [],
            'source_types_raw': [],
            'failed': 'False',
            'running': 'False',
            'ready': 'False',
            'cache_hit': 'False',
            'python_object_id': id(node),
        },
        'position': {'x': 600, 'y': 110},
        'type': 'reverseSubNode',
        'layer': layer,
        'style': {'padding': 5,
                  'background': "rgba(171, 190, 209, 1)",
                  'borderRadius': '10px',
                  'width': '100px',
                  'width_unitless': 100,
                  'height': '70px',
                  'height_unitless': 70},
        'targetPosition': 'left',
        'sourcePosition': 'right',
        'draggable' : False,
        'parentId': node.label,
        'extent': 'parent',
    }



def single_in_node_dict(node):

    node_id = node.label + "_input"
    x = len(list(node.inputs.channel_dict))*16 + 8
    #x = 18
    pos = 10
    #pos = 10+16*i
    layer = 1

    #            'source_labels': [list(node.inputs.channel_dict)[i]],
    #            'source_labels': list(node.inputs.channel_dict),
    
    return {
        'id': node_id,
        'data': {
            'label': node_id,
            'source_labels': list(node.inputs.channel_dict),
            'target_labels': [],
            'import_path': '',
            'target_values': [],
            'target_types': [],
            'target_types_raw': [],
            'target_literal_values': [],
            'target_literal_types': [],
            'source_values': [],
            'source_types': [],
            'source_types_raw': [],
            'failed': 'False',
            'running': 'False',
            'ready': 'False',
            'cache_hit': 'False',
            'python_object_id': id(node),
        },
        'position': {'x': 8, 'y': 22},
        'type': 'inNode',
        'layer': layer,
        'style': {'padding': 0,
                  'background': "rgba(171, 190, 209, 1)",
                  'borderRadius': '2px',
                  'width': '100px',
                  'width_unitless': 100,
                  'height': f'{x}px',
                  'height_unitless': x},
        'targetPosition': 'left',
        'sourcePosition': 'right',
        'parentId': node.label,
        'extent': 'parent',
    }


def single_out_node_dict(node, x_pos):

    node_id = node.label + "_output"   
    #node_id = node.label + "_output_" + str(i)
    x = len(list(node.outputs.channel_dict))*16+8
    #x = 18
    pos = 10
    #pos = 10+16*i
    layer = 1

    #            'target_labels': [list(node.outputs.channel_dict)[i]],
    #            'target_labels': list(node.outputs.channel_dict),
    
    return {
        'id': node_id,
        'data': {
            'label': node_id,
            'source_labels': [],
            'target_labels': list(node.outputs.channel_dict),
            'import_path': '',
            'target_values': [],
            'target_types': [],
            'target_types_raw': [],
            'target_literal_values': [],
            'target_literal_types': [],
            'source_values': [],
            'source_types': [],
            'source_types_raw': [],
            'failed': 'False',
            'running': 'False',
            'ready': 'False',
            'cache_hit': 'False',
            'python_object_id': id(node),
        },
        'position': {'x': x_pos, 'y': 22},
        'type': 'inNode',
        'layer': layer,
        'style': {'padding': 0,
                  'background': "rgba(171, 190, 209, 1)",
                  'borderRadius': '2px',
                  'width': '100px',
                  'width_unitless': 100,
                  'height': f'{x}px',
                  'height_unitless': x},
        'targetPosition': 'left',
        'sourcePosition': 'right',
        'draggable' : False,
        'parentId': node.label,
        'extent': 'parent',
    }



def iter_zip_node_dict(node_type, node):

    color = 'rgba(162, 234, 159, 1)'
    
    if node_type == "iter_on":
        node_id = node.label + "_iter"  
        i_list = node._iter_on
    
    elif node_type == "zip_on":
        node_id = node.label + "_zip"  
        i_list = node._zip_on


    x = len(i_list)*16 + 40 

    layer = 1
    
    return {
        'id': node_id,
        'data': {
            'label': node_type,
            'source_labels': i_list,
            'target_labels': i_list,
            'import_path': '',
            'target_values': [],
            'target_types': [],
            'target_types_raw': [],
            'target_literal_values': [],
            'target_literal_types': [],
            'source_values': [],
            'source_types': [],
            'source_types_raw': [],
            'failed': 'False',
            'running': 'False',
            'ready': 'False',
            'cache_hit': 'False',
            'python_object_id': id(node),
        },
        'position': {'x': 0, 'y': 0},
        'type': 'subNode',
        'layer': layer,
        'style': {'padding': 5,
                  'background': color,
                  'borderRadius': '10px',
                  'width': '100px',
                  'width_unitless': 100,
                  'height': f'{x}px',
                  'height_unitless': x},
        'targetPosition': 'left',
        'sourcePosition': 'right',
        'draggable' : False,
        'parentId': node.label,
        'extent': 'parent',
    }




#------------------------------------------------------------------------------------------

def get_nodes(wf, expandedMacros, buildExpand):
    nodes = [] 
    
    for k, v in wf.children.items():
        if isinstance(v, Macro):
            if v.label in expandedMacros:
                nodes.append(get_node_dict(v, "expanded", key=k))
                for child in list(v):
                    nodes.append(get_macro_subnode_dict(child, v.label, key=k))
                nodes.append(single_in_node_dict(v))
                width, height = get_macro_node_size(v)
                nodes.append(single_out_node_dict(v, width*200+292))
            else:
                nodes.append(get_node_dict(v, "collapsed", key=k))
        elif isinstance(v, While): 
            if v.label in expandedMacros:

                temp_wf = Workflow('temp')
                temp_wf.body1 = v._body_node_class()
                temp_wf.body2 = v._body_node_class()
                temp_wf.test = v._test_node_class()
                
                body_node_label = type(temp_wf.body1).__name__
                body_node_id = v.label + "_" + body_node_label      
                test_node_label =  type(temp_wf.test).__name__
                test_node_id = v.label + "_" + test_node_label  

                width, height = get_macro_node_size(temp_wf.body1)
                
                if v.label in buildExpand: 
                    
                    nodes.append(get_node_dict(v, "while_loop_expanded", key=k))
                    temp_save = get_loop_body_node_dict(temp_wf.body1, "dummy_macro_expanded", v, key=None)

                    temp_save['id'] = body_node_id + "_0"   
                    temp_save['data']['label'] = body_node_label + "_0"
                    temp_save["position"] = {'x': 150, 'y':150}
                    nodes.append(temp_save)
    
                    
                    for child in list(temp_wf.body1):
                        temp_save = get_macro_subnode_dict(child, temp_wf.body1.label, key=k)
                        temp_save['id'] = body_node_id + "_0_" + temp_save['data']['label']
                        temp_save['parentId'] = body_node_id + "_0"  
                        nodes.append(temp_save)

                    #nodes.append(in_node_dict(temp_wf.body1))
                    #nodes.append(out_node_dict(temp_wf.body1))
                    
                    temp_save = single_in_node_dict(temp_wf.body1)
                    temp_save['id'] = body_node_id + "_0_input"
                    temp_save['data']['label'] = body_node_label + "_0_input"
                    temp_save['parentId'] = body_node_id + "_0"
                    nodes.append(temp_save)

                    
                    temp_save = single_out_node_dict(temp_wf.body1, width*200+282)
                    temp_save['id'] = body_node_id + "_0_output"
                    temp_save['data']['label'] = body_node_label + "_0_output"
                    temp_save['parentId'] = body_node_id + "_0"
                    nodes.append(temp_save)
    
                    temp_save = get_loop_body_node_dict(temp_wf.body2, "collapsed", v, key=None)
                    temp_save['id'] = body_node_id + "_1"   
                    temp_save['data']['label'] = body_node_label + "_1"
                    temp_save["position"] = {'x': width*200 + 650, 'y':150}
                    nodes.append(temp_save)
    
                    temp_save = get_loop_body_node_dict(temp_wf.test, "custom", v, key=None)
                    temp_save['id'] = test_node_id   
                    temp_save['data']['label'] = test_node_label
                    temp_save["position"] = {'x': width*200 + 650, 'y':50}
                    nodes.append(temp_save)

                    """
                    if len(v.inputs.channel_dict) > 0 :
                        for i in range(len(v.inputs.channel_dict)):
                            nodes.append(single_in_node_dict(v, i))

                    if len(v.outputs.channel_dict) > 0 :
                        for i in range(len(v.outputs.channel_dict)):
                            nodes.append(single_out_node_dict(v, i))
                    """
                    
                    nodes.append(single_in_node_dict(v))
                    nodes.append(single_out_node_dict(v, width*200 + 892))
                    

                
                else:
                    
                    nodes.append(get_node_dict(v, "while_loop_expanded", key=k))

                    
                    temp_save = get_loop_view_node_dict(temp_wf.body1, "body", v, key=None)
                    temp_save['id'] = body_node_id + "_cf"   
                    temp_save['data']['label'] = body_node_label
                    temp_save["position"] = {'x': 700, 'y':200}
                    temp_save["parent"] = v.label
                    nodes.append(temp_save)
    
                        
                    nodes.append(start_node_dict(v))
                    nodes.append(end_node_dict(v))

                    temp_save = get_loop_view_node_dict(temp_wf.test, "test", v, key=None)
                    temp_save['id'] = test_node_id + "_cf"   
                    temp_save['data']['label'] = test_node_label
                    temp_save["position"] = {'x': 400, 'y':200}
                    temp_save["parent"] = v.label
                    nodes.append(temp_save)

                    nodes.append(single_in_node_dict(v))
                    nodes.append(single_out_node_dict(v, 1190))
                    
                    if len(v.inputs.channel_dict) > 0 :
                            nodes.append(single_in_node_dict(v))
                            nodes.append(single_out_node_dict(v, width*200 + 892))


                    temp_save = get_loop_body_node_dict(temp_wf.body2, "control", v, key=None)
                    temp_save['id'] = v.label + "_cf_label"                       
                    temp_save["position"] = {'x': 500, 'y':50}
                    temp_save["parent"] = v.label
                    nodes.append(temp_save)
                    
            else:
                nodes.append(get_node_dict(v, "loop_collapsed", key=k))

        elif isinstance(v, For):
            if v.label in expandedMacros:

                temp_wf = Workflow('temp')
                temp_wf.body = v._body_node_class()
                
                body_node_label = type(temp_wf.body).__name__
                body_node_id = v.label + "_" + body_node_label      

                width, height = get_macro_node_size(temp_wf.body)


                if v.label in buildExpand: 

                    nodes.append(get_node_dict(v, "for_loop_expanded", key=k))

                    temp_save = get_loop_body_node_dict(temp_wf.body, "dummy_macro_expanded", v, key=None)

                    temp_save['id'] = body_node_id    
                    temp_save['data']['label'] = body_node_label 
                    temp_save["position"] = {'x': 300, 'y':150}
                    nodes.append(temp_save)

                    for child in list(temp_wf.body):
                        temp_save = get_macro_subnode_dict(child, temp_wf.body.label, key=k)
                        temp_save['id'] = body_node_id + "_" + temp_save['data']['label']
                        temp_save['parentId'] = body_node_id + ""  
                        nodes.append(temp_save)

                    temp_save = single_in_node_dict(temp_wf.body)
                    temp_save['id'] = body_node_id + "_input"
                    temp_save['data']['label'] = body_node_label + "_input"
                    temp_save['parentId'] = body_node_id
                    nodes.append(temp_save)

                    
                    temp_save = single_out_node_dict(temp_wf.body, width*200+282)
                    temp_save['id'] = body_node_id + "_output"
                    temp_save['data']['label'] = body_node_label + "_output"
                    temp_save['parentId'] = body_node_id
                    nodes.append(temp_save)          

                    nodes.append(single_in_node_dict(v))
                    nodes.append(single_out_node_dict(v, max(width * 200 + 790, 1390)))
                    

                    if len(v._iter_on) > 0:
                        temp_save = iter_zip_node_dict("iter_on", v)
                        temp_save["position"] = {'x': 150, 'y':100}
                        nodes.append(temp_save)
                        
                    if len(v._zip_on) > 0:
                        temp_save = iter_zip_node_dict("zip_on", v)
                        temp_save["position"] = {'x': 150, 'y':200}
                        nodes.append(temp_save)

                
                else:
                    nodes.append(get_node_dict(v, "for_loop_expanded", key=k))
                    
                    temp_save = get_loop_view_node_dict(temp_wf.body, "body", v, key=None)
                    temp_save['id'] = body_node_id + "_cf"
                    temp_save['data']['label'] = body_node_label
                    temp_save["position"] = {'x': 700, 'y':200}
                    nodes.append(temp_save)
    
                        
                    temp_save = start_node_dict(v)
                    temp_save["id"] = v.label + "_start"
                    nodes.append(temp_save)
                    temp_save = end_node_dict(v)
                    temp_save["id"] = v.label + "_end"
                    nodes.append(temp_save)

                    temp_save = get_loop_view_node_dict(temp_wf.body, "range", v, key=None)
                    temp_save['id'] = v.label + "_in_range"
                    temp_save["position"] = {'x': 400, 'y':200}
                    nodes.append(temp_save)

                    temp_save = get_loop_view_node_dict(temp_wf.body, "increment", v, key=None)
                    temp_save['id'] = v.label + "_increment"
                    temp_save["position"] = {'x': 1000, 'y':200}
                    nodes.append(temp_save)

                    nodes.append(single_in_node_dict(v))
                    nodes.append(single_out_node_dict(v, max(width * 200 + 790, 1390)))


                    temp_save = get_loop_body_node_dict(temp_wf.body, "control", v, key=None)
                    temp_save['id'] = v.label + "_cf_label"   
                    temp_save["position"] = {'x': 600, 'y':50}
                    temp_save['parentId'] = v.label
                    nodes.append(temp_save)    
            else:
                nodes.append(get_node_dict(v, "loop_collapsed", key=k))
        else:
            nodes.append(get_node_dict(v, "normal", key=k))

    return nodes


def get_node_from_path(import_path, log=None, reload=False):
    """Import a node from a file path.

    Be careful with `reload` as it will break type hints from pyiron_workflow.

    Args:
        import_path (str): where to import from
        log (???): where to log to
        reload (bool): whether to reload modules in case their source changed.

    Returns:
        node
    """
    # Split the path into module and object part
    module_path, _, name = import_path.rpartition(".")
    # Import the module
    try:
        module = importlib.import_module(module_path)
    except ModuleNotFoundError as e:
        log.append_stderr(e)
        return None

    if reload:
        # Reload the module
        try:
            importlib.reload(module)
        except ImportError as e:
            if log:
                log.append_stderr(e)
            return None

    # Get the object
    object_from_path = getattr(module, name)
    return object_from_path


def get_edges(wf, expandedMacros, buildExpand):
    edges = []
    n = 0
    ic = 0
    for ic, (out, inp) in enumerate(wf.graph_as_dict["edges"]["data"].keys()):
        out_node, out_port = out.split('/')[-1].split('.', 1)
        inp_node, inp_port = inp.split('/')[-1].split('.', 1)

        edge_id = out_node + "__" + out_port + "-" + inp_node + "__" + inp_port

        edge_dict = dict()
        edge_dict["source"] = out_node
        edge_dict["sourceHandle"] = out_port
        edge_dict["target"] = inp_node
        edge_dict["targetHandle"] = inp_port
        edge_dict["id"] = edge_id
        edge_dict["type"] = "edge"
        edge_dict["parent"] = ""
        edge_dict["style"] = {"stroke": "black", "strokeWidth": 2}

        edges.append(edge_dict)

    try:
        id_count = ic
    except:
        id_count = 0

    for k, v in wf.children.items():
        if isinstance(v, Macro) and v.label in expandedMacros:
            for ic2, (out, inp) in enumerate(v.graph_as_dict["edges"]["data"].keys()):
                out_node, out_port = out.split('/')[-1].split('.', 1)
                inp_node, inp_port = inp.split('/')[-1].split('.', 1)
                parentId = out.split('/')[-2]
                id_count += 1

                edge_id = out_node + "__" + out_port + "-" + inp_node + "__" + inp_port
                
                edge_dict = dict()
                edge_dict["source"] = parentId + "_" + out_node
                edge_dict["sourceHandle"] = out_port
                edge_dict["target"] = parentId + "_" + inp_node
                edge_dict["targetHandle"] = inp_port
                edge_dict["id"] = edge_id 
                edge_dict["type"] = "macroSubEdge"
                edge_dict["layer"] = 1
                edge_dict["parent"] = parentId
                edge_dict["style"] = {"stroke": "black", "strokeWidth": 2}

                edges.append(edge_dict)

            inputs_label = v.label + "_input"
            outputs_label = v.label + "_output"

            for n in v.inputs:
            
                target_node, target_handle = n._value_receiver.full_label.split('/')[-1].split('.', 1)
                edge_id = v.label + "inEdge_" + n.label
                
                edge_dict = dict()
                edge_dict["source"] = inputs_label
                edge_dict["sourceHandle"] = n.label
                edge_dict["target"] = v.label + "_" + target_node
                edge_dict["targetHandle"] = target_handle
                edge_dict["id"] = edge_id
                edge_dict["type"] = "macroSubEdge"
                edge_dict["layer"] = 1
                edge_dict["parent"] = v.label
                edge_dict["style"] = {"stroke": "darkgray", "strokeWidth": 2}
                edges.append(edge_dict)

            for m in v.outputs:
                for i, (k, w) in enumerate(v.children.items()):
                    if k == m.label:
                        out_handle = list(w.outputs.channel_dict.keys())[0]
                        
                edge_id = v.label + "_outEdge_" + m.label
                
                edge_dict = dict()
                edge_dict["source"] = v.label + "_" + m.label
                edge_dict["sourceHandle"] = out_handle
                edge_dict["target"] = outputs_label
                edge_dict["targetHandle"] = m.label
                edge_dict["id"] = edge_id
                edge_dict["type"] = "macroSubEdge"
                edge_dict["layer"] = 1
                edge_dict["parent"] = v.label
                edge_dict["style"] = {"stroke": "darkgray", "strokeWidth": 2}
                edges.append(edge_dict)
            

#------------------------------------------------------------------------------
        
        elif isinstance(v, While): 
            if v.label in expandedMacros:

                temp_wf = Workflow('temp')
                temp_wf.body = v._body_node_class()
                temp_wf.test = v._test_node_class()
                loop_body_id = v.label + '_' + v._body_node_class.__name__ + '_0'
                loop_other_body_id = v.label + '_' + v._body_node_class.__name__ + '_1'
                loop_test_id = v.label + '_' + v._test_node_class.__name__    
                

            
                if v.label in buildExpand: 

                    edge_dict = []
                    
                    for n in v.inputs:

                        n_cut = n.label.split("_",1)[1]  
                        edge_id = v.label + "_inEdge_" + n_cut
                        
                        
                        if n.label.split("_",1)[0] == "test":
                            
                            edge_dict = dict()
                            edge_dict["source"] = v.label + "_input"
                            edge_dict["sourceHandle"] = "test_" + n_cut
                            edge_dict["target"] = loop_test_id
                            edge_dict["targetHandle"] = n_cut
                            edge_dict["id"] = edge_id
                            edge_dict["type"] = "macroSubEdge"
                            edge_dict["layer"] = 1
                            edge_dict["parent"] = v.label
                            edge_dict["style"] = {"stroke": "darkgray", "strokeWidth": 2}
                            edges.append(edge_dict)
                        
                        if n.label.split("_",1)[0] == "body":
                            n_cut = n.label.split("_",1)[1]
                            
                            edge_dict = dict()
                            edge_dict["source"] = v.label + "_input"
                            edge_dict["sourceHandle"] = "body_" + n_cut
                            edge_dict["target"] = loop_body_id
                            edge_dict["targetHandle"] = n_cut
                            edge_dict["id"] = edge_id
                            edge_dict["type"] = "macroSubEdge"
                            edge_dict["layer"] = 1
                            edge_dict["parent"] = v.label
                            edge_dict["style"] = {"stroke": "darkgray", "strokeWidth": 2}
                            edges.append(edge_dict)


                    for port_tuple in v._body_to_test_connections:

                        edge_id = loop_body_id +"__" + port_tuple[0] + "-" + loop_test_id + "__" + port_tuple[1]
                        
                        edge_dict = dict()
                        edge_dict["source"] = loop_body_id
                        edge_dict["sourceHandle"] = port_tuple[0]
                        edge_dict["target"] = loop_test_id
                        edge_dict["targetHandle"] = port_tuple[1]
                        edge_dict["id"] = edge_id
                        edge_dict["type"] = "macroSubEdge"
                        edge_dict["layer"] = 1
                        edge_dict["parent"] = v.label
                        edge_dict["style"] = {"stroke": "black", "strokeWidth": 2}
                        edges.append(edge_dict)

                    for port_tuple in v._body_to_body_connections:

                        edge_id = loop_body_id +"__" + port_tuple[0] + "-" + loop_other_body_id + "__" + port_tuple[1]
                        
                        edge_dict = dict()
                        edge_dict["source"] = loop_body_id
                        edge_dict["sourceHandle"] = port_tuple[0]
                        edge_dict["target"] = loop_other_body_id
                        edge_dict["targetHandle"] = port_tuple[1]
                        edge_dict["id"] = edge_id
                        edge_dict["type"] = "macroSubEdge"
                        edge_dict["layer"] = 1
                        edge_dict["parent"] = v.label
                        edge_dict["style"] = {"stroke": "black", "strokeWidth": 2}
                        edges.append(edge_dict)
                        
                    for out_port in v.outputs:     

                        edge_id = loop_other_body_id + "__" + out_port.label + "-" + v.label + "_output__" + out_port.label
                        
                        edge_dict = dict()
                        edge_dict["source"] = loop_other_body_id
                        edge_dict["sourceHandle"] = out_port.label
                        edge_dict["target"] = v.label + "_output"
                        edge_dict["targetHandle"] = out_port.label
                        edge_dict["id"] = edge_id
                        edge_dict["type"] = "macroSubEdge"
                        edge_dict["layer"] = 1
                        edge_dict["parent"] = v.label
                        edge_dict["style"] = {"stroke": "darkgray", "strokeWidth": 2}
                        edges.append(edge_dict)

                    
                    
                    for ic2, (out, inp) in enumerate(temp_wf.body.graph_as_dict["edges"]["data"].keys()):
                        out_node, out_port = out.split('/')[-1].split('.', 1)
                        inp_node, inp_port = inp.split('/')[-1].split('.', 1)
                    
                    
                        edge_dict = dict()
                        edge_dict["source"] = loop_body_id + "_" + out_node
                        edge_dict["sourceHandle"] =out_port
                        edge_dict["target"] = loop_body_id + "_" + inp_node
                        edge_dict["targetHandle"] =inp_port
                        edge_dict["id"] = out_node + out_port + "-" + inp_node + inp_port  
                        edge_dict["type"] = "macroSubEdge"
                        edge_dict["layer"] = 1
                        edge_dict["parent"] = loop_body_id
                        edge_dict["style"] = {"stroke": "black", "strokeWidth": 2}

                        edges.append(edge_dict)    

                    for n in temp_wf.body.inputs:
                                
                        target_node, target_handle = n._value_receiver.full_label.split('/')[-1].split('.', 1)
                        edge_id = loop_body_id + "inEdge_" + n.label
                    
                        #print(target_node, target_handle, n.label)
                    
                        edge_dict = dict()
                        edge_dict["source"] = loop_body_id + "_input"
                        edge_dict["sourceHandle"] = n.label
                        edge_dict["target"] = loop_body_id + "_" + target_node
                        edge_dict["targetHandle"] = target_handle
                        edge_dict["id"] = edge_id
                        edge_dict["type"] = "macroSubEdge"
                        edge_dict["layer"] = 1
                        edge_dict["parent"] = loop_body_id
                        edge_dict["style"] = {"stroke": "darkgray", "strokeWidth": 2}
                        edges.append(edge_dict)
                        
                        
                    for m in temp_wf.body.outputs:
                        for i, (k, w) in enumerate(temp_wf.body.children.items()):
                            if k == m.label:
                                out_handle = list(w.outputs.channel_dict.keys())[0]
                    
                                #print(out_handle)
                    
                    
                        edge_dict = dict()
                        edge_dict["source"] = loop_body_id + "_" + m.label
                        edge_dict["sourceHandle"] = out_handle
                        edge_dict["target"] = loop_body_id + "_output"
                        edge_dict["targetHandle"] = m.label
                        edge_dict["id"] = loop_body_id + "_outEdge_" + out_handle
                        edge_dict["type"] = "macroSubEdge"
                        edge_dict["layer"] = 1
                        edge_dict["parent"] = loop_body_id
                        edge_dict["style"] = {"stroke": "darkgray", "strokeWidth": 2}
                        edges.append(edge_dict)


                else:

                    body_cf_id = v.label + '_' + v._body_node_class.__name__ + "_cf"
                    test_cf_id = v.label + '_' + v._test_node_class.__name__ + "_cf"
                    
                    edge_dict = dict()
                    edge_dict["source"] = v.label + "_start"
                    edge_dict["target"] = test_cf_id
                    edge_dict["id"] = v.label + "_start" + "-" + v.label + "test_cf"
                    edge_dict["type"] = "macroSubEdge"
                    edge_dict["layer"] = 1
                    edge_dict["parent"] = v.label
                    edge_dict["style"] = {"stroke": "blue", "strokeWidth": 2}
                    edge_dict["markerEnd"] = {"type":"arrowclosed", "color": "blue"}
                    edges.append(edge_dict)

                    edge_dict = dict()
                    edge_dict["source"] = test_cf_id
                    edge_dict["sourceHandle"] = "true"                   
                    edge_dict["target"] = body_cf_id
                    edge_dict["id"] = v.label + "_test_cf" + "-" + v.label + "_body_cf"
                    edge_dict["type"] = "macroSubEdge"
                    edge_dict["layer"] = 1
                    edge_dict["parent"] = v.label
                    edge_dict["style"] = {"stroke": "blue", "strokeWidth": 2}
                    edge_dict["markerEnd"] = {"type":"arrowclosed", "color": "blue"}
                    edges.append(edge_dict)

                    edge_dict = dict()
                    edge_dict["source"] = test_cf_id
                    edge_dict["sourceHandle"] = "false"                   
                    edge_dict["target"] = v.label + "_end"
                    edge_dict["id"] = v.label + "_test_cf" + "-" + v.label + "_end"
                    edge_dict["type"] = "macroSubEdge"
                    edge_dict["layer"] = 1
                    edge_dict["parent"] = v.label
                    edge_dict["style"] = {"stroke": "blue", "strokeWidth": 2}
                    edge_dict["markerEnd"] = {"type":"arrowclosed", "color": "blue"}
                    edges.append(edge_dict)

                    edge_dict = dict()
                    edge_dict["source"] = body_cf_id              
                    edge_dict["target"] = test_cf_id
                    edge_dict["id"] = v.label + "_body_cf" + "-" + v.label + "_test_cf"
                    edge_dict["type"] = "loopEdge"
                    edge_dict["layer"] = 1
                    edge_dict["parent"] = v.label
                    edge_dict["style"] = {"stroke": "blue", "strokeWidth": 2}
                    edge_dict["markerEnd"] = {"type":"arrowclosed", "color": "blue"}
                    edges.append(edge_dict)


        elif isinstance(v, For): 
            if v.label in expandedMacros:

                temp_wf = Workflow('temp')
                temp_wf.body = v._body_node_class()
                
                if v.label in buildExpand: 


                    loop_body_id = v.label + '_' + v._body_node_class.__name__
    
                    for iterator in v._iter_on:
                    
                        out_node = v.label + "_input"
                        out_port = iterator
                        inp_node = v.label + "_iter"
                        inp_port = iterator
                        parentId = v.label            
                        
                        edge_dict = dict()
                        edge_dict["source"] = out_node
                        edge_dict["sourceHandle"] = out_port
                        edge_dict["target"] = inp_node
                        edge_dict["targetHandle"] = inp_port
                        edge_dict["id"] = out_node + out_port + "-" + inp_node + inp_port 
                        edge_dict["type"] = "macroSubEdge"
                        edge_dict["layer"] = 1
                        edge_dict["parent"] = parentId
                        edge_dict["style"] = {"stroke": "darkgray", "strokeWidth": 2}
    
                        edges.append(edge_dict)
    
                        out_node = v.label + "_iter"
                        out_port = iterator
                        inp_node = loop_body_id
                        inp_port = iterator
                        parentId = v.label            
                        
                        edge_dict = dict()
                        edge_dict["source"] = out_node
                        edge_dict["sourceHandle"] = out_port
                        edge_dict["target"] = inp_node
                        edge_dict["targetHandle"] = inp_port
                        edge_dict["id"] = out_node + out_port + "-" + inp_node + inp_port 
                        edge_dict["type"] = "macroSubEdge"
                        edge_dict["layer"] = 1
                        edge_dict["parent"] = parentId
                        edge_dict["style"] = {"stroke": "darkgray", "strokeWidth": 2}                    
    
                        edges.append(edge_dict)
                        
                        out_node = v.label + "_iter"
                        out_port = iterator
                        inp_node = v.label + "_output"
                        inp_port = iterator
                        parentId = v.label            
                        
                        edge_dict = dict()
                        edge_dict["source"] = out_node
                        edge_dict["sourceHandle"] = out_port
                        edge_dict["target"] = inp_node
                        edge_dict["targetHandle"] = inp_port
                        edge_dict["id"] = out_node + out_port + "-" + inp_node + inp_port 
                        edge_dict["type"] = "macroSubEdge"
                        edge_dict["layer"] = 1
                        edge_dict["parent"] = parentId
                        edge_dict["style"] = {"stroke": "darkgray", "strokeWidth": 2}  

                        edges.append(edge_dict)

                    for iterator in v._zip_on:
                    
                        out_node = v.label + "_input"
                        out_port = iterator
                        inp_node = v.label + "_zip"
                        inp_port = iterator
                        parentId = v.label            
                        
                        edge_dict = dict()
                        edge_dict["source"] = out_node
                        edge_dict["sourceHandle"] = out_port
                        edge_dict["target"] = inp_node
                        edge_dict["targetHandle"] = inp_port
                        edge_dict["id"] = out_node + out_port + "-" + inp_node + inp_port 
                        edge_dict["type"] = "macroSubEdge"
                        edge_dict["layer"] = 1
                        edge_dict["parent"] = parentId
                        edge_dict["style"] = {"stroke": "darkgray", "strokeWidth": 2}
    
                        edges.append(edge_dict)
    
                        out_node = v.label + "_zip"
                        out_port = iterator
                        inp_node = loop_body_id
                        inp_port = iterator
                        parentId = v.label            
                        
                        edge_dict = dict()
                        edge_dict["source"] = out_node
                        edge_dict["sourceHandle"] = out_port
                        edge_dict["target"] = inp_node
                        edge_dict["targetHandle"] = inp_port
                        edge_dict["id"] = out_node + out_port + "-" + inp_node + inp_port 
                        edge_dict["type"] = "macroSubEdge"
                        edge_dict["layer"] = 1
                        edge_dict["parent"] = parentId
                        edge_dict["style"] = {"stroke": "black", "strokeWidth": 2}                    
    
                        edges.append(edge_dict)
                        
                        out_node = v.label + "_zip"
                        out_port = iterator
                        inp_node = v.label + "_output"
                        inp_port = iterator
                        parentId = v.label            
                        
                        edge_dict = dict()
                        edge_dict["source"] = out_node
                        edge_dict["sourceHandle"] = out_port
                        edge_dict["target"] = inp_node
                        edge_dict["targetHandle"] = inp_port
                        edge_dict["id"] = out_node + out_port + "-" + inp_node + inp_port 
                        edge_dict["type"] = "macroSubEdge"
                        edge_dict["layer"] = 1
                        edge_dict["parent"] = parentId
                        edge_dict["style"] = {"stroke": "black", "strokeWidth": 2}  

                        edges.append(edge_dict)


                    
                    for ic2, (out, inp) in enumerate(temp_wf.body.graph_as_dict["edges"]["data"].keys()):
                        out_node, out_port = out.split('/')[-1].split('.', 1)
                        inp_node, inp_port = inp.split('/')[-1].split('.', 1)
                    
                    
                        edge_dict = dict()
                        edge_dict["source"] = loop_body_id + "_" + out_node
                        edge_dict["sourceHandle"] =out_port
                        edge_dict["target"] = loop_body_id + "_" + inp_node
                        edge_dict["targetHandle"] =inp_port
                        edge_dict["id"] = out_node + out_port + "-" + inp_node + inp_port  
                        edge_dict["type"] = "macroSubEdge"
                        edge_dict["layer"] = 1
                        edge_dict["parent"] = loop_body_id
                        edge_dict["style"] = {"stroke": "black", "strokeWidth": 2}

                        edges.append(edge_dict)    

                    for n in temp_wf.body.inputs:
                                
                        target_node, target_handle = n._value_receiver.full_label.split('/')[-1].split('.', 1)
                        edge_id = loop_body_id + "inEdge_" + n.label
                    
                        #print(target_node, target_handle, n.label)
                    
                        edge_dict = dict()
                        edge_dict["source"] = loop_body_id + "_input"
                        edge_dict["sourceHandle"] = n.label
                        edge_dict["target"] = loop_body_id + "_" + target_node
                        edge_dict["targetHandle"] = target_handle
                        edge_dict["id"] = edge_id
                        edge_dict["type"] = "macroSubEdge"
                        edge_dict["layer"] = 1
                        edge_dict["parent"] = loop_body_id
                        edge_dict["style"] = {"stroke": "darkgray", "strokeWidth": 2}
                        edges.append(edge_dict)
                        
                        
                    for m in temp_wf.body.outputs:
                        for i, (k, w) in enumerate(temp_wf.body.children.items()):
                            if k == m.label:
                                out_handle = list(w.outputs.channel_dict.keys())[0]
                    
                                #print(out_handle)
                    
                    
                        edge_dict = dict()
                        edge_dict["source"] = loop_body_id + "_" + m.label
                        edge_dict["sourceHandle"] = out_handle
                        edge_dict["target"] = loop_body_id + "_output"
                        edge_dict["targetHandle"] = m.label
                        edge_dict["id"] = loop_body_id + "_outEdge_" + out_handle
                        edge_dict["type"] = "macroSubEdge"
                        edge_dict["layer"] = 1
                        edge_dict["parent"] = loop_body_id
                        edge_dict["style"] = {"stroke": "darkgray", "strokeWidth": 2}
                        edges.append(edge_dict)

                    for in_port in v.outputs:  
                        for out_port in temp_wf.body.outputs:
                            if in_port.label == out_port.label:   
                    
                                edge_id = loop_body_id + "__" + out_port.label + "-" + v.label + "_output__" + in_port.label
                                
                                edge_dict = dict()
                                edge_dict["source"] = loop_body_id
                                edge_dict["sourceHandle"] = out_port.label
                                edge_dict["target"] = v.label + "_output"
                                edge_dict["targetHandle"] = in_port.label
                                edge_dict["id"] = edge_id
                                edge_dict["type"] = "macroSubEdge"
                                edge_dict["layer"] = 1
                                edge_dict["parent"] = v.label
                                edge_dict["style"] = {"stroke": "darkgray", "strokeWidth": 2}
                                edges.append(edge_dict)



                else:                         

                    body_cf_id = v.label + '_' + v._body_node_class.__name__ + "_cf"
                    range_id = v.label + "_in_range"
                    inc_id = v.label + "_increment"
                    
                    edge_dict = dict()
                    edge_dict["source"] = v.label + "_start"
                    edge_dict["target"] = range_id
                    edge_dict["id"] = v.label + "_start" + "-" + range_id
                    edge_dict["type"] = "macroSubEdge"
                    edge_dict["layer"] = 1
                    edge_dict["parent"] = v.label
                    edge_dict["style"] = {"stroke": "blue", "strokeWidth": 2}
                    edge_dict["markerEnd"] = {"type":"arrowclosed", "color": "blue"}
                    edges.append(edge_dict)

                    edge_dict = dict()
                    edge_dict["source"] = range_id
                    edge_dict["sourceHandle"] = "true"                   
                    edge_dict["target"] = body_cf_id
                    edge_dict["id"] = range_id + "_true-" + body_cf_id
                    edge_dict["type"] = "macroSubEdge"
                    edge_dict["layer"] = 1
                    edge_dict["parent"] = v.label
                    edge_dict["style"] = {"stroke": "blue", "strokeWidth": 2}
                    edge_dict["markerEnd"] = {"type":"arrowclosed", "color": "blue"}
                    edges.append(edge_dict)

                    edge_dict = dict()
                    edge_dict["source"] = range_id
                    edge_dict["sourceHandle"] = "false"                   
                    edge_dict["target"] = v.label + "_end"
                    edge_dict["id"] = range_id + "-" + v.label + "_end"
                    edge_dict["type"] = "macroSubEdge"
                    edge_dict["layer"] = 1
                    edge_dict["parent"] = v.label
                    edge_dict["style"] = {"stroke": "blue", "strokeWidth": 2}
                    edge_dict["markerEnd"] = {"type":"arrowclosed", "color": "blue"}
                    edges.append(edge_dict)

                    edge_dict = dict()
                    edge_dict["source"] = body_cf_id              
                    edge_dict["target"] = inc_id
                    edge_dict["id"] = body_cf_id + "-" + inc_id
                    edge_dict["type"] = "macroSubEdge"
                    edge_dict["layer"] = 1
                    edge_dict["parent"] = v.label
                    edge_dict["style"] = {"stroke": "blue", "strokeWidth": 2}
                    edge_dict["markerEnd"] = {"type":"arrowclosed", "color": "blue"}
                    edges.append(edge_dict)

                    edge_dict = dict()
                    edge_dict["source"] = inc_id            
                    edge_dict["target"] = range_id
                    edge_dict["id"] = inc_id + "-" + range_id
                    edge_dict["type"] = "loopEdge"
                    edge_dict["layer"] = 1
                    edge_dict["parent"] = v.label
                    edge_dict["style"] = {"stroke": "blue", "strokeWidth": 2}
                    edge_dict["markerEnd"] = {"type":"arrowclosed", "color": "blue"}
                    edges.append(edge_dict)
    
    return edges


#-------------------------------------------------------------------------------

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


def get_macro_node_size(macroNode):

    length_list = []
    depth_list = []
    counter = 0
    
    for out in (list(macroNode.outputs.channel_dict.keys())):

        counter += 1
        graph_list = []
        end = []
        edges = []
        end.append(out.split("__")[0])
    
        graph_list.append(end)
        
        for ic, (out, inp) in enumerate(macroNode.graph_as_dict["edges"]["data"].keys()):
            n = out.count('/')
            out_node, out_port = out.split('/')[n].split('.', 1)
            inp_node, inp_port = inp.split('/')[n].split('.', 1)
        
            edges.append([inp_node, out_node])
        
        i = 0;
        depth = 0
        while graph_list[i] != []:
        
            depth = max(len(graph_list[i]),depth)
            stage = []
            for node in graph_list[i]:
                for edge in edges:
                    if node == edge[0]:
                        stage.append(edge[1])
            graph_list.append(stage)
            i += 1
    
        length = len(graph_list)-1
        
        length_list.append(length)
        depth_list.append(depth)
    
    return (max(length_list), max(depth_list))

    
def create_macro(wf = dict, name = str, root_path='../pyiron_nodes'):

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
                var_def = var_def + v.label + "_" + j.label + ": " + get_input_types_from_hint(j).split(" ")[-1] + " = " + value + ", "

    var_def = var_def[:-2]    

    count = 0
    new_list = list("")
    for ic, (out, inp) in enumerate(wf.graph_as_dict["edges"]["data"].keys()):
        out_node, out_port = out.split('/')[2].split('.', 1)
        inp_node, inp_port = inp.split('/')[2].split('.', 1)
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
    rest_list = list(dict.fromkeys(rest_list))
    
    out_str = "    return "
    for strs in rest_list:
        out_str = out_str + "self." + strs + ", "

    file.write(out_str)
    print("\nSuccessfully created macro: " + root_path + '/' + name + '.py')
    file.close()

    return
