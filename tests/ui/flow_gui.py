"""Page object for the rendered PyironFlow widget."""

import pyiron_workflow as pwf
import pytest

import pyironflow

sync_api = pytest.importorskip("playwright.sync_api")


class FlowGui:
    def __init__(self, page: sync_api.Page, pf: pyironflow.PyironFlow) -> None:
        self.page = page
        self.pf = pf

    @property
    def run_button(self) -> sync_api.Locator:
        return self.page.get_by_role("button", name="Run", exact=True)

    def node(self, label: str) -> sync_api.Locator:
        return self.page.get_by_test_id(f"rf__node-{label}")

    def input(self, node: str, index: int = 0) -> sync_api.Locator:
        # TODO: switch to a port-name-based locator once you know the DOM,
        # e.g. .filter(has_text=port) on the port's row container.
        return self.node(node).get_by_role("textbox").nth(index)

    def set_input(self, node: str, value, index: int = 0) -> None:
        box = self.input(node, index)
        box.fill(str(value))
        box.press("Enter")

    def run(self) -> None:
        self.run_button.click()

    def expect_text(self, text: str, exact: bool = False) -> None:
        sync_api.expect(self.page.get_by_text(text, exact=exact)).to_be_visible()

    def last_run(self, widget_index: int = 0) -> pwf.schemas.Run:
        return self.pf.wf_widgets[widget_index].last_run
