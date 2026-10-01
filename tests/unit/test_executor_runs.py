"""Nodes run through the GUI on the executors it creates, in threads and processes."""

import importlib.util
import os
import pathlib
import sys
import tempfile
import types
import unittest
import unittest.mock
from concurrent.futures import process

import ipywidgets as widgets
import pyiron_workflow as pwf
from pyiron_workflow.execution import RunStatus

from pyironflow import executors, executors_lib, reactflow
from tests.unit.executor_fixtures import extra_creators, nodes


def _widget(wf: pwf.Workflow) -> reactflow.PyironFlowWidget:
    return reactflow.PyironFlowWidget(
        wf=wf, log=widgets.Output(), out_widget=widgets.Output()
    )


class _RunsTestCase(unittest.TestCase):
    def setUp(self):
        self.registry = executors.ExecutorRegistry(
            executors.find_creators([executors_lib, extra_creators])
        )
        self.addCleanup(self.registry.close)

    def _create(self, creator: str, **kwargs) -> executors.ExecutorLike:
        name = self.registry.default_name(creator)
        return self.registry.create(name, creator, kwargs).value

    def _run_one(self, node, executor) -> reactflow.PyironFlowWidget:
        wf = pwf.Workflow("wf")
        wf.n = node
        wf.n.executor = executor
        widget = _widget(wf)
        widget.run_workflow(widget.wf)
        return widget


class TestThreadPools(_RunsTestCase):
    def test_instance(self):
        pool = self._create("thread_pool_executor", thread_name_prefix="gui_tp")
        self._run_one(pwf.node(nodes.record_thread, x=1), pool)
        self.assertTrue(nodes.THREADS[1].startswith("gui_tp_"))

    def test_instructions(self):
        instructions = self._create(
            "thread_pool_executor_instructions", thread_name_prefix="gui_tpi"
        )
        self._run_one(pwf.node(nodes.record_thread, x=2), instructions)
        self.assertTrue(nodes.THREADS[2].startswith("gui_tpi_"))

    def test_a_creator_from_a_user_module(self):
        pool = self._create("tagged_thread_pool", prefix="user_mod")
        self._run_one(pwf.node(nodes.record_thread, x=3), pool)
        self.assertTrue(nodes.THREADS[3].startswith("user_mod_"))

    def test_a_pull_uses_the_executor(self):
        pool = self._create("thread_pool_executor", thread_name_prefix="gui_pull")
        wf = pwf.Workflow("wf")
        wf.n = pwf.node(nodes.record_thread, x=4)
        wf.n.executor = pool
        widget = _widget(wf)
        widget.pull_workflow(widget.wf.nodes["n"])
        self.assertTrue(nodes.THREADS[4].startswith("gui_pull_"))


class TestProcessPools(_RunsTestCase):
    def _assert_ran_elsewhere(self, widget):
        self.assertNotEqual(os.getpid(), widget.last_run.outputs["n__pid"])
        self.assertEqual(RunStatus.FINISHED, widget._statuses["n"])

    def test_instance(self):
        pool = self._create("process_pool_executor", max_workers=1)
        self._assert_ran_elsewhere(self._run_one(pwf.node(nodes.report_pid), pool))

    def test_instructions(self):
        instructions = self._create("process_pool_executor_instructions", max_workers=1)
        self._assert_ran_elsewhere(
            self._run_one(pwf.node(nodes.report_pid), instructions)
        )

    def test_a_node_error_comes_back_readable(self):
        instructions = self._create("process_pool_executor_instructions", max_workers=1)
        with self.assertRaisesRegex(RuntimeError, "fixture failure"):
            self._run_one(pwf.node(nodes.fail), instructions)


class TestPayload(unittest.TestCase):
    def test_no_gui_state_is_sent(self):
        executor = nodes.PicklingExecutor()
        wf = pwf.Workflow("wf")
        wf.n = pwf.node(nodes.report_pid)
        wf.n.executor = executor
        widget = _widget(wf)
        widget.run_workflow(widget.wf)
        (payload,) = executor.payloads
        for forbidden in [b"PyironFlowWidget", b"ipywidgets", b"traitlets"]:
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, payload)


_PARENT_ONLY_SOURCE = """
import flowrep as fr

@fr.atomic("out")
def parent_only(x: int = 0) -> int:
    return x
"""


class TestPoolFailuresAreReadable(_RunsTestCase):
    def _node_from(self, module_name: str):
        """A node from a module that exists only in this process's `sys.modules`."""
        module = types.ModuleType(module_name)
        patcher = unittest.mock.patch.dict(sys.modules, {module_name: module})
        patcher.start()
        self.addCleanup(patcher.stop)
        exec(_PARENT_ONLY_SOURCE, module.__dict__)
        return pwf.node(module.parent_only)

    def test_the_preflight_refuses_a_notebook_node(self):
        pool = self._create("process_pool_executor", max_workers=1)
        widget = self._run_one(self._node_from("__main__"), pool)
        self.assertIsNone(widget.last_run)
        (shown,) = [o["text"] for o in widget.out_widget.outputs]
        self.assertIn("Process pool can't import:", shown)
        self.assertIn(
            "wf.n (executor 'ProcessPoolExecutor'): __main__.parent_only", shown
        )
        self.assertIn(executors.IMPORT_HINT, shown)

    def test_the_preflight_names_executors_from_the_registry(self):
        pool = self._create("process_pool_executor", max_workers=1)
        wf = pwf.Workflow("wf")
        wf.n = self._node_from("__main__")
        wf.n.executor = pool
        widget = _widget(wf)
        widget.executors = self.registry
        widget.run_workflow(widget.wf)
        (shown,) = [o["text"] for o in widget.out_widget.outputs]
        self.assertIn("(executor 'process_pool_executor_0')", shown)

    def test_a_pull_is_refused_too(self):
        pool = self._create("process_pool_executor_instructions", max_workers=1)
        wf = pwf.Workflow("wf")
        wf.n = self._node_from("__main__")
        wf.n.executor = pool
        widget = _widget(wf)
        widget.pull_workflow(widget.wf.nodes["n"])
        self.assertIsNone(widget.last_run)
        self.assertIn(
            "Process pool can't import:", widget.out_widget.outputs[0]["text"]
        )

    def test_a_broken_instance_is_explained(self):
        pool = self._create("process_pool_executor", max_workers=1)
        wf = pwf.Workflow("wf")
        wf.n = self._node_from("parent_only_nodes")
        wf.n.executor = pool
        widget = _widget(wf)
        widget.executors = self.registry
        with self.assertRaises(executors.ProcessPoolBroken) as caught:
            widget.run_workflow(widget.wf)
        self.assertIsInstance(caught.exception.__cause__, process.BrokenProcessPool)
        self.assertIn(
            "Pool 'process_pool_executor_0' is now permanently broken",
            str(caught.exception),
        )

    def test_broken_instructions_are_explained(self):
        instructions = self._create("process_pool_executor_instructions", max_workers=1)
        with self.assertRaises(executors.ProcessPoolBroken) as caught:
            self._run_one(self._node_from("parent_only_nodes"), instructions)
        self.assertIn("wf.n (executor 'ExecutorInstructions')", str(caught.exception))
        self.assertNotIn("permanently broken", str(caught.exception))

    @unittest.skipUnless(
        importlib.util.find_spec("executorlib"), "executorlib is not installed"
    )
    def test_a_crashed_executorlib_process_is_explained(self):
        """A module on a `sys.path` entry added this session, as a library root is."""
        import executorlib
        from executorlib.standalone.interactive import communication

        root = pathlib.Path(self.enterContext(tempfile.TemporaryDirectory()))
        (root / "session_path_nodes.py").write_text(
            _PARENT_ONLY_SOURCE.replace("parent_only", "session_only")
        )
        self.enterContext(
            unittest.mock.patch.object(sys, "path", [*sys.path, str(root)])
        )
        self.enterContext(unittest.mock.patch.dict(sys.modules))
        import session_path_nodes  # type: ignore[import-not-found]

        executor = executorlib.SingleNodeExecutor(max_workers=1)
        self.addCleanup(executor.shutdown)
        wf = pwf.Workflow("wf")
        wf.n = pwf.node(session_path_nodes.session_only)
        wf.n.executor = executor
        widget = _widget(wf)
        widget.executors = self.registry
        self.registry.adopt(executor)
        with self.assertRaises(executors.ExecutorlibBroken) as caught:
            widget.run_workflow(widget.wf)
        self.assertIsInstance(
            caught.exception.__cause__, communication.ExecutorlibSocketError
        )
        self.assertIn("wf.n (executor 'external_0')", str(caught.exception))
        self.assertIn(executors.PATH_HINT, str(caught.exception))


if __name__ == "__main__":
    unittest.main()
