from __future__ import annotations

from typing import Optional

from pyiron_workflow import as_function_node

from pyiron_nodes.atomistic.calculator.data import OutputCalcMinimize, OutputCalcStatic


@as_function_node("energy_last")
def GetEnergyLast(
    calculator: Optional[OutputCalcMinimize | OutputCalcStatic] = None,
) -> float:
    if isinstance(calculator, OutputCalcMinimize):
        energy_last = calculator.final.energy
    elif isinstance(calculator, OutputCalcStatic):
        energy_last = calculator.energy
    return energy_last
    # print ('energy_last:', calculator.energy[-1], type(calculator.energy[-1]))
    # return calculator.energy[-1]
