import pyiron_workflow as pwf
import pytest

from . import flow_gui  # skips this module if playwright is missing
from .test_ui import relu


@pytest.fixture
def workflow() -> pwf.Workflow:
    wf = pwf.Workflow("node_info_demo")
    wf.n1 = pwf.node(relu)
    return wf


def test_info_shows_output_and_source(gui: flow_gui.FlowGui) -> None:
    gui.node("n1").info()
    node_info = gui.node_info
    node_info.expect_open()
    node_info.expect_node("n1")
    node_info.output_section.expect_open()
    node_info.source_section.expect_open()
    node_info.expect_output_containing("n1 has not been run yet.")
    node_info.expect_source_containing("def relu")


def test_open_node_info_follows_the_selection(gui: flow_gui.FlowGui) -> None:
    node_info = gui.node_info
    node_info.open()
    node_info.expect_open()
    gui.node("n1").select()
    node_info.expect_node("n1")
    gui.click_canvas()  # deselects
    node_info.expect_no_node()


def test_pull_opens_the_node_output(gui: flow_gui.FlowGui) -> None:
    # Distinctive enough not to match anything in the "Queried @ <timestamp>" line
    gui.input("n1", "x").set_input(3.25)
    gui.node("n1").pull()
    node_info = gui.node_info
    node_info.expect_open()
    node_info.expect_node("n1")
    node_info.output_section.expect_open()
    node_info.source_section.expect_closed()
    node_info.expect_output_containing("3.25")
