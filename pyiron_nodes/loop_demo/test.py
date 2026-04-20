import pyiron_workflow as pwf
from pyiron_workflow import as_function_node, as_macro_node


@as_function_node()
def diff_above(x: float | int = 0, y: float | int = 0, max_diff: float | int = 0):
    
    diff = abs(x-y)
    if diff > max_diff:
        diff_above = True
    else:
        diff_above = False
        
    return diff_above