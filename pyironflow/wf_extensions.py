import importlib
import types
import typing
from collections.abc import Iterator
from contextlib import contextmanager
from enum import StrEnum
from typing import Annotated, Any, get_args, get_origin

import flowrep as fr
from flowrep.parsers import label_helpers
from pyiron_workflow import constant
from pyiron_workflow.constructors import atomictype2node

from pyironflow import datamodel, entry
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


def is_constant(node) -> bool:
    """Whether *node* is a flowrep constant: a fixed JSONABLE value with no inputs.

    Asks the recipe rather than the class. It is the same question either way, but a
    recipe check does not depend on which import root produced the class object, and it
    matches how the rest of this module reads a node.
    """
    return isinstance(getattr(node, "recipe", None), fr.schemas.ConstantRecipe)


def validate_constants(wf) -> None:
    """Raise unless every constant in *wf* feeds at least one child port.

    The GUI draws a constant as a locked value on the port it feeds, so a constant that
    feeds nothing has nowhere to be drawn. Refusing is better than dropping it silently,
    which would lose a node the user never saw.
    """
    fed_by = {edge.source.node for edge in wf.edges if edge.source.node is not None}
    dangling = [
        label
        for label, node in wf.nodes.items()
        if is_constant(node) and label not in fed_by
    ]
    if dangling:
        removals = "".join(f"\n    wf.remove_node({label!r})" for label in dangling)
        raise ValueError(
            f"pyironFlow draws a constant as a locked value on the port it feeds, so a "
            f"constant feeding nothing cannot be shown, but {wf.label!r} has "
            f"{tuple(dangling)}. Drop them with:{removals}"
        )


def extract_locks(wf) -> datamodel.LockedPorts:
    """The locked-port view of every constant in *wf*, one key per port it feeds.

    A constant feeding several ports yields several keys carrying the same value. This
    is the deliberately lossy half of the mapping: rebuilding from these keys produces
    one constant per port rather than the single shared one that came in. Nothing about
    the result changes, only how verbosely the graph is written down.
    """
    validate_constants(wf)
    locked: datamodel.LockedPorts = {}
    for edge in wf.edges:
        if edge.source.node is None or edge.target.node is None:
            continue
        source = wf.nodes.get(edge.source.node)
        if source is None or not is_constant(source):
            continue
        locked[port_cache_key(edge.target.node, edge.target.port)] = (
            source.recipe.constant
        )
    return locked


def rebuild_constants(wf, locked: datamodel.LockedPorts) -> None:
    """Make *wf*'s constant nodes agree with *locked*, by replacing all of them.

    Constants are derived, never persisted. `dict_to_node` disconnects every node the
    GUI knows about so `dict_to_edge` can rebuild its edges, which would strip a hidden
    constant's edge on every sync. Rather than teach that code about constants, this
    wipes them and builds them again from the one place the GUI's lock state lives.

    A key whose node or port has since disappeared is skipped and left in *locked*,
    inert, exactly as a stale `PortCache` entry is: if a node with that label and port
    comes back, so does its lock.

    A port already fed by a real edge is skipped too. The browser will not let an edge
    be dropped on a locked port, but two edges into one input port is not a graph
    flowrep will accept, so the invariant is enforced here as well as there.
    """
    existing = [label for label, node in wf.nodes.items() if is_constant(node)]
    if existing:
        wf.remove_node(*existing)

    fed = fed_input_ports(wf)
    pending = [
        (child.label, port_label, locked[key])
        for child in wf.nodes.values()
        for port_label in child.inputs
        if (child.label, port_label) not in fed
        and (key := port_cache_key(child.label, port_label)) in locked
    ]

    for child_label, port_label, value in pending:
        node = constant.Constant.from_value(
            value,
            label_helpers.unique_suffix(
                f"{child_label}_{port_label}_constant", wf.nodes
            ),
        )
        wf.add_node(node)
        wf.connect(
            node.outputs[fr.schemas.ConstantRecipe.std_label],
            wf.nodes[child_label].inputs[port_label],
        )


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
    if node is None:
        return None

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


def unwrap_annotated(hint: typing.Any) -> typing.Any:
    while get_origin(hint) is Annotated:
        hint = get_args(hint)[0]
    return hint


def get_node_entry_kinds(port_map) -> list[str]:
    """Per port, the widget its hint earns, as an `entry.EntryKind` value."""
    return [entry.entry_kind(port.type_hint) for port in port_map.values()]


def get_node_literal_values(port_map) -> list[list[str] | None]:
    """Per port, its dropdown options rendered as text, or None."""
    return [entry.options(port.type_hint) for port in port_map.values()]


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


def get_node_step(run, node_label: str):
    """Return the step *run* recorded for *node_label*, if any.

    A step's `lexical_path` is rooted at whatever was run, so it reads
    'wf_label.node_label' after a full run and 'pulled_x.node_label' after a pull.
    Matching on the trailing label rather than the whole path is what lets one lookup
    serve both. `None` means the node took no part in *run*, which is not the same as
    a node whose output happened to be `None`.
    """
    if run is None:
        return None
    for step in run.steps:
        if (
            step.lexical_path.endswith(f".{node_label}")
            or step.lexical_path == node_label
        ):
            return step
    return None


LOCKED_TEXT_MAX = 120
"""Characters of a locked value the port field shows before clipping."""

LOCKED_TITLE_MAX = 2000
"""Characters of a locked value the hover tooltip shows before clipping.

Larger than the field, because the tooltip is where a user goes to read the whole thing,
but still bounded: a constant can hold an arbitrarily large nested structure, and this
payload is re-sent on every redraw.
"""


class _NoDefault:
    """The type of `NO_DEFAULT`."""

    def __repr__(self) -> str:
        return "<NO DEFAULT>"


NO_DEFAULT = _NoDefault()
"""Marks a port with no usable default.

A sentinel rather than `None`, because `None` is a perfectly good default on a port
hinted to accept it, and the two must stay distinguishable.
"""


def _port_default_value(node, port_label: str) -> Any:
    """*node*'s default for *port_label*, or `NO_DEFAULT` if it has none to show.

    The value lives on the flowrep live node; the port dataclass only records whether a
    default exists. A default that is not JSONABLE, such as a tuple, has nothing a field
    could show, so it is dropped.
    """
    try:
        live = node.generate_flowrep_live_node()
    except Exception:
        return NO_DEFAULT
    port_data = live.input_ports.get(port_label)
    if port_data is None:
        return NO_DEFAULT
    default = port_data.default
    if isinstance(default, NotData):
        return NO_DEFAULT
    hint = node.inputs[port_label].type_hint
    if entry.entry_kind(hint) is entry.EntryKind.NONE:
        # `entry.coerce` only checks a value against the hint, not the hint's own
        # JSONABLE-ness, so a default that happens to satisfy a non-JSONABLE hint
        # (e.g. a tuple matching `tuple[int, int]`) would otherwise render instead
        # of being dropped.
        return NO_DEFAULT
    try:
        return entry.coerce(default, hint)
    except entry.EntryError:
        return NO_DEFAULT


def _get_port_default(node, port_label: str) -> str | None:
    """*node*'s default for *port_label* rendered as text, if it can be shown at all."""
    value = _port_default_value(node, port_label)
    if value is NO_DEFAULT:
        return None
    return entry.render(value, node.inputs[port_label].type_hint)


def get_node_defaults(node) -> list[str | None]:
    """Per input port, the default rendered as placeholder text, or None."""
    return [_get_port_default(node, label) for label in node.inputs]


def get_node_has_defaults(node) -> list[bool]:
    """Per input port, whether it has a default at all, primitive or not.

    This is what drives the unfed marker. ``get_node_defaults`` cannot: a port whose
    default is not a primitive has one, but has nothing to display.
    """
    return [port.has_default for port in node.inputs.values()]


def get_node_cached_values(node, cache: datamodel.PortCache) -> dict[str, str]:
    """Per entered input port, the cached value rendered as text.

    Only ports carrying an entry appear. A port the user left alone is absent rather
    than present-and-null, so the browser can tell the two apart.
    """
    values = {}
    for label, port in node.inputs.items():
        key = port_cache_key(node.label, label)
        if key in cache:
            values[label] = entry.render(cache[key], port.type_hint)
    return values


def get_node_errors(node, invalid: dict[str, Any]) -> dict[str, dict[str, str]]:
    """Per input port holding a rejected entry, the text typed and why it failed."""
    errors = {}
    for label in node.inputs:
        key = port_cache_key(node.label, label)
        if key in invalid:
            errors[label] = {
                "text": invalid[key].text,
                "message": invalid[key].message,
            }
    return errors


def _clip(text: str, limit: int) -> str:
    """*text*, shortened to *limit* characters with a trailing ellipsis if it must be."""
    return text if len(text) <= limit else text[: limit - 1] + "…"


def get_node_locked(
    node, locked: datamodel.LockedPorts
) -> dict[str, dict[str, str | bool]]:
    """Per locked input port, what the browser needs to draw it.

    Presence in the result means the port is locked. ``releasable`` says whether the
    port has an entry field to release the value back into: if it does the browser draws
    a padlock, and if it does not the only thing unlocking could do is delete, so it
    draws a trashcan instead.

    ``text`` is for the field and ``full`` is for the hover tooltip, clipped to
    different lengths. Clipping loses nothing, because the field is read-only and its
    text is never read back -- both unlocking and rebuilding take the value from
    *locked*, never from what was displayed.
    """
    shown: dict[str, dict[str, str | bool]] = {}
    for port_label, port in node.inputs.items():
        key = port_cache_key(node.label, port_label)
        if key not in locked:
            continue
        value = locked[key]
        hint = port.type_hint
        releasable = entry.entry_kind(hint) is not entry.EntryKind.NONE
        # A non-releasable port's hint is not one `entry.render` is meant for, but the
        # value is JSONABLE by construction, so `repr` is always available and honest.
        rendered = entry.render(value, hint) if releasable else repr(value)
        shown[port_label] = {
            "text": _clip(rendered, LOCKED_TEXT_MAX),
            "full": _clip(rendered, LOCKED_TITLE_MAX),
            "releasable": releasable,
        }
    return shown


def get_node_dict(
    node,
    wf=None,
    key=None,
    port_cache: datamodel.PortCache | None = None,
    invalid: dict[str, Any] | None = None,
    locked: datamodel.LockedPorts | None = None,
):
    node_height = 40 + (16 * max(len(node.inputs), len(node.outputs)))
    label = node.label
    if (node.label != key) and (key is not None):
        label = f"{node.label}: {key}"

    step = get_node_step(None if wf is None else wf.last_run, node.label)
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
            "target_values": get_node_cached_values(node, port_cache or {}),
            "target_errors": get_node_errors(node, invalid or {}),
            "target_locked": get_node_locked(node, locked or {}),
            "target_defaults": get_node_defaults(node),
            "target_has_default": get_node_has_defaults(node),
            "target_types": get_node_entry_kinds(node.inputs),
            "target_types_raw": get_raw_target_types(node.inputs),
            "target_literal_values": get_node_literal_values(node.inputs),
            "source_types": get_node_entry_kinds(node.outputs),
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


def get_nodes(
    wf,
    port_cache: datamodel.PortCache | None = None,
    invalid: dict[str, Any] | None = None,
    locked: datamodel.LockedPorts | None = None,
):
    """Serialize the children of *wf* as GUI elements.

    Args:
        wf: the workflow or macro to serialize.
        port_cache: values typed in the GUI, so a redraw does not blank the fields.
        invalid: rejected entries typed in the GUI, keyed by `port_cache_key`.
        locked: values frozen into constant nodes, keyed by `port_cache_key`.

    A constant is drawn as a locked value on the port it feeds, not as a node of its
    own, so it is skipped here even though it is a member of `wf.nodes`.
    """
    return [
        get_node_dict(
            v, wf=wf, key=k, port_cache=port_cache, invalid=invalid, locked=locked
        )
        for k, v in wf.nodes.items()
        if not is_constant(v)
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
        # A constant is drawn on the port it feeds, so its edge has no endpoint in the
        # GUI to draw between.
        source = wf.nodes.get(edge.source.node) if edge.source.node else None
        if source is not None and is_constant(source):
            continue
        # Workflow boundary edges (None node = workflow input/output port)
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


class TransientInputs(StrEnum):
    """Which unconnected child input ports get a workflow input port for a while.

    A port is unconnected when no edge from another node feeds it. Every mode exposes
    each unconnected port without a default, because a workflow recipe that leaves
    one dangling fails validation.
    """

    USED = "used"
    """Ports without a default, plus ports with a value typed into the GUI."""
    UNCONNECTED = "unconnected"
    """Every unconnected port, defaulted or not."""
    UNDEFAULTED = "undefaulted"
    """Only ports without a default, typed value or not."""


def _selects(inputs: TransientInputs, has_default: bool, cached: bool) -> bool:
    match inputs:
        case TransientInputs.USED:
            return cached or not has_default
        case TransientInputs.UNCONNECTED:
            return True
        case TransientInputs.UNDEFAULTED:
            return not has_default
    typing.assert_never(inputs)


def create_transient_input(
    wf, cache: datamodel.PortCache, inputs: TransientInputs
) -> list[str]:
    """Give *wf* one input port per unconnected child port that *inputs* selects.

    Each port is labelled with `port_cache_key` and wired to the child port it feeds.

    Returns the labels created, for tests to assert against directly. The caller
    cannot rely on this return value to know what to remove: a raise partway through
    the loop means the function never reaches its `return`, so cleanup instead reads
    the labels back off `wf` once it is done.
    """
    fed = fed_input_ports(wf)
    created = []
    for child in wf.nodes.values():
        for port_label, port in child.inputs.items():
            if (child.label, port_label) in fed:
                continue
            key = port_cache_key(child.label, port_label)
            if _selects(inputs, port.has_default, key in cache):
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


@contextmanager
def transient_io(
    wf, cache: datamodel.PortCache, inputs: TransientInputs
) -> Iterator[Any]:
    """Give *wf* terminal IO for the length of the block, then take it all away.

    Input ports come from `create_transient_input` and output ports from
    `create_dangling_output`. *wf* is expected to arrive IO-free, as every workflow
    `PyironFlow` holds does, since everything it holds afterwards is removed.

    Cleanup reads back whatever labels *wf* actually holds once the `try` exits,
    rather than trusting the return values of `create_transient_input` and
    `create_dangling_output`. Either can raise after creating only some of its
    ports -- two cache keys can collide on the same terminal label -- and an
    interrupted return statement would otherwise lose track of exactly what needs
    removing, leaving the workflow with terminal IO the caller never sees coming.

    `create_input_for`, `set_outputs_to_unconnected_child_output`, `remove_input` and
    `remove_output` are all `@_undoable` in `pyiron_workflow`, so this bookkeeping
    would otherwise push its own diffs onto `wf.undo_stack` and wipe `wf.redo_stack`.
    It is an implementation detail, not an edit the user made, so the undo/redo
    history is snapshotted first and restored in `finally`: otherwise a single
    `undo()` afterwards would put terminal IO back onto the workflow, tripping the
    constructor guard the next time it is handed to `PyironFlow`, and it would also
    silently discard whatever the user could previously redo.

    Both stacks are restored by copy, clear and extend rather than by comparing
    lengths before and after. `undo_stack` is a bounded `deque`: once it is already
    at `maxlen`, these pushes evict genuine user entries one for one, so its length
    never grows past the snapshot and a length-based truncation would leave these
    diffs sitting on top while silently dropping the user's. A full copy sidesteps
    that regardless of how full the stack was beforehand.
    """
    undo_snapshot = wf.undo_stack.copy()
    redo_snapshot = wf.redo_stack.copy()
    try:
        create_transient_input(wf, cache, inputs)
        create_dangling_output(wf)
        yield wf
    finally:
        wf.remove_input(*list(wf.inputs))
        wf.remove_output(*list(wf.outputs))
        wf.undo_stack.clear()
        wf.undo_stack.extend(undo_snapshot)
        wf.redo_stack.clear()
        wf.redo_stack.extend(redo_snapshot)


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


def invalid_entries(
    wf, cache: datamodel.PortCache, invalid: dict[str, datamodel.InvalidEntry]
) -> list[tuple[str, str, str]]:
    """``(node, port, message)`` for every unfed child port whose entry cannot be used.

    Two ways that happens: the user's text was rejected when they typed it, or a value
    cached earlier no longer fits the port, which is what a node deleted and re-added
    under the same label with different hints leaves behind.
    """
    fed = fed_input_ports(wf)
    found = []
    for child in wf.nodes.values():
        for port_label, port in child.inputs.items():
            if (child.label, port_label) in fed:
                continue
            key = port_cache_key(child.label, port_label)
            if key in invalid:
                found.append((child.label, port_label, invalid[key].message))
            elif key in cache:
                try:
                    entry.coerce(cache[key], port.type_hint)
                except entry.EntryError as err:
                    found.append((child.label, port_label, str(err)))
    return found


def cached_run_kwargs(wf, cache: datamodel.PortCache) -> dict:
    """The values to run *wf* with, one per terminal input port that has one.

    Each value is re-checked against the port it will feed, which also promotes an int
    to a float where the hint wants one. A value that no longer fits raises, but
    `invalid_entries` has already reported it by the time this runs.
    """
    return {
        label: entry.coerce(cache[label], port.type_hint)
        for label, port in wf.inputs.items()
        if label in cache
    }
