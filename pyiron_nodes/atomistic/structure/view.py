from pyiron_workflow import as_function_node

from ase import Atoms


@as_function_node("plot")
def Plot3d(structure: Atoms, particle_size: int = 1):
    return structure.plot3d(particle_size=particle_size)
