"""Page object for the rendered PyironFlow widget."""

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

    def node(self, label: str) -> sync_api.Locator:
        return self.page.get_by_test_id(f"rf__node-{label}")

    def port(self, node: str, port: str) -> sync_api.Locator:
        """The row holding one input port's label, lock button and entry widget."""
        return self.node(node).get_by_test_id(f"port-in-{port}")

    def port_input_field(self, node: str, port: str) -> sync_api.Locator:
        """
        The port's entry widget: a text box, checkbox or dropdown.

        Raises:
            NoInputFieldError: If the port exists but currently shows no entry widget,
                because it is connected or its type hint admits no typed value.
        """
        row = self.port(node, port)
        # The entry renders in the same React pass as its row, so once the row is in
        # the DOM an absent entry is really absent, not merely not-yet-rendered.
        row.wait_for(state="attached")
        field = row.get_by_test_id("port-entry")
        if field.count() == 0:
            raise NoInputFieldError(
                f"{node}.{port} has no input field: it is connected, or its type "
                f"hint admits no typed value"
            )
        return field

    def port_required_marker(self, node: str, port: str) -> sync_api.Locator:
        """
        The red asterisk flagging a port that still needs a value or a connection.

        Present only while the port is unfilled, so assert on it with
        ``expect(...).to_be_visible()`` or ``expect(...).to_have_count(0)``.
        """
        return self.port(node, port).get_by_test_id("port-required")

    def set_input(self, node: str, port: str, value) -> None:
        box = self.port_input_field(node, port)
        box.fill(str(value))
        box.press("Enter")

    def run(self) -> None:
        self.run_button.click()

    def expect_text(self, text: str, exact: bool = False) -> None:
        sync_api.expect(self.page.get_by_text(text, exact=exact)).to_be_visible()

    def last_run(self, widget_index: int = 0) -> pwf.schemas.Run:
        return self.pf.wf_widgets[widget_index].last_run
