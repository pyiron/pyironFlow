from pyiron_workflow.nodes.function import Function
from pyiron_workflow.nodes.macro import Macro
from pyiron_workflow.nodes.transform import DataclassNode


def node_color(node, theme):

    if theme == 'light':
        return light_mode(node)

def light_mode(node):
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
