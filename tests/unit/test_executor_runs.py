"""Nodes run through the GUI on the executors it creates, in threads and processes."""

import os
import unittest

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


if __name__ == "__main__":
    unittest.main()
