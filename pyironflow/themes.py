import typing

from pyiron_workflow.datatypes import Node
from pyiron_workflow.atomic_node import Atomic
from pyiron_workflow.dag import Macro
from pyiron_workflow.workflow_node import Workflow
from pyiron_workflow.constant import Constant


def get_color(node: Node, theme: typing.Literal['light']):

    if theme == 'light':
        return light_mode(node)
    else:
        raise ValueError(f'Theme must be one of ("light",) but got {theme}')

def light_mode(node: Node):
    if isinstance(node, Atomic):
        color_light_green = "#a2ea9f"
        return color_light_green
    elif isinstance(node, Macro):
        color_light_orange = "#eacf9f"
        return color_light_orange
    elif isinstance(node, (Workflow, Constant)):
        color_light_purple = "#cb9fea"
        return color_light_purple
    else:
        return "#d0d0d0"
