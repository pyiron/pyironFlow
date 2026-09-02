import warnings

import ipywidgets as widgets
from pyiron_workflow import Workflow

from pyironflow.reactflow import PyironFlowWidget
from pyironflow.treeview import TreeView

__author__ = "Joerg Neugebauer"
__copyright__ = (
    "Copyright 2024, Max-Planck-Institut for Sustainable Materials GmbH - "
    "Computational Materials Design (CM) Department"
)
__version__ = "0.2"
__maintainer__ = ""
__email__ = ""
__status__ = "development"
__date__ = "Aug 1, 2024"


class PyironFlow:
    def __init__(
        self,
        wf_list: list[Workflow] = None,
        root_path: str | None = None,
        flow_widget_ratio: float = 0.85,
        reload_node_library: bool = False,
    ):
        """

        Args:
            wf_list (list[Workflow]): list of workflows to be displayed in the
                workflow view.
            root_path (str | None): path to the node library. If None, the
                default path (../pyiron_nodes/pyiron_nodes) is used.
            flow_widget_ratio (float): fraction of the widget width that is
                reserved for the workflow view.
            reload_node_library (bool): allow the refresh button to reload node
                modules
        """
        # throw a warning; debate value limits
        flow_widget_ratio = max(min(flow_widget_ratio, 0.95), 0.05)

        # generate empty default workflow if workflow list is empty
        if wf_list is None:
            wf_list = []
        if len(wf_list) == 0:
            wf_list = [Workflow("workflow")]

        if root_path is None:
            try:
                import pyiron_nodes

                root_path = pyiron_nodes.__spec__.submodule_search_locations[0]
            except (ImportError, IndexError):
                root_path = ""

        self._flow_widget_factor = 1 / (1 / flow_widget_ratio - 1)
        self.workflows = wf_list

        self.out_log = widgets.Output(
            layout={
                "border": "1px solid black",
                "overflow": "auto",
            }
        )
        self.out_widget = widgets.Output(
            layout={
                "border": "1px solid black",
                "overflow": "auto",
            }
        )
        self.wf_widgets = [
            PyironFlowWidget(
                wf=wf,
                root_path=root_path,
                log=self.out_log,
                out_widget=self.out_widget,
                reload_node_library=reload_node_library,
            )
            for wf in self.workflows
        ]
        tree_view = TreeView(
            root_path=root_path, flow_widget=self.wf_widgets[0], log=self.out_log
        )
        accordion = widgets.Accordion(
            children=[tree_view.gui, self.out_widget, self.out_log],
            titles=["Node Library", "Output", "Logging Info"],
            layout={
                "border": "1px solid black",
                "width": f"{int(100*(1-flow_widget_ratio))}%",
                "flex": "1 0 auto",
                "overflow": "auto",
            },
        )
        for widget in self.wf_widgets:
            widget.accordion_widget = accordion
            widget.tree_widget = tree_view

        self.gui = widgets.HBox(
            [accordion, self.view_flows()],
            layout={
                "border": "1px solid black",
                "flex": "1 1 auto",
                "width": "auto",
                "height": "75vh",
            },
        )

    def view_flows(self):
        tab = widgets.Tab(
            layout={
                "width": "auto",
                "flex": f"{self._flow_widget_factor} 0 auto",
                "height": "100%",
            }
        )
        tab.children = [w.gui for w in self.wf_widgets]
        tab.titles = [wf.label for wf in self.workflows]
        return tab
