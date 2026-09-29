import typing

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

    gui.input("n1", "x").set_input(2)
    gui.run()
    gui.expect_text("2.0", exact=True)
    assert gui.last_run().outputs.accumulate__added == 2.0


@pytest.mark.parametrize(("x", "expected"), [(2, 2.0), (-1, 0.0), (0.5, 0.5)])
def test_relu_values(gui: flow_gui.FlowGui, x: float, expected: float) -> None:
    gui.input("n1", "x").set_input(x)
    gui.run()
    gui.expect_text(str(expected), exact=True)
    assert gui.last_run().outputs.accumulate__added == expected


def test_port_input_field_by_name(gui: flow_gui.FlowGui) -> None:
    """
    Tests our access routine in flow gui, and validates that ports with defaults get
    placeholder values at the same time.

    bias is the *second* port, so this could not pass by accident of ordering
    """
    gui.input("n1", "bias").expect_placeholder_data("0.0")


def test_port_input_field_missing(gui: flow_gui.FlowGui) -> None:
    """
    Validates clean failure if a test asks for GUI input field where none exists.

    accumulate.a is fed by n1, so it renders a port row but no entry widget
    """
    with pytest.raises(flow_gui.NoInputFieldError, match="accumulate.a"):
        _ = gui.input("accumulate", "a").input_field


def test_port_required_marker(gui: flow_gui.FlowGui) -> None:
    n1_x = gui.input("n1", "x")
    n1_x.expect_required()  # no default
    gui.input("n1", "bias").expect_not_required()  # has default
    gui.input("accumulate", "a").expect_not_required()  # connected

    n1_x.set_input(1)
    n1_x.expect_not_required()


@fr.atomic("chosen")
def choose(mode: typing.Literal["up", "down"]) -> str:
    return mode


class TestLocking:
    @pytest.fixture
    def workflow(self) -> pwf.Workflow:
        wf = pwf.Workflow("locking_demo")
        wf.pick = pwf.node(choose)
        return wf

    def test_lock_needs_a_value(self, gui: flow_gui.FlowGui) -> None:
        mode = gui.input("pick", "mode")
        mode.expect_unlocked()
        mode.expect_not_lockable()  # dropdown still shows "Select"

        mode.set_input("'down'")  # options render as Python reprs
        mode.expect_lockable()

        mode.lock()
        mode.expect_locked()

        mode.unlock()
        mode.expect_unlocked()


@fr.atomic("flipped")
def flip(flag: bool) -> bool:
    return not flag


class TestCheckbox:
    @pytest.fixture
    def workflow(self) -> pwf.Workflow:
        wf = pwf.Workflow("checkbox_demo")
        wf.toggle = pwf.node(flip)
        return wf

    def test_set_checkbox(self, gui: flow_gui.FlowGui) -> None:
        flag = gui.input("toggle", "flag")
        flag.expect_required()

        flag.set_input(True)
        flag.expect_not_required()
        gui.run()
        gui.expect_text("False", exact=True)
        assert gui.last_run().outputs.toggle__flipped is False

        flag.set_input(False)
        gui.run()
        gui.expect_text("True", exact=True)
        assert gui.last_run().outputs.toggle__flipped is True


def test_connect_to_locked_port_refused(gui: flow_gui.FlowGui) -> None:
    n1_signal = gui.output("n1", "signal")
    n1_signal.connect(gui.input("n2", "x"))  # locked: refused
    n1_signal.connect(gui.input("n2", "bias"))  # allowed
    # Asserting the later, allowed edge first proves the refused drag was processed
    gui.edge("n1", "signal", "n2", "bias").expect_present()
    gui.edge("n1", "signal", "n2", "x").expect_absent()
    gui.input("n2", "x").expect_locked()


class TestEdges:
    @pytest.fixture
    def workflow(self) -> pwf.Workflow:
        wf = pwf.Workflow("edges_demo")
        wf.a = pwf.node(relu)
        wf.b = pwf.node(relu)
        return wf

    def test_connect_feeds_port(self, gui: flow_gui.FlowGui) -> None:
        b_x = gui.input("b", "x")
        b_x.expect_required()
        _ = b_x.input_field  # present while unconnected

        gui.output("a", "signal").connect(b_x)
        gui.edge("a", "signal", "b", "x").expect_present()
        b_x.expect_not_required()
        with pytest.raises(flow_gui.NoInputFieldError):
            _ = b_x.input_field

    def test_connect_reaches_backend(self, gui: flow_gui.FlowGui) -> None:
        edge = gui.edge("a", "signal", "b", "x")
        gui.output("a", "signal").connect(gui.input("b", "x"))
        edge.expect_in_backend()

        gui.input("a", "x").set_input(2)
        gui.run()
        gui.expect_text("2.0", exact=True)
        assert gui.last_run().outputs.b__signal == 2.0

    def test_edge_id_survives_round_trip(self, gui: flow_gui.FlowGui) -> None:
        """The same id finds the edge JS drew and the one Python sends back."""
        edge = gui.edge("a", "signal", "b", "x")
        gui.output("a", "signal").connect(gui.input("b", "x"))
        edge.expect_present()

        gui.input("a", "x").set_input(1)
        gui.run()  # Python re-sends every edge afterwards
        gui.node("b").expect_has_run()
        edge.expect_present()


class TestConnected:
    @pytest.fixture
    def workflow(self) -> pwf.Workflow:
        wf = pwf.Workflow("connected_demo")
        wf.a = pwf.node(relu)
        wf.b = pwf.node(relu, x=wf.a.outputs.signal)
        return wf

    def test_rename_node(self, gui: flow_gui.FlowGui) -> None:
        gui.input("a", "x").set_input(2)

        first = gui.node("a").rename("first")
        first.expect_titled()
        gui.edge("first", "signal", "b", "x").expect_present()
        gui.node("a").expect_absent()

        gui.run()  # needs the value typed into a.x, now first.x
        gui.expect_text("2.0", exact=True)
        assert gui.last_run().outputs.b__signal == 2.0

    def test_group_nodes(self, gui: flow_gui.FlowGui) -> None:
        gui.input("a", "x").set_input(2)

        pair = gui.group("pair", "a", "b")
        pair.expect_titled()
        gui.node("a").expect_absent()

        gui.run()  # needs the value typed into a.x, now pair.a__x
        gui.expect_text("2.0", exact=True)
        assert gui.last_run().outputs.pair__b__signal == 2.0

    def test_group_needs_two_nodes(self, gui: flow_gui.FlowGui) -> None:
        gui.node("a").select()
        gui.expect_group_disabled()
        gui.node("b").add_to_selection()
        gui.expect_group_enabled()

    def test_ungroup_a_group(self, gui: flow_gui.FlowGui) -> None:
        gui.group("pair", "a", "b").ungroup()
        gui.node("pair_a").expect_titled()
        gui.edge("pair_a", "signal", "pair_b", "x").expect_present()
        gui.node("pair").expect_absent()

    def test_delete_edge(self, gui: flow_gui.FlowGui) -> None:
        edge = gui.edge("a", "signal", "b", "x")
        b_x = gui.input("b", "x")
        edge.expect_present()
        b_x.expect_not_required()

        edge.delete()
        edge.expect_absent()
        b_x.expect_required()
        _ = b_x.input_field  # the entry widget is back
        edge.expect_not_in_backend()

    def test_delete_one_of_two_parallel_edges(self, gui: flow_gui.FlowGui) -> None:
        to_bias = gui.edge("a", "signal", "b", "bias")
        to_x = gui.edge("a", "signal", "b", "x")
        gui.output("a", "signal").connect(gui.input("b", "bias"))
        to_bias.expect_present()

        to_bias.delete()
        to_bias.expect_absent()
        to_x.expect_present()

    def test_delete_node(self, gui: flow_gui.FlowGui) -> None:
        a = gui.node("a")
        edge = gui.edge("a", "signal", "b", "x")
        a.expect_present()

        a.delete()
        a.expect_absent()
        edge.expect_absent()
        gui.input("b", "x").expect_required()
        a.expect_not_in_backend()
        edge.expect_not_in_backend()

    def test_backspace_in_input_field_keeps_node(self, gui: flow_gui.FlowGui) -> None:
        field = gui.input("a", "x").input_field
        field.fill("12")  # uncommitted, so Python cannot normalize it to "12.0"
        field.press("Backspace")
        # The value check proves the key was handled before we look for the node
        flow_gui.sync_api.expect(field).to_have_value("1")
        gui.node("a").expect_present()


@fr.workflow("out")
def double_relu(y: float) -> float:
    first = relu(x=y)
    out = relu(x=first)
    return out


class TestMacro:
    @pytest.fixture
    def workflow(self) -> pwf.Workflow:
        wf = pwf.Workflow("macro_demo")
        wf.m = pwf.node(double_relu)
        return wf

    def test_ungroup_a_referenced_macro_needs_confirming(
        self, gui: flow_gui.FlowGui
    ) -> None:
        macro = gui.node("m")
        macro.ungroup()
        macro.expect_ungroup_armed()
        macro.expect_ungroup_warns_of("the python reference")
        gui.click_canvas()
        macro.expect_ungroup_not_armed()

        macro.ungroup()
        macro.expect_ungroup_armed()
        macro.confirm_ungroup()
        gui.node("m_relu_1").expect_titled()
        gui.node("m").expect_absent()


class TestDesignedIO:
    @pytest.fixture
    def workflow(self) -> pwf.Workflow:
        """Arrives wrapped, as one node, since its ``first`` output is designed."""
        wf = pwf.Workflow("designed")
        wf.a = pwf.node(relu, x=1.0)
        wf.b = pwf.node(relu, x=wf.a.outputs.signal)
        wf.create_output_from(wf.a.outputs.signal, label="first")
        return wf

    def test_ungrouping_away_designed_io_needs_confirming(
        self, gui: flow_gui.FlowGui
    ) -> None:
        designed = gui.node("designed")
        designed.ungroup()
        designed.expect_ungroup_armed()
        designed.expect_ungroup_warns_of("output 'first'")

        designed.confirm_ungroup()
        gui.node("designed_a").expect_titled()
        gui.node("designed").expect_absent()
