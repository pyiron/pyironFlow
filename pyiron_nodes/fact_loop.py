import pyiron_workflow as pwf
from pyiron_nodes.loop_nodes import fib
from pyiron_workflow.nodes.while_loop import while_node_factory

def fact_loop():
    loop_node_class = while_node_factory(
        pwf.std.LessThan,
        fib.Fibonacci,
        [("next", "obj")],
        [("next", "this"),("now", "last")],
        True,
        False,
        )
    
    return loop_node_class


'''
import pyiron_workflow as pwf
from pyiron_nodes.loop_nodes import fib
from pyiron_workflow.nodes.while_loop import while_node_factory

blah_loop = while_node_factory(
    pwf.std.LessThan,
    fib.Fibonacci,
    [("next", "obj")],
    [("next", "this"),("now", "last")],
    True,
    False,
)



def Fibonacci(self, this, last):
    self.next = pwf.std.Add(this, last)
    self.now = standard.UserInput(this)
    return self.next, self.now




def fact_loop():
    return(while_node_factory(
        pwf.std.LessThan,
        fib.Fibonacci,
        [("next", "obj")],
        [("next", "this"),("now", "last")],
        True,
        False,
        )
    )


'''