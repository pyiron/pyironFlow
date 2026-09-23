import html
import inspect
import json
import pathlib
import sys
import traceback
import warnings
from contextlib import contextmanager
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any

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

from pyironflow import datamodel, entry
from pyironflow.wf_extensions import (
    NO_DEFAULT,
    NODE_WIDTH,
    TransientInputs,
    _port_default_value,
    cached_run_kwargs,
    dict_to_edge,
    dict_to_node,
    extract_locks,
    get_edges,
    get_node_locked,
    get_node_step,
    get_nodes,
    invalid_entries,
    is_constant,
    missing_required_input,
    port_cache_key,
    prune_uncached_input,
    rebuild_constants,
    transient_io,
)

if TYPE_CHECKING:
    from pyironflow.files_panel import FilesPanel
    from pyironflow.pyironflow import PyironFlow
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
                widget.run_workflow(widget.wf)
                widget.update_status()

            case GlobalCommand.EXPORT | GlobalCommand.IMPORT | GlobalCommand.SAVE:
                # The toolbar only opens the Files panel; file IO happens there
                if widget.files_panel is None:
                    widget.select_output_widget()
                    widget.out_widget.append_stdout(
                        f"{self.value.capitalize()} needs the full PyironFlow GUI, "
                        f"whose Files panel does the work.\n"
                    )
                else:
                    widget.files_panel.open(self.value)

            case GlobalCommand.RENAME | GlobalCommand.CLOSE:
                # Tabs belong to PyironFlow, not to the widget drawn inside one
                if widget.flow is None:
                    widget.select_output_widget()
                    widget.out_widget.append_stdout(
                        f"{self.value.capitalize()} needs the full PyironFlow GUI, "
                        f"which owns the workflow tabs.\n"
                    )
                elif self is GlobalCommand.CLOSE:
                    widget.flow.close_workflow(widget)
                else:
                    try:
                        widget.flow.rename_workflow(widget, argument or "")
                    except ValueError as err:
                        widget.select_output_widget()
                        widget.out_widget.append_stdout(f"Cannot rename: {err}\n")


@dataclass
class NodeCommand:
    """Specifies a command to run a node or selection of them."""

    command: str
    node: str


def parse_command(com: str) -> GlobalCommand | NodeCommand:
    """Parses commands from GUI into the correct command class."""
    if "executed at" in com:
        return GlobalCommand(com.split(" ")[0])

    command_name, node_name = com.split(":")
    node_name = node_name.split("-")[0].strip()
    return NodeCommand(command_name, node_name)


def command_argument(com: str) -> str | None:
    """The text a global command carries after ``" as "``, such as a tab's new name."""
    _, separator, argument = com.partition(" as ")
    return argument if separator else None


def _fed_by_a_live_node(wf, node: str, port: str) -> bool:
    """Whether *node*'s *port* is fed by an edge from something other than a constant.

    `wf_extensions.fed_input_ports` counts a constant's edge as "fed" too, which is
    right for deciding whether a run needs a value but wrong here: `lock_port` and
    `unlock_port` never touch `wf`, so the constant feeding this very port may be
    stale -- freshly orphaned by an `unlock_port` that has not yet been reconciled by
    `get_workflow` -- and such a stale edge must not block a fresh lock.
    """
    return any(
        edge.target.node == node
        and edge.target.port == port
        and edge.source.node is not None
        and not is_constant(wf.nodes.get(edge.source.node))
        for edge in wf.edges
    )


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
def GentleError(out, log, clear: bool = True):
    """Catch various exception from workflows and try to print nicer messages.

    Args:
        out: widget for "normal" output immediately visible to user
        log: widget for "logging" output only visible after a click
        clear: whether to clear all outputs
    """
    if clear:
        out.outputs = ()
    try:
        yield out
    except Exception as err:
        out.append_stdout(f"Error: {err}\n")
        log.append_stdout(traceback.format_exc() + "\n")


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
        self.tree_widget: TreeView | None = None
        self.files_panel: FilesPanel | None = None
        self.flow: PyironFlow | None = None
        self.gui = ReactFlowWidget(layout={"height": "100%"})
        self.wf = wf
        self.gui.label = wf.label
        self.reload_node_library = reload_node_library

        self.gui.observe(self.on_value_change, names="commands")
        self.gui.on_msg(self._on_custom_msg)

        self._port_cache: datamodel.PortCache = {}
        self._invalid_entries: dict[str, datamodel.InvalidEntry] = {}
        self._locked: datamodel.LockedPorts = extract_locks(wf)
        rebuild_constants(wf, self._locked)
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

    @property
    def locked(self) -> datamodel.LockedPorts:
        """Values frozen into constant nodes, keyed by `wf_extensions.port_cache_key`."""
        return self._locked

    def _on_custom_msg(self, _widget, content, _buffers) -> None:
        """Route a custom message from the browser. Unknown types are ignored."""
        if not isinstance(content, dict):
            return
        match content.get("type"):
            case "entry":
                self.commit_entry(content["node"], content["port"], content["text"])
            case "lock":
                self.lock_port(content["node"], content["port"])
            case "unlock":
                self.unlock_port(content["node"], content["port"])

    def commit_entry(self, node: str, port: str, text: str) -> dict:
        """Record what the user typed into *node*'s *port*, and reply to the browser.

        Blank text clears the port, which is how a defaulted port goes back to using
        its default: `create_transient_input` builds a terminal port only for a cached
        entry, so popping the key is the whole mechanism.

        A rejected entry pops the cached value too. Leaving the old value in place
        would run the workflow on something the field no longer shows, so instead the
        entry is remembered as invalid and the pre-flight check refuses to run.
        """
        reply = {
            "type": "entry",
            "node": node,
            "port": port,
            "text": None,
            "error": None,
            "cleared": False,
        }
        key = port_cache_key(node, port)
        child = self.wf.nodes.get(node)
        if child is None or port not in child.inputs:
            reply["error"] = f"No such port: {node}.{port}"
            self.gui.send(reply)
            return reply

        if key in self._locked:
            reply["error"] = f"{node}.{port} is locked."
            self.gui.send(reply)
            return reply

        if not text.strip():
            self._port_cache.pop(key, None)
            self._invalid_entries.pop(key, None)
            reply["cleared"] = True
            self.gui.send(reply)
            return reply

        hint = child.inputs[port].type_hint
        try:
            value = entry.parse(text, hint)
        except entry.EntryError as err:
            self._port_cache.pop(key, None)
            self._invalid_entries[key] = datamodel.InvalidEntry(text, str(err))
            reply["error"] = str(err)
            # Echoed back so the field can keep showing the rejected text, which
            # Python is now the only holder of, and so a redraw does not lose it.
            reply["text"] = text
        else:
            self._port_cache[key] = value
            self._invalid_entries.pop(key, None)
            reply["text"] = entry.render(value, hint)
        self.gui.send(reply)
        return reply

    def lock_port(self, node: str, port: str) -> dict:
        """Freeze what *node*'s *port* currently shows into a constant node.

        The value is whatever the field would use if the workflow ran right now: the
        entry the user committed, or failing that the port's own default. Locking moves
        it out of the port cache, because from here on it reaches the port through a
        constant in the graph rather than as run-time input.

        `wf` is deliberately untouched. `get_workflow` rebuilds the constants from this
        state, and everything that reads the graph syncs through it first.
        """
        reply: dict[str, Any] = {
            "type": "lock",
            "node": node,
            "port": port,
            "error": None,
            "locked": None,
        }
        child = self.wf.nodes.get(node)
        if child is None or port not in child.inputs:
            reply["error"] = f"No such port: {node}.{port}"
            self.gui.send(reply)
            return reply

        key = port_cache_key(node, port)
        if key in self._locked:
            reply["error"] = f"{node}.{port} is already locked."
        elif key in self._invalid_entries:
            reply["error"] = "Fix or clear the entry before locking it."
        elif _fed_by_a_live_node(self.wf, node, port):
            reply["error"] = f"{node}.{port} is fed by an edge."
        else:
            value = self._port_cache.get(key, NO_DEFAULT)
            if value is NO_DEFAULT:
                value = _port_default_value(child, port)
            if value is NO_DEFAULT:
                reply["error"] = f"{node}.{port} has no value to lock."
            else:
                self._port_cache.pop(key, None)
                self._locked[key] = value
                reply["locked"] = get_node_locked(child, self._locked)[port]

        self.gui.send(reply)
        return reply

    def unlock_port(self, node: str, port: str) -> dict:
        """Release *node*'s *port*, deleting the constant that feeds it.

        Where the port has an entry field, the value lands in the port cache, so the
        field stays populated and editable and the run computes exactly what it did
        before -- the value simply travels as run-time input instead of as a node.

        Where it has no entry field there is nowhere to release the value to, so it is
        discarded. That is what the browser's trashcan icon is warning about, and it is
        the only way to free such a port for a different edge.
        """
        reply: dict[str, Any] = {
            "type": "unlock",
            "node": node,
            "port": port,
            "error": None,
            "text": None,
        }
        child = self.wf.nodes.get(node)
        if child is None or port not in child.inputs:
            reply["error"] = f"No such port: {node}.{port}"
            self.gui.send(reply)
            return reply

        key = port_cache_key(node, port)
        if key not in self._locked:
            reply["error"] = f"{node}.{port} is not locked."
            self.gui.send(reply)
            return reply

        value = self._locked.pop(key)
        hint = child.inputs[port].type_hint
        if entry.entry_kind(hint) is not entry.EntryKind.NONE:
            self._port_cache[key] = value
            reply["text"] = entry.render(value, hint)

        self.gui.send(reply)
        return reply

    def _display_dict(self, to_display: dict[str, Any]) -> None:
        for k, v in to_display.items():
            header = f"{k}:"
            self.out_widget.append_display_data(
                display_mod.HTML(
                    f"<h3 style='margin-bottom:0.2em'>{html.escape(header)}</h3>"
                )
            )
            self.out_widget.append_display_data(v)

    def _display_last_output(self, node_name: str) -> None:
        """Show what the most recent run produced for *node_name*.

        The source is `last_run`, the widget's own record of the last run *or* pull.
        The workflow's `wf.last_run` is no use here: `pull_workflow` runs a throwaway
        cone, so a pull never writes it and every port would read back as `None`.

        A node absent from that run gets a note instead of values, because a bare
        `None` could equally mean the node ran and returned `None`.
        """
        if self.last_run is None:
            self.out_widget.append_stdout(f"{node_name} has not been run yet.\n")
            return
        step = get_node_step(self.last_run, node_name)
        if step is None:
            self.out_widget.append_stdout(
                f"{node_name} was not part of the last run.\n"
            )
            return
        self._display_dict(dict(step.outputs))

    def run_workflow(self, workflow: Workflow):
        """Run *workflow* with the values typed in the GUI, then restore its IO.

        The workflow the user holds carries no terminal ports of its own. They exist
        only for the length of the run, inside `transient_io`, which is what lets the
        same object be handed back to `PyironFlow` afterwards.

        The missing-input check comes first: under `TransientInputs.USED` a port with
        no default and no typed value would otherwise get a terminal port that
        nothing feeds, and the user would read a validation error instead of a list.
        """
        with transient_io(workflow, self._port_cache, TransientInputs.USED):
            self._run_and_display_workflow(workflow)

    def pull_workflow(self, node):
        """Run the dependency cone of *node* with the values typed in the GUI.

        The cone is a throwaway workflow, so nothing needs restoring. It is built with
        defaults exposed, because otherwise a value typed into a defaulted port is
        discarded, and then pruned back so untouched defaults apply again. The run is
        kept as `last_run`, like a full run's.
        """
        pulled = node.pulled_workflow(True, True)
        prune_uncached_input(pulled, self._port_cache)
        self._run_and_display_workflow(pulled)

    def _run_and_display_workflow(self, wf: Workflow):
        if input_failure_msg := self._validate_current_input_for(wf):
            self.out_widget.append_stdout(input_failure_msg)
            return
        run = self._run_and_cache(wf, **cached_run_kwargs(wf, self._port_cache))
        self._display_dict(run.outputs)

    def _validate_current_input_for(self, wf: Workflow) -> str | None:
        missing = missing_required_input(wf, self._port_cache)
        bad = invalid_entries(wf, self._port_cache, self._invalid_entries)
        if missing or bad:
            msg = "Cannot run:"
            if missing:
                msg += "\n  No value(s) for:"
                for node_label, port_label in missing:
                    msg += f"\n    {node_label}.{port_label}"
                msg += "\n  Type a value into the node's input field, or connect an edge to it."
            if bad:
                msg += "\n  Invalid value(s) for:"
                for node_label, port_label, message in bad:
                    msg += f"\n    {node_label}.{port_label}: {message}"
                msg += "\n  Fix or clear the field, then run again."
            msg += "\n"
            return msg
        return None

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

    def on_value_change(self, change):
        with (
            FormattedTB(),
            GentleError(self.out_widget, self.log),
            warnings.catch_warnings(action="ignore"),
        ):
            self.out_widget.append_stdout(f"command: {change['new']}\n")
            self.wf = self.get_workflow()

            match parse_command(change["new"]):
                case GlobalCommand() as global_command:
                    global_command.handle(self, command_argument(change["new"]))

                case NodeCommand(command, node_name):
                    if node_name not in self.wf.nodes:
                        return
                    node = self.wf.nodes[node_name]
                    self.select_output_widget()
                    match command:
                        case "source":
                            self.out_widget.append_stdout(highlight_node_source(node))
                        case "pull":
                            self.pull_workflow(node)
                            self.update_status()
                        case "output":
                            self._display_last_output(node_name)
                            self.update_status()
                        case "delete_node":
                            self.wf.remove_node(node_name)
                        case command:
                            self.out_widget.append_stdout(
                                f"ERROR: unknown command: {command}!\n"
                            )
                case unknown:
                    self.out_widget.append_stdout(
                        f"Command not yet implemented: {unknown}\n"
                    )

    def update(self):
        nodes = get_nodes(
            self.wf,
            port_cache=self._port_cache,
            invalid=self._invalid_entries,
            locked=self._locked,
        )
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
        """Sync `wf` from what the browser currently shows, then rebuild constants.

        Constants are rebuilt here rather than kept as-is because `dict_to_node`
        disconnects every node the GUI knows about, which would strip a hidden
        constant's edge on every sync; rebuilding from `self._locked` afterwards is
        what makes the locked-port mapping enforced rather than merely maintained.
        """
        wf = self.wf
        dict_nodes = json.loads(self.gui.nodes)
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

        rebuild_constants(wf, self._locked)
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
