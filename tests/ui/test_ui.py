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

    gui.port("n1", "x").set_input(2)
    gui.run()
    gui.expect_text("2.0", exact=True)
    assert gui.last_run().outputs.accumulate__added == 2.0


@pytest.mark.parametrize(("x", "expected"), [(2, 2.0), (-1, 0.0), (0.5, 0.5)])
def test_relu_values(gui: flow_gui.FlowGui, x: float, expected: float) -> None:
    gui.port("n1", "x").set_input(x)
    gui.run()
    gui.expect_text(str(expected), exact=True)
    assert gui.last_run().outputs.accumulate__added == expected


def test_port_input_field_by_name(gui: flow_gui.FlowGui) -> None:
    """
    Tests our access routine in flow gui, and validates that ports with defaults get
    placeholder values at the same time.

    bias is the *second* port, so this could not pass by accident of ordering
    """
    gui.port("n1", "bias").expect_placeholder_data("0.0")


def test_port_input_field_missing(gui: flow_gui.FlowGui) -> None:
    """
    Validates clean failure if a test asks for GUI input field where none exists.

    accumulate.a is fed by n1, so it renders a port row but no entry widget
    """
    with pytest.raises(flow_gui.NoInputFieldError, match="accumulate.a"):
        _ = gui.port("accumulate", "a").input_field


def test_port_required_marker(gui: flow_gui.FlowGui) -> None:
    n1_x = gui.port("n1", "x")
    n1_x.expect_required()  # no default
    gui.port("n1", "bias").expect_not_required()  # has default
    gui.port("accumulate", "a").expect_not_required()  # connected

    n1_x.set_input(1)
    n1_x.expect_not_required()
