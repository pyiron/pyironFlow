"""
For mathematical operations.
"""

from __future__ import annotations

import numpy as np

from pyiron_workflow import as_function_node


@as_function_node("sin")
def Sin(x: list | np.ndarray | float | int):
    return np.sin(x)


@as_function_node("cos")
def Cos(x: list | np.ndarray | float | int):
    return np.cos(x)


@as_function_node("tan")
def Tan(x: list | np.ndarray | float | int):
    return np.tan(x)


@as_function_node("arcsin")
def Arcsin(x: list | np.ndarray | float | int):
    arcsin = np.arcsin(x)
    return arcsin


@as_function_node("arccos")
def Arccos(x: list | np.ndarray | float | int):
    return np.arccos(x)


@as_function_node("arctan")
def Arctan(x: list | np.ndarray | float | int):
    return np.arctan(x)


@as_function_node("arctan2")
def Arctan2(x: list | np.ndarray | float | int, y: list | np.ndarray | float | int):
    return np.arctan2(y, x)
