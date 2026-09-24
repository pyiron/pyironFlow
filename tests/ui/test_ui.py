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

    gui.set_input("n1", "x", 2)
    gui.run()
    gui.expect_text("2.0", exact=True)
    assert gui.last_run().outputs.accumulate__added == 2.0


@pytest.mark.parametrize(("x", "expected"), [(2, 2.0), (-1, 0.0), (0.5, 0.5)])
def test_relu_values(gui: flow_gui.FlowGui, x: float, expected: float) -> None:
    gui.set_input("n1", "x", x)
    gui.run()
    gui.expect_text(str(expected), exact=True)
    assert gui.last_run().outputs.accumulate__added == expected


def test_port_input_field_by_name(gui: flow_gui.FlowGui) -> None:
    """
    Tests our access routine in flow gui, and validates that ports with defaults get
    placeholder values at the same time.

    bias is the *second* port, so this could not pass by accident of ordering
    """
    flow_gui.sync_api.expect(gui.port_input_field("n1", "bias")).to_have_attribute(
        "placeholder", "0.0"
    )


def test_port_input_field_missing(gui: flow_gui.FlowGui) -> None:
    """
    Validates clean failure if a test asks for GUI input field where none exists.

    accumulate.a is fed by n1, so it renders a port row but no entry widget
    """
    with pytest.raises(flow_gui.NoInputFieldError, match="accumulate.a"):
        gui.port_input_field("accumulate", "a")
