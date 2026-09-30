"""Typed input nodes, always shown in the Node Library.

Each passes its value straight through. Place one to type a value into the GUI once
and feed it to as many consumers as need it; the type hint picks the entry widget.
"""

import flowrep as fr


@fr.atomic
def input_int(x: int) -> int:
    return x


@fr.atomic
def input_float(x: float) -> float:
    return x


@fr.atomic
def input_str(x: str) -> str:
    return x


@fr.atomic
def input_bool(x: bool) -> bool:
    return x
