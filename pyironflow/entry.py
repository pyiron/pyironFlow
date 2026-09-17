"""Turning text typed into a port field into a value, and back again.

The browser cannot see a port's type hint, so it does no parsing at all: it sends
text, and everything here happens on the Python side. Values are JSONABLE, which is
both what a flowrep constant may hold and what a traitlet can carry to the browser.
"""

import ast
import math
import types
import typing
from enum import StrEnum
from typing import Annotated, Any, Literal, get_args, get_origin

import flowrep as fr
import pydantic

_LEAVES = (str, int, float, bool, type(None))
_UNIONS = (types.UnionType, typing.Union)


class EntryKind(StrEnum):
    """Which widget, if any, a port's hint earns in the GUI."""

    CHECKBOX = "checkbox"
    DROPDOWN = "dropdown"
    TEXT = "text"
    NONE = "none"


class EntryError(ValueError):
    """A rejected entry, with a message fit to show the user as-is."""


def normalize(hint: Any) -> Any:
    """*hint* with `Annotated` stripped and bare containers widened to JSONABLE.

    A bare `list` or `dict` says nothing about its contents, so the JSONABLE ceiling
    is the honest reading of it.
    """
    while get_origin(hint) is Annotated:
        hint = get_args(hint)[0]
    if hint is list:
        return list[fr.schemas.JSONABLE]
    if hint is dict:
        return dict[str, fr.schemas.JSONABLE]
    return hint


def is_jsonable_hint(hint: Any) -> bool:
    """Whether every value *hint* admits is JSONABLE.

    An unhinted port arrives as `None`, which `pyiron_workflow` cannot distinguish
    from a hint written literally as `None`, so both are excluded rather than risk
    offering a field on a port that accepts anything.
    """
    hint = normalize(hint)
    if hint is None:
        return False
    if hint is fr.schemas.JSONABLE or hint in _LEAVES:
        return True
    origin = get_origin(hint)
    if origin is Literal:
        return all(isinstance(member, _LEAVES) for member in get_args(hint))
    if origin in _UNIONS or origin is list:
        return all(is_jsonable_hint(arg) for arg in get_args(hint))
    if origin is dict:
        key, value = get_args(hint)
        return normalize(key) is str and is_jsonable_hint(value)
    return False


def _literal_members(hint: Any) -> list | None:
    """The members of a Literal hint, or of a union made only of Literals, else None."""
    hint = normalize(hint)
    if get_origin(hint) is Literal:
        members = list(get_args(hint))
    elif get_origin(hint) in _UNIONS and all(
        get_origin(arg) is Literal for arg in get_args(hint)
    ):
        members = [member for arg in get_args(hint) for member in get_args(arg)]
    else:
        return None
    return members if all(isinstance(m, _LEAVES) for m in members) else None


def entry_kind(hint: Any) -> EntryKind:
    """Which widget *hint* earns: a checkbox, a dropdown, a text field, or nothing."""
    hint = normalize(hint)
    if hint is bool:
        return EntryKind.CHECKBOX
    if _literal_members(hint) is not None:
        return EntryKind.DROPDOWN
    if is_jsonable_hint(hint):
        return EntryKind.TEXT
    return EntryKind.NONE


def options(hint: Any) -> list[str] | None:
    """The dropdown options for *hint*, rendered as text, or None if it has none."""
    members = _literal_members(hint)
    if members is None:
        return None
    return [render(member, hint) for member in members]


def _name(hint: Any) -> str:
    """*hint* named the way a user would recognise it in an error message."""
    if isinstance(hint, type):
        return hint.__name__
    return str(hint).replace("typing.", "")


def _admits_str(hint: Any) -> bool:
    """Whether raw text is a value *hint* would accept.

    Literal members are deliberately not counted. A Literal port is a dropdown whose
    options are rendered, so bare text never arrives on one, and counting them would
    make `Literal['a', '1']` ambiguous about what `1` means.
    """
    hint = normalize(hint)
    if hint is str or hint is fr.schemas.JSONABLE:
        return True
    if get_origin(hint) in _UNIONS:
        return any(_admits_str(arg) for arg in get_args(hint))
    return False


def _reject_non_finite(value: Any, text: str) -> None:
    """Raise unless every float in *value* is finite.

    `literal_eval('1e400')` yields `inf`, and `json.dumps(float('nan'))` emits `NaN`,
    which is not JSON and breaks the browser's `JSON.parse`.
    """
    if isinstance(value, float) and not math.isfinite(value):
        raise EntryError(f"{text} is not finite, and JSON cannot carry it.")
    if isinstance(value, list):
        for item in value:
            _reject_non_finite(item, text)
    elif isinstance(value, dict):
        for item in value.values():
            _reject_non_finite(item, text)


def _validate(value: Any, hint: Any, text: str) -> Any:
    """*value* checked strictly against *hint*, or an `EntryError` naming *text*."""
    try:
        result = pydantic.TypeAdapter(hint).validate_python(value, strict=True)
    except pydantic.ValidationError as err:
        raise EntryError(_rejection(text, hint)) from err
    if isinstance(value, bool) != isinstance(result, bool):
        # Strict `Literal['a', 1]` accepts True and returns 1.
        raise EntryError(_rejection(text, hint))
    _reject_non_finite(result, text)
    return result


def _rejection(text: str, hint: Any) -> str:
    message = f"{text} is not a valid {_name(hint)}."
    if _admits_str(hint):
        message += " Quote it to enter a string."
    return message


def _unparseable(text: str, hint: Any) -> str:
    return f"{text} is not a Python literal, and {_name(hint)} needs one."


def parse(text: str, hint: Any) -> fr.schemas.JSONABLE:
    """The value *text* means on a port hinted *hint*.

    A hint of exactly `str` takes the text verbatim. Otherwise the text is read as a
    Python literal and checked strictly against the hint. Text that is not a literal
    falls back to itself where the hint admits a string; text that *is* a literal but
    does not fit the hint is an error rather than a fallback, so a typo inside a
    container is reported instead of silently becoming a string.

    Callers pass non-blank text; blank text means "cleared" and never reaches here.
    """
    hint = normalize(hint)
    if hint is str:
        return text
    try:
        literal = ast.literal_eval(text)
    except (SyntaxError, ValueError, MemoryError, RecursionError):
        if _admits_str(hint):
            return text
        raise EntryError(_unparseable(text, hint)) from None
    return _validate(literal, hint, text)


def coerce(value: Any, hint: Any) -> fr.schemas.JSONABLE:
    """*value* re-checked against *hint*, for a cached value whose port may have moved."""
    hint = normalize(hint)
    return _validate(value, hint, repr(value))


def render(value: Any, hint: Any) -> str:
    """*value* as text a field can show and `parse` can read back unchanged."""
    return value if normalize(hint) is str else repr(value)
