import pyiron_workflow as pwf
from pyiron_workflow import as_function_node, as_macro_node


@as_function_node()

def int_input(a: int = 0):
    return a
