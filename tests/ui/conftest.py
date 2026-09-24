import pytest
from IPython import display

import pyironflow


@pytest.fixture
def workflow():
    raise NotImplementedError("Override `workflow` in your test module")


@pytest.fixture
def root_path():
    """The node library's location; `None` lets `PyironFlow` pick its default."""
    return None


@pytest.fixture
def gui(solara_test, page_session, workflow, root_path):
    from . import flow_gui  # lazy: keeps conftest importable without playwright

    pf = pyironflow.PyironFlow([workflow], root_path=root_path)
    display.display(pf.gui)
    yield flow_gui.FlowGui(page_session, pf)
    # teardown here, if you ever need any
