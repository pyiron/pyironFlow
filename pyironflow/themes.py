import typing

from pyiron_workflow.nodes.function import Function
from pyiron_workflow.nodes.macro import Macro
from pyiron_workflow.nodes.transform import DataclassNode

if typing.TYPE_CHECKING:
    from pyiron_workflow.node import Node


def get_color(node: Node, theme: typing.Literal['light']):

    if theme == 'light':
        return light_mode(node)
    else:
        raise ValueError(f'Theme must be one of ("light",) but got {theme}')

def light_mode(node: Node):
    if isinstance(node, Function):
        color_light_green = "#a2ea9f"
        return color_light_green
    elif isinstance(node, Macro):
        color_light_orange = "#eacf9f"
        return color_light_orange
    elif isinstance(node, DataclassNode):
        color_light_purple = "#cb9fea"
        return color_light_purple
    else:
        return node.color
