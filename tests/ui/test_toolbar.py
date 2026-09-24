import pathlib

import flowrep as fr
import pyiron_workflow as pwf
import pytest

from pyironflow import wf_extensions

from . import flow_gui  # skips this module if playwright is missing
from .test_ui import relu


@pytest.fixture
def workflow() -> pwf.Workflow:
    wf = pwf.Workflow("minimal_demo")
    wf.n1 = pwf.node(relu)
    wf.n2 = pwf.node(relu, x=-0.5)
    wf.accumulate = pwf.node(fr.std.add, a=wf.n1.outputs.signal, b=wf.n2.outputs.signal)
    return wf


@pytest.fixture
def workdir(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> pathlib.Path:
    """Files paths resolve against the kernel's cwd; keep them in a temp dir."""
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_export(gui: flow_gui.FlowGui, workdir: pathlib.Path) -> None:
    gui.export()
    gui.files.expect_open()
    gui.files.expect_action("Export")

    gui.files.go()  # a blank path defaults to the workflow label
    gui.files.expect_status("Exported")
    assert (workdir / "minimal_demo.json").is_file()


def _structure(wf: pwf.Workflow) -> tuple[set[str], set[str]]:
    """What a user sees of *wf*: its non-constant nodes and its edges."""
    nodes = {
        label for label, node in wf.nodes.items() if not wf_extensions.is_constant(node)
    }
    edges = {edge["id"] for edge in wf_extensions.get_edges(wf)}
    return nodes, edges


def test_import(gui: flow_gui.FlowGui, workdir: pathlib.Path) -> None:
    # Create something to subsequently import
    gui.export()
    gui.files.go()
    gui.files.expect_status("Exported")

    # Make sure import will re-contextualize to the files panel by looking away briefly
    output = gui.section("Output")
    output.open()
    output.expect_open()
    gui.files.expect_closed()

    gui.import_()
    gui.files.expect_open()
    gui.files.expect_action("Import")
    gui.files.set_path("minimal_demo")
    gui.files.go()
    gui.files.expect_status("Imported")

    gui.expect_tabs(["minimal_demo", "minimal_demo_1"])
    gui.expect_selected_tab("minimal_demo_1")
    gui.node("n1").expect_present()  # exactly one: the selected tab's
    original, imported = (gui.widget(i).get_workflow() for i in (0, 1))
    assert _structure(imported) == _structure(original)


def test_save(gui: flow_gui.FlowGui, workdir: pathlib.Path) -> None:
    gui.expect_save_disabled()  # nothing has run yet
    gui.input("n1", "x").set_input(1)
    gui.run()
    gui.expect_save_enabled()

    gui.save()
    gui.files.expect_open()
    gui.files.expect_action("Save run")
    gui.files.go()  # a blank path defaults to the run label
    gui.files.expect_status("Saved run")
    assert (workdir / f"{gui.last_run().label}.pckl").is_file()
