"""The Files accordion tab: export and import recipes, and save a tab's last run."""

from __future__ import annotations

import html
import pathlib
import traceback
from enum import StrEnum
from typing import TYPE_CHECKING, Any

import ipywidgets as widgets
from pyiron_workflow.execution import Run

from pyironflow import storage
from pyironflow.reactflow import AccordionTab
from pyironflow.wf_extensions import TransientInputs

if TYPE_CHECKING:
    from pyironflow.pyironflow import PyironFlow


class FileAction(StrEnum):
    EXPORT = "export"
    IMPORT = "import"
    SAVE = "save"


_ACTION_LABELS = {
    FileAction.EXPORT: "Export",
    FileAction.IMPORT: "Import",
    FileAction.SAVE: "Save run",
}

_INPUTS_HELP = (
    "Which unconnected child inputs become workflow inputs in the exported recipe. "
    "used: ports without a default, plus ports with a typed value. "
    "unconnected: every unconnected port. "
    "undefaulted: only ports without a default."
)

_NO_RUN = (
    "There is no run to save in this tab yet; press Run, or pull on a node, first."
)


def _show(widget: widgets.DOMWidget, visible: bool) -> None:
    widget.layout.display = None if visible else "none"


class FilesPanel:
    """Path entry and controls for the selected workflow tab's files.

    The panel always acts on `PyironFlow.active_widget`. Saving a run is offered
    only while that widget holds one. `refresh` keeps that current as tabs change;
    `PyironFlowWidget` also calls it directly right after every run or pull, so a
    later run updates an already-open Save run view instead of going stale.
    """

    def __init__(self, flow: PyironFlow):
        self.flow = flow
        self.action = widgets.ToggleButtons(
            options=self._options([FileAction.EXPORT, FileAction.IMPORT])
        )
        self.path = widgets.Text(placeholder="path/to/file", description="Path")
        self.export_inputs = widgets.Dropdown(
            options=[(mode.value, mode) for mode in TransientInputs],
            value=TransientInputs.USED,
            description="Inputs",
            tooltip=_INPUTS_HELP,
        )
        self.run_format = widgets.ToggleButtons(
            options=[
                ("pickle", storage.RunFormat.PICKLE),
                ("h5", storage.RunFormat.H5),
            ]
        )
        self.run_info = widgets.HTML()
        self.create_dirs = widgets.Checkbox(
            value=False, description="Create missing directories", indent=False
        )
        self.overwrite = widgets.Checkbox(
            value=False, description="Overwrite existing", indent=False
        )
        self.go = widgets.Button(description="Go", button_style="info")
        self.status = widgets.HTML()
        self.gui = widgets.VBox(
            [
                self.action,
                self.path,
                self.export_inputs,
                self.run_format,
                self.run_info,
                self.create_dirs,
                self.overwrite,
                self.go,
                self.status,
            ]
        )
        self.action.observe(self._sync_controls, names="value")
        self.go.on_click(self._on_go)
        self._sync_controls()

    @staticmethod
    def _options(actions: list[FileAction]) -> list[tuple[str, FileAction]]:
        return [(_ACTION_LABELS[action], action) for action in actions]

    def _available(self) -> list[FileAction]:
        return [value for _, value in self.action.options]

    def refresh(self, change: Any = None) -> None:
        """Offer Save run only while the selected tab holds a run."""
        available = [FileAction.EXPORT, FileAction.IMPORT]
        if self.flow.active_widget.last_run is not None:
            available.append(FileAction.SAVE)
        if available != self._available():
            current = self.action.value
            # Replacing options resets the value, so put the selection back
            self.action.options = self._options(available)
            self.action.value = current if current in available else FileAction.EXPORT
        self._sync_controls()

    def open(self, action: FileAction | str) -> None:
        """Show the Files tab with *action* selected, if it is available."""
        self.refresh()
        requested = FileAction(action)
        if requested in self._available():
            self.action.value = requested
            self.status.value = ""
        else:
            self._report(_NO_RUN, ok=False)
        self.flow.accordion.selected_index = AccordionTab.FILES.index

    def _sync_controls(self, change: Any = None) -> None:
        action = self.action.value
        writes = action in (FileAction.EXPORT, FileAction.SAVE)
        self.path.placeholder = "path/to/file"
        _show(self.export_inputs, action == FileAction.EXPORT)
        _show(self.run_format, action == FileAction.SAVE)
        _show(self.run_info, action == FileAction.SAVE)
        _show(self.create_dirs, writes)
        _show(self.overwrite, writes)
        # `active_widget` is only read once we know we need it, so construction
        # (action defaults to Export) never touches `flow.active_widget`.
        if (
            action == FileAction.SAVE
            and (run := self.flow.active_widget.last_run) is not None
        ):
            self.run_info.value = self._describe_last_run(run)
            self.path.placeholder = run.label
        elif action == FileAction.EXPORT and hasattr(self.flow, "active_widget"):
            self.path.placeholder = self.flow.active_widget.wf.label

    def _describe_last_run(self, run: Run[Any]) -> str:
        finished = (
            "not finished"
            if run.finished_at is None
            else f"finished {run.finished_at:%Y-%m-%d %H:%M:%S}"
        )
        return html.escape(f"Last run: {run.label} ({run.status.value}, {finished})")

    def _on_go(self, _button: Any = None) -> None:
        self.status.value = ""
        try:
            message = self._dispatch(FileAction(self.action.value))
        except storage.StorageError as err:
            self._report(str(err), ok=False)
            if err.__cause__ is not None:
                self._log(err)
        except Exception as err:
            self._report(f"Error: {err}", ok=False)
            self._log(err)
        else:
            self._report(message, ok=True)

    def _dispatch(self, action: FileAction) -> str:
        match action:
            case FileAction.EXPORT:
                return self._export()
            case FileAction.IMPORT:
                return self._import()
            case FileAction.SAVE:
                return self._save()

    def _export(self) -> str:
        widget = self.flow.active_widget
        widget.wf = widget.get_workflow()
        path = self._output_path(storage.RECIPE_EXTENSION, widget.wf.label)
        storage.check_writable(path, self.create_dirs.value, self.overwrite.value)
        recipe = storage.export_recipe(
            widget.wf, widget.port_cache, TransientInputs(self.export_inputs.value)
        )
        storage.write_recipe(recipe, path, self.create_dirs.value, self.overwrite.value)
        return f"Exported {widget.wf.label!r} to {path}"

    def _import(self) -> str:
        path = storage.resolve_path(self.path.value, storage.RECIPE_EXTENSION)
        recipe = storage.read_recipe(path)
        wf = storage.recipe_to_gui_workflow(recipe, path.stem)
        wf.label = self.flow.unique_label(wf.label)
        self.flow.add_workflow(wf)
        return f"Imported {path} as {wf.label!r}"

    def _save(self) -> str:
        run = self.flow.active_widget.last_run
        if run is None:
            raise storage.StorageError(_NO_RUN)
        fmt = storage.RunFormat(self.run_format.value)
        path = self._output_path(fmt.extension, run.label)
        storage.save_run(run, path, fmt, self.create_dirs.value, self.overwrite.value)
        return f"Saved run {run.label!r} ({run.status.value}) to {path}"

    def _output_path(self, extension: str, default: str) -> pathlib.Path:
        """Resolve an output path, defaulting a blank field to the item's label."""
        return storage.resolve_path(self.path.value, extension, default=default)

    def _report(self, message: str, ok: bool) -> None:
        color = "green" if ok else "red"
        self.status.value = f"<span style='color:{color}'>{html.escape(message)}</span>"

    def _log(self, err: BaseException) -> None:
        self.flow.out_log.append_stderr("".join(traceback.format_exception(err)))
