"""
Wrappers to create executor instances or instructions from functions which are
explicitly typed with JSONable input (for GUI representation) and an
executor/instruction return value.
"""

import multiprocessing
from concurrent import futures

import pyiron_workflow as pwf


def thread_pool_executor(
    max_workers: int | None = None, thread_name_prefix: str = ""
) -> futures.ThreadPoolExecutor:
    return futures.ThreadPoolExecutor(
        max_workers=max_workers, thread_name_prefix=thread_name_prefix
    )


def process_pool_executor(
    max_workers: int | None = None, max_tasks_per_child: int | None = None
) -> futures.ProcessPoolExecutor:
    return futures.ProcessPoolExecutor(
        max_workers=max_workers,
        max_tasks_per_child=max_tasks_per_child,
        # As ExecutorInstructions forces: fork is unsafe from a threaded parent
        mp_context=multiprocessing.get_context("spawn"),
    )


def thread_pool_executor_instructions(
    max_workers: int | None = None, thread_name_prefix: str = ""
) -> pwf.ExecutorInstructions:
    return pwf.ExecutorInstructions(
        futures.ThreadPoolExecutor,
        kwargs=dict(max_workers=max_workers, thread_name_prefix=thread_name_prefix),
    )


def process_pool_executor_instructions(
    max_workers: int | None = None, max_tasks_per_child: int | None = None
) -> pwf.ExecutorInstructions:
    return pwf.ExecutorInstructions(
        futures.ProcessPoolExecutor,
        kwargs=dict(max_workers=max_workers, max_tasks_per_child=max_tasks_per_child),
    )
