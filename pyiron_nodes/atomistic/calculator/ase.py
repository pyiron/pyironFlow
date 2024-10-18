from ase import Atoms
from pyiron_workflow import as_function_node


@as_function_node
def Static(
    structure: Atoms,
    engine=None,
):
    import numpy as np
    from pyiron_nodes.atomistic.calculator.data import OutputCalcStatic

    if engine is None:
        from ase.calculators.emt import EMT
        from pyiron_nodes.atomistic.engine.generic import OutputEngine

        engine = OutputEngine(calculator=EMT())

    structure.calc = engine.calculator

    out = OutputCalcStatic()
    out.energy = np.array(
        [float(structure.get_potential_energy())]
    )  # TODO: originally of type np.float32 -> why??
    out.force = np.array([structure.get_forces()])

    return out


@as_function_node("out")
def Minimize(structure=None, engine=None, fmax=0.005, log_file="tmp.log"):
    from ase.optimize import BFGS
    from ase.io.trajectory import Trajectory
    from pyiron_nodes.atomistic.calculator.data import OutputCalcMinimize

    # import numpy as np

    if engine is None:
        from ase.calculators.emt import EMT
        from pyiron_nodes.atomistic.engine.generic import OutputEngine

        engine = OutputEngine(calculator=EMT())

    out = OutputCalcMinimize()

    initial_structure = structure.copy()
    initial_structure.calc = engine.calculator
    out.initial.energy = float(initial_structure.get_potential_energy())
    out.initial.forces = initial_structure.get_forces()

    if log_file is None:  # write to standard io
        log_file = "-"

    dyn = BFGS(initial_structure, logfile=log_file, trajectory="minimize.traj")
    out_dyn = dyn.run(fmax=fmax)

    traj = Trajectory("minimize.traj")
    atoms_relaxed = traj[-1]
    atoms_relaxed.calc = engine.calculator

    out.final.forces = atoms_relaxed.get_forces()
    out.final.energy = float(atoms_relaxed.get_potential_energy())
    atoms_relaxed.calc = None  # ase calculator is not pickable!!
    out.final.structure = atoms_relaxed

    out.is_converged = dyn.converged()
    out.iter_steps = dyn.nsteps

    return out
