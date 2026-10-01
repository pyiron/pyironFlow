import pickle
import threading
import unittest
from concurrent import futures

import flowrep as fr
import pyiron_workflow as pwf

from pyironflow import executors, executors_lib
from tests.unit.executor_fixtures import clashing_creators, extra_creators

LIB_CREATORS = [
    "thread_pool_executor",
    "process_pool_executor",
    "thread_pool_executor_instructions",
    "process_pool_executor_instructions",
]


class TestValidateCreator(unittest.TestCase):
    def test_the_library_creators_are_valid(self):
        for name in LIB_CREATORS:
            with self.subTest(name=name):
                executors.validate_creator(getattr(executors_lib, name))

    def test_rejections_say_why(self):
        cases = [
            (extra_creators.NOT_CALLABLE, "not callable"),
            (extra_creators._hidden, "no public name"),
            (extra_creators.positional_only, "positional-only"),
            (extra_creators.star_args, r"variadic \(\*args\)"),
            (extra_creators.not_jsonable, "not JSONABLE"),
            (extra_creators.unhinted, "has no type hint"),
            (extra_creators.wrong_return, "must be hinted to return"),
        ]
        for obj, reason in cases:
            with (
                self.subTest(reason=reason),
                self.assertRaisesRegex(executors.InvalidCreator, reason),
            ):
                executors.validate_creator(obj)

    def test_variadic_keywords_are_rejected(self):
        def kw(**kwargs: int) -> futures.ThreadPoolExecutor:
            return futures.ThreadPoolExecutor()

        with self.assertRaisesRegex(executors.InvalidCreator, r"\*\*kwargs"):
            executors.validate_creator(kw)

    def test_unresolvable_hints_are_rejected(self):
        def bad(x: "Nope" = 1) -> futures.ThreadPoolExecutor:  # type: ignore[name-defined] # noqa: F821
            return futures.ThreadPoolExecutor()

        with self.assertRaisesRegex(executors.InvalidCreator, "do not resolve"):
            executors.validate_creator(bad)

    def test_a_callable_without_a_signature_is_rejected(self):
        with self.assertRaisesRegex(executors.InvalidCreator, "signature"):
            executors.validate_creator(ValueError)

    def test_is_valid_creator(self):
        self.assertTrue(executors.is_valid_creator(extra_creators.tagged_thread_pool))
        self.assertFalse(executors.is_valid_creator(extra_creators.wrong_return))


class TestFindCreators(unittest.TestCase):
    def test_the_library_alone(self):
        self.assertEqual(LIB_CREATORS, list(executors.find_creators([executors_lib])))

    def test_a_user_module_adds_only_its_public_valid_creators(self):
        found = executors.find_creators([executors_lib, extra_creators])
        self.assertEqual([*LIB_CREATORS, "tagged_thread_pool"], list(found))
        self.assertIs(executors_lib.thread_pool_executor, found["thread_pool_executor"])

    def test_one_creator_under_two_names_is_kept_once(self):
        alias = type(executors_lib)("alias")
        alias.another_name = executors_lib.thread_pool_executor
        found = executors.find_creators([executors_lib, alias])
        self.assertEqual(LIB_CREATORS, list(found))

    def test_a_creator_bound_to_a_private_name_is_skipped(self):
        private = type(executors_lib)("private")
        private._alias = extra_creators.tagged_thread_pool
        self.assertEqual({}, executors.find_creators([private]))

    def test_a_clash_names_both_modules(self):
        with self.assertRaisesRegex(
            ValueError,
            r"'thread_pool_executor' is defined by both pyironflow\.executors_lib "
            r"and tests\.unit\.executor_fixtures\.clashing_creators",
        ):
            executors.find_creators([executors_lib, clashing_creators])


class TestCreatorParameters(unittest.TestCase):
    def test_hints_and_defaults(self):
        (prefix,) = executors.creator_parameters(extra_creators.tagged_thread_pool)
        self.assertEqual(executors.CreatorParameter("prefix", str, "extra"), prefix)
        self.assertFalse(prefix.required)

    def test_a_parameter_without_a_default_is_required(self):
        def needs(n: int) -> futures.ThreadPoolExecutor:
            return futures.ThreadPoolExecutor(max_workers=n)

        (n,) = executors.creator_parameters(needs)
        self.assertTrue(n.required)
        self.assertIs(executors.NO_DEFAULT, n.default)
        self.assertEqual("NO_DEFAULT", repr(n.default))


class TestExecutorsLib(unittest.TestCase):
    def test_the_process_pool_instance_spawns(self):
        pool = executors_lib.process_pool_executor(max_workers=1)
        self.addCleanup(pool.shutdown)
        self.assertEqual("spawn", pool._mp_context.get_start_method())

    def test_creators_build_what_they_promise(self):
        thread = executors_lib.thread_pool_executor(max_workers=1)
        self.addCleanup(thread.shutdown)
        self.assertIsInstance(thread, futures.ThreadPoolExecutor)
        for name in [
            "thread_pool_executor_instructions",
            "process_pool_executor_instructions",
        ]:
            with self.subTest(name=name):
                self.assertIsInstance(
                    getattr(executors_lib, name)(), pwf.ExecutorInstructions
                )


@fr.atomic("out")
def ident(x: int = 0) -> int:
    return x


def _registry() -> executors.ExecutorRegistry:
    return executors.ExecutorRegistry(executors.find_creators([executors_lib]))


def _nested_workflow(label: str) -> pwf.Workflow:
    wf = pwf.Workflow(label)
    wf.a = pwf.node(ident)
    inner = pwf.Workflow("inner")
    inner.b = pwf.node(ident)
    wf.inner = inner
    return wf


class TestRegistry(unittest.TestCase):
    def setUp(self):
        self.registry = _registry()
        self.addCleanup(self.registry.close)

    def test_create_records_how_it_was_made(self):
        created = self.registry.create(
            "  pool  ", "thread_pool_executor", {"max_workers": 2}
        )
        self.assertEqual("pool", created.name)
        self.assertIs(executors_lib.thread_pool_executor, created.creator)
        self.assertEqual({"max_workers": 2}, created.kwargs)
        self.assertIsInstance(created.value, futures.ThreadPoolExecutor)
        self.assertEqual({"pool": created}, self.registry.created)

    def test_create_refuses_blank_and_held_names(self):
        self.registry.create("pool", "thread_pool_executor_instructions", {})
        for name, message in [
            ("  ", "Give the executor a name."),
            ("pool", "An executor named 'pool' already exists."),
        ]:
            with self.subTest(name=name), self.assertRaises(ValueError) as caught:
                self.registry.create(name, "thread_pool_executor_instructions", {})
            self.assertEqual(message, str(caught.exception))

    def test_a_creator_error_propagates_and_adds_nothing(self):
        with self.assertRaises(ValueError):
            self.registry.create("p", "thread_pool_executor", {"max_workers": 0})
        self.assertEqual({}, self.registry.created)

    def test_default_name_avoids_held_names(self):
        first = self.registry.default_name("thread_pool_executor")
        self.assertTrue(first.startswith("thread_pool_executor"))
        self.registry.create(first, "thread_pool_executor_instructions", {})
        second = self.registry.default_name("thread_pool_executor")
        self.assertTrue(second.startswith("thread_pool_executor"))
        self.assertNotEqual(first, second)

    def test_name_of_is_by_identity(self):
        created = self.registry.create("i", "thread_pool_executor_instructions", {})
        self.assertEqual("i", self.registry.name_of(created.value))
        self.assertIsNone(
            self.registry.name_of(executors_lib.thread_pool_executor_instructions())
        )
        self.assertIsNone(self.registry.name_of(None))

    def test_adopt_names_externals_once(self):
        value = executors_lib.thread_pool_executor_instructions()
        first = self.registry.adopt(value)
        self.assertTrue(first.name.startswith(executors.EXTERNAL))
        self.assertIsNone(first.creator)
        self.assertEqual({}, first.kwargs)
        self.assertIs(first, self.registry.adopt(value))
        other = self.registry.adopt(executors_lib.thread_pool_executor_instructions())
        self.assertTrue(other.name.startswith(executors.EXTERNAL))
        self.assertNotEqual(first.name, other.name)

    def test_adopt_from_walks_nested_nodes(self):
        wf = _nested_workflow("wf")
        outer = executors_lib.thread_pool_executor_instructions()
        inner = executors_lib.thread_pool_executor_instructions()
        wf.a.executor = outer
        wf.inner.b.executor = inner
        self.registry.adopt_from(wf)
        self.assertEqual(
            [outer, inner], [c.value for c in self.registry.created.values()]
        )

    def test_delete_clears_every_node_holding_it(self):
        created = self.registry.create("t", "thread_pool_executor", {})
        first, second = _nested_workflow("one"), _nested_workflow("two")
        first.a.executor = created.value
        first.inner.b.executor = created.value
        second.a.executor = created.value
        keep = executors_lib.thread_pool_executor_instructions()
        second.inner.b.executor = keep
        self.registry.delete("t", [first, second])
        self.assertIsNone(first.a.executor)
        self.assertIsNone(first.inner.b.executor)
        self.assertIsNone(second.a.executor)
        self.assertIs(keep, second.inner.b.executor)
        self.assertEqual({}, self.registry.created)
        with self.assertRaises(RuntimeError):
            created.value.submit(int)

    def test_deleting_instructions_needs_no_shutdown(self):
        self.registry.create("i", "thread_pool_executor_instructions", {})
        self.registry.delete("i", [])
        self.assertEqual({}, self.registry.created)

    def test_close_shuts_instances_down_and_forgets_everything(self):
        created = self.registry.create("t", "thread_pool_executor", {})
        self.registry.create("i", "thread_pool_executor_instructions", {})
        self.registry.close()
        self.assertEqual({}, self.registry.created)
        with self.assertRaises(RuntimeError):
            created.value.submit(int)


class _HoldsALock:
    def __init__(self):
        self.lock = threading.Lock()
        self.calls = []

    def hook(self, *args):
        self.calls.append(args)


class TestLocalOnly(unittest.TestCase):
    def test_calls_forward(self):
        holder = _HoldsALock()
        executors.LocalOnly(holder.hook)(1, 2)
        self.assertEqual([(1, 2)], holder.calls)

    def test_pickles_to_a_no_op_without_its_owner(self):
        holder = _HoldsALock()
        copy = pickle.loads(pickle.dumps(executors.LocalOnly(holder.hook)))
        self.assertIsNone(copy(1, 2))
        self.assertEqual([], holder.calls)


if __name__ == "__main__":
    unittest.main()
