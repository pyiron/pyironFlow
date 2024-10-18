from pyiron_workflow import as_function_node, as_macro_node
import typing
from typing import Optional

@as_function_node()
def part_1(a: Optional[float | int] = None):
    return a+1

@as_function_node()
def part_2(a: int):
    return a+2

@as_function_node()
def part_3(a: int | float = 300):
    return a+3

'''@as_function_node()
def part_4(a: typing.Union[float, int, NoneType]):
    return a+3
'''

@as_macro_node()
def macro_add(wf, a: int):

    # imports

    wf.st = part_1(a)
    wf.nd = part_2(wf.st)
    wf.rd = part_3(wf.nd)
    
    return wf.rd

@as_function_node()
def part_4(a: int, b: int):
    return a/b



from pyiron_workflow import as_function_node, as_macro_node

@as_macro_node()
def macro_new(wf, part1_a: int, part2_a: int, part3_a: int):
    
    from pyiron_nodes.custom_node import part_1
    from pyiron_nodes.custom_node import part_2
    from pyiron_nodes.custom_node import part_3
    wf.part1 = part_1(part1_a)
    wf.part2 = part_2(a = wf.part1)
    wf.part3 = part_3(a = wf.part2)
    return wf.part3
