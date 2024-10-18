"""
For graphical representations of data.
"""

from __future__ import annotations

from typing import Optional

import numpy as np
import pandas

from pyiron_workflow import as_function_node


@as_function_node("fig")
def PlotDataFrame(df: pandas.DataFrame, x: Optional[list | np.ndarray] = None):
    from matplotlib import pyplot as plt

    fig, ax = plt.subplots()
    plot = df.plot(x=x, ax=ax)
    return plt.show()


@as_function_node("fig")
def Scatter(
    x: Optional[list | np.ndarray] = None, y: Optional[list | np.ndarray] = None
):
    from matplotlib import pyplot as plt

    plt.scatter(x, y)
    return plt.show()


@as_function_node("fig")
def ShowArray(mat: Optional[np.ndarray]):
    from matplotlib import pyplot as plt

    plt.imshow(mat)
    return plt.show()


@as_function_node("fig")
def Histogram(x: Optional[list | np.ndarray], bins: int = 50):
    from matplotlib import pyplot as plt

    plt.hist(x, bins=bins)
    return plt.show()


@as_function_node("axis")
def Plot(
    x: Optional[list | np.ndarray | pandas.core.series.Series] = None,
    y: Optional[list | np.ndarray | pandas.core.series.Series] = None,
    axis: Optional[object] = None,
    title: Optional[str] = "",
    color: Optional[str] = "b",
    symbol: Optional[str] = "o",
    legend_label: Optional[str] = "",
):
    from matplotlib import pyplot as plt

    if axis is None:
        axis = plt
        axis.title = title
    else:
        axis.set_title(title)  # Set the title of the plot
    axis.plot(x, y, color=color, marker=symbol, label=legend_label)

    return axis


@as_function_node("linspace")
def Linspace(
    start: Optional[int | float] = 0.0,
    stop: Optional[int | float] = 1.0,
    num: Optional[int] = 50,
    endpoint: Optional[bool] = True,
):
    from numpy import linspace

    return linspace(start, stop, num, endpoint=endpoint)


@as_function_node("mean")
def Mean(numbers: list | np.ndarray | float | int):
    return np.mean(numbers)


@as_function_node("axes")
def Subplot(
    nrows: Optional[int] = 1,
    ncols: Optional[int] = 1,
    sharex: Optional[bool] = False,
    sharey: Optional[bool] = False,
):
    from matplotlib import pyplot as plt

    _, axes = plt.subplots(nrows, ncols, sharex=sharex, sharey=sharey)
    return axes


@as_function_node("axis")
def Title(axis: Optional[object] = None, title: Optional[str] = ""):
    from matplotlib import pyplot as plt

    if axis is None:
        axis = plt

    return axis.set_title(title)
