"""Stand-ins that look, by name, like executorlib's classes, without importing it."""

from concurrent import futures

_EXECUTORLIB = "executorlib.standalone.interactive.communication"


class FakeExecutorlibExecutor(futures.Executor):
    __module__ = "executorlib.executor.single"


class FakeExecutorlibSubclass(FakeExecutorlibExecutor):
    """Like pyiron_workflow's wrappers, which live outside executorlib."""

    __module__ = "pyiron_workflow.executorlib"


class NotExecutorlibExecutor(futures.Executor):
    __module__ = "executorlib_lookalike.executor"


class ExecutorlibSocketError(RuntimeError):
    __module__ = _EXECUTORLIB


class SubclassedSocketError(ExecutorlibSocketError):
    __module__ = "somewhere.else"


class UnrelatedSocketError(RuntimeError):
    """Same name, different package."""

    __module__ = "elsewhere"
    __qualname__ = "ExecutorlibSocketError"


UnrelatedSocketError.__name__ = "ExecutorlibSocketError"


class OtherExecutorlibError(RuntimeError):
    """An executorlib error that is not a lost connection."""

    __module__ = _EXECUTORLIB
