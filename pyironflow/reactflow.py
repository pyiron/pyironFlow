import inspect
import json
import pathlib
import sys
from contextlib import contextmanager
from dataclasses import dataclass
from enum import Enum
from typing import Literal

import anywidget
import traitlets
from IPython.core import ultratb
from pygments import highlight
from pygments.formatters import TerminalFormatter
from pygments.lexers import PythonLexer
from pyiron_workflow import Workflow
from pyiron_workflow.constructors import atomictype2node
from pyiron_workflow.dag import Macro
from pyiron_workflow.datatypes import Node

from pyironflow import wf_extensions
from pyironflow.wf_extensions import (
    NODE_WIDTH,
    PORT_ID_DELIMITER,
    dict_to_edge,
    dict_to_node,
    get_edges,
    get_node_from_path,
    get_nodes,
    is_port_element,
    rebuild_terminal_ports,
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

_CHANNEL_CONNECTION_REGEX = r".*/[^/]+/(.*)\.\w+ = (.*); /[^/]+/(.*)\.\w+ = (.*)$"
_CHANNEL_TYPE_REGEX = r"^The channel /[^/]/([^\w]+) cannot take the value .* not compliant with the type hint (.*)$"


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
    OUTPUT = "Output"
    LOGGING_INFO = "Logging Info"

    @property
    def index(self) -> int:
        return list(type(self)).index(self)


class GlobalCommand(Enum):
    """Types of commands pertaining to the full workflow."""

    RUN = "run"
    SAVE = "save"
    LOAD = "load"
    DELETE = "delete"
    EXPOSE_IO = "expose_io"

    def handle(self, widget: "PyironFlowWidget"):
        """Execute command on widget."""
        match self:
            case GlobalCommand.RUN:
                widget.select_output_widget()
                widget.out_widget.clear_output()
                widget.run_and_display_outputs(widget.wf)
                widget.update_status()

            case GlobalCommand.SAVE:
                widget.select_output_widget()
                print("Save/load is not supported in this version of pyiron_workflow.")

            case GlobalCommand.LOAD:
                widget.select_output_widget()
                print("Save/load is not supported in this version of pyiron_workflow.")

            case GlobalCommand.DELETE:
                widget.select_output_widget()
                print(
                    "Storage deletion is not supported in this version of pyiron_workflow."
                )

            case GlobalCommand.EXPOSE_IO:
                widget.select_output_widget()
                widget.out_widget.clear_output()
                widget.wf.set_io_to_unconnected_child_io(
                    remove_existing=True, build_for_defaults=True
                )
                print(
                    f"Exposed {len(widget.wf.inputs)} input and "
                    f"{len(widget.wf.outputs)} output port(s)."
                )
                widget.update()


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

    command_name, node_name = com.split(":", 1)
    node_name = node_name.split("-")[0].strip()
    return NodeCommand(command_name, node_name)


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
        self.gui = ReactFlowWidget(layout={"height": "100%"})
        self.wf = wf
        self.reload_node_library = reload_node_library
        self._port_cache: dict = {}

        self.gui.observe(self.on_value_change, names="commands")

        self.update()

    def select_output_widget(self):
        """Makes sure output widget is visible if accordion is set."""
        if self.accordion_widget is not None:
            self.accordion_widget.selected_index = AccordionTab.OUTPUT.index

    def run_and_display_outputs(self, workflow: Workflow):
        from IPython.display import display

        with FormattedTB(), GentleError(self.out_widget, self.log):
            run = workflow.run(
                **{
                    k: self._port_cache.get(
                        f"input{wf_extensions.PORT_ID_DELIMITER}{k}"
                    ).get("value")
                    for k in workflow.inputs
                }
            )
            display(run.outputs)

    def on_value_change(self, change):

        self.out_widget.clear_output()

        error_message = ""

        with FormattedTB(), GentleError(self.out_widget, self.log):
            try:
                self.wf = self.get_workflow()
            except Exception as error:
                error_message = error
                raise

        if "done" in change["new"]:
            return

        import warnings

        with self.out_widget, warnings.catch_warnings(action="ignore"):
            match parse_command(change["new"]):
                case GlobalCommand() as global_command:
                    global_command.handle(self)

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
                                self.run_and_display_outputs(
                                    node.pulled_workflow(True, True)
                                )
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
        nodes should be visible to the user and not completely overlap.

        FIXME: Probably this is better handled completely in UI by elk.
        """
        view = json.loads(self.gui.view)
        if view == {}:
            position = [0, 0]
        else:
            position = [
                -view["x"] + 0.1 * view["height"],
                -view["y"] + 0.9 * view["height"],
            ]

        def blocked():
            for node in self.wf.nodes.values():
                if hasattr(node, "position") and node.position == tuple(position):
                    return True
            return False

        while blocked():
            position[0] += NODE_WIDTH + 10

        return tuple(position)

    def add_node(self, node_path, label):
        self.wf = self.get_workflow()
        func = get_node_from_path(node_path, log=self.log)
        if func is None:
            return
        node = atomictype2node(func, label)
        node.position = self.place_new_node()
        self.log.append_stdout(f"add_node (reactflow): {node}, {label} \n")
        self.wf.add_node(node)
        self.update()

    def _harvest_port_cache(self, port_dicts):
        """Record entered values and positions before anything is torn down."""
        for dict_port in port_dicts:
            data = dict_port.get("data", {})
            self._port_cache[dict_port["id"]] = {
                "value": data.get("value"),
                "position": dict_port.get("position", {"x": 0, "y": 0}),
            }

    def get_workflow(self):
        wf = self.wf
        dict_nodes = json.loads(self.gui.nodes)
        port_dicts = [d for d in dict_nodes if is_port_element(d)]
        child_dicts = [d for d in dict_nodes if not is_port_element(d)]

        # Harvest before the rebuild below discards the elements.
        self._harvest_port_cache(port_dicts)

        for dict_node in child_dicts:
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

        # Remember hints before the terminal IO is dropped below, so an unwired
        # port that already carried a hint doesn't lose it across the round-trip.
        port_hints = {
            ("input", label): (port.type_hint, port.type_metadata)
            for label, port in wf.inputs.items()
        }
        port_hints.update(
            {
                ("output", label): (port.type_hint, port.type_metadata)
                for label, port in wf.outputs.items()
            }
        )

        # The GUI owns terminal IO, so drop it and rebuild from the elements.
        wf.remove_input(*list(wf.inputs.values()))
        wf.remove_output(*list(wf.outputs.values()))

        dict_edges = json.loads(self.gui.edges)
        for dict_edge in dict_edges:
            # Test the id's shape, not whether a matching port element happens to
            # still be present in gui.nodes: the two traitlets can go momentarily
            # out of sync, and a stray edge naming a missing port element must
            # still be skipped here rather than reaching dict_to_edge.
            if (
                PORT_ID_DELIMITER in dict_edge["source"]
                or PORT_ID_DELIMITER in dict_edge["target"]
            ):
                continue
            dict_to_edge(dict_edge, dict(wf.nodes), wf)

        rebuild_terminal_ports(
            wf, port_dicts, dict_edges, log=self.log, port_hints=port_hints
        )

        return wf

    def get_selected_workflow(self):
        wf = Workflow("temp_workflow")
        dict_nodes = [
            d for d in json.loads(self.gui.selected_nodes) if not is_port_element(d)
        ]
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
