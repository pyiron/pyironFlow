import html
import inspect
import json
import pathlib
import sys
from contextlib import contextmanager
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any, Literal

import anywidget
import traitlets
from IPython import display as display_mod
from IPython.core import ultratb
from pygments import highlight
from pygments.formatters import TerminalFormatter
from pygments.lexers import PythonLexer
from pyiron_workflow import Workflow
from pyiron_workflow.dag import Macro
from pyiron_workflow.datatypes import Node
from pyiron_workflow.execution import Run, RunConfig

from pyironflow import datamodel
from pyironflow.wf_extensions import (
    NODE_WIDTH,
    TransientInputs,
    cached_run_kwargs,
    dict_to_edge,
    dict_to_node,
    get_edges,
    get_nodes,
    harvest_port_cache,
    missing_required_input,
    prune_uncached_input,
    transient_io,
)

if TYPE_CHECKING:
    from pyironflow.files_panel import FilesPanel
    from pyironflow.pyironflow import PyironFlow

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

_CHANNEL_CONNECTION_REGEX = r".*/[^/]+/(.*)\.\w+ = (.*); /[^/]+/(.*)\.\w+ = (.*)$"
_CHANNEL_TYPE_REGEX = r"^The channel /[^/]/([^\w]+) cannot take the value .* not compliant with the type hint (.*)$"

_PLACEMENT_CYCLE = 10  # new nodes step down, then wrap back to the top
_PLACEMENT_STEP_FRACTION = 0.09  # of the view height, per step
_PLACEMENT_STEP_WITHOUT_VIEW = 50


@contextmanager
def FormattedTB():
    sys_excepthook = sys.excepthook
    sys.excepthook = ultratb.FormattedTB(mode="Verbose", theme_name="Neutral")
    yield
    sys.excepthook = sys_excepthook


def highlight_node_source(node: Node) -> str:
    """Extract and highlight source code of a node.

    Supported node types are Atomic nodes (function-based) and Macro nodes.

    Args:
        node (pyiron_workflow.datatypes.Node): node to extract source from

    Returns:
        highlighted source code.
    """
    try:
        recipe = getattr(node, "recipe", None)
        if recipe is not None and hasattr(recipe, "fully_qualified_name"):
            fqn = recipe.fully_qualified_name
            module_path, _, name = fqn.rpartition(".")
            import importlib as _importlib

            module = _importlib.import_module(module_path)
            obj = getattr(module, name)
            code = inspect.getsource(obj)
        elif isinstance(node, Macro):
            code = inspect.getsource(type(node))
        else:
            return "Function to extract code not implemented!"
        return highlight(code, PythonLexer(), TerminalFormatter())
    except OSError as e:
        if e.args[0] == "could not find class definition":
            return "Could not locate source code."
        raise


class AccordionTab(Enum):
    NODE_LIBRARY = "Node Library"
    FILES = "Files"
    OUTPUT = "Output"
    LOGGING_INFO = "Logging Info"

    @property
    def index(self) -> int:
        return list(type(self)).index(self)


class GlobalCommand(Enum):
    """Types of commands pertaining to the full workflow."""

    RUN = "run"
    EXPORT = "export"
    IMPORT = "import"
    SAVE = "save"
    RENAME = "rename"
    CLOSE = "close"

    def handle(self, widget: "PyironFlowWidget", argument: str | None = None):
        """Execute command on widget.

        Args:
            argument: the text a command carries, such as a tab's new name.
        """
        match self:
            case GlobalCommand.RUN:
                widget.select_output_widget()
                widget.out_widget.clear_output()
                widget.run_workflow(widget.wf)
                widget.update_status()

            case GlobalCommand.EXPORT | GlobalCommand.IMPORT | GlobalCommand.SAVE:
                # The toolbar only opens the Files panel; file IO happens there
                if widget.files_panel is None:
                    widget.select_output_widget()
                    print(
                        f"{self.value.capitalize()} needs the full PyironFlow GUI, "
                        f"whose Files panel does the work."
                    )
                else:
                    widget.files_panel.open(self.value)

            case GlobalCommand.RENAME | GlobalCommand.CLOSE:
                # Tabs belong to PyironFlow, not to the widget drawn inside one
                if widget.flow is None:
                    widget.select_output_widget()
                    print(
                        f"{self.value.capitalize()} needs the full PyironFlow GUI, "
                        f"which owns the workflow tabs."
                    )
                elif self is GlobalCommand.CLOSE:
                    widget.flow.close_workflow(widget)
                else:
                    try:
                        widget.flow.rename_workflow(widget, argument or "")
                    except ValueError as err:
                        widget.select_output_widget()
                        print(f"Cannot rename: {err}")


@dataclass
class NodeCommand:
    """Specifies a command to run a node or selection of them."""

    command: Literal["source", "pull", "push", "delete_node", "reset"]
    node: str


def parse_command(com: str) -> GlobalCommand | NodeCommand:
    """Parses commands from GUI into the correct command class."""
    print("command: ", com)
    if "executed at" in com:
        return GlobalCommand(com.split(" ")[0])

    command_name, node_name = com.split(":")
    node_name = node_name.split("-")[0].strip()
    return NodeCommand(command_name, node_name)


def command_argument(com: str) -> str | None:
    """The text a global command carries after ``" as "``, such as a tab's new name."""
    _, separator, argument = com.partition(" as ")
    return argument if separator else None


class ReactFlowWidget(anywidget.AnyWidget):
    path = pathlib.Path(__file__).parent / "static"
    _esm = path / "widget.js"
    _css = path / "widget.css"
    nodes = traitlets.Unicode("[]").tag(sync=True)
    edges = traitlets.Unicode("[]").tag(sync=True)
    selected_nodes = traitlets.Unicode("[]").tag(sync=True)
    selected_edges = traitlets.Unicode("[]").tag(sync=True)
    commands = traitlets.Unicode("[]").tag(sync=True)
    # position and size of the current view on the graph in JS space
    view = traitlets.Unicode("{}").tag(sync=True)
    # whether the Python side holds a run the user can save
    has_run = traitlets.Bool(False).tag(sync=True)
    # the workflow's label, offered as the default when renaming
    label = traitlets.Unicode("").tag(sync=True)


@contextmanager
def GentleError(out, log):
    """Catch various exception from workflows and try to print nicer messages.

    Args:
        out: widget for "normal" output immediately visible to user
        log: widget for "logging" output only visible after a click
    """
    try:
        try:
            yield
        except Exception as err:
            with out:
                print(f"Error: {err}")
            with log:
                sys.excepthook(*sys.exc_info())
    except Exception as e:
        print("Error:", e)
        with log:
            sys.excepthook(*sys.exc_info())
    finally:
        pass


class PyironFlowWidget:
    def __init__(
        self,
        wf: Workflow,
        log=None,
        out_widget=None,
        reload_node_library=False,
    ):
        self.log = log
        self.out_widget = out_widget
        self.accordion_widget = None
        self.tree_widget = None
        self.files_panel: FilesPanel | None = None
        self.flow: PyironFlow | None = None
        self.gui = ReactFlowWidget(layout={"height": "100%"})
        self.wf = wf
        self.gui.label = wf.label
        self.reload_node_library = reload_node_library

        self.gui.observe(self.on_value_change, names="commands")

        self._port_cache: datamodel.PortCache = {}
        self._placement_count = 0
        self.last_run: Run[Any] | None = None

        self.update()

    def select_output_widget(self):
        """Makes sure output widget is visible if accordion is set."""
        if self.accordion_widget is not None:
            self.accordion_widget.selected_index = AccordionTab.OUTPUT.index

    @property
    def port_cache(self) -> datamodel.PortCache:
        """Values typed into the GUI, keyed by `wf_extensions.port_cache_key`."""
        return self._port_cache

    @staticmethod
    def _display_dict(to_display: dict[str, Any]) -> None:
        for k, v in to_display.items():
            header = f"{k}:"
            display_mod.display(
                display_mod.HTML(
                    f"<h3 style='margin-bottom:0.2em'>{html.escape(header)}</h3>"
                )
            )
            display_mod.display(v)

    def run_workflow(self, workflow: Workflow):
        """Run *workflow* with the values typed in the GUI, then restore its IO.

        The workflow the user holds carries no terminal ports of its own. They exist
        only for the length of the run, inside `transient_io`, which is what lets the
        same object be handed back to `PyironFlow` afterwards.

        The missing-input check comes first: under `TransientInputs.USED` a port with
        no default and no typed value would otherwise get a terminal port that
        nothing feeds, and the user would read a validation error instead of a list.
        """
        with FormattedTB(), GentleError(self.out_widget, self.log):
            missing = missing_required_input(workflow, self._port_cache)
            if missing:
                self._print_missing(missing)
                return
            with transient_io(workflow, self._port_cache, TransientInputs.USED):
                run = self._run_and_cache(
                    workflow, **cached_run_kwargs(workflow, self._port_cache)
                )
                self._display_dict(run.outputs)

    def pull_workflow(self, node):
        """Run the dependency cone of *node* with the values typed in the GUI.

        The cone is a throwaway workflow, so nothing needs restoring. It is built with
        defaults exposed, because otherwise a value typed into a defaulted port is
        discarded, and then pruned back so untouched defaults apply again. The run is
        kept as `last_run`, like a full run's.
        """
        with FormattedTB(), GentleError(self.out_widget, self.log):
            pulled = node.pulled_workflow(True, True)
            prune_uncached_input(pulled, self._port_cache)
            missing = missing_required_input(pulled, self._port_cache)
            if missing:
                self._print_missing(missing)
                return
            run = self._run_and_cache(
                pulled, **cached_run_kwargs(pulled, self._port_cache)
            )
            self._display_dict(run.outputs)

    def _run_and_cache(self, workflow: Workflow, **input_data: Any) -> Run[Any]:
        """Run *workflow* and keep the resulting `Run` as `last_run`, even on failure.

        `Node.run` only records a run that returns, and a failed one is otherwise
        lost to the raise. `pyiron_workflow` hands the failed `Run` of the node
        being run to the config's exception hooks, so a hook catches it. A failure
        before any `Run` exists leaves the previous `last_run` in place.
        """
        failed: list[Run[Any]] = []

        def remember(
            _run_dir: pathlib.Path, run: Run[Any], _error: BaseException
        ) -> None:
            failed.append(run)

        try:
            run = workflow.run(RunConfig(exception_hooks=[remember]), **input_data)
        except BaseException:
            if failed:
                self.last_run = failed[-1]
            raise
        else:
            self.last_run = run
            return run
        finally:
            self.gui.has_run = self.last_run is not None
            if self.files_panel is not None:
                self.files_panel.refresh()

    @staticmethod
    def _print_missing(missing: list[tuple[str, str]]):
        print("Cannot run: no value for")
        for node_label, port_label in missing:
            print(f"  {node_label}.{port_label}")
        print("Type a value into the node's input field, or connect an edge to it.")

    def on_value_change(self, change):

        self.out_widget.clear_output()

        error_message = ""

        with FormattedTB(), GentleError(self.out_widget, self.log):
            try:
                self.wf = self.get_workflow()
            except Exception as error:
                error_message = error
                raise

        import warnings

        with self.out_widget, warnings.catch_warnings(action="ignore"):
            match parse_command(change["new"]):
                case GlobalCommand() as global_command:
                    global_command.handle(self, command_argument(change["new"]))

                case NodeCommand(command, node_name):
                    if node_name not in self.wf.nodes:
                        return
                    node = self.wf.nodes[node_name]
                    self.select_output_widget()
                    match command:
                        case "reset":
                            self.wf = self.get_workflow()
                            self.update_status()
                        case "source":
                            print(highlight_node_source(node))
                        case "pull":
                            if error_message:
                                print(f"Could not pull on node {node_name}!")
                            else:
                                self.pull_workflow(node)
                            self.update_status()
                        case "push":
                            if error_message:
                                print(f"Could not push from node {node_name}!")
                            else:
                                print(
                                    "Push is not supported in this version of pyiron_workflow."
                                )
                            self.update_status()
                        case "output":
                            if error_message:
                                print(f"Could fetch outputs from node {node_name}!")
                            else:
                                from IPython.display import display

                                for out_label in node.outputs:
                                    print(out_label + ":")
                                    # get value from last run
                                    val = None
                                    if self.wf.last_run is not None:
                                        node_data = self.wf.last_run.result.nodes.get(
                                            node_name
                                        )
                                        if node_data is not None:
                                            out_port_data = node_data.output_ports.get(
                                                out_label
                                            )
                                            if out_port_data is not None:
                                                val = out_port_data.value
                                    display(val)
                                    print()
                            self.update_status()
                        case "delete_node":
                            self.wf.remove_node(node_name)
                        case command:
                            print(f"ERROR: unknown command: {command}!")
                case unknown:
                    print(f"Command not yet implemented: {unknown}")

    def update(self):
        nodes = get_nodes(self.wf, port_cache=self._port_cache)
        edges = get_edges(self.wf)
        self.gui.nodes = json.dumps(nodes)
        self.gui.edges = json.dumps(edges)

    def update_status(self):
        self.wf = self.get_workflow()
        self.update()

    def place_new_node(self):
        """Find a suitable location in UI space for the newly added node.

        Exact layouting not required as this can be done in UI, but newly added
        nodes should be visible to the user and not completely overlap. Successive
        nodes step down by a small fraction of the view height and wrap back to the
        top every ``_PLACEMENT_CYCLE`` placements.

        FIXME: Probably this is better handled completely in UI by elk.
        """
        view = json.loads(self.gui.view)
        step = self._placement_count % _PLACEMENT_CYCLE
        self._placement_count += 1
        if view == {}:
            position = [0, step * _PLACEMENT_STEP_WITHOUT_VIEW]
        else:
            position = [
                -view["x"] + 0.1 * view["height"],
                -view["y"] + step * _PLACEMENT_STEP_FRACTION * view["height"],
            ]

        def blocked():
            for node in self.wf.nodes.values():
                if hasattr(node, "position") and node.position == tuple(position):
                    return True
            return False

        while blocked():
            position[0] += NODE_WIDTH + 10

        return tuple(position)

    def node_labels(self) -> set[str]:
        """Labels a new node must avoid: those drawn in the GUI and in the workflow.

        Syncs the workflow from the GUI first, so the answer reflects what the user
        currently sees.
        """
        self.wf = self.get_workflow()
        return set(self.wf.nodes) | {
            dict_node["id"] for dict_node in json.loads(self.gui.nodes)
        }

    def add_node(self, node: Node) -> None:
        """Place an already-built, uniquely labelled *node* in the view and graph."""
        node.position = self.place_new_node()
        if self.log is not None:
            self.log.append_stdout(f"add_node (reactflow): {node.label} \n")
        self.wf.add_node(node)
        self.update()

    def get_workflow(self):
        wf = self.wf
        dict_nodes = json.loads(self.gui.nodes)
        harvest_port_cache(dict_nodes, self._port_cache)
        for dict_node in dict_nodes:
            node = dict_to_node(
                dict_node, dict(wf.nodes), wf=wf, reload=self.reload_node_library
            )
            if node is None:
                continue
            if node not in wf.nodes.values():
                # New node appeared in GUI with the same name but different id –
                # user removed and added something in place.
                if node.label in wf.nodes:
                    wf.remove_node(node.label)
                wf.add_node(node)

        dict_edges = json.loads(self.gui.edges)
        for dict_edge in dict_edges:
            dict_to_edge(dict_edge, dict(wf.nodes), wf)

        return wf

    def get_selected_workflow(self):
        wf = Workflow("temp_workflow")
        dict_nodes = json.loads(self.gui.selected_nodes)
        node_labels = []
        for dict_node in dict_nodes:
            node = dict_to_node(dict_node, {}, wf=wf)
            if node is None:
                continue
            wf.add_node(node)
            node_labels.append(dict_node["data"]["label"])
        print("\nSelected nodes:")
        print(node_labels)

        dict_edges = json.loads(self.gui.selected_edges)
        subset_dict_edges = []
        edge_labels = []
        for edge in dict_edges:
            if edge["source"] in node_labels and edge["target"] in node_labels:
                subset_dict_edges.append(edge)
                edge_labels.append(edge["id"])
        print("\nSelected edges:")
        print(edge_labels)

        for dict_edge in subset_dict_edges:
            dict_to_edge(dict_edge, dict(wf.nodes), wf)

        return wf
