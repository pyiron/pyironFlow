"""Executors for nodes: the callables that create them, and the ones the GUI holds.

A *Valid Creator* is a public callable taking only keyword-able parameters, each
hinted with a JSONABLE type (so the GUI can offer a field for it), and hinted to
return a `concurrent.futures.Executor` subclass or `pyiron_workflow.ExecutorInstructions`.

This module stays light: a process pool's child imports it to unpickle `LocalOnly`.
"""

from __future__ import annotations

import dataclasses
import inspect
import types
import typing
from collections.abc import Callable, Iterable, Iterator
from concurrent import futures
from typing import Any, TypeAlias

import flowrep as fr
import pyiron_workflow as pwf
from pyiron_workflow import datatypes

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


def walk_nodes(graph: datatypes.Graph) -> Iterator[datatypes.Node]:
    """Every node inside *graph*, depth first, each before its own children."""
    for node in graph.nodes.values():
        yield node
        if isinstance(node, datatypes.Graph):
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

    def adopt_from(self, graph: datatypes.Graph) -> None:
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

    def delete(self, name: str, graphs: Iterable[datatypes.Graph]) -> None:
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
