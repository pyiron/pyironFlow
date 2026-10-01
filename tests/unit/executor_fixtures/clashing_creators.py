"""Defines a creator whose name clashes with one in `pyironflow.executors_lib`."""

from concurrent import futures


def thread_pool_executor(
    max_workers: int | None = None,
) -> futures.ThreadPoolExecutor:
    return futures.ThreadPoolExecutor(max_workers=max_workers)
