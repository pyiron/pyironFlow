import flowrep as fr
import pyiron_workflow as pwf
import pytest

from . import flow_gui  # skips this module if playwright is missing


@fr.atomic("signal")
def relu(x: float, bias: float = 0.0) -> float:
    return float(max(0.0, x - bias))


@pytest.fixture
def workflow() -> pwf.Workflow:
    wf = pwf.Workflow("minimal_demo")
    wf.n1 = pwf.node(relu)
    wf.n2 = pwf.node(relu, x=-0.5)
    wf.accumulate = pwf.node(fr.std.add, a=wf.n1.outputs.signal, b=wf.n2.outputs.signal)
    return wf


def test_run_error_then_result(gui: flow_gui.FlowGui) -> None:
    gui.run()
    gui.expect_text("Cannot run:")
    gui.expect_text("n1.x")

    gui.set_input("n1", 2)
    gui.run()
    gui.expect_text("2.0", exact=True)
    assert gui.last_run().outputs.accumulate__added == 2.0


@pytest.mark.parametrize(("x", "expected"), [(2, 2.0), (-1, 0.0), (0.5, 0.5)])
def test_relu_values(gui: flow_gui.FlowGui, x: float, expected: float) -> None:
    gui.set_input("n1", x)
    gui.run()
    gui.expect_text(str(expected), exact=True)
    assert gui.last_run().outputs.accumulate__added == expected
