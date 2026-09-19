"""File IO behind the Files panel: saving runs, and exporting and importing recipes.

Nothing here touches widgets. Failures a user can fix raise `StorageError`, with a
message fit to show as-is.
"""

from __future__ import annotations

import keyword
import os
import pathlib
import pickle
import re
import traceback
from enum import StrEnum
from typing import Any

import bagofholding as boh
import flowrep as fr
import pydantic
from pyiron_workflow import Workflow, constructors
from pyiron_workflow.execution import Run

from pyironflow import datamodel
from pyironflow.wf_extensions import TransientInputs, transient_io

RECIPE_EXTENSION = ".json"


class StorageError(Exception):
    """A failure the user can fix, with a message fit to show as-is."""


class RunFormat(StrEnum):
    PICKLE = "pickle"
    H5 = "h5"

    @property
    def extension(self) -> str:
        return ".pckl" if self is RunFormat.PICKLE else f".{self}"


DEFAULT_LABEL = "imported"

_RECIPE_ADAPTER: pydantic.TypeAdapter[Any] = pydantic.TypeAdapter(
    fr.schemas.RecipeDiscrimination
)
_LABEL_ADAPTER: pydantic.TypeAdapter[str] = pydantic.TypeAdapter(fr.schemas.Label)


class RecipeInvalidError(StorageError):
    """The graph cannot currently be expressed as a flowrep recipe."""


def to_label(stem: str) -> str:
    """A flowrep-valid label made from a file name's *stem*."""
    candidate = re.sub(r"\W", "_", stem)
    if not candidate or not (candidate[0].isalpha() or candidate[0] == "_"):
        candidate = f"wf_{candidate}"
    if keyword.iskeyword(candidate) or candidate in fr.schemas.RESERVED_NAMES:
        candidate = f"{candidate}_"
    try:
        return _LABEL_ADAPTER.validate_python(candidate)
    except ValueError:
        return DEFAULT_LABEL


def export_recipe(
    wf: Workflow,
    cache: datamodel.PortCache,
    inputs: TransientInputs = TransientInputs.USED,
) -> fr.schemas.WorkflowRecipe:
    """The recipe of *wf*, with terminal IO built only for as long as that takes.

    Any failure, from building the ports or from recipe validation, becomes a
    `RecipeInvalidError`. *wf* is IO-free afterwards either way.
    """
    try:
        with transient_io(wf, cache, inputs):
            return wf.recipe
    except Exception as err:
        raise RecipeInvalidError(
            f"The graph is not currently a valid flowrep recipe, so it cannot be "
            f"exported: {err}"
        ) from err


def write_recipe(
    recipe: fr.schemas.NodeRecipe,
    path: pathlib.Path,
    create_dirs: bool,
    overwrite: bool,
) -> None:
    """Write *recipe* as JSON, creating directories only once there is text to write."""
    check_writable(path, create_dirs, overwrite)
    text = recipe.model_dump_json(indent=2)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def read_recipe(path: pathlib.Path) -> fr.schemas.NodeRecipe:
    """The recipe stored at *path*, of whichever recipe type it declares."""
    if not path.is_file():
        raise StorageError(f"No such file: {path}")
    try:
        return _RECIPE_ADAPTER.validate_json(path.read_bytes())
    except pydantic.ValidationError as err:
        raise StorageError(f"{path} is not a flowrep recipe: {err}") from err


def recipe_to_gui_workflow(recipe: fr.schemas.NodeRecipe, stem: str) -> Workflow:
    """A workflow `PyironFlow` accepts, labelled from *stem*, that realizes *recipe*.

    A workflow recipe without a python reference is safely mutable, so it becomes
    the workflow itself with its IO stripped, since `PyironFlow` owns terminal IO.
    Anything else, including a workflow with a reference, which must stay a locked
    `Macro`, becomes the sole child of a fresh workflow.
    """
    label = to_label(stem)
    reference = getattr(recipe, "reference", None)
    try:
        if isinstance(recipe, fr.schemas.WorkflowRecipe) and reference is None:
            wf = Workflow.from_recipe(recipe, label)
            wf.remove_input(*list(wf.inputs))
            wf.remove_output(*list(wf.outputs))
        else:
            child_label = (
                label
                if reference is None
                else to_label(reference.info.qualname.rpartition(".")[2])
            )
            wf = Workflow(label)
            wf.add_node(constructors.recipe2node(recipe, child_label))
    except Exception as err:
        name = getattr(recipe, "fully_qualified_name", None)
        origin = f" ({name})" if name else ""
        raise StorageError(
            f"Could not build the {recipe.type} recipe{origin}: {err}"
        ) from err
    wf.undo_stack.clear()
    wf.redo_stack.clear()
    return wf


def resolve_path(text: str, extension: str, default: str | None = None) -> pathlib.Path:
    """The absolute path *text* names, relative to the kernel's working directory.

    *extension* is appended unless the name already ends with it, so ``run.v2``
    becomes ``run.v2.h5`` rather than keeping a suffix that does not match.
    """
    stripped = text.strip()
    if not stripped:
        if default is not None:
            stripped = default.strip()
            if not stripped:
                raise StorageError("Enter a file path.")
        else:
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
        # A failed `H5Bag.save` leaves its file open, held by the traceback's
        # frames; Windows refuses to delete an open file, so release them first.
        traceback.clear_frames(err.__traceback__)
        temporary.unlink(missing_ok=True)
        raise StorageError(f"Could not save the run to {path}: {err}") from err
