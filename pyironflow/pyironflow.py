import ipywidgets as widgets
from pyiron_workflow import Workflow
from pyiron_workflow.dag import Macro

from pyironflow.reactflow import AccordionTab, PyironFlowWidget
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


def _validate_workflows(wf_list: list[Workflow]) -> None:
    """Reject anything pyironFlow cannot drive, with the fix in the message.

    pyironFlow owns terminal IO: it builds ports from the values typed in the GUI when
    a run starts and removes them when it ends. A workflow that arrives with IO of its
    own would have it silently overwritten, so say so instead.
    """
    for index, wf in enumerate(wf_list):
        if not isinstance(wf, Workflow):
            hint = ""
            if isinstance(wf, Macro):
                hint = (
                    "\n\nConvert it first:\n\n"
                    "    from pyiron_workflow.constructors import macro2workflow\n"
                    "    wf = macro2workflow(macro)"
                )
            raise TypeError(
                f"pyironFlow displays pyiron_workflow.Workflow instances, but "
                f"wf_list[{index}] is a {type(wf).__name__}.{hint}"
            )

        if not wf.inputs and not wf.outputs:
            continue

        has = " and ".join(
            part
            for part in (
                f"input {tuple(wf.inputs)}" if wf.inputs else "",
                f"output {tuple(wf.outputs)}" if wf.outputs else "",
            )
            if part
        )
        removals = "".join(
            f"\n    wf.remove_input({label!r})" for label in wf.inputs
        ) + "".join(f"\n    wf.remove_output({label!r})" for label in wf.outputs)
        raise ValueError(
            f"pyironFlow builds workflow IO itself and needs a workflow with none, "
            f"but wf_list[{index}] ({wf.label!r}) has {has}. Drop it with:\n{removals}"
        )


class PyironFlow:
    def __init__(
        self,
        wf_list: list[Workflow] | None = None,
        root_path: str | None = None,
        flow_widget_ratio: float = 0.85,
        reload_node_library: bool = False,
    ):
        """

        Args:
            wf_list (list[Workflow] | None ): list of workflows to be displayed
                in the workflow view.
            root_path (str | None): path to the node library
            flow_widget_ratio (float): fraction of the widget width that is
                reserved for the workflow view.
            reload_node_library (bool): allow the refresh button to reload node
                modules
        """
        # throw a warning; debate value limits
        flow_widget_ratio = max(min(flow_widget_ratio, 0.95), 0.05)

        # generate empty default workflow if workflow list is empty
        if wf_list is None or len(wf_list) == 0:
            wf_list = [Workflow("workflow")]

        _validate_workflows(wf_list)

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
            titles=[tab.value for tab in AccordionTab],
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
