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
from collections.abc import Callable, Iterable
from concurrent import futures
from typing import Any, TypeAlias

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
