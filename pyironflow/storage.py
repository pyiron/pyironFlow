"""File IO behind the Files panel: saving and loading runs, and exporting and importing
recipes.

Nothing here touches widgets. Failures a user can fix raise `StorageError`, with a
message fit to show as-is.
"""

from __future__ import annotations

import dataclasses
import keyword
import os
import pathlib
import pickle
import re
import traceback
from collections.abc import Iterable, Iterator
from enum import StrEnum
from typing import Any

import bagofholding as boh
import flowrep as fr
import pydantic
from flowrep import base_models
from pyiron_workflow import Workflow, constructors, lexical
from pyiron_workflow.execution import Run, Steps

from pyironflow import datamodel
from pyironflow.wf_extensions import (
    TransientInputs,
    has_only_unconnected_child_io,
    transient_io,
)

RECIPE_EXTENSION = ".json"


class StorageError(Exception):
    """A failure the user can fix, with a message fit to show as-is."""


class RunFormat(StrEnum):
    PICKLE = "pickle"
    H5 = "h5"

    @property
    def extension(self) -> str:
        return ".pckl" if self is RunFormat.PICKLE else f".{self}"


class LoadFormat(StrEnum):
    """How to read a saved run: as its extension suggests, or as a `RunFormat`."""

    INFER = "infer"
    PICKLE = RunFormat.PICKLE.value
    H5 = RunFormat.H5.value


DEFAULT_LABEL = "imported"

RESULT_STORAGE_ROOT = "object/state/result"
"""Where an `H5Bag` of a `Run` keeps the run's `result`."""

_OUTPUTS = base_models.IOTypes.OUTPUTS

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

    A workflow recipe without a python reference, whose IO is only what
    `pyiron_workflow` builds automatically, becomes the workflow itself with that IO
    stripped, since `PyironFlow` owns terminal IO. Anything else becomes the sole
    child of a fresh workflow: a workflow whose IO someone designed keeps it, to be
    seen and ungrouped by choice, and one with a reference must stay a locked `Macro`.
    """
    wf, _ = _build_gui_workflow(recipe, to_label(stem))
    return wf


def _build_gui_workflow(
    recipe: fr.schemas.NodeRecipe, label: str, child_label: str | None = None
) -> tuple[Workflow, bool]:
    """`recipe_to_gui_workflow`, also saying whether *recipe* became a child.

    A child is labelled *child_label* when given; otherwise after the reference's
    name, or *label* when there is none.
    """
    reference = getattr(recipe, "reference", None)
    if child_label is None:
        child_label = (
            label
            if reference is None
            else to_label(reference.info.qualname.rpartition(".")[2])
        )
    wrapped = True
    try:
        if isinstance(recipe, fr.schemas.WorkflowRecipe) and reference is None:
            wf = Workflow.from_recipe(recipe, label)
            if has_only_unconnected_child_io(wf):
                wf.remove_input(*list(wf.inputs))
                wf.remove_output(*list(wf.outputs))
                wrapped = False
            else:
                wf = Workflow.from_recipe(recipe, child_label)
                child = wf
                wf = Workflow(label)
                wf.add_node(child)
        else:
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
    return wf, wrapped


def load_run(path: pathlib.Path, fmt: LoadFormat) -> Run[Any]:
    """The `Run` saved at *path*, read as *fmt* says or as its extension suggests.

    Loading a pickle runs whatever code it names, so only load files you trust.
    """
    run_format = _checked_format(path, fmt)
    try:
        if run_format is RunFormat.PICKLE:
            with path.open("rb") as f:
                loaded = pickle.load(f)
        else:
            loaded = boh.H5Bag(str(path)).load()
    except Exception as err:
        raise StorageError(f"Could not load a run from {path}: {err}") from err
    if not isinstance(loaded, Run):
        raise StorageError(
            f"{path} holds a {type(loaded).__name__}, not a run, so it cannot be loaded."
        )
    return loaded


def _run_format(path: pathlib.Path, fmt: LoadFormat) -> RunFormat:
    if fmt is not LoadFormat.INFER:
        return RunFormat(fmt)
    for run_format in RunFormat:
        if path.suffix == run_format.extension:
            return run_format
    known = ", ".join(repr(f.extension) for f in RunFormat)
    raise StorageError(
        f"Cannot tell the format of {path} from its extension (expected one of "
        f"{known}); choose pickle or h5 instead."
    )


def _checked_format(path: pathlib.Path, fmt: LoadFormat) -> RunFormat:
    """The format to read *path* as, once it is known to exist."""
    if not path.is_file():
        raise StorageError(f"No such file: {path}")
    return _run_format(path, fmt)


def browse_run_outputs(path: pathlib.Path, fmt: LoadFormat) -> list[str]:
    """The lexical path of every output port in the run saved at *path*, sorted.

    Paths start below the run's own node, e.g. ``outputs.y`` or ``child.outputs.y``.
    An `H5Bag` is browsed without loading any data; a pickle is loaded whole.
    """
    paths: Iterable[str]
    if _checked_format(path, fmt) is RunFormat.H5:
        paths = _result_browser(path).list_paths()
    else:
        paths = _output_paths(load_run(path, fmt).result, "")
    return sorted(p for p in paths if lexical.LexicalPath(p).parent.label == _OUTPUTS)


def _result_browser(path: pathlib.Path) -> fr.tools.LexicalBagBrowser:
    """A browser of the result of the run in the `H5Bag` at *path*."""
    try:
        bag = boh.H5Bag(str(path))
        held = bag["object"].qualname
    except Exception as err:
        raise StorageError(f"Could not read {path} as an h5 file: {err}") from err
    if held != Run.__qualname__:
        raise StorageError(
            f"{path} holds a {held}, not a run, so its results cannot be read."
        )
    return fr.tools.LexicalBagBrowser(bag, storage_root=RESULT_STORAGE_ROOT)


def _output_paths(data: fr.schemas.NodeData, prefix: str) -> Iterator[str]:
    """The lexical path of every output port in *data*, whose own path is *prefix*."""
    for port in data.output_ports:
        yield str(lexical.LexicalPath(prefix, _OUTPUTS, port))
    if isinstance(data, fr.schemas.CompositeData):
        for label, child in data.nodes.items():
            yield from _output_paths(child, str(lexical.LexicalPath(prefix, label)))


def run_to_gui_workflow(run: Run[Any], stem: str) -> tuple[Workflow, Run[Any]]:
    """A workflow built from *run*'s recipe, as `recipe_to_gui_workflow` would,
    and the run to keep as its last run.

    That is *run* itself when its recipe became the workflow. When it became the
    sole child instead, labelled after *run*, the last run must be the parent's: a
    run of the fresh workflow whose only step is *run*, re-rooted beneath it, the
    same shape `pyiron_workflow` gives a nested run. *run* is left untouched.
    """
    child_label = to_label(run.label)
    wf, wrapped = _build_gui_workflow(run.result.recipe, to_label(stem), child_label)
    if not wrapped:
        return wf, run
    parent = Run(
        lexical_path=lexical.LexicalPath(wf.label),
        result=_parent_data(wf, child_label, run.result),
        status=run.status,
        exception=run.exception,
        started_at=run.started_at,
        finished_at=run.finished_at,
        run_dir=run.run_dir,
        steps=Steps([_reroot(run, lexical.LexicalPath(wf.label))]),
    )
    return wf, parent


def _parent_data(
    wf: Workflow, child_label: str, child: fr.schemas.NodeData
) -> fr.schemas.DagData:
    """What running *wf* in the GUI would have recorded, had its child made *child*.

    A recipe needs every child input without a default fed, so *wf* gets terminal
    IO for all its unconnected child ports, as a GUI run would, carrying the values
    *child* took in and gave out.
    """
    recipe = export_recipe(wf, {}, TransientInputs.UNCONNECTED)
    data = fr.schemas.DagData.from_recipe(recipe)
    data.nodes[child_label] = child
    for target, source in recipe.input_edges.items():
        data.input_ports[source.port].value = child.input_ports[target.port].value
    for output, handle in recipe.output_edges.items():
        data.output_ports[output.port].value = child.output_ports[handle.port].value
    return data


def _reroot(run: Run[Any], root: lexical.LexicalPath) -> Run[Any]:
    """A copy of *run*, and of its steps, with every lexical path under *root*."""
    return dataclasses.replace(
        run,
        lexical_path=lexical.LexicalPath(root, run.lexical_path),
        steps=Steps(_reroot(step, root) for step in run.steps),
    )


def resolve_path(text: str, extension: str, default: str | None = None) -> pathlib.Path:
    """The absolute path *text* names, relative to the kernel's working directory.

    *extension* is appended unless the name already ends with it, so ``run.v2``
    becomes ``run.v2.h5`` rather than keeping a suffix that does not match.
    """
    stripped = text.strip() or (default.strip() if default is not None else "")
    if not stripped:
        raise StorageError("Enter a file path.")
    path = (pathlib.Path.cwd() / pathlib.Path(stripped).expanduser()).resolve()
    if not path.name.endswith(extension):
        path = path.with_name(path.name + extension)
    return path


def resolve_run_path(text: str, fmt: LoadFormat) -> pathlib.Path:
    """The saved run *text* names: the file as typed if there is one, otherwise,
    for a chosen format, with that format's extension added as `resolve_path` would.
    """
    path = resolve_path(text, "")
    if fmt is LoadFormat.INFER or path.is_file():
        return path
    return resolve_path(text, RunFormat(fmt).extension)


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
