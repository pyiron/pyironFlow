import unittest

import flowrep as fr
import pyiron_workflow as pwf
from pyiron_workflow.constructors import macro2workflow

from pyironflow import PyironFlow


@fr.atomic("signal")
def relu(x: float, bias: float = 0.0) -> float:
    return max(0.0, x - bias)


@fr.atomic("sum")
def add(a: float, b: float) -> float:
    return a + b


class TestVersion(unittest.TestCase):
    def test_instance(self):
        wf = pwf.Workflow("minimal_demo")
        wf.n1 = pwf.node(relu, x=0.2)
        wf.n2 = pwf.node(relu, x=-0.5)
        wf.accumulate = pwf.node(
            add,
            a=wf.n1.outputs.signal,
            b=wf.n2.outputs.signal,
        )
        wf.n3 = pwf.node(relu, x=wf.accumulate.outputs.sum)

        pf = PyironFlow([wf])

        self.assertIsInstance(pf, PyironFlow)


@fr.workflow
def has_own_io(x):
    y = relu(x)
    return y


class TestWorkflowValidation(unittest.TestCase):
    def test_rejects_a_macro(self):
        macro = pwf.node(has_own_io)
        with self.assertRaises(TypeError) as caught:
            PyironFlow([macro])
        self.assertIn("macro2workflow", str(caught.exception))

    def test_rejects_a_workflow_with_its_own_io(self):
        wf = macro2workflow(pwf.node(has_own_io))
        with self.assertRaises(ValueError) as caught:
            PyironFlow([wf])
        message = str(caught.exception)
        self.assertIn("wf.remove_input('x')", message)
        self.assertIn("wf.remove_output('y')", message)

    def test_names_the_offending_entry(self):
        clean = pwf.Workflow("clean")
        wf = macro2workflow(pwf.node(has_own_io))
        with self.assertRaises(ValueError) as caught:
            PyironFlow([clean, wf])
        self.assertIn("wf_list[1]", str(caught.exception))

    def test_accepts_a_workflow_with_no_io(self):
        wf = pwf.Workflow("clean")
        wf.n1 = pwf.node(relu)
        self.assertIsInstance(PyironFlow([wf]), PyironFlow)

    def test_accepts_the_default_empty_list(self):
        self.assertIsInstance(PyironFlow(), PyironFlow)

    def test_rejects_a_workflow_with_only_input(self):
        wf = pwf.Workflow("only_in")
        wf.n1 = pwf.node(relu)
        wf.set_inputs_to_unconnected_child_input(build_for_defaults=True)
        input_label = next(iter(wf.inputs))
        with self.assertRaises(ValueError) as caught:
            PyironFlow([wf])
        message = str(caught.exception)
        self.assertIn(input_label, message)
        self.assertIn(f"wf.remove_input({input_label!r})", message)
        self.assertNotIn("output", message)

    def test_rejects_a_workflow_with_only_output(self):
        wf = pwf.Workflow("only_out")
        wf.n1 = pwf.node(relu, x=0.1)
        wf.set_outputs_to_unconnected_child_output()
        output_label = next(iter(wf.outputs))
        with self.assertRaises(ValueError) as caught:
            PyironFlow([wf])
        message = str(caught.exception)
        self.assertIn(output_label, message)
        self.assertIn(f"wf.remove_output({output_label!r})", message)
        self.assertNotIn("input", message)

    def test_rejects_something_that_is_neither_workflow_nor_macro(self):
        with self.assertRaises(TypeError) as caught:
            PyironFlow(["not a workflow"])
        message = str(caught.exception)
        self.assertIn("str", message)
        self.assertNotIn("macro2workflow", message)
