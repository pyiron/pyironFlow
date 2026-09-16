"""Typed structures shared between the widget and its serialization helpers."""

import dataclasses

import flowrep as fr

PortCache = dict[str, fr.schemas.JSONABLE]
"""Values typed into child node input fields, keyed by :func:`wf_extensions.port_cache_key`.

A key is present exactly when the user entered something that parsed, and absent
otherwise. Absence is the only marker for "nothing entered", which is what leaves
``None`` free to mean the user typed ``None`` on a port whose hint admits it. Never test
a cache entry against ``None`` to decide whether it exists; test membership.

Values are JSONABLE: the ceiling of what a traitlet can carry to the browser, and of
what a flowrep constant may hold. `pyironflow.entry` is what puts them here.
"""


@dataclasses.dataclass(frozen=True)
class InvalidEntry:
    """Text a user entered that could not be parsed, and the reason.

    Kept apart from the `PortCache` so that the cache stays exactly JSONABLE. A port
    with an entry here has no cached value: a rejected entry must not run on whatever
    was there before.
    """

    text: str
    message: str
