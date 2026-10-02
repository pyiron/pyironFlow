import json
import os
import types
import warnings
from collections.abc import Iterable
from pathlib import Path
from typing import Final, TypeAlias, TypeGuard, cast

import flowrep as fr
import ipywidgets as widgets
import pydantic
from pyiron_workflow import Workflow, datatypes

from pyironflow import executors, executors_lib, node_info, pyironflow_std, storage
from pyironflow.executors_panel import ExecutorsPanel
from pyironflow.files_panel import FilesPanel
from pyironflow.node_info import NodeInfoPanel
from pyironflow.reactflow import AccordionTab, PyironFlowWidget
from pyironflow.splitter import Splitter
from pyironflow.treeview import TreeView
from pyironflow.wf_extensions import (
    copy_node,
    has_only_unconnected_child_io,
    validate_constants,
)

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


GuiInput: TypeAlias = datatypes.Node | fr.schemas.NodeRecipe


def _as_workflow(item: GuiInput, name: str, taken: set[str]) -> Workflow:
    """*item*, called *name* in any error, as a workflow for a tab of its own.

    A node is copied first, so the GUI never changes the caller's object. A workflow whose IO is only what `pyiron_workflow` builds automatically is shown
    itself, stripped of that IO, since pyironFlow owns terminal IO. Anything else,
    including a workflow whose IO someone designed, is made the sole child of a fresh
    workflow, labelled so as to avoid the tab labels in *taken*.
    """
    if isinstance(item, datatypes.Node):
        item = copy_node(item)

    if _shown_directly(item):
        if item.inputs:
            item.remove_input(*list(item.inputs))
        if item.outputs:
            item.remove_output(*list(item.outputs))
        return item
    if isinstance(item, datatypes.Node):
        wf = Workflow(_unique_label(item.label, taken))
        wf.add_node(item)
        return wf
    if isinstance(item, fr.schemas.NodeRecipe):
        reference = getattr(item, "reference", None)
        stem = (
            DEFAULT_WORKFLOW_LABEL
            if reference is None
            else reference.info.qualname.rpartition(".")[2]
        )
        wf = storage.recipe_to_gui_workflow(item, stem)
        wf.label = _unique_label(wf.label, taken)
        return wf
    raise TypeError(
        f"pyironFlow displays pyiron_workflow nodes and flowrep recipes, but "
        f"{name} is a {type(item).__name__}."
    )


def _shown_directly(item: GuiInput) -> TypeGuard[Workflow]:
    return isinstance(item, Workflow) and has_only_unconnected_child_io(item)


def _unique_label(label: str, taken: set[str]) -> str:
    """*label*, or *label* with the first free ``_<n>`` suffix not in *taken*."""
    candidate, suffix = label, 0
    while candidate in taken:
        suffix += 1
        candidate = f"{label}_{suffix}"
    return candidate


LibraryRoot: TypeAlias = str | os.PathLike | types.ModuleType
LibraryRoots: TypeAlias = LibraryRoot | Iterable[LibraryRoot] | None

DEFAULT_LIBRARY_ROOTS: Final = Path(".")
"""The working directory: `PyironFlow`'s node library unless told otherwise."""

_STD_LIBRARY_ROOTS: Final = (
    Path(fr.std.__file__),
    Path(pyironflow_std.__file__),
)


class _Unset:
    """Marks an argument that was not passed."""


_UNSET: Final = _Unset()


def _one_library_path(root: object) -> Path:
    if isinstance(root, (str, os.PathLike)):
        return Path(root)
    if isinstance(root, types.ModuleType):
        if hasattr(root, "__path__"):
            return Path(list(root.__path__)[0])
        file = getattr(root, "__file__", None)
        if file is not None:
            return Path(file)
        raise TypeError(f"Module {root.__name__} has no file to use as a library root")
    raise TypeError(
        f"A library root is a path or a module, not {type(root).__name__}: {root!r}"
    )


def _as_library_paths(roots: LibraryRoots) -> list[Path]:
    """*roots* as a list of paths: `None` is none, a path or module is one, and an
    iterable is each of its (non-iterable) elements in order."""
    if roots is None:
        return []
    if isinstance(roots, (str, os.PathLike, types.ModuleType)):
        return [_one_library_path(roots)]
    if not isinstance(roots, Iterable):
        return [_one_library_path(roots)]  # raises the TypeError
    # typeshed's ModuleType.__getattr__ keeps modules in mypy's Iterable narrowing
    return [_one_library_path(root) for root in cast(Iterable[LibraryRoot], roots)]


ExecutorCreators: TypeAlias = types.ModuleType | Iterable[types.ModuleType] | None


def _as_modules(given: ExecutorCreators) -> list[types.ModuleType]:
    """*given* as a list: `None` is none, a module is one, an iterable is its items."""
    if given is None:
        return []
    if isinstance(given, types.ModuleType):
        return [given]
    return list(given)


class PyironFlow:
    def __init__(
        self,
        wf_list: list[GuiInput] | None = None,
        library_roots: LibraryRoots = DEFAULT_LIBRARY_ROOTS,
        flow_widget_ratio: float = 0.78,
        reload_node_library: bool = False,
        root_path: LibraryRoots | _Unset = _UNSET,
        executor_creators: ExecutorCreators = None,
    ):
        """

        Args:
            wf_list (list[GuiInput] | None ): what to display in the workflow view,
                one tab each. A workflow whose IO is only what `pyiron_workflow`
                builds automatically is shown itself, and loses that IO. Anything
                else, including a workflow with IO of its own design, is shown as the
                sole child of a new workflow, which is what `workflows` then holds in
                its place; ungroup it to edit its insides.
            library_roots (LibraryRoots): where the node library looks for nodes:
                a directory or python file path, an imported module (a package
                means its directory), or an iterable of these; `None` for none.
                Defaults to the working directory. flowrep's `std` and
                `pyironflow_std` are always shown first, whatever is passed.
            flow_widget_ratio (float): initial fraction of the widget width that is
                reserved for the workflow view; drag the divider to change it.
                Clamped to [0.05, 0.95].
            reload_node_library (bool): allow the refresh button to reload node
                modules
            root_path (LibraryRoots): deprecated alias for `library_roots`.
            executor_creators (ExecutorCreators): modules whose public Valid
                Creators the Executors panel offers, after those of
                `pyironflow.executors_lib`, which are always offered; see
                `pyironflow.executors`. Executors already set on the nodes of
                *wf_list* are held too, named ``external_<n>``.
        """
        # generate empty default workflow if workflow list is empty
        if wf_list is None or len(wf_list) == 0:
            wf_list = [Workflow(DEFAULT_WORKFLOW_LABEL)]

        taken = {item.label for item in wf_list if _shown_directly(item)}
        workflows = []
        for index, item in enumerate(wf_list):
            wf = _as_workflow(item, f"wf_list[{index}]", taken)
            taken.add(wf.label)
            workflows.append(wf)
        for wf in workflows:
            validate_constants(wf)
        self.executors = executors.ExecutorRegistry(
            executors.find_creators([executors_lib, *_as_modules(executor_creators)])
        )
        for wf in workflows:
            self.executors.adopt_from(wf)

        if not isinstance(root_path, _Unset):
            if library_roots is not DEFAULT_LIBRARY_ROOTS:
                raise TypeError(
                    "Pass library_roots only; root_path is its deprecated alias."
                )
            warnings.warn(
                "root_path is deprecated; use library_roots instead.",
                DeprecationWarning,
                stacklevel=2,
            )
            library_roots = root_path
        roots = [*_STD_LIBRARY_ROOTS, *_as_library_paths(library_roots)]

        self.workflows = workflows

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
            roots=roots, flow_widget=self.wf_widgets[0], log=self.out_log
        )
        self._tree_view = tree_view
        self.tab = self.view_flows()
        self.tab.observe(self._on_tab_selected, names="selected_index")
        self.files_panel = FilesPanel(self)
        self.node_info = NodeInfoPanel(on_executor_chosen=self._on_executor_chosen)
        self.executors_panel = ExecutorsPanel(
            self.executors, self._on_executor_created, self._on_executor_deleted
        )
        self.executors_panel.refresh()
        self.accordion = widgets.Accordion(
            children=[
                tree_view.gui,
                self.files_panel.gui,
                self.out_widget,
                self.node_info.gui,
                self.executors_panel.gui,
                self.out_log,
            ],
            titles=[tab.value for tab in AccordionTab],
            layout={
                "border": "1px solid black",
                "flex": "0 0 auto",
                "overflow": "auto",
            },
        )
        self._node_info_target: tuple[PyironFlowWidget, str] | None = None
        # The node a `[Create new]` came from, to receive the executor made next
        self._executor_target: tuple[PyironFlowWidget, str] | None = None
        for widget in self.wf_widgets:
            self._wire(widget)
        self.accordion.observe(self._on_accordion_selected, names="selected_index")
        self.files_panel.refresh()

        self.splitter = Splitter(
            ratio=flow_widget_ratio, layout={"flex": "0 0 auto", "height": "100%"}
        )
        self.splitter.observe(self._on_split, names="ratio")
        self._on_split()

        self.gui = widgets.HBox(
            [self.accordion, self.splitter, self.tab],
            layout={
                "border": "1px solid black",
                "flex": "1 1 auto",
                "width": "auto",
                "height": "75vh",
            },
        )

    def close(self) -> None:
        """Tear down the GUI: release the node library's ``sys.path`` entry, if this
        GUI added it, shut down the executors it holds, and close the widget."""
        self.executors.close()
        self._tree_view.close()
        self.gui.close()

    @property
    def active_widget(self) -> PyironFlowWidget:
        """The widget of the workflow tab currently selected."""
        return self.wf_widgets[self.tab.selected_index or 0]

    def get_workflow(self) -> Workflow:
        """The selected tab's workflow, first synced with what the browser shows."""
        widget = self.active_widget
        widget.wf = widget.get_workflow()
        return widget.wf

    def add_workflow(self, item: GuiInput) -> PyironFlowWidget:
        """Show *item* in a tab of its own and select it.

        *item* is shown as in the constructor: a workflow with only automatic IO is
        shown itself, without that IO, and anything else is wrapped as the sole child
        of a new workflow, labelled apart from the open tabs.

        Existing tabs are left alone, except that a tab whose workflow has no nodes,
        as synced from the GUI, is replaced rather than kept beside the new one.
        A new widget is always built, so its freshly mounted view lays the graph out.
        """
        taken = {workflow.label for workflow in self.workflows}
        wf = _as_workflow(item, "the item", taken)
        validate_constants(wf)
        self.executors.adopt_from(wf)
        self.executors_panel.refresh()
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

    def new_workflow(self) -> PyironFlowWidget:
        """Open a fresh, empty workflow in a tab of its own and select it.

        As with `add_workflow`, an empty selected tab is replaced rather than kept, so
        its label is free for the new workflow.
        """
        taken = {workflow.label for workflow in self.workflows}
        current = self.active_widget
        if len(current.get_workflow().nodes) == 0:
            taken.discard(current.wf.label)
        return self.add_workflow(Workflow(_unique_label(DEFAULT_WORKFLOW_LABEL, taken)))

    def unique_label(self, label: str) -> str:
        """*label*, or *label* with the first free ``_<n>`` suffix among open tabs."""
        return _unique_label(label, {workflow.label for workflow in self.workflows})

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
        widget.executors = self.executors
        widget.gui.observe(
            lambda _change, w=widget: self._on_selection(w), names="selected_nodes"
        )

    def _on_split(self, change=None) -> None:
        self.accordion.layout.width = f"{100 * (1 - self.splitter.ratio):.1f}%"

    def _on_tab_selected(self, change=None) -> None:
        self._tree_view.flow_widget = self.active_widget
        self.files_panel.refresh()
        self._set_node_info_target(None)
        self.node_info.clear()

    def _on_selection(self, widget: PyironFlowWidget) -> None:
        """Track the active canvas's single selected node as Node Info's target."""
        if widget is not self.active_widget:
            return
        selected = json.loads(widget.gui.selected_nodes)
        self._set_node_info_target(
            (widget, selected[0]["id"]) if len(selected) == 1 else None
        )
        self._refresh_node_info()

    def _on_accordion_selected(self, change=None) -> None:
        if self.accordion.selected_index == AccordionTab.NODE_INFO.index:
            self._refresh_node_info()

    def _refresh_node_info(self) -> None:
        """Show the target while Node Info is open, else leave the panel empty.

        Content is only built for an open panel, so browsing the canvas with another
        section open costs nothing. A target whose node has gone is dropped.
        """
        target = self._node_info_target
        if target is not None and target[1] not in target[0].wf.nodes:
            self._set_node_info_target(None)
            target = None
        if (
            target is None
            or self.accordion.selected_index != AccordionTab.NODE_INFO.index
        ):
            self.node_info.clear()
        else:
            widget, label = target
            self.node_info.show(
                widget,
                label,
                list(self.executors.created),
                self.executors.name_of(widget.wf.nodes[label].executor),
            )

    def _set_node_info_target(
        self, target: tuple[PyironFlowWidget, str] | None
    ) -> None:
        """Retarget Node Info; a pending `[Create new]` belongs to the old target."""
        if target != self._node_info_target:
            self._executor_target = None
        self._node_info_target = target

    def _on_executor_chosen(self, value: str) -> None:
        """Apply Node Info's executor choice to its node, or go and create one."""
        target = self._node_info_target
        if target is None:
            return
        if value == node_info.CREATE_NEW:
            self.node_info.revert()
            self._executor_target = target
            self.executors_panel.open_create()
            self.accordion.selected_index = AccordionTab.EXECUTORS.index
            return
        widget, label = target
        widget.wf.nodes[label].executor = (
            None
            if value == node_info.NO_EXECUTOR
            else self.executors.created[value].value
        )

    def _on_executor_created(self, created: executors.Created) -> None:
        """Give *created* to the node that asked for it, if any, and show it there."""
        target, self._executor_target = self._executor_target, None
        if target is not None and target[1] in target[0].wf.nodes:
            widget, label = target
            widget.wf.nodes[label].executor = created.value
            self.show_node_info(widget, label, last_input=False, source=False)
        else:
            self._refresh_node_info()

    def _on_executor_deleted(self, name: str) -> None:
        """Forget *name*, and clear it from every node in every tab."""
        self.executors.delete(name, self.workflows)
        self.executors_panel.refresh()
        self._refresh_node_info()

    def node_deleted(self, widget: PyironFlowWidget, label: str) -> None:
        """Forget Node Info's target if it was *widget*'s node *label*."""
        if self._node_info_target == (widget, label):
            self._set_node_info_target(None)
            self.node_info.clear()

    def node_renamed(self, widget: PyironFlowWidget, old: str, new: str) -> None:
        """Keep Node Info on *widget*'s node if it was the one renamed *old* to *new*."""
        if self._executor_target == (widget, old):
            self._executor_target = (widget, new)
        if self._node_info_target == (widget, old):
            # Assigned directly: the target is the same node, so a pending
            # `[Create new]` stays with it
            self._node_info_target = (widget, new)
            self._refresh_node_info()

    def show_node_info(
        self, widget: PyironFlowWidget, label: str, last_input: bool, source: bool
    ) -> None:
        """Focus Node Info on *widget*'s node *label*, opening Last Output.

        Last Input and Source open too where flagged; a section left unflagged stays
        as the user set it.
        """
        self._set_node_info_target((widget, label))
        self.node_info.expand(last_input=last_input, last_output=True, source=source)
        if self.accordion.selected_index == AccordionTab.NODE_INFO.index:
            self._refresh_node_info()
        else:
            self.accordion.selected_index = AccordionTab.NODE_INFO.index  # refreshes

    def view_flows(self):
        tab = widgets.Tab(
            layout={
                "width": "auto",
                "min_width": "0",
                "flex": "1 1 auto",
                "height": "100%",
            }
        )
        tab.children = [w.gui for w in self.wf_widgets]
        tab.titles = [wf.label for wf in self.workflows]
        return tab
