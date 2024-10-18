from pyiron_workflow import as_function_node, as_macro_node
from typing import Optional

@as_macro_node()
def macro_new(wf, cell_name: str = 'Pb', cell_crystalstructure: Optional[str] = None, cell_a: Optional[float|int] = None, cell_c: Optional[float|int] = None, cell_c_over_a: Optional[float|int] = None, cell_u: Optional[float|int] = None, cell_orthorhombic: bool = False, cell_cubic: bool = True, view_particle_size: int = 1):
    from pyiron_nodes.atomistic.structure.build import Bulk
    from pyiron_nodes.atomistic.structure.view import Plot3d
    wf.cell = Bulk(name = cell_name, crystalstructure = cell_crystalstructure, a = cell_a, c = cell_c, c_over_a = cell_c_over_a, u = cell_u, orthorhombic = cell_orthorhombic, cubic = cell_cubic)
    wf.view = Plot3d(particle_size = view_particle_size, structure = wf.cell)
    return wf.view