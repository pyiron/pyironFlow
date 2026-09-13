"""Typed structures shared between the widget and its serialization helpers."""

PortCache = dict[str, str | int | float | bool | None]
"""Values typed into child node input fields, keyed by :func:`wf_extensions.port_cache_key`.

A key is present exactly when the user entered something into that port's field, and
absent otherwise. Absence is the only marker for "nothing entered", which is what leaves
``None`` free to mean the user typed ``None`` on a port whose hint admits it. Never test
a cache entry against ``None`` to decide whether it exists; test membership.

The value types are what a JSON round trip through the GUI can carry. ``Literal`` hints
widen this no further: a literal of any other type, an enum member or bytes, cannot be
serialized to the browser in the first place.
"""
