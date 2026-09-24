"""
A model to map the page object for the rendered PyironFlow widget back to python.

This provides an abstraction layer so that the actual tests act on concepts; changes
that break the ability of this layer to find graphical elements _might_ indicate a
regression in the GUI UX, or may be due to insignificant technical changes -- treat
them with caution. In contrast, with this abstraction in place, failures in the tests
that use it _always_ represent regression in the GUI UX, because then actual concepts
are failing to fire correctly.
"""

from __future__ import annotations

import re
import time
from collections.abc import Callable

import pyiron_workflow as pwf
import pytest

import pyironflow
from pyironflow import reactflow, wf_extensions

sync_api = pytest.importorskip("playwright.sync_api")


class NoInputFieldError(LookupError):
    """The port exists but shows no entry widget."""


def _center(locator: sync_api.Locator) -> tuple[float, float]:
    locator.wait_for(state="visible")
    box = locator.bounding_box()
    assert box is not None, f"{locator} has no bounding box"
    return box["x"] + box["width"] / 2, box["y"] + box["height"] / 2


class FlowGui:
    def __init__(self, page: sync_api.Page, pf: pyironflow.PyironFlow) -> None:
        self.page = page
        self.pf = pf

    @property
    def canvas(self) -> sync_api.Locator:
        """
        The selected workflow tab's canvas. Other tabs' canvases stay in the page,
        hidden, and xyflow's test ids do not know about tabs.
        """
        return self.page.get_by_test_id("rf__wrapper").filter(visible=True)

    def _toolbar_button(self, name: str) -> sync_api.Locator:
        # Scoped to the canvas: the Files panel has buttons with the same names
        return self.canvas.get_by_role("button", name=name, exact=True)

    @property
    def run_button(self) -> sync_api.Locator:
        return self._toolbar_button("Run")

    def export(self) -> None:
        self._toolbar_button("Export").click()

    def import_(self) -> None:
        self._toolbar_button("Import").click()

    def save(self) -> None:
        self._toolbar_button("Save").click()

    def expect_save_disabled(self) -> None:
        sync_api.expect(self._toolbar_button("Save")).to_be_disabled()

    def expect_save_enabled(self) -> None:
        sync_api.expect(self._toolbar_button("Save")).to_be_enabled()

    def rename(self, name: str) -> None:
        """Rename the workflow, answering the name prompt with *name*."""
        # Playwright dismisses dialogs nobody handles, which cancels the rename
        self.page.once("dialog", lambda dialog: dialog.accept(name))
        self._toolbar_button("Rename").click()

    @property
    def _close_button(self) -> sync_api.Locator:
        # Its label changes when armed
        return self.canvas.get_by_role(
            "button", name=re.compile(r"^(Confirm close|Close)$")
        )

    def close(self) -> None:
        """One click: the first arms the button, a second closes the tab."""
        self._close_button.click()

    def expect_close_armed(self) -> None:
        sync_api.expect(self._close_button).to_have_text("Confirm close")

    def expect_close_not_armed(self) -> None:
        # Shorter than the 4 s after which the button disarms by itself, so only a
        # prompt disarm passes
        sync_api.expect(self._close_button).to_have_text("Close", timeout=1000)

    def click_canvas(self) -> None:
        """Click empty canvas: the pane's left edge, clear of toolbar and nodes."""
        pane = self.canvas.locator(".react-flow__pane")
        box = pane.bounding_box()
        assert box is not None, "the canvas has no pane"
        pane.click(position={"x": 5, "y": box["height"] / 2})

    def expect_tabs(self, labels: list[str]) -> None:
        """The workflow tabs, all of them, in order."""
        sync_api.expect(self.page.get_by_role("tab")).to_have_text(labels)

    def expect_selected_tab(self, label: str) -> None:
        sync_api.expect(
            self.page.get_by_role("tab", name=label, exact=True)
        ).to_have_attribute("aria-selected", "true")

    def section(self, title: str) -> _FlowSection:
        """One section of the accordion beside the canvas."""
        return _FlowSection(self, title)

    @property
    def files(self) -> FlowFiles:
        return FlowFiles(self, "Files")

    @property
    def library(self) -> FlowLibrary:
        return FlowLibrary(self, "Node Library")

    def node(self, label: str) -> FlowNode:
        return FlowNode(self, label)

    def input(self, node: str, port: str) -> FlowInput:
        """The row holding one input port's label, lock button and entry widget."""
        return self.node(node).input(port)

    def output(self, node: str, port: str) -> FlowOutput:
        """The row and dot of one output port."""
        return self.node(node).output(port)

    def edge(
        self, source_node: str, source_port: str, target_node: str, target_port: str
    ) -> FlowEdge:
        return FlowEdge(self, source_node, source_port, target_node, target_port)

    def run(self) -> None:
        self.run_button.click()

    def expect_text(self, text: str, exact: bool = False) -> None:
        sync_api.expect(self.page.get_by_text(text, exact=exact)).to_be_visible()

    def last_run(self, widget_index: int = 0) -> pwf.schemas.Run:
        return self.widget(widget_index).last_run

    def widget(self, index: int = 0) -> reactflow.PyironFlowWidget:
        return self.pf.wf_widgets[index]

    def expect_eventually(
        self, condition: Callable[[], bool], message: str, timeout: float = 5.0
    ) -> None:
        """
        Retry *condition* until it holds, like `expect` does for the page.

        The browser syncs its state to Python asynchronously, so a back-end check made
        straight after a GUI action can see the state from before it.
        """
        deadline = time.monotonic() + timeout
        while not condition():
            if time.monotonic() > deadline:
                raise AssertionError(message)
            self.page.wait_for_timeout(100)  # lets the browser keep talking meanwhile


class FlowNode:
    def __init__(self, gui: FlowGui, label: str):
        self.label = label
        self.gui = gui
        self.object = self.gui.canvas.get_by_test_id(f"rf__node-{label}")

    def input(self, label: str) -> FlowInput:
        return FlowInput(self, label)

    def output(self, label: str) -> FlowOutput:
        return FlowOutput(self, label)

    @property
    def title(self) -> sync_api.Locator:
        """The node's label, prefixed by a status square that is ⬜ until it runs."""
        return self.object.get_by_test_id("node-title")

    def expect_has_run(self) -> None:
        sync_api.expect(self.title).not_to_have_text(re.compile("^⬜"))

    def expect_titled(self) -> None:
        """The title shows the node's label, after its status square."""
        sync_api.expect(self.title).to_have_text(
            re.compile(rf"\s{re.escape(self.label)}$")
        )

    def expect_present(self) -> None:
        sync_api.expect(self.object).to_have_count(1)

    def expect_absent(self) -> None:
        sync_api.expect(self.object).to_have_count(0)

    def delete(self) -> None:
        # Click the title, not the centre: a click there can focus an input field,
        # where Backspace edits text instead of deleting the node.
        self.title.click()
        self.gui.page.keyboard.press("Backspace")

    def expect_not_in_backend(self) -> None:
        """Checked after a sync, so a node the GUI would resurrect still counts."""
        self.gui.expect_eventually(
            lambda: self.label not in self.gui.widget().get_workflow().nodes,
            f"{self.label} still in the workflow",
        )


class FlowInput:
    def __init__(self, node: FlowNode, label: str) -> None:
        self.label = label
        self.node = node
        self.object = self.node.object.get_by_test_id(f"port-in-{label}")

    @property
    def handle(self) -> sync_api.Locator:
        """The dot an edge attaches to."""
        return self.node.object.get_by_test_id(f"handle-in-{self.label}")

    @property
    def input_field(self) -> sync_api.Locator:
        """
        The port's entry widget: a text box, checkbox or dropdown.

        Raises:
            NoInputFieldError: If the port exists but currently shows no entry widget,
                because it is connected or its type hint admits no typed value.
        """
        self.object.wait_for(state="attached")
        field = self.object.get_by_test_id("port-entry")
        if field.count() == 0:
            raise NoInputFieldError(
                f"{self.node.label}.{self.label} has no input field: it is connected, or its type "
                f"hint admits no typed value"
            )
        return field

    def set_input(self, value) -> None:
        field = self.input_field
        if field.evaluate("el => el.tagName") == "SELECT":
            field.select_option(str(value))  # a dropdown commits on change
        elif field.get_attribute("type") == "checkbox":
            field.set_checked(value)  # so does a checkbox, but only if it changes
        else:
            field.fill(str(value))
            field.press("Enter")

    def expect_placeholder_data(self, placeholder: str) -> None:
        sync_api.expect(self.input_field).to_have_attribute("placeholder", placeholder)

    @property
    def _required(self) -> sync_api.Locator:
        """
        The red asterisk flagging a port that still needs a value or a connection.

        Present only while the port is unfilled, so assert on it with
        ``expect(...).to_be_visible()`` or ``expect(...).to_have_count(0)``.
        """
        return self.object.get_by_test_id("port-required")

    def expect_required(self) -> None:
        sync_api.expect(self._required).to_be_visible()

    def expect_not_required(self) -> None:
        sync_api.expect(self._required).to_have_count(0)

    @property
    def _lock_button(self) -> sync_api.Locator:
        """
        The padlock beside the entry: it locks, unlocks or (with nowhere to release the
        value to) deletes the port's fixed value.
        """
        return self.object.get_by_test_id("port-lock")

    def lock(self) -> None:
        self._lock_button.click()

    def unlock(self) -> None:
        self._lock_button.click()

    def expect_lockable(self) -> None:
        sync_api.expect(self._lock_button).to_be_enabled()

    def expect_not_lockable(self) -> None:
        """There is nothing to lock yet: no value entered and no default."""
        sync_api.expect(self._lock_button).to_be_disabled()

    _LOCKED_CLASS = re.compile(r"(^|\s)port-entry--locked(\s|$)")

    def expect_locked(self) -> None:
        sync_api.expect(self.input_field).to_have_class(self._LOCKED_CLASS)
        sync_api.expect(self.input_field).not_to_be_editable()

    def expect_unlocked(self) -> None:
        sync_api.expect(self.input_field).not_to_have_class(self._LOCKED_CLASS)
        sync_api.expect(self.input_field).to_be_editable()


class FlowOutput:
    def __init__(self, node: FlowNode, label: str) -> None:
        self.label = label
        self.node = node
        self.object = self.node.object.get_by_test_id(f"port-out-{label}")

    @property
    def handle(self) -> sync_api.Locator:
        """The dot an edge starts from."""
        return self.node.object.get_by_test_id(f"handle-out-{self.label}")

    def connect(self, target: FlowInput) -> None:
        """Drag from this port's dot to *target*'s, as a user draws an edge."""
        page = self.node.gui.page
        page.mouse.move(*_center(self.handle))
        page.mouse.down()
        # xyflow tracks the pointer between the dots; one jump can skip its hit test
        page.mouse.move(*_center(target.handle), steps=10)
        page.mouse.up()


class FlowEdge:
    def __init__(
        self,
        gui: FlowGui,
        source_node: str,
        source_port: str,
        target_node: str,
        target_port: str,
    ) -> None:
        self.gui = gui
        self.id = wf_extensions.edge_id(
            source_node, source_port, target_node, target_port
        )
        self.object = self.gui.canvas.get_by_test_id(f"rf__edge-{self.id}")

    def expect_present(self) -> None:
        sync_api.expect(self.object).to_have_count(1)

    def expect_absent(self) -> None:
        sync_api.expect(self.object).to_have_count(0)

    def select(self) -> None:
        """Click the edge's own line: a curve's bounding-box centre may miss it."""
        path = self.object.locator("path.react-flow__edge-path").first
        path.wait_for(state="attached")
        x, y = path.evaluate("""p => {
                const m = p.getPointAtLength(p.getTotalLength() / 2);
                const s = new DOMPoint(m.x, m.y).matrixTransform(p.getScreenCTM());
                return [s.x, s.y];
            }""")
        self.gui.page.mouse.click(x, y)

    def delete(self) -> None:
        self.select()
        self.gui.page.keyboard.press("Backspace")

    def _in_backend(self) -> bool:
        """
        Whether the workflow holds this edge once synced from the GUI -- the state the
        next GUI command acts on. Syncing mutates the widget's workflow, exactly as
        every GUI command does.
        """
        wf = self.gui.widget().get_workflow()
        return self.id in {e["id"] for e in wf_extensions.get_edges(wf)}

    def expect_in_backend(self) -> None:
        self.gui.expect_eventually(self._in_backend, f"{self.id} not in the workflow")

    def expect_not_in_backend(self) -> None:
        self.gui.expect_eventually(
            lambda: not self._in_backend(), f"{self.id} still in the workflow"
        )


class _FlowSection:
    """
    A base class for the accordion tab regions
    """

    _OPEN_CLASS = re.compile(r"(^|\s)jupyter-widget-Collapse-open(\s|$)")

    def __init__(self, gui: FlowGui, title: str) -> None:
        self.gui = gui
        self.title = title
        self._header = gui.page.locator(
            ".jupyter-widget-Collapse-header",
            has_text=re.compile(f"^{re.escape(title)}$"),
        )
        self.object = gui.page.locator(".jupyter-widget-Accordion-child").filter(
            has=self._header
        )

    def open(self) -> None:
        # The header toggles, so only click a closed section
        if not self._OPEN_CLASS.search(self.object.get_attribute("class") or ""):
            self._header.click()

    def expect_open(self) -> None:
        sync_api.expect(self.object).to_have_class(self._OPEN_CLASS)

    def expect_closed(self) -> None:
        sync_api.expect(self.object).not_to_have_class(self._OPEN_CLASS)


class FlowFiles(_FlowSection):
    """The Files section: export or import recipes, save runs."""

    _ACTIVE_CLASS = re.compile(r"(^|\s)mod-active(\s|$)")

    def expect_action(self, label: str) -> None:
        """
        *label* ("Export", "Import", "Save run") is the selected action, and it is
        actionable by being a button.
        """
        sync_api.expect(
            self.object.get_by_role("button", name=label, exact=True)
        ).to_have_class(self._ACTIVE_CLASS)

    def set_path(self, text: str) -> None:
        self.object.get_by_role("textbox").fill(text)

    def go(self) -> None:
        self.object.get_by_role("button", name="Go", exact=True).click()

    def expect_status(self, text: str) -> None:
        """The status line reports success containing *text*."""
        sync_api.expect(self.object.get_by_text(text)).to_be_visible()


class FlowLibrary(_FlowSection):
    """The Node Library section: a tree of node definitions to place."""

    def add(self, name: str) -> None:
        """Place a new node from the definition called *name*."""
        # Match the item's own text: jstree's icon markup spoils its accessible name
        self.object.get_by_role("treeitem").filter(
            has_text=re.compile(rf"^\s*{re.escape(name)}\s*$")
        ).click()
