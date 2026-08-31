import unittest

import pyiron_workflow as pwf

from pyironflow import PyironFlow


@pwf.as_function_node("signal")
def relu(x: float, bias: float = 0.0) -> float:
    return max(0.0, x - bias)


class TestVersion(unittest.TestCase):
    def test_instance(self):
        wf = pwf.Workflow("minimal_demo")
        wf.n1 = relu(0.2)
        wf.n2 = relu(-0.5)
        wf.accumulate = pwf.std.Add(wf.n1, wf.n2)
        wf.n3 = relu(wf.accumulate)

        pf = PyironFlow([wf])

        self.assertIsInstance(pf, PyironFlow)
