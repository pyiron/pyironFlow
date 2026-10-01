"""The Node Info panel: what the GUI can tell about a single node."""

from __future__ import annotations

import datetime
from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING, Any

import ipywidgets as widgets
from pyiron_workflow.execution import RunStatus

from pyironflow import reactflow

if TYPE_CHECKING:
    from pyironflow.reactflow import PyironFlowWidget

LAST_INPUT_TITLE = "Last Input"
LAST_OUTPUT_TITLE = "Last Output"
SOURCE_TITLE = "Source"
QUERIED_PREFIX = "Queried @ "
EXECUTOR_LABEL = "Executor:"
NO_EXECUTOR = "None"
CREATE_NEW = "[Create new]"

STATUS_SYMBOLS = {
    RunStatus.RUNNING: "🟨",
    RunStatus.FINISHED: "🟩",
    RunStatus.FAILED: "🟥",
}
"""The block drawn before a node's label; mirrors `js/nodeStatus.js`."""
NOT_RUN = "⬜"


def _queried() -> str:
    return f"{QUERIED_PREFIX}{datetime.datetime.now():%Y-%m-%d %H:%M:%S}"


class NodeInfoPanel:
    """A header naming a node and its status, above its collapsible sections.

    The sections are Last Input, Last Output and Source. The header also offers the
    node's executor; a choice there is reported to *on_executor_chosen*, and
    `PyironFlow` decides what it means.

    Each section is an accordion of its own, because an `ipywidgets.Accordion` opens at
    most one child and all of them must be able to show at once. The panel knows nothing of
    selection or of the accordion it sits in; `PyironFlow` decides what it shows.
    """

    def __init__(
        self, on_executor_chosen: Callable[[str], None] = lambda _: None
    ) -> None:
        self.header = widgets.Label(value="")
        self.header.add_class("node-info-header")
        self.status = widgets.HTML(value="")
        self.title = widgets.HBox([self.status, self.header])
        self._on_executor_chosen = on_executor_chosen
        self._quiet = False
        self._previous: str | None = None
        self.executor = widgets.Dropdown(options=(), value=None, disabled=True)
        self.executor.observe(self._on_executor, names="value")
        self.executor_row = widgets.HBox([widgets.Label(EXECUTOR_LABEL), self.executor])
        self.last_input = widgets.Output()
        self.last_output = widgets.Output()
        self.source = widgets.Output()
        self.last_input_section = widgets.Accordion(
            children=[self.last_input], titles=(LAST_INPUT_TITLE,)
        )
        self.last_output_section = widgets.Accordion(
            children=[self.last_output], titles=(LAST_OUTPUT_TITLE,)
        )
        self.source_section = widgets.Accordion(
            children=[self.source], titles=(SOURCE_TITLE,)
        )
        self.gui = widgets.VBox(
            [
                self.title,
                self.executor_row,
                self.last_input_section,
                self.last_output_section,
                self.source_section,
            ]
        )

    def show(
        self,
        widget: PyironFlowWidget,
        label: str,
        executor_names: Sequence[str] = (),
        current: str | None = None,
    ) -> None:
        """Describe *widget*'s node *label*: its last input and output, and its source.

        The executor dropdown offers *executor_names*, with *current* selected.
        """
        self.clear()
        self.header.value = label
        self.status.value = STATUS_SYMBOLS.get(widget.node_status(label), NOT_RUN)
        widget._say(_queried(), out=self.last_input)
        widget._display_last_input(label, out=self.last_input)
        widget._say(_queried(), out=self.last_output)
        widget._display_last_output(label, out=self.last_output)
        widget._say(_queried(), out=self.source)
        widget._say(
            reactflow.highlight_node_source(widget.wf.nodes[label]), out=self.source
        )
        self._set_executor(
            (NO_EXECUTOR, *executor_names, CREATE_NEW), current or NO_EXECUTOR
        )
        self.executor.disabled = False

    def clear(self) -> None:
        self.header.value = ""
        self.status.value = ""
        self.last_input.outputs = ()
        self.last_output.outputs = ()
        self.source.outputs = ()
        self._set_executor((), None)
        self.executor.disabled = True

    def expand(self, last_input: bool, last_output: bool, source: bool) -> None:
        """Open the sections flagged ``True``; leave the others as they are."""
        if last_input:
            self.last_input_section.selected_index = 0
        if last_output:
            self.last_output_section.selected_index = 0
        if source:
            self.source_section.selected_index = 0

    def revert(self) -> None:
        """Put the executor dropdown back to its last real choice, without reporting it."""
        self._set_executor(self.executor.options, self._previous)

    def _set_executor(self, options: tuple[str, ...], value: str | None) -> None:
        self._quiet = True
        try:
            self.executor.options = options
            self.executor.value = value
        finally:
            self._quiet = False
        self._previous = value

    def _on_executor(self, change: dict[str, Any]) -> None:
        if self._quiet:
            return
        self._on_executor_chosen(change["new"])
        if change["new"] != CREATE_NEW:
            self._previous = change["new"]
