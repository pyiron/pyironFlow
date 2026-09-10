import importlib
import types
import typing
from typing import Annotated, get_args, get_origin

from pyiron_workflow.constructors import atomictype2node

from pyironflow.themes import get_color

try:
    from flowrep.retrospective.datastructures import NotData
except ImportError:
    from flowrep.schemas import NotData  # type: ignore[no-redef]

NODE_WIDTH = 240

PORT_ELEMENT_TYPE = "portNode"
PORT_ID_DELIMITER = "::"
PORT_WIDTH = 150
PORT_HEIGHT_PLAIN = 40
PORT_HEIGHT_WITH_ENTRY = 60
# Rough estimate of how many characters of the semi-bold ~10px label font fit
# on one line inside a PORT_WIDTH box with 5px padding on each side.
PORT_LABEL_CHARS_PER_LINE = 24
# Extra pixels of estimated height per label line beyond the first. This is a
# layout hint for elk, not a measurement of rendered text.
PORT_HEIGHT_PER_EXTRA_LABEL_LINE = 12

# Type-kind names for which no value can be typed in.
NON_ENTRY_KINDS = frozenset({"NonPrimitive", "None"})


def get_import_path(node) -> str:
    """Return a dotted import path for *node* that can be used to reconstruct it."""
    recipe = getattr(node, "recipe", None)
    if recipe is not None and hasattr(recipe, "fully_qualified_name"):
        path = recipe.fully_qualified_name
    else:
        module = (
            node.__module__
            if hasattr(node, "__module__")
            else node.__class__.__module__
        )
        name = node.__name__ if "__name__" in dir(node) else node.__class__.__name__
        path = f"{module}.{name}"

    if path == "numpy.ndarray":
        path = "numpy.array"
    return path


def dict_to_node(
    dict_node: dict, live_nodes: dict | None = None, wf=None, reload=False
):
    """Convert a dict spec of a node back to a Node object.

    When *wf* is provided, existing edges for this node are removed so that
    ``dict_to_edge`` can rebuild them. Nodes carry no values: runtime data
    enters only through the parent-most workflow's terminal input.
    """
    if live_nodes is None:
        live_nodes = {}
    data = dict_node["data"]
    label = dict_node["id"]
    node_id = data["python_object_id"]

    # Reuse existing node if it is the same object.
    if id(node := live_nodes.get(label)) != node_id:
        func = get_node_from_path(data["import_path"], reload=reload)
        if func is None:
            return None
        node = atomictype2node(func, label)

    # Disconnect all existing edges for this node so dict_to_edge can rebuild them.
    if wf is not None and node.label in wf.nodes:
        wf.disconnect(node)

    if "position" in dict_node:
        x, y = dict_node["position"].values()
        node.position = (x, y)
    else:
        print("no position: ", node.label)

    return node


def dict_to_edge(dict_edge, nodes, wf):
    """Reconnect an edge described by *dict_edge* between *nodes* in *wf*."""
    source_node = nodes[dict_edge["source"]]
    target_node = nodes[dict_edge["target"]]
    out_port = source_node.outputs[dict_edge["sourceHandle"]]
    inp_port = target_node.inputs[dict_edge["targetHandle"]]
    wf.connect(out_port, inp_port)
    return True


def is_primitive(obj):
    primitives = (bool, str, int, float, type(None))
    return isinstance(obj, primitives)


def _get_port_default(node, port_label: str):
    """Return a primitive default for *node*'s input port, or None if there is none.

    The default lives on the flowrep live node rather than on the port dataclass,
    which only records whether a default exists.
    """
    try:
        live = node.generate_flowrep_live_node()
    except Exception:
        return None
    port_data = live.input_ports.get(port_label)
    if port_data is None:
        return None
    default = port_data.default
    if isinstance(default, NotData) or not is_primitive(default):
        return None
    return default


def get_node_unfilled(node, wf=None) -> list[bool]:
    """Per input port of *node*, whether it has neither a default nor a feed."""
    fed = set()
    if wf is not None:
        for edge in wf.edges:
            if edge.target.node == node.label:
                fed.add(edge.target.port)
    return [
        (not port.has_default) and (label not in fed)
        for label, port in node.inputs.items()
    ]


def _get_generic_type(t):
    non_none_types = [arg for arg in t.__args__ if arg is not type(None)]
    hints = {float, int, str}.intersection(non_none_types)
    if int in hints and float in hints:
        return int | float
    if int in hints:
        return int
    if float in hints:
        return float
    if str in hints:
        return str
    return non_none_types[0]


def unwrap_annotated(hint: typing.Any) -> typing.Any:
    while get_origin(hint) is Annotated:
        hint = get_args(hint)[0]
    return hint


def _get_type_name(t):
    t = unwrap_annotated(t)
    primitive_types = (bool, str, int, float, typing._LiteralGenericAlias, type(None))
    if t is None:
        return "None"
    elif isinstance(t, (types.UnionType, typing._UnionGenericAlias)):
        return "int-float"
    elif t in primitive_types:
        return t.__name__
    else:
        return "NonPrimitive"


def get_node_types(port_map):
    node_io_types = []
    for k in port_map:
        type_hint = unwrap_annotated(port_map[k].type_hint)
        if isinstance(type_hint, (types.UnionType, typing._UnionGenericAlias)):
            if all(
                isinstance(arg, typing._LiteralGenericAlias)
                for arg in get_args(type_hint)
            ):
                type_hint = typing._LiteralGenericAlias
            elif all(
                not isinstance(arg, typing._LiteralGenericAlias)
                for arg in get_args(type_hint)
            ):
                if all(arg is not bool for arg in get_args(type_hint)):
                    type_hint = _get_generic_type(type_hint)
                else:
                    type_hint = object
            else:
                type_hint = object
        if isinstance(type_hint, typing._LiteralGenericAlias):
            type_hint = typing._LiteralGenericAlias

        node_io_types.append(_get_type_name(type_hint))
    return node_io_types


def get_node_literal_values(port_map):
    node_io_literal_values = []
    for k in port_map:
        type_hint = unwrap_annotated(port_map[k].type_hint)
        if isinstance(type_hint, typing._LiteralGenericAlias):
            args = list(get_args(type_hint))
        elif all(
            isinstance(arg, typing._LiteralGenericAlias) for arg in get_args(type_hint)
        ):
            args = []
            for arg in get_args(type_hint):
                for arg_1 in get_args(arg):
                    args.append(arg_1)
        else:
            args = None
        node_io_literal_values.append(args)
    return node_io_literal_values


def get_node_literal_types(port_map):
    node_io_literal_types = []
    for k in port_map:
        type_hint = unwrap_annotated(port_map[k].type_hint)
        if isinstance(type_hint, typing._LiteralGenericAlias):
            args = [type(arg).__name__ for arg in list(get_args(type_hint))]
        elif all(
            isinstance(arg, typing._LiteralGenericAlias) for arg in get_args(type_hint)
        ):
            args = []
            for arg in get_args(type_hint):
                for arg_1 in get_args(arg):
                    args.append(type(arg_1).__name__)
        else:
            args = None
        node_io_literal_types.append(args)
    return node_io_literal_types


def get_raw_target_types(port_map):
    node_input_types = []
    for k in port_map:
        type_hint = unwrap_annotated(port_map[k].type_hint)
        if isinstance(type_hint, (types.UnionType, typing._UnionGenericAlias)):
            union_types = [arg.__name__ for arg in type_hint.__args__]
            node_input_types.append(union_types)
        else:
            try:
                node_input_types.append(type_hint.__name__)
            except Exception:
                node_input_types.append("Not Explicitly Defined")
    return node_input_types


def get_raw_source_types(port_map):
    node_output_types = []
    for k in port_map:
        type_hint = unwrap_annotated(port_map[k].type_hint)
        if isinstance(type_hint, (types.UnionType, typing._UnionGenericAlias)):
            union_types = [arg.__name__ for arg in type_hint.__args__]
            node_output_types.append(union_types)
        else:
            try:
                node_output_types.append(type_hint.__name__)
            except Exception:
                node_output_types.append("Not Explicitly Defined")
    return node_output_types


def get_node_position(node):
    if hasattr(node, "position"):
        x, y = node.position
    else:
        x, y = 0, 0
    return {"x": x, "y": y}


def _get_node_step(wf, node_label: str):
    """Return the Run step for *node_label* from *wf*'s last run, if any."""
    if wf is None or wf.last_run is None:
        return None
    for step in wf.last_run.steps:
        # lexical_path is like 'wf_label.node_label'
        if (
            step.lexical_path.endswith(f".{node_label}")
            or step.lexical_path == node_label
        ):
            return step
    return None


def get_node_dict(node, wf=None, key=None):
    node_height = 40 + (16 * max(len(node.inputs), len(node.outputs)))
    label = node.label
    if (node.label != key) and (key is not None):
        label = f"{node.label}: {key}"

    step = _get_node_step(wf, node.label)
    if step is not None:
        from pyiron_workflow.execution import RunStatus

        failed = str(step.status == RunStatus.FAILED)
        running = str(step.status == RunStatus.RUNNING)
        ready = str(step.status != RunStatus.FAILED)
    else:
        failed = "False"
        running = "False"
        ready = "False"

    return {
        "id": node.label,
        "data": {
            "label": label,
            "source_labels": list(node.outputs.keys()),
            "target_labels": list(node.inputs.keys()),
            "import_path": get_import_path(node),
            "target_types": get_node_types(node.inputs),
            "target_types_raw": get_raw_target_types(node.inputs),
            "target_unfilled": get_node_unfilled(node, wf),
            "target_literal_values": get_node_literal_values(node.inputs),
            "target_literal_types": get_node_literal_types(node.inputs),
            "source_types": get_node_types(node.outputs),
            "source_types_raw": get_raw_source_types(node.outputs),
            "failed": failed,
            "running": running,
            "ready": ready,
            "cache_hit": "False",
            "python_object_id": id(node),
        },
        "position": get_node_position(node),
        "type": "customNode",
        "style": {
            "padding": 5,
            "background": get_color(node=node, theme="light"),
            "borderRadius": "10px",
            "width": f"{NODE_WIDTH}PX",
            "width_unitless": NODE_WIDTH,
            "height": f"{node_height}px",
            "height_unitless": node_height,
        },
        "targetPosition": "left",
        "sourcePosition": "right",
    }


def port_element_id(variant: str, label: str) -> str:
    """The GUI element id for a terminal port.

    The delimiter is illegal in a flowrep label, which must be a Python
    identifier, so a port element id can never collide with a node id.
    """
    return f"{variant}{PORT_ID_DELIMITER}{label}"


def parse_port_element_id(element_id: str) -> tuple[str, str]:
    """Split a port element id back into its variant and port label."""
    variant, _, label = element_id.partition(PORT_ID_DELIMITER)
    return variant, label


def is_port_element(dict_node: dict) -> bool:
    """Whether a serialized GUI node is a terminal port element."""
    return dict_node.get("type") == PORT_ELEMENT_TYPE


def get_port_hint(port) -> str:
    """A short display string for a port's type hint. Nothing parses this.

    Plain classes render as their bare name; everything else renders as its
    repr with the ``typing.`` prefix dropped. Reaching for ``__name__`` first
    would be wrong: ``Literal["a", "b"].__name__`` is ``"Literal"`` and
    ``dict[str, int].__name__`` is ``"dict"``, both of which throw away the
    part the user needs.
    """
    hint = unwrap_annotated(port.type_hint)
    if hint is None:
        return "None"
    if isinstance(hint, type) and not get_args(hint):
        return hint.__name__
    return str(hint).removeprefix("typing.")


def get_port_dict(
    port,
    variant: str,
    allow_value_entry: bool = False,
    value=None,
    position: dict | None = None,
) -> dict:
    """Serialize one terminal port of a workflow into a GUI element.

    Args:
        port: an InputPort or OutputPort belonging to the workflow itself.
        variant (str): "input" or "output".
        allow_value_entry (bool): whether to offer a value entry field. Only
            honoured on the input variant, and only for primitive hints.
        value: initial contents of the entry field.
        position (dict | None): {"x": ..., "y": ...} in GUI space.

    The element's ``style["height_unitless"]`` is only ever an estimate used
    as a layout hint by ``js/useElkLayout.jsx``; the box itself grows to fit
    its actual rendered content via ``minHeight`` in the CSS-facing style
    dict, so this need not be precise.
    """
    port_map = {port.label: port}
    entry_kind = get_node_types(port_map)[0]
    show_entry = (
        variant == "input" and allow_value_entry and entry_kind not in NON_ENTRY_KINDS
    )
    height = PORT_HEIGHT_WITH_ENTRY if show_entry else PORT_HEIGHT_PLAIN
    label_lines = -(-len(port.label) // PORT_LABEL_CHARS_PER_LINE) or 1
    height += (label_lines - 1) * PORT_HEIGHT_PER_EXTRA_LABEL_LINE
    is_input = variant == "input"

    return {
        "id": port_element_id(variant, port.label),
        "data": {
            "variant": variant,
            "label": port.label,
            "hint": get_port_hint(port),
            "entry_kind": entry_kind,
            "literal_values": get_node_literal_values(port_map)[0],
            "literal_types": get_node_literal_types(port_map)[0],
            "allow_value_entry": allow_value_entry,
            "value": value,
            "source_labels": [port.label] if is_input else [],
            "target_labels": [] if is_input else [port.label],
        },
        "position": position if position is not None else {"x": 0, "y": 0},
        "type": PORT_ELEMENT_TYPE,
        "style": {
            "padding": 5,
            "background": "#f4f4f4",
            "borderRadius": "12px",
            "width": f"{PORT_WIDTH}PX",
            "width_unitless": PORT_WIDTH,
            "minHeight": f"{height}px",
            "height_unitless": height,
        },
        "targetPosition": "left",
        "sourcePosition": "right",
    }


def get_nodes(wf):
    nodes = []
    for k, v in wf.nodes.items():
        nodes.append(get_node_dict(v, wf=wf, key=k))
    return nodes


def get_node_from_path(import_path, log=None, reload=False):
    """Import a node function/class from a dotted import path.

    Args:
        import_path (str): dotted path to the function or class
        log: widget to log errors to
        reload (bool): whether to reload the module

    Returns:
        The imported function/class, or None on error.
    """
    module_path, _, name = import_path.rpartition(".")
    try:
        module = importlib.import_module(module_path)
    except ModuleNotFoundError as e:
        if log:
            log.append_stderr(e)
        return None

    if reload:
        try:
            importlib.reload(module)
        except ImportError as e:
            if log:
                log.append_stderr(e)
            return None

    return getattr(module, name)


def get_edges(wf):
    edges = []
    ic = 0
    for edge in wf.edges:
        # Skip hidden constant-node edges
        # Skip workflow boundary edges (None node = workflow input/output port)
        if edge.source.node is None or edge.target.node is None:
            continue
        edge_dict = {
            "source": edge.source.node,
            "sourceHandle": edge.source.port,
            "target": edge.target.node,
            "targetHandle": edge.target.port,
            "id": ic,
        }
        edges.append(edge_dict)
        ic += 1
    return edges
