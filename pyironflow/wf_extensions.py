import importlib
import math
import pathlib
import types
import typing
from typing import Union, get_args

from pyiron_workflow.constant import Constant
from pyiron_workflow.constructors import atomictype2node
from pyiron_workflow.type_hinting import type_hint_to_tuple, valid_value

from pyironflow.themes import get_color

try:
    from flowrep.retrospective.datastructures import NOT_DATA, NotData
except ImportError:
    from flowrep.schemas import NOT_DATA, NotData  # type: ignore[no-redef]

NODE_WIDTH = 240

# Prefix for hidden constant nodes that store user-set input values
_CONST_PREFIX = "_const_"


def _const_node_name(node_label: str, port_label: str) -> str:
    return f"{_CONST_PREFIX}{node_label}__{port_label}"


def _is_const_node(label: str | None) -> bool:
    return label is not None and label.startswith(_CONST_PREFIX)


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


def _get_node_input_value(node, port_label: str, wf=None):
    """
    Get the value for an input port of *node*.

    Looks for a connected constant node in *wf* first; falls back to the
    default from the live node data.
    """
    if wf is not None:
        const_name = _const_node_name(node.label, port_label)
        const_node = wf.nodes.get(const_name)
        if const_node is not None:
            return const_node.recipe.constant

    # Fall back to recipe default via live node
    try:
        live = node.generate_flowrep_live_node()
        port_data = live.input_ports.get(port_label)
        if port_data is not None:
            default = port_data.default
            if not isinstance(default, NotData):
                return default
    except Exception:
        pass

    return NOT_DATA


def _get_node_output_value(node, port_label: str, wf=None):
    """
    Get the last computed value for an output port of *node* from the
    workflow's ``last_run`` if available.
    """
    if wf is not None and wf.last_run is not None:
        node_data = wf.last_run.result.nodes.get(node.label)
        if node_data is not None:
            out_port = node_data.output_ports.get(port_label)
            if out_port is not None:
                return out_port.value

    return NOT_DATA


def dict_to_node(
    dict_node: dict, live_nodes: dict | None = None, wf=None, reload=False
):
    """Convert a dict spec of a node back to a Node object.

    When *wf* is provided, existing edges and stale constant nodes are cleaned
    up so that ``dict_to_edge`` can rebuild them.  Values stored in the GUI
    dict are applied via hidden constant nodes **after** the node has been
    added to *wf*; callers must ensure the node is part of *wf* before calling
    ``apply_node_values``.
    """
    if live_nodes is None:
        live_nodes = {}
    data = dict_node["data"]
    label = dict_node["id"]
    node_id = data["python_object_id"]

    # Reuse existing node if it is the same object.
    if id(node := live_nodes.get(label, None)) != node_id:
        func = get_node_from_path(data["import_path"], reload=reload)
        if func is None:
            return None
        node = atomictype2node(func, label)

    # Disconnect all existing edges for this node so dict_to_edge can rebuild them.
    if wf is not None and node.label in wf.nodes:
        wf.disconnect(node)
        # Also remove stale constant nodes for this node
        for port_label in list(node.inputs.keys()):
            const_name = _const_node_name(label, port_label)
            if const_name in wf.nodes:
                wf.remove_node(const_name)

    if "position" in dict_node:
        x, y = dict_node["position"].values()
        node.position = (x, y)
    else:
        print("no position: ", node.label)

    # Attach pending values to the node so they can be applied once it is in wf.
    node._pending_gui_values = {}
    if "target_values" in data:
        for k, v in zip(data["target_labels"], data["target_values"]):
            if v not in ("NonPrimitive", "NOT_DATA.__class__", ""):
                type_hint = node.inputs[k].type_hint
                if (
                    isinstance(v, int)
                    and not valid_value(v, type_hint)
                    and valid_value(float(v), type_hint)
                    and v == float(v)
                ):
                    v = float(v)
                node._pending_gui_values[k] = v

    return node


def apply_node_values(node, wf):
    """Create/connect constant nodes for any pending GUI-set values on *node*.

    Must be called *after* the node has been added to *wf*.
    """
    pending = getattr(node, "_pending_gui_values", {})
    for k, v in pending.items():
        const_name = _const_node_name(node.label, k)
        # Remove pre-existing constant node if present
        if const_name in wf.nodes:
            wf.remove_node(const_name)
        const_node = Constant.from_value(v, const_name)
        wf.add_node(const_node)
        wf.connect(const_node.outputs["constant"], node.inputs[k])
    node._pending_gui_values = {}


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


def get_node_values(node, wf=None, io: str = "inputs"):
    """Return displayable values for *node*'s input or output ports."""
    values = []
    port_map = node.inputs if io == "inputs" else node.outputs
    for k in port_map:
        if io == "inputs":
            value = _get_node_input_value(node, k, wf)
        else:
            value = _get_node_output_value(node, k, wf)

        if isinstance(value, NotData):
            value = "NOT_DATA.__class__"
        elif not is_primitive(value):
            value = "NonPrimitive"

        if isinstance(value, float) and not math.isfinite(value):
            value = None
        values.append(value)

    return values


def _get_generic_type(t):
    non_none_types = [arg for arg in t.__args__ if arg is not type(None)]
    hints = {float, int, str}.intersection(non_none_types)
    if int in hints and float in hints:
        return Union[int, float]
    if int in hints:
        return int
    if float in hints:
        return float
    if str in hints:
        return str
    return non_none_types[0]


def _get_type_name(t):
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
        type_hint = port_map[k].type_hint
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
        type_hint = port_map[k].type_hint
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
        type_hint = port_map[k].type_hint
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
        type_hint = port_map[k].type_hint
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
        type_hint = port_map[k].type_hint
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
    n_inputs = len(list(node.inputs.keys()))
    n_outputs = len(list(node.outputs.keys()))
    if n_outputs > n_inputs:
        node_height = 30 + (16 * n_outputs) + 10
    else:
        node_height = 30 + (16 * n_inputs) + 10
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
            "target_values": get_node_values(node, wf, io="inputs"),
            "target_types": get_node_types(node.inputs),
            "target_types_raw": get_raw_target_types(node.inputs),
            "target_literal_values": get_node_literal_values(node.inputs),
            "target_literal_types": get_node_literal_types(node.inputs),
            "source_values": get_node_values(node, wf, io="outputs"),
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


def get_nodes(wf):
    nodes = []
    for k, v in wf.nodes.items():
        if _is_const_node(k):
            continue
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
        if _is_const_node(edge.source.node) or _is_const_node(edge.target.node):
            continue
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


def get_input_types_from_hint(node_input):
    new_type = ""
    for listed_type in list(type_hint_to_tuple(node_input.type_hint)):
        if listed_type is None:
            listed_type = type(None)
        if listed_type.__name__ != "NoneType":
            new_type = new_type + listed_type.__name__ + "|"

    new_type = new_type[:-1]

    for listed_type in list(type_hint_to_tuple(node_input.type_hint)):
        if listed_type is None:
            listed_type = type(None)
        if listed_type.__name__ == "NoneType" and new_type != "":
            new_type = ": Optional[" + new_type + "]"

    return new_type


def create_macro(wf, name: str, root_path: str | pathlib.Path | None = None):
    """Generate a macro file from the selected workflow."""
    if root_path is None:
        root_path = str(pathlib.Path(__file__).parent / "pyiron_nodes/pyiron_nodes")
    imports = list("")
    var_def = ""

    file = open(root_path + "/" + name + ".py", "w")

    for i, (k, v) in enumerate(wf.nodes.items()):
        if _is_const_node(k):
            continue
        rest, n = get_import_path(v).rsplit(".", 1)
        new_import = "    from " + rest + " import " + n
        imports.append(new_import)

        for port_label, port in v.inputs.items():
            wf_input_key = v.label + "__" + port_label
            if wf_input_key in wf.inputs:
                value = _get_node_input_value(v, port_label, wf)
                if isinstance(value, NotData) or value is None:
                    value_str = "None"
                elif isinstance(value, str):
                    value_str = "'" + value + "'"
                else:
                    value_str = str(value)
                var_def = (
                    var_def
                    + v.label
                    + "_"
                    + port_label
                    + get_input_types_from_hint(port)
                    + " = "
                    + value_str
                    + ", "
                )

    var_def = var_def[:-2]

    new_list = []
    for edge in wf.edges:
        if not _is_const_node(edge.source.node) and not _is_const_node(
            edge.target.node
        ):
            new_list.append([edge.source.node, edge.target.node, edge.target.port])

    file.write(
        "from pyiron_workflow import Workflow\n"
        "from typing import Optional\n\n"
        "def " + name + "(" + var_def + "):\n"
    )
    file.writelines(j + "\n" for j in imports)

    for k, v in wf.nodes.items():
        if _is_const_node(k):
            continue
        rest, n = get_import_path(v).rsplit(".", 1)
        file.write("    " + v.label + " = " + n + "()\n")

    for k, v in wf.nodes.items():
        if _is_const_node(k):
            continue
        rest, n = get_import_path(v).rsplit(".", 1)

        node_def = ""

        for wf_input_key in list(wf.inputs.keys()):
            node_label, input_label = wf_input_key.rsplit("__", 1)
            if v.label == node_label:
                node_def = (
                    node_def
                    + input_label
                    + " = "
                    + node_label
                    + "_"
                    + input_label
                    + ", "
                )

        for p in new_list:
            if v.label == p[1]:
                node_def = node_def + p[2] + " = " + p[0] + ", "
        node_def = node_def[:-2]
        file.write("    " + v.label + "(" + node_def + ")\n")

    rest_list = []
    for wf_output_key in list(wf.outputs.keys()):
        rest, n = wf_output_key.rsplit("__", 1)
        rest_list.append(rest)

    out_str = "    return "
    for strs in rest_list:
        out_str = out_str + strs + ", "

    file.write(out_str)
    print("\nSuccessfully created macro: " + root_path + "/" + name + ".py")
    file.close()
