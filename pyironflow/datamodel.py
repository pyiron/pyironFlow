"""Typed structures shared between the widget and its serialization helpers."""

import dataclasses
from typing import Any


@dataclasses.dataclass(frozen=True)
class PortCacheEntry:
    """One value a user typed into a child node's input port field."""

    value: Any


PortCache = dict[str, PortCacheEntry]
"""Values typed in the GUI, keyed by :func:`wf_extensions.port_cache_key`."""
