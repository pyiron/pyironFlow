from __future__ import annotations

from pyiron_workflow import as_macro_node


@as_macro_node("chemical_potential")
def GetChemicalPotential(
    wf,
    element: str,
    engine=None,
):

    import pyiron_nodes.atomistic as atomistic

    wf.bulk = atomistic.structure.build.Bulk(name=element)
    wf.minimize = atomistic.calculator.ase.Minimize(
        structure=wf.bulk, engine=engine
    )  # pressure = 0
    wf.n_atoms = atomistic.structure.calc.NumberOfAtoms(structure=wf.bulk)
    wf.energy = atomistic.calculator.output.GetEnergyLast(calculator=wf.minimize)

    return wf.energy / wf.n_atoms
