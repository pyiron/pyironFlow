from __future__ import annotations

from pyiron_workflow import as_function_node, as_macro_node
from typing import Optional


# from pyiron_workflow.workflow import Workflow


@as_function_node("structure")
def Bulk(
    name: str,
    crystalstructure: Optional[str] = None,
    a: Optional[float | int] = None,
    c: Optional[float | int] = None,
    c_over_a: Optional[float] | int = None,
    u: Optional[float | int] = None,
    orthorhombic: bool = False,
    cubic: bool = False,
):
    from pyiron_atomistics import _StructureFactory

    return _StructureFactory().bulk(
        name,
        crystalstructure,
        a,
        c,
        c_over_a,
        u,
        orthorhombic,
        cubic,
    )


@as_macro_node("structure")
def CubicBulkCell(
    wf, element: str, cell_size: int = 1, vacancy_index: int | None = None
):
    from pyiron_nodes.atomistic.structure.transform import (
        CreateVacancy,
        Repeat,
    )

    wf.bulk = Bulk(name=element, cubic=True)
    wf.cell = Repeat(structure=wf.bulk, repeat_scalar=cell_size)

    wf.structure = CreateVacancy(structure=wf.cell, index=vacancy_index)
    return wf.structure
