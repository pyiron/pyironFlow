import pytest
from IPython import display

import pyironflow


@pytest.fixture
def workflow():
    raise NotImplementedError("Override `workflow` in your test module")


@pytest.fixture
def gui(solara_test, page_session, workflow):
    from . import flow_gui  # lazy: keeps conftest importable without playwright

    pf = pyironflow.PyironFlow([workflow])
    display.display(pf.gui)
    yield flow_gui.FlowGui(page_session, pf)
    # teardown here, if you ever need any
