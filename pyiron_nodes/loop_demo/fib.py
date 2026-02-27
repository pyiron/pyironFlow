import pyiron_workflow as pwf
from pyiron_workflow import as_function_node, as_macro_node
from pyiron_nodes.loop_nodes import standard


@as_macro_node()
def Fibonacci(self, this, last):
    self.next = pwf.std.Add(this, last)
    self.now = standard.UserInput(this)
    return self.next, self.now
