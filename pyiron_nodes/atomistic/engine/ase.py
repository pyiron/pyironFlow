from __future__ import annotations

from pyiron_workflow import as_function_node

from pyiron_nodes.atomistic.engine.generic import OutputEngine


@as_function_node("engine")
def EMT():
    from ase.calculators.emt import EMT

    out = OutputEngine(calculator=EMT())

    return out


@as_function_node("engine")
def M3GNet():
    import matgl
    from matgl.ext.ase import M3GNetCalculator

    out = OutputEngine(
        calculator=M3GNetCalculator(matgl.load_model("M3GNet-MP-2021.2.8-PES"))
    )
    return out
