"""The Node Info panel: what the GUI can tell about a single node."""

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING

import ipywidgets as widgets
from pyiron_workflow.execution import RunStatus

from pyironflow import reactflow

if TYPE_CHECKING:
    from pyironflow.reactflow import PyironFlowWidget

OUTPUT_TITLE = "Output"
SOURCE_TITLE = "Source"
QUERIED_PREFIX = "Queried @ "

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
    """A header naming a node and its status, above collapsible Output and Source.

    Each section is an accordion of its own, because an `ipywidgets.Accordion` opens at
    most one child and both must be able to show at once. The panel knows nothing of
    selection or of the accordion it sits in; `PyironFlow` decides what it shows.
    """

    def __init__(self) -> None:
        self.header = widgets.Label(value="")
        self.header.add_class("node-info-header")
        self.status = widgets.HTML(value="")
        self.title = widgets.HBox([self.status, self.header])
        self.output = widgets.Output()
        self.source = widgets.Output()
        self.output_section = widgets.Accordion(
            children=[self.output], titles=(OUTPUT_TITLE,)
        )
        self.source_section = widgets.Accordion(
            children=[self.source], titles=(SOURCE_TITLE,)
        )
        self.gui = widgets.VBox([self.title, self.output_section, self.source_section])

    def show(self, widget: PyironFlowWidget, label: str) -> None:
        """Describe *widget*'s node *label*: its latest output and its source."""
        self.clear()
        self.header.value = label
        self.status.value = STATUS_SYMBOLS.get(widget.node_status(label), NOT_RUN)
        widget._say(_queried(), out=self.output)
        widget._display_last_output(label, out=self.output)
        widget._say(_queried(), out=self.source)
        widget._say(
            reactflow.highlight_node_source(widget.wf.nodes[label]), out=self.source
        )

    def clear(self) -> None:
        self.header.value = ""
        self.status.value = ""
        self.output.outputs = ()
        self.source.outputs = ()

    def expand(self, output: bool, source: bool) -> None:
        """Open the sections flagged ``True``; leave the others as they are."""
        if output:
            self.output_section.selected_index = 0
        if source:
            self.source_section.selected_index = 0
