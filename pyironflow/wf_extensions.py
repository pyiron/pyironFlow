import importlib
import math
import types
import typing
from typing import Annotated, get_args, get_origin

from pyiron_workflow.constructors import atomictype2node
from pyiron_workflow.type_hinting import valid_value

from pyironflow import datamodel
from pyironflow.themes import get_color

try:
    from flowrep.retrospective.datastructures import NotData
except ImportError:
    from flowrep.schemas import NotData  # type: ignore[no-redef]

NODE_WIDTH = 240


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


def port_cache_key(node_label: str, port_label: str) -> str:
    """Key under which a value typed on ``node_label``'s ``port_label`` is cached.

    This is the same label `pyiron_workflow` gives a terminal input port built for that
    child port, both in ``set_inputs_to_unconnected_child_input`` and in the keys
    ``pull.pulled_workflow`` asks for, so one cache serves the GUI, a run and a pull.
    """
    return f"{node_label}__{port_label}"


def harvest_port_cache(dict_nodes: list[dict], cache: datamodel.PortCache) -> None:
    """Record values typed in the GUI into *cache*, in place.

    ``data["target_values"]`` carries one key per port the user entered something into,
    so a port of the node missing from it has been cleared and its cache key is dropped.
    Absence is the only marker for "nothing entered", which is what lets a stored
    ``None`` mean the value the user typed rather than an empty field.

    Keys for nodes absent from *dict_nodes* are left alone, so a node deleted and
    re-added under the same label keeps what the user typed.
    """
    for dict_node in dict_nodes:
        data = dict_node.get("data", {})
        entered = data.get("target_values")
        if entered is None:
            continue
        for label in data["target_labels"]:
            key = port_cache_key(dict_node["id"], label)
            if label in entered:
                cache[key] = entered[label]
            else:
                cache.pop(key, None)


def fed_input_ports(wf) -> set[tuple[str, str]]:
    """``(node, port)`` for every child input port fed by an edge from another node.

    Edges out of the workflow's own input are excluded on purpose. On the workflow the
    GUI holds they exist only inside a run, and on a pulled workflow they mark exactly
    the ports whose values still have to be supplied.
    """
    return {
        (edge.target.node, edge.target.port)
        for edge in wf.edges
        if edge.source.node is not None and edge.target.node is not None
    }


def dict_to_node(
    dict_node: dict, live_nodes: dict | None = None, wf=None, reload=False
):
    """Convert a dict spec of a node back to a Node object.

    When *wf* is provided, existing edges are disconnected so that ``dict_to_edge``
    can rebuild them. Values no longer travel on the node; they are cached
    separately and applied to a terminal port only for the duration of a run.
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


def _get_port_default(node, port_label: str):
    """The default of *node*'s input port if it can be shown in a field, else None.

    The value lives on the flowrep live node; the port dataclass only records whether a
    default exists at all. A non-finite float is dropped because JSON cannot carry it.
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
    if isinstance(default, float) and not math.isfinite(default):
        return None
    return default


def get_node_defaults(node) -> list:
    """Per input port, the default to show in a dimmed field, or None."""
    return [_get_port_default(node, label) for label in node.inputs]


def get_node_has_defaults(node) -> list[bool]:
    """Per input port, whether it has a default at all, primitive or not.

    This is what drives the unfed marker. ``get_node_defaults`` cannot: a port whose
    default is not a primitive has one, but has nothing to display.
    """
    return [port.has_default for port in node.inputs.values()]


def get_node_cached_values(node, cache: datamodel.PortCache) -> dict:
    """The values the user typed into *node*'s input ports, keyed by port label.

    Only ports carrying an entry appear. A port the user left alone is absent rather
    than present-and-null, so the browser can tell the two apart and a typed ``None``
    survives the round trip.
    """
    values = {}
    for label in node.inputs:
        key = port_cache_key(node.label, label)
        if key in cache:
            values[label] = cache[key]
    return values


def get_node_dict(
    node, wf=None, key=None, port_cache: datamodel.PortCache | None = None
):
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
            "target_values": get_node_cached_values(
                node, {} if port_cache is None else port_cache
            ),
            "target_defaults": get_node_defaults(node),
            "target_has_default": get_node_has_defaults(node),
            "target_types": get_node_types(node.inputs),
            "target_types_raw": get_raw_target_types(node.inputs),
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


def get_nodes(wf, port_cache: datamodel.PortCache | None = None):
    """Serialize the children of *wf* as GUI elements.

    Args:
        wf: the workflow or macro to serialize.
        port_cache: values typed in the GUI, so a redraw does not blank the fields.
    """
    return [
        get_node_dict(v, wf=wf, key=k, port_cache=port_cache)
        for k, v in wf.nodes.items()
    ]


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


def create_cached_input(wf, cache: datamodel.PortCache) -> list[str]:
    """Give *wf* one input port per cached value, wired to the child port it feeds.

    Ports are built only for values the user actually typed. A terminal input port
    never carries a default, so a port built for anything else would be mandatory with
    nothing able to satisfy it.

    Returns the labels created, for tests to assert against directly. The caller
    cannot rely on this return value to know what to remove: a raise partway through
    the loop means the function never reaches its `return`, so cleanup instead reads
    the labels back off `wf` once the run is over.
    """
    fed = fed_input_ports(wf)
    created = []
    for child in wf.nodes.values():
        for port_label, port in child.inputs.items():
            key = port_cache_key(child.label, port_label)
            if key not in cache or (child.label, port_label) in fed:
                continue
            wf.create_input_for(port, label=key)
            created.append(key)
    return created


def create_dangling_output(wf) -> list[str]:
    """Expose every unconsumed child output, so a run's results have somewhere to land.

    Returns the labels created, for tests to assert against directly. The caller
    cannot rely on this return value to know what to remove: the run itself, not this
    call, is what can raise before cleanup runs, so cleanup reads the labels back off
    `wf` once the run is over rather than trusting a value captured before it.
    """
    wf.set_outputs_to_unconnected_child_output(remove_existing=True)
    return list(wf.outputs)


def missing_required_input(wf, cache: datamodel.PortCache) -> list[tuple[str, str]]:
    """``(node, port)`` for every child input with no edge, no default and no value.

    Checked before a run so the user reads a list of ports rather than a pydantic
    validation error from deep inside recipe construction.
    """
    fed = fed_input_ports(wf)
    return [
        (child.label, port_label)
        for child in wf.nodes.values()
        for port_label, port in child.inputs.items()
        if (child.label, port_label) not in fed
        and not port.has_default
        and port_cache_key(child.label, port_label) not in cache
    ]


def prune_uncached_input(wf, cache: datamodel.PortCache) -> list[str]:
    """Drop terminal input ports with no cached value whose destinations all default.

    Used on the throwaway workflow ``pulled_workflow`` builds. Asked to expose defaults,
    which it must be for a typed value to reach a defaulted port at all, it also demands
    a value for every defaulted port the user left alone. Removing the port lets the
    default apply again.

    Returns the labels removed.
    """
    removed = []
    for label in list(wf.inputs):
        if label in cache:
            continue
        destinations = [
            edge.target
            for edge in wf.edges
            if edge.source.node is None and edge.source.port == label
        ]
        if not destinations:
            # A port with no destination cannot affect the run, but keeping it
            # leaves a mandatory port nothing can satisfy. Unlike the ``all(...)``
            # branch below, there is no "genuinely must be supplied" case to protect,
            # so it is always safe to drop.
            wf.remove_input(label)
            removed.append(label)
            continue
        if all(
            target.node is not None
            and wf.nodes[target.node].inputs[target.port].has_default
            for target in destinations
        ):
            wf.remove_input(label)
            removed.append(label)
    return removed


def _coerce_to_hint(value, type_hint):
    """Promote an int to a float where the hint wants one and nothing is lost.

    A GUI text field yields ``2`` where ``2.0`` was meant. ``bool`` is excluded, so
    ``True`` cannot arrive at a float-hinted port as ``1.0``.
    """
    hint = unwrap_annotated(type_hint)
    if hint is None or isinstance(value, bool) or not isinstance(value, int):
        return value
    if (
        not valid_value(value, hint)
        and valid_value(float(value), hint)
        and value == float(value)
    ):
        return float(value)
    return value


def cached_run_kwargs(wf, cache: datamodel.PortCache) -> dict:
    """The values to run *wf* with, one per terminal input port that has one."""
    kwargs = {}
    for label, port in wf.inputs.items():
        if label in cache:
            kwargs[label] = _coerce_to_hint(cache[label], port.type_hint)
    return kwargs
