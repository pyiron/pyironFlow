import typing

from pyiron_workflow.nodes.function import Function
from pyiron_workflow.nodes.macro import Macro
from pyiron_workflow.nodes.transform import DataclassNode
from pyiron_workflow.node import Node


def get_node_instance_type(node: Node):

    if isinstance(node, Function):
        return "function"
    elif isinstance(node, Macro):
        return "macro"
    elif isinstance(node, DataclassNode):
        return "dataClassNode"
