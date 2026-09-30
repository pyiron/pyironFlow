"""Standard nodes, always shown in the Node Library.

The typed inputs each pass their value straight through. Place one to type a value
into the GUI once and feed it to as many consumers as need it; the type hint picks the
entry widget.

The loaders read a run saved from the Files panel: `browse_paths` lists the output
paths inside it, and `load_result` gives back the value at one of them.
"""

from typing import Any, Literal

import flowrep as fr

from pyironflow import storage

Format = Literal[
    storage.LoadFormat.INFER, storage.LoadFormat.PICKLE, storage.LoadFormat.H5
]


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


@fr.atomic("value")
def load_result(
    file: str, lexical_path: str, format: Format = storage.LoadFormat.INFER
) -> Any:
    """The value of one output in a saved run.

    *lexical_path* is as `browse_paths` lists it; node steps may be divided by ``/``
    as well as ``.``. Loading a pickle runs whatever code it names, so only load files
    you trust.
    """
    fmt = storage.LoadFormat(format)
    return storage.load_run_output(
        storage.resolve_run_path(file, fmt), lexical_path, fmt
    )


@fr.atomic("paths")
def browse_paths(file: str, format: Format = storage.LoadFormat.INFER) -> list[str]:
    """The path of every output in a saved run, for use with `load_result`."""
    fmt = storage.LoadFormat(format)
    return storage.browse_run_outputs(storage.resolve_run_path(file, fmt), fmt)
