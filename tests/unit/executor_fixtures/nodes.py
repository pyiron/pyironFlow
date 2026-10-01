"""Nodes whose runs reveal where they ran. Importable, so pool children find them."""

import os
import pickle
import threading
from concurrent import futures
from typing import Any

import flowrep as fr

THREADS: dict[int, str] = {}
"""Per `record_thread` input, the name of the thread it ran on (same process only)."""


@fr.atomic("thread")
def record_thread(x: int = 0) -> str:
    THREADS[x] = threading.current_thread().name
    return THREADS[x]


@fr.atomic("pid")
def report_pid(x: int = 0) -> int:
    return os.getpid()


@fr.atomic("out")
def fail(x: int = 0) -> int:
    raise RuntimeError("fixture failure")


class PicklingExecutor(futures.Executor):
    """Runs each call inline on a pickled copy of it, keeping the bytes it sent.

    Shows what a process pool would be sent, without starting one.
    """

    def __init__(self) -> None:
        self.payloads: list[bytes] = []

    def submit(self, fn: Any, /, *args: Any, **kwargs: Any) -> futures.Future:
        payload = pickle.dumps((fn, args, kwargs))
        self.payloads.append(payload)
        fn, args, kwargs = pickle.loads(payload)
        future: futures.Future = futures.Future()
        future.set_result(fn(*args, **kwargs))
        return future
