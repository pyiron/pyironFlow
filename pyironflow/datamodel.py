import dataclasses
from typing import Any, NamedTuple


class Position(NamedTuple):
    x: float
    y: float


@dataclasses.dataclass(frozen=True)
class PortCacheEntry:
    value: Any
    position: Position


PortCache = dict[str, PortCacheEntry]
