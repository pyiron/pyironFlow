import pyiron_workflow as pwf
import pytest

from . import flow_gui  # skips this module if playwright is missing
from .test_ui import relu


@pytest.fixture
def workflow() -> pwf.Workflow:
    wf = pwf.Workflow("executors_demo")
    wf.n1 = pwf.node(relu)
    return wf


def test_create_new_for_node(gui: flow_gui.FlowGui) -> None:
    gui.node("n1").info()
    gui.node_info.expect_node("n1")
    gui.node_info.choose_executor("[Create new]")
    gui.executors.expect_open()
    gui.executors.create_section.expect_open()
    gui.executors.choose_creator("thread_pool_executor_instructions")
    gui.executors.create()
    gui.node_info.expect_open()
    gui.node_info.expect_node("n1")
    gui.node_info.expect_executor("thread_pool_executor_instructions_0")
    gui.expect_eventually(
        lambda: gui.widget().wf.nodes["n1"].executor
        is gui.pf.executors.created["thread_pool_executor_instructions_0"].value,
        "n1 never got its new executor",
    )


def test_delete_takes_two_clicks(gui: flow_gui.FlowGui) -> None:
    made = gui.pf.executors.create("made", "thread_pool_executor_instructions", {})
    gui.widget().wf.nodes["n1"].executor = made.value
    gui.pf.executors_panel.refresh()
    gui.node("n1").info()
    gui.node_info.expect_executor("made")  # positive first: the node holds it
    gui.executors.open()
    gui.executors.browse_section.open()
    gui.executors.select("made")
    gui.executors.delete()
    gui.expect_eventually(
        lambda: gui.widget().wf.nodes["n1"].executor is None,
        "deleting did not clear n1's executor",
    )
    gui.node("n1").info()
    gui.node_info.expect_executor("None")
