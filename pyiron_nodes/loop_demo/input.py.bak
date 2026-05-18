import pyiron_workflow as pwf
from pyiron_workflow import as_function_node, as_macro_node


@as_function_node()

def int_input(a: int = 0):
    return a

@as_function_node()

def float_input(a: float = 0.0):
    return a

@as_function_node()

def list_input(a_list: list = []):
    return a_list


@as_function_node()

def list_0_to_4():
    return [0,1,2,3,4]

@as_function_node()

def strains():
    strain_list = [-0.06, -0.048, -0.036, -0.024, -0.012,  0.,  0.012,  0.024, 0.036,  0.048,  0.06]
    return strain_list

@as_function_node()

def cellpar():
    par = [2.5526554800834367]
    return par

    