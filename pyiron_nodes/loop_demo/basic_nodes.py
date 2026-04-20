import pyiron_workflow as pwf
from pyiron_workflow import as_function_node, as_macro_node


@as_function_node()
def add(a: float | int = 0, b: float | int = 0):
    added = a+b
    return added
    
    
@as_function_node()
def add_1(a: float | int = 0):
    return a+1


@as_function_node()
def divide(x: float | int = 0, y: float | int = 0):
    out = x/y
    return out

@as_function_node()
def multiply(x: float | int = 0, y: float | int = 0):
    out = x*y
    return out

@as_function_node()
def half(x: float | int = 0):
    x_halfed = x/2
    return x_halfed
 

@as_function_node()
def square(n):
    n_squared = n*n
    return n_squared
 

@as_macro_node()
def heron_step(self, S: float | int = 0, x_n: float | int = 0):
    self.divide = divide(S, x_n)    
    self.add = add(x_n, self.divide)
    self.half = half(self.add)

    return self.half, x_n
    
    
    
@as_macro_node()
def add_and_square_macro(self, n):

    self.add_1 = add_1(n)
    self.square = square(self.add_1)
      
    return self.square