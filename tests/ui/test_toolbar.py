import pathlib

import flowrep as fr
import pyiron_workflow as pwf
import pytest

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
