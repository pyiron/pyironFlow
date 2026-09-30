import pyiron_workflow as pwf
import pytest

from . import flow_gui  # skips this module if playwright is missing


@pytest.fixture
def workflow() -> pwf.Workflow:
    return pwf.Workflow("library_demo")


def test_add_node_twice(gui: flow_gui.FlowGui) -> None:
    library = gui.library
    library.open()
    library.expand("std")

    library.add("add")
    gui.node("add_0").expect_titled()
    library.expect_open()  # adding does not pull the user away from the library

    library.add("add")
    gui.node("add_1").expect_titled()
    library.expect_open()

    assert list(gui.widget().get_workflow().nodes) == ["add_0", "add_1"]
