"""File IO behind the Files panel: saving runs, and exporting and importing recipes.

Nothing here touches widgets. Failures a user can fix raise `StorageError`, with a
message fit to show as-is.
"""

from __future__ import annotations

import os
import pathlib
import pickle
from enum import StrEnum
from typing import Any

import bagofholding as boh
from pyiron_workflow.execution import Run

RECIPE_EXTENSION = ".json"


class StorageError(Exception):
    """A failure the user can fix, with a message fit to show as-is."""


class RunFormat(StrEnum):
    PICKLE = "pickle"
    H5 = "h5"

    @property
    def extension(self) -> str:
        return ".pckl" if self is RunFormat.PICKLE else f".{self}"


def resolve_path(text: str, extension: str) -> pathlib.Path:
    """The absolute path *text* names, relative to the kernel's working directory.

    *extension* is appended unless the name already ends with it, so ``run.v2``
    becomes ``run.v2.h5`` rather than keeping a suffix that does not match.
    """
    stripped = text.strip()
    if not stripped:
        raise StorageError("Enter a file path.")
    path = (pathlib.Path.cwd() / pathlib.Path(stripped).expanduser()).resolve()
    if not path.name.endswith(extension):
        path = path.with_name(path.name + extension)
    return path


def check_writable(path: pathlib.Path, create_dirs: bool, overwrite: bool) -> None:
    """Raise `StorageError` unless *path* could be written. Creates nothing."""
    if path.is_dir():
        raise StorageError(f"{path} is a directory; add a file name.")
    if path.exists() and not overwrite:
        raise StorageError(
            f"{path} already exists; tick 'Overwrite existing' to replace it."
        )
    for ancestor in path.parents:
        if ancestor.exists():
            if not ancestor.is_dir():
                raise StorageError(
                    f"{ancestor} is a file, so {path} cannot be created under it."
                )
            break
    if not path.parent.is_dir() and not create_dirs:
        raise StorageError(
            f"The directory {path.parent} does not exist; tick 'Create missing "
            f"directories' to make it."
        )


def save_run(
    run: Run[Any],
    path: pathlib.Path,
    fmt: RunFormat,
    create_dirs: bool,
    overwrite: bool,
) -> None:
    """Write the whole *run* to *path* as a pickle or an `H5Bag`.

    The run is written to a sibling temporary file and moved into place, so a
    serialization failure leaves no truncated file behind. Directories created
    for it are left in place if serialization fails.
    """
    check_writable(path, create_dirs, overwrite)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.partial{fmt.extension}")
    temporary.unlink(missing_ok=True)
    try:
        if fmt is RunFormat.PICKLE:
            with temporary.open("wb") as f:
                pickle.dump(run, f)
        else:
            boh.H5Bag.save(run, temporary)
        os.replace(temporary, path)
    except Exception as err:
        temporary.unlink(missing_ok=True)
        raise StorageError(f"Could not save the run to {path}: {err}") from err
