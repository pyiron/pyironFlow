import flowrep as fr
import pyiron_workflow as pwf
import pytest

from . import flow_gui  # skips this module if playwright is missing


@pytest.fixture
def workflow() -> pwf.Workflow:
    wf = pwf.Workflow("minimal_demo")
    wf.n1 = pwf.node(fr.std.add, a=1, b=2)
    return wf


def test_drag_divider(gui: flow_gui.FlowGui) -> None:
    gui.drag_divider(0.5)
    gui.expect_split(0.5)

    gui.drag_divider(0.3)
    gui.expect_split(0.3)
