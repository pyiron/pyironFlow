"""The Executors panel: make executors from Valid Creators, and browse or delete them.

Creator fields are read the way port fields are, through `pyironflow.entry`, so a
field shows the same widgets, defaults and error messages a port's would.
"""

from __future__ import annotations

import html
from collections.abc import Callable
from typing import Any

import ipywidgets as widgets
import pyiron_workflow as pwf

from pyironflow import entry, executors

CREATE_TITLE = "Create"
BROWSE_TITLE = "Browse"
CREATE = "Create"
DELETE = "Delete"
CONFIRM_DELETE = "Confirm delete"
EXTERNAL_CREATOR = "external (adopted)"


class ParameterField:
    """One creator parameter's entry widget, and the message it shows when wrong."""

    def __init__(self, parameter: executors.CreatorParameter) -> None:
        self.parameter = parameter
        hint = parameter.hint
        kind = entry.entry_kind(hint)
        self.widget: widgets.ValueWidget
        if kind is entry.EntryKind.CHECKBOX:
            self.widget = widgets.Checkbox(
                value=False if parameter.required else bool(parameter.default)
            )
        elif kind is entry.EntryKind.DROPDOWN:
            self.widget = widgets.Dropdown(
                options=entry.options(hint),
                value=(
                    None
                    if parameter.required
                    else entry.render(parameter.default, hint)
                ),
            )
        else:
            self.widget = widgets.Text(
                value=(
                    "" if parameter.required else entry.render(parameter.default, hint)
                )
            )
        self.message = widgets.Label("")
        self.row = widgets.VBox(
            [
                widgets.HBox(
                    [
                        widgets.Label(f"{parameter.name}: {entry.hint_name(hint)}"),
                        self.widget,
                    ]
                ),
                self.message,
            ]
        )

    def value(self) -> Any:
        """The entered value, or `NO_DEFAULT` for a blank field.

        A prefilled default is read like typed text, so one that does not fit its own
        hint is reported rather than passed on.

        Raises:
            entry.EntryError: If the text does not fit the parameter's hint.
        """
        raw = self.widget.value
        if isinstance(raw, bool):
            return raw
        if raw is None or raw == "":
            return executors.NO_DEFAULT
        return entry.parse(raw, self.parameter.hint)

    def observe(self, callback: Callable[[Any], None]) -> None:
        self.widget.observe(callback, names="value")


class ExecutorsPanel:
    """Create and Browse, each a section of its own so both can be open at once.

    The panel knows nothing of nodes. It reports a new executor to *on_created* and a
    confirmed deletion to *on_deleted*; `PyironFlow` decides what follows.
    """

    def __init__(
        self,
        registry: executors.ExecutorRegistry,
        on_created: Callable[[executors.Created], None],
        on_deleted: Callable[[str], None],
    ) -> None:
        self.registry = registry
        self._on_created = on_created
        self._on_deleted = on_deleted
        self.fields: dict[str, ParameterField] = {}
        self._armed = False

        self.creator = widgets.Dropdown(
            options=list(registry.creators), value=None, description="Creator"
        )
        self.creator.observe(self._on_creator, names="value")
        self.name = widgets.Text(description="name")
        self.name.observe(self._update_create, names="value")
        self.fields_box = widgets.VBox([])
        self.create_button = widgets.Button(description=CREATE, disabled=True)
        self.create_button.on_click(self._create)
        self.error = widgets.Output()
        self.create_section = widgets.Accordion(
            children=[
                widgets.VBox(
                    [self.creator, self.fields_box, self.create_button, self.error]
                )
            ],
            titles=(CREATE_TITLE,),
        )

        self.browse = widgets.Select(options=[], value=None, rows=6)
        self.browse.observe(self._on_browse, names="value")
        self.details = widgets.HTML("")
        self.delete_button = widgets.Button(description=DELETE, disabled=True)
        self.delete_button.on_click(self._delete)
        self.browse_section = widgets.Accordion(
            children=[widgets.VBox([self.browse, self.details, self.delete_button])],
            titles=(BROWSE_TITLE,),
        )
        self.gui = widgets.VBox([self.create_section, self.browse_section])

    def open_create(self) -> None:
        self.create_section.selected_index = 0

    def refresh(self) -> None:
        """Re-read the registry into Browse, keeping the selection if it survives."""
        selected = self.browse.value
        names = list(self.registry.created)
        self.browse.options = names
        self.browse.value = selected if selected in names else None
        self._on_browse()
        self._update_create()

    # Create

    def _on_creator(self, _change: Any = None) -> None:
        self.error.outputs = ()
        creator = self.creator.value
        if creator is None:
            self.fields = {}
            self.fields_box.children = ()
        else:
            self.fields = {
                parameter.name: ParameterField(parameter)
                for parameter in executors.creator_parameters(
                    self.registry.creators[creator]
                )
            }
            for field in self.fields.values():
                field.observe(self._update_create)
            self.name.value = self.registry.default_name(creator)
            self.fields_box.children = (
                self.name,
                *(field.row for field in self.fields.values()),
            )
        self._update_create()

    def _kwargs(self) -> dict[str, Any] | None:
        """The entered values, or None while any field is missing or invalid.

        Each field's message is updated on the way.
        """
        kwargs: dict[str, Any] = {}
        complete = True
        for name, field in self.fields.items():
            try:
                value = field.value()
            except entry.EntryError as err:
                field.message.value = str(err)
                complete = False
                continue
            field.message.value = ""
            if value is executors.NO_DEFAULT:
                complete = complete and not field.parameter.required
            else:
                kwargs[name] = value
        return kwargs if complete else None

    def _update_create(self, _change: Any = None) -> None:
        name = self.name.value.strip()
        kwargs = self._kwargs()
        self.create_button.disabled = (
            self.creator.value is None
            or not name
            or name in self.registry.created
            or kwargs is None
        )

    def _create(self, _button: widgets.Button) -> None:
        kwargs = self._kwargs()
        if self.creator.value is None or kwargs is None:
            return
        self.error.outputs = ()
        try:
            created = self.registry.create(self.name.value, self.creator.value, kwargs)
        except Exception as err:
            self.error.append_stdout(f"{type(err).__name__}: {err}\n")
            return
        self.refresh()
        self._on_creator()  # the same creator, under a fresh default name
        self._on_created(created)

    # Browse

    def _on_browse(self, _change: Any = None) -> None:
        self._disarm()
        name = self.browse.value
        self.delete_button.disabled = name is None
        self.details.value = (
            "" if name is None else _details(self.registry.created[name])
        )

    def _disarm(self) -> None:
        self._armed = False
        self.delete_button.description = DELETE
        self.delete_button.button_style = ""

    def _delete(self, _button: widgets.Button) -> None:
        name = self.browse.value
        if name is None:
            return
        if not self._armed:
            self._armed = True
            self.delete_button.description = CONFIRM_DELETE
            self.delete_button.button_style = "danger"
            return
        self._disarm()
        self._on_deleted(name)


def _details(created: executors.Created) -> str:
    """*created* as read-only HTML: its name and type, creator, and arguments."""
    if created.creator is None:
        creator, hints = EXTERNAL_CREATOR, {}
    else:
        creator = f"{created.creator.__module__}.{created.creator.__qualname__}"
        hints = {
            parameter.name: parameter.hint
            for parameter in executors.creator_parameters(created.creator)
        }
    type_suffix = (
        f" -- {created.value.constructor.__name__}"
        if isinstance(created.value, pwf.ExecutorInstructions)
        else ""
    )
    lines = [
        f"<b>{html.escape(created.name)}</b>: "
        f"{html.escape(type(created.value).__qualname__)}{html.escape(type_suffix)}",
        f"creator: {html.escape(creator)}",
        *(
            html.escape(f"{key} = {entry.render(value, hints.get(key))}")
            for key, value in created.kwargs.items()
        ),
    ]
    return "<br>".join(lines)
