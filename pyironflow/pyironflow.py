import flowrep as fr
import ipywidgets as widgets
import pydantic
from pyiron_workflow import Workflow
from pyiron_workflow.dag import Macro

from pyironflow.files_panel import FilesPanel
from pyironflow.reactflow import AccordionTab, PyironFlowWidget
from pyironflow.treeview import TreeView
from pyironflow.wf_extensions import validate_constants

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

DEFAULT_WORKFLOW_LABEL = "workflow"
_LABEL_ADAPTER: pydantic.TypeAdapter[str] = pydantic.TypeAdapter(fr.schemas.Label)


def _validate_workflows(wf_list: list[Workflow]) -> None:
    """Reject anything pyironFlow cannot drive, with the fix in the message.

    pyironFlow owns terminal IO: it builds ports from the values typed in the GUI when
    a run starts and removes them when it ends. A workflow that arrives with IO of its
    own would have it silently overwritten, so say so instead.
    """
    for index, wf in enumerate(wf_list):
        if not isinstance(wf, Workflow):
            hint = (
                f"pyironFlow displays pyiron_workflow.Workflow instances, but "
                f"wf_list[{index}] is a {type(wf).__name__}."
            )
            if isinstance(wf, Macro):
                hint += (
                    "\n\nConvert it first:\n\n"
                    "    from pyiron_workflow.constructors import macro2workflow\n"
                    "    wf = macro2workflow(macro)"
                )
            raise TypeError(hint)

        validate_constants(wf)

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
            wf_list = [Workflow(DEFAULT_WORKFLOW_LABEL)]

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
        self._reload_node_library = reload_node_library
        self.wf_widgets = [self._build_widget(wf) for wf in self.workflows]
        tree_view = TreeView(
            root_path=root_path, flow_widget=self.wf_widgets[0], log=self.out_log
        )
        self._tree_view = tree_view
        self.tab = self.view_flows()
        self.tab.observe(self._on_tab_selected, names="selected_index")
        self.files_panel = FilesPanel(self)
        self.accordion = widgets.Accordion(
            children=[
                tree_view.gui,
                self.files_panel.gui,
                self.out_widget,
                self.out_log,
            ],
            titles=[tab.value for tab in AccordionTab],
            layout={
                "border": "1px solid black",
                "width": f"{int(100*(1-flow_widget_ratio))}%",
                "flex": "1 0 auto",
                "overflow": "auto",
            },
        )
        for widget in self.wf_widgets:
            self._wire(widget)
        self.files_panel.refresh()

        self.gui = widgets.HBox(
            [self.accordion, self.tab],
            layout={
                "border": "1px solid black",
                "flex": "1 1 auto",
                "width": "auto",
                "height": "75vh",
            },
        )

    def close(self) -> None:
        """Tear down the GUI: release the node library's ``sys.path`` entry, if this
        GUI added it, and close the widget."""
        self._tree_view.close()
        self.gui.close()

    @property
    def active_widget(self) -> PyironFlowWidget:
        """The widget of the workflow tab currently selected."""
        return self.wf_widgets[self.tab.selected_index or 0]

    def add_workflow(self, wf: Workflow) -> PyironFlowWidget:
        """Show *wf* in a tab of its own and select it.

        Existing tabs are left alone, except that a tab whose workflow has no nodes,
        as synced from the GUI, is replaced rather than kept beside the new one.
        A new widget is always built, so its freshly mounted view lays the graph out.
        """
        _validate_workflows([wf])
        widget = self._build_widget(wf)
        self._wire(widget)
        index = self.tab.selected_index or 0
        current = self.active_widget
        replaced: PyironFlowWidget | None = current
        if len(current.get_workflow().nodes) == 0:
            self.wf_widgets[index] = widget
            self.workflows[index] = wf
        else:
            index = len(self.wf_widgets)
            self.wf_widgets.append(widget)
            self.workflows.append(wf)
            replaced = None
        self._sync_tabs()
        if replaced is not None:
            replaced.gui.close()
        self.tab.selected_index = index
        self._on_tab_selected()
        return widget

    def unique_label(self, label: str) -> str:
        """*label*, or *label* with the first free ``_<n>`` suffix among open tabs."""
        taken = {workflow.label for workflow in self.workflows}
        candidate, suffix = label, 0
        while candidate in taken:
            suffix += 1
            candidate = f"{label}_{suffix}"
        return candidate

    def rename_workflow(self, widget: PyironFlowWidget, name: str) -> None:
        """Give *widget*'s workflow, and its tab, the label *name*.

        Raises:
            ValueError: With a message fit to show the user, if *name* is not a
                valid label or another open tab already uses it.
        """
        try:
            label = _LABEL_ADAPTER.validate_python(name)
        except ValueError:
            raise ValueError(
                f"{name!r} is not a valid workflow name; use a Python identifier."
            ) from None
        if label == widget.wf.label:
            return
        if label in {workflow.label for workflow in self.workflows}:
            raise ValueError(f"another open tab is already named {label!r}.")
        widget.wf.label = label
        widget.gui.label = label
        self._sync_tabs()

    def close_workflow(self, widget: PyironFlowWidget) -> None:
        """Remove *widget*'s tab and select the tab now at its position.

        Closing the only tab leaves a fresh, empty workflow in its place, so there is
        always a canvas to work on. The workflow object itself is untouched; only the
        GUI lets go of it.
        """
        index = self.wf_widgets.index(widget)
        if len(self.wf_widgets) == 1:
            replacement = self._build_widget(Workflow(DEFAULT_WORKFLOW_LABEL))
            self._wire(replacement)
            self.wf_widgets[index] = replacement
            self.workflows[index] = replacement.wf
        else:
            del self.wf_widgets[index]
            del self.workflows[index]
        self._sync_tabs()
        widget.gui.close()
        # Shrinking `Tab.children` does not clamp `selected_index`, so set it here
        self.tab.selected_index = min(index, len(self.wf_widgets) - 1)
        self._on_tab_selected()

    def _sync_tabs(self) -> None:
        self.tab.children = [w.gui for w in self.wf_widgets]
        self.tab.titles = [workflow.label for workflow in self.workflows]

    def _build_widget(self, wf: Workflow) -> PyironFlowWidget:
        return PyironFlowWidget(
            wf=wf,
            log=self.out_log,
            out_widget=self.out_widget,
            reload_node_library=self._reload_node_library,
        )

    def _wire(self, widget: PyironFlowWidget) -> None:
        widget.accordion_widget = self.accordion
        widget.tree_widget = self._tree_view
        widget.files_panel = self.files_panel
        widget.flow = self

    def _on_tab_selected(self, change=None) -> None:
        self._tree_view.flow_widget = self.active_widget
        self.files_panel.refresh()

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
