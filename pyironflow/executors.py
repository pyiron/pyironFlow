"""Executors for nodes: the callables that create them, and the ones the GUI holds.

A *Valid Creator* is a public callable taking only keyword-able parameters, each
hinted with a JSONABLE type (so the GUI can offer a field for it), and hinted to
return a `concurrent.futures.Executor` subclass or `pyiron_workflow.ExecutorInstructions`.

This module stays light: a process pool's child imports it to unpickle `LocalOnly`.
"""

from __future__ import annotations

import dataclasses
import functools
import importlib
import inspect
import sys
import types
import typing
from collections.abc import Callable, Iterable, Iterator
from concurrent import futures
from concurrent.futures import process
from typing import Any, TypeAlias

import flowrep as fr
import pyiron_workflow as pwf

from pyironflow import entry

ExecutorLike: TypeAlias = futures.Executor | pwf.ExecutorInstructions
Creator: TypeAlias = Callable[..., ExecutorLike]

_FORBIDDEN_KINDS: dict[inspect._ParameterKind, str] = {
    inspect.Parameter.POSITIONAL_ONLY: "positional-only",
    inspect.Parameter.VAR_POSITIONAL: "variadic (*args)",
    inspect.Parameter.VAR_KEYWORD: "variadic (**kwargs)",
}


class InvalidCreator(TypeError):
    """Why an object is not a Valid Creator."""


def validate_creator(obj: object) -> None:
    """Raise `InvalidCreator` unless *obj* is a Valid Creator."""
    if not callable(obj):
        raise InvalidCreator(f"{obj!r} is not callable.")
    name = getattr(obj, "__name__", None)
    if not isinstance(name, str) or name.startswith("_"):
        raise InvalidCreator(f"{obj!r} has no public name.")
    try:
        signature = inspect.signature(obj)
    except (TypeError, ValueError) as err:
        raise InvalidCreator(f"{name} has no signature to inspect.") from err
    for parameter in signature.parameters.values():
        if parameter.kind in _FORBIDDEN_KINDS:
            raise InvalidCreator(
                f"{name}'s parameter {parameter.name!r} is "
                f"{_FORBIDDEN_KINDS[parameter.kind]}; creators take keywords only."
            )
    try:
        hints = typing.get_type_hints(obj)
    except Exception as err:
        raise InvalidCreator(f"{name}'s type hints do not resolve: {err}") from err
    for parameter in signature.parameters.values():
        if parameter.name not in hints:
            raise InvalidCreator(
                f"{name}'s parameter {parameter.name!r} has no type hint."
            )
        if not entry.is_jsonable_hint(hints[parameter.name]):
            raise InvalidCreator(
                f"{name}'s parameter {parameter.name!r} is hinted "
                f"{hints[parameter.name]!r}, which is not JSONABLE."
            )
    returns = hints.get("return")
    if not (
        isinstance(returns, type)
        and issubclass(returns, (futures.Executor, pwf.ExecutorInstructions))
    ):
        raise InvalidCreator(
            f"{name} must be hinted to return a concurrent.futures.Executor "
            f"subclass or pyiron_workflow.ExecutorInstructions, not {returns!r}."
        )


def is_valid_creator(obj: object) -> bool:
    try:
        validate_creator(obj)
    except InvalidCreator:
        return False
    return True


def find_creators(modules: Iterable[types.ModuleType]) -> dict[str, Creator]:
    """The Valid Creators bound to public names in *modules*, in the order found.

    An object found again, under any name, is kept once. A name bound to two
    different creators would be ambiguous in the GUI's menu, so it raises.

    Raises:
        ValueError: If two modules bind the same name to different creators.
    """
    found: dict[str, Creator] = {}
    for module in modules:
        for name, obj in vars(module).items():
            if name.startswith("_") or not is_valid_creator(obj):
                continue
            held = found.get(name)
            if held is None:
                if not any(obj is creator for creator in found.values()):
                    found[name] = obj
            elif held is not obj:
                raise ValueError(
                    f"Executor creator {name!r} is defined by both "
                    f"{held.__module__} and {obj.__module__}."
                )
    return found


class _NoDefault:
    def __repr__(self) -> str:
        return "NO_DEFAULT"


NO_DEFAULT: Any = _NoDefault()
"""A `CreatorParameter.default` meaning the parameter must be given."""


@dataclasses.dataclass(frozen=True)
class CreatorParameter:
    name: str
    hint: Any
    default: Any = NO_DEFAULT

    @property
    def required(self) -> bool:
        return self.default is NO_DEFAULT


def creator_parameters(creator: Creator) -> list[CreatorParameter]:
    """*creator*'s parameters, for building one input field each."""
    hints = typing.get_type_hints(creator)
    return [
        CreatorParameter(
            parameter.name,
            hints[parameter.name],
            (
                NO_DEFAULT
                if parameter.default is inspect.Parameter.empty
                else parameter.default
            ),
        )
        for parameter in inspect.signature(creator).parameters.values()
    ]


EXTERNAL = "external"
"""The name stem of an executor the GUI found on a node rather than made."""


@dataclasses.dataclass(frozen=True)
class Created:
    """An executor the GUI holds, and how it came to be."""

    name: str
    creator: Creator | None  # None for an adopted external executor
    kwargs: dict[str, Any]
    value: ExecutorLike


def walk_nodes(graph: pwf.schemas.Graph) -> Iterator[pwf.schemas.Node]:
    """Every node inside *graph*, depth first, each before its own children."""
    for node in graph.nodes.values():
        yield node
        if isinstance(node, pwf.schemas.Graph):
            yield from walk_nodes(node)


def shutdown(value: ExecutorLike) -> None:
    """Stop *value* without waiting, if it is a live executor rather than instructions."""
    if isinstance(value, futures.Executor):
        value.shutdown(wait=False, cancel_futures=True)


class ExecutorRegistry:
    """The executors the GUI holds, keyed by a user-facing name, in creation order."""

    def __init__(self, creators: dict[str, Creator]) -> None:
        self.creators = dict(creators)
        self.created: dict[str, Created] = {}

    def default_name(self, stem: str) -> str:
        return fr.tools.unique_suffix(stem, self.created)

    def create(self, name: str, creator_name: str, kwargs: dict[str, Any]) -> Created:
        """Call the creator called *creator_name* and hold the result as *name*.

        Raises:
            ValueError: With a message fit to show the user, if *name* is blank or
                already held. Whatever the creator raises propagates unchanged.
        """
        name = name.strip()
        if not name:
            raise ValueError("Give the executor a name.")
        if name in self.created:
            raise ValueError(f"An executor named {name!r} already exists.")
        creator = self.creators[creator_name]
        created = Created(name, creator, dict(kwargs), creator(**kwargs))
        self.created[name] = created
        return created

    def adopt(self, value: ExecutorLike) -> Created:
        """Hold *value*, found on a node, unless it is held already."""
        if (name := self.name_of(value)) is not None:
            return self.created[name]
        created = Created(self.default_name(EXTERNAL), None, {}, value)
        self.created[created.name] = created
        return created

    def adopt_from(self, graph: pwf.schemas.Graph) -> None:
        """Hold every executor found on a node inside *graph*."""
        for node in walk_nodes(graph):
            if node.executor is not None:
                self.adopt(node.executor)

    def name_of(self, value: ExecutorLike | None) -> str | None:
        """The name *value* is held under, by identity; None if it is not held."""
        return next(
            (name for name, held in self.created.items() if held.value is value),
            None,
        )

    def delete(self, name: str, graphs: Iterable[pwf.schemas.Graph]) -> None:
        """Forget *name*, clear it from every node in *graphs*, and shut it down."""
        created = self.created.pop(name)
        for graph in graphs:
            for node in walk_nodes(graph):
                if node.executor is created.value:
                    node.executor = None
        shutdown(created.value)

    def close(self) -> None:
        """Shut every held executor down and forget them all."""
        for created in self.created.values():
            shutdown(created.value)
        self.created.clear()


class LocalOnly:
    """Calls *fn* in this process; pickles to a no-op.

    The GUI's run hooks are bound to widgets. `pyiron_workflow` sends a node's run
    config to the node's executor, and a process pool would otherwise pickle the whole
    GUI (or fail to, on its locks). Progress for the submitted node itself is still
    reported in this process, so nothing the canvas shows is lost.
    """

    def __init__(self, fn: Callable[..., Any]) -> None:
        self.fn = fn

    def __call__(self, *args: Any, **kwargs: Any) -> None:
        self.fn(*args, **kwargs)

    def __reduce__(self) -> tuple[type[_Noop], tuple[()]]:
        return (_Noop, ())


class _Noop:
    """What a `LocalOnly` becomes in another process."""

    def __call__(self, *args: Any, **kwargs: Any) -> None:
        pass


IMPORT_HINT = (
    "Was it defined in the notebook? Move it into its own module on your Python path."
    "Remember that the Node Library is added to the path for the GUI's python session "
    "only, so if your failed node came from the library you may need to put that "
    "library path in your system's PYTHONPATH environment variable."
)


def is_process_pool(value: object) -> bool:
    """Whether *value* runs nodes in a `ProcessPoolExecutor`, or will."""
    if isinstance(value, futures.ProcessPoolExecutor):
        return True
    return (
        isinstance(value, pwf.ExecutorInstructions)
        and isinstance(value.constructor, type)
        and issubclass(value.constructor, futures.ProcessPoolExecutor)
    )


def _executor_name(value: ExecutorLike, registry: ExecutorRegistry | None) -> str:
    name = None if registry is None else registry.name_of(value)
    return type(value).__name__ if name is None else name


def _unimportable(node: pwf.schemas.Node) -> str | None:
    """Where *node*'s definition lives, if a fresh process could not import it.

    Checked in this process, so a module only this process has passes; the
    broken-pool explanation covers that. A `__main__` without a file is a notebook or
    REPL, which a spawned child cannot re-import; a script's `__main__` it can.
    """
    reference = getattr(node.recipe, "reference", None)
    if reference is None:
        return None
    module, qualname = reference.info.module, reference.info.qualname
    where = f"{module}.{qualname}"
    if module == "__main__":
        return None if hasattr(sys.modules.get("__main__"), "__file__") else where
    try:
        functools.reduce(getattr, qualname.split("."), importlib.import_module(module))
    except Exception:
        return where
    return None


def process_pool_problems(
    graph: pwf.schemas.Graph, registry: ExecutorRegistry | None
) -> list[str]:
    """One line per node that a process pool in *graph* would fail to import."""
    problems: list[str] = []
    for node in walk_nodes(graph):
        if not is_process_pool(node.executor):
            continue
        name = _executor_name(node.executor, registry)
        members = [node]
        if isinstance(node, pwf.schemas.Graph):
            members.extend(walk_nodes(node))
        for member in members:
            if (where := _unimportable(member)) is not None:
                line = f"{member.lexical_path} (executor {name!r}): {where}"
                if line not in problems:
                    problems.append(line)
    return problems


_LOST_ERROR = (
    "Its own error went to the terminal running this Python session "
    "(for Jupyter, the server's terminal), not here."
)

PATH_HINT = (
    "Most often the process could not import a node: executorlib starts a fresh "
    "Python, which finds installed packages, PYTHONPATH and the working directory, "
    "but not paths added during this session (such as a node library root). "
    "Install the node's module, or put its directory on PYTHONPATH."
)


def _from_executorlib(cls: type) -> bool:
    """Whether *cls* is, or derives from, a class of the `executorlib` package.

    Checked by name so pyironFlow does not depend on executorlib.
    """
    return any(k.__module__.partition(".")[0] == "executorlib" for k in cls.__mro__)


def is_executorlib(value: object) -> bool:
    """Whether *value* runs nodes on an `executorlib` executor, or will."""
    if isinstance(value, pwf.ExecutorInstructions):
        constructor = value.constructor
        return isinstance(constructor, type) and _from_executorlib(constructor)
    return isinstance(value, futures.Executor) and _from_executorlib(type(value))


def _is_executorlib_crash(err: BaseException) -> bool:
    """Whether *err* is executorlib's lost-connection error, recognised by name."""
    return any(
        k.__name__ == "ExecutorlibSocketError"
        and k.__module__.partition(".")[0] == "executorlib"
        for k in type(err).__mro__
    )


class ExecutorCrashed(RuntimeError):
    """An executor's process died running a node, and its own error went elsewhere."""


class ProcessPoolBroken(ExecutorCrashed):
    """A process pool died running a node; says what most likely went wrong."""


class ExecutorlibBroken(ExecutorCrashed):
    """An executorlib process died running a node; says what most likely went wrong."""


def _find(err: BaseException, matches: Callable[[BaseException], bool]) -> bool:
    """Whether *err* matches, or is a group holding a match at any depth."""
    if matches(err):
        return True
    return isinstance(err, BaseExceptionGroup) and any(
        _find(inner, matches) for inner in err.exceptions
    )


def _running(nodes: list[pwf.schemas.Node], registry: ExecutorRegistry | None) -> str:
    return ", ".join(
        f"{node.lexical_path} (executor {_executor_name(node.executor, registry)!r})"
        for node in nodes
    )


def explain_crashed_executor(
    err: BaseException, graph: pwf.schemas.Graph, registry: ExecutorRegistry | None
) -> ExecutorCrashed | None:
    """A readable error for *err* if an executor's process died under it, else None.

    Covers the standard library's process pools and executorlib, whose failures
    otherwise read only as "terminated abruptly" or "SocketInterface crashed".
    """
    if _find(err, lambda e: isinstance(e, process.BrokenProcessPool)):
        return _explain_pool(graph, registry)
    if _find(err, _is_executorlib_crash):
        return _explain_executorlib(graph, registry)
    return None


def _explain_pool(
    graph: pwf.schemas.Graph, registry: ExecutorRegistry | None
) -> ProcessPoolBroken:
    pooled = [node for node in walk_nodes(graph) if is_process_pool(node.executor)]
    lines = [
        f"A process pool stopped abruptly while running {_running(pooled, registry)}.",
        _LOST_ERROR,
        f"Most often the pool could not import a node. {IMPORT_HINT}",
    ]
    instances = dict.fromkeys(
        _executor_name(node.executor, registry)
        for node in pooled
        if isinstance(node.executor, futures.Executor)
    )
    lines.extend(
        f"Pool {name!r} is now permanently broken; delete it in "
        f"Executors > Browse and create a new one."
        for name in instances
    )
    return ProcessPoolBroken("\n".join(lines))


def _explain_executorlib(
    graph: pwf.schemas.Graph, registry: ExecutorRegistry | None
) -> ExecutorlibBroken:
    used = [node for node in walk_nodes(graph) if is_executorlib(node.executor)]
    lines = [
        f"An executorlib process failed while running {_running(used, registry)}.",
        _LOST_ERROR,
        PATH_HINT,
    ]
    return ExecutorlibBroken("\n".join(lines))
