import pyiron_workflow as pwf
from loop_nodes.fib import Fibonacci
from loop_nodes.standard import LessThan


fib_loop = type(
    "fib_loop",
    (pwf.while_node,),
    {
        "body_node_class" : Fibonacci,
        "test_node_class" : LessThan,
        "body_to_body_connections" : (('next', 'this'),('now', 'last'),),
        "body_to_test_connections" : (('next', 'obj'),),
        "strict_condition_hint" : False,
    }
) 