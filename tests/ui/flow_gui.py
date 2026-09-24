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

import pyiron_workflow as pwf
import pytest

import pyironflow

sync_api = pytest.importorskip("playwright.sync_api")


class NoInputFieldError(LookupError):
    """The port exists but shows no entry widget."""


class FlowGui:
    def __init__(self, page: sync_api.Page, pf: pyironflow.PyironFlow) -> None:
        self.page = page
        self.pf = pf

    @property
    def run_button(self) -> sync_api.Locator:
        return self.page.get_by_role("button", name="Run", exact=True)

    def node(self, label: str) -> FlowNode:
        return FlowNode(self, label)

    def input(self, node: str, port: str) -> FlowInput:
        """The row holding one input port's label, lock button and entry widget."""
        return self.node(node).input(port)

    def run(self) -> None:
        self.run_button.click()

    def expect_text(self, text: str, exact: bool = False) -> None:
        sync_api.expect(self.page.get_by_text(text, exact=exact)).to_be_visible()

    def last_run(self, widget_index: int = 0) -> pwf.schemas.Run:
        return self.pf.wf_widgets[widget_index].last_run


class FlowNode:
    def __init__(self, gui: FlowGui, label: str):
        self.label = label
        self.gui = gui
        self.object = self.gui.page.get_by_test_id(f"rf__node-{label}")

    def input(self, label: str) -> FlowInput:
        return FlowInput(self, label)


class FlowInput:
    def __init__(self, node: FlowNode, label: str) -> None:
        self.label = label
        self.node = node
        self.object = self.node.object.get_by_test_id(f"port-in-{label}")

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
