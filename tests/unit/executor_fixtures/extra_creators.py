"""A user's module of executor creators, with distractors that are not Valid Creators."""

from concurrent import futures

from pyironflow.executors_lib import thread_pool_executor  # noqa: F401  (re-export)


def tagged_thread_pool(prefix: str = "extra") -> futures.ThreadPoolExecutor:
    return futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix=prefix)


def _hidden(prefix: str = "hidden") -> futures.ThreadPoolExecutor:
    return futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix=prefix)


def positional_only(prefix: str = "x", /) -> futures.ThreadPoolExecutor:
    return futures.ThreadPoolExecutor(thread_name_prefix=prefix)


def star_args(*prefixes: str) -> futures.ThreadPoolExecutor:
    return futures.ThreadPoolExecutor()


def not_jsonable(
    prefixes: tuple[str, str] = ("a", "b"),
) -> futures.ThreadPoolExecutor:
    return futures.ThreadPoolExecutor()


def unhinted(prefix="x") -> futures.ThreadPoolExecutor:  # type: ignore[no-untyped-def]
    return futures.ThreadPoolExecutor(thread_name_prefix=prefix)


def wrong_return(prefix: str = "x") -> int:
    return 0


NOT_CALLABLE = 42
