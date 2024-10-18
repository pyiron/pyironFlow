from __future__ import annotations

from dataclasses import asdict
from typing import Optional

from ase import Atoms
from phonopy.api_phonopy import Phonopy
from pyiron_workflow import (
    as_dataclass_node,
    as_function_node,
    as_macro_node,
    for_node,
    standard_nodes as standard,
)
from structuretoolkit.common import atoms_to_phonopy, phonopy_to_atoms

from pyiron_nodes.atomistic.calculator.ase import Static
from pyiron_nodes.atomistic.engine.generic import OutputEngine


@as_function_node("phonopy")
def PhonopyObject(structure):
    return Phonopy(unitcell=atoms_to_phonopy(structure))


@as_dataclass_node
class PhonopyParameters:
    distance: float = 0.01
    is_plusminus: str | bool = "auto"
    is_diagonal: bool = True
    is_trigonal: bool = False
    number_of_snapshots: Optional[int] = None
    random_seed: Optional[int] = None
    temperature: Optional[float] = None
    cutoff_frequency: Optional[float] = None
    max_distance: Optional[float] = None


@as_function_node
def GenerateSupercells(
    phonopy: Phonopy, parameters: PhonopyParameters.dataclass | None
) -> list[Atoms]:

    parameters = PhonopyParameters.dataclass() if parameters is None else parameters
    phonopy.generate_displacements(**asdict(parameters))

    supercells = [phonopy_to_atoms(s) for s in phonopy.supercells_with_displacements]
    return supercells


@as_macro_node("phonopy", "calculations")
def CreatePhonopy(
    self,
    structure: Atoms,
    engine: OutputEngine | None = None,
    parameters: PhonopyParameters.dataclass | None = None,
):
    import warnings

    warnings.simplefilter(action="ignore", category=(DeprecationWarning, UserWarning))

    self.phonopy = PhonopyObject(structure)
    self.cells = GenerateSupercells(self.phonopy, parameters=parameters)
    self.calculations = for_node(
        body_node_class=Static,
        iter_on=("structure",),
        engine=engine,
        structure=self.cells,
    )
    self.forces = ExtractFinalForces(self.calculations)
    self.phonopy_with_forces = standard.SetAttr(self.phonopy, "forces", self.forces)

    return self.phonopy_with_forces, self.calculations


@as_function_node("forces")
def ExtractFinalForces(df):
    return [getattr(e, "force")[-1] for e in df["out"].tolist()]


@as_function_node
def GetDynamicalMatrix(phonopy, q=None):
    import numpy as np

    q = [0, 0, 0] if q is None else q
    if phonopy.dynamical_matrix is None:
        phonopy.produce_force_constants()
        phonopy.dynamical_matrix.run(q=q)
    dynamical_matrix = np.real_if_close(phonopy.dynamical_matrix.dynamical_matrix)
    # print (dynamical_matrix)
    return dynamical_matrix


@as_function_node
def GetEigenvalues(matrix):
    import numpy as np

    ew = np.linalg.eigvalsh(matrix)
    return ew


@as_macro_node
def CheckConsistency(self, phonopy: Phonopy, tolerance: float = 1e-10):
    self.dyn_matrix = GetDynamicalMatrix(phonopy).run()
    self.ew = GetEigenvalues(self.dyn_matrix)
    self.has_imaginary_modes = HasImaginaryModes(self.ew, tolerance)
    return self.has_imaginary_modes


@as_function_node
def GetTotalDos(phonopy, mesh=None):
    from pandas import DataFrame

    mesh = 3 * [10] if mesh is None else mesh

    phonopy.produce_force_constants()
    phonopy.run_mesh(mesh=mesh)
    phonopy.run_total_dos()
    total_dos = DataFrame(phonopy.get_total_dos_dict())
    return total_dos


@as_function_node
def HasImaginaryModes(eigenvalues, tolerance: float = 1e-10) -> bool:
    ew_lt_zero = eigenvalues[eigenvalues < -tolerance]
    if len(ew_lt_zero) > 0:
        print(f"WARNING: {len(ew_lt_zero)} imaginary modes exist")
        has_imaginary_modes = True
    else:
        has_imaginary_modes = False
    return has_imaginary_modes
