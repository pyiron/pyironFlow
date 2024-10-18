from pyiron_workflow import as_function_node

from pyiron_nodes.atomistic.calculator.data import (
    InputCalcMinimize,
    InputCalcMD,
    InputCalcStatic,
)


@as_function_node("generic")
def Static(structure=None, engine=None):  # , keys_to_store=None):
    output = engine(
        structure=structure,
        calculator=InputCalcStatic(),  # keys_to_store=keys_to_store)
    )
    return output.generic
