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


LockedPorts = dict[str, fr.schemas.JSONABLE]
"""Values frozen into constant nodes, keyed by :func:`wf_extensions.port_cache_key`.

A key is present exactly when that port is fed by a flowrep constant, which the GUI
draws as a read-only value on the port rather than as a node of its own.

Kept apart from the `PortCache` because the two mean different things to a run: a cached
value is passed in as workflow input when the run starts, while a locked value is already
in the graph as a constant node and must not be passed again. The separation is also what
lets a locked value sit on a port whose hint has no entry field at all, which
`cached_run_kwargs` would choke on.
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
