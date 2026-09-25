import pathlib

import anywidget
import traitlets

MIN_RATIO = 0.05
MAX_RATIO = 0.95


class Splitter(anywidget.AnyWidget):
    """A draggable vertical bar dividing the two children of its parent box.

    Dragging sets ``ratio``, the fraction of the parent's width right of the bar;
    the owner observes it to size the boxes either side.
    """

    path = pathlib.Path(__file__).parent / "static"
    _esm = path / "splitter.js"
    _css = path / "splitter.css"
    ratio = traitlets.Float(0.85).tag(sync=True)

    @traitlets.validate("ratio")
    def _clamp(self, proposal: dict) -> float:
        return max(min(proposal["value"], MAX_RATIO), MIN_RATIO)
