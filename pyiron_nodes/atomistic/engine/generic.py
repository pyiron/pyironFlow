from __future__ import annotations

from dataclasses import field
from typing import Optional

from pyiron_nodes.dev_tools import wf_data_class, wfMetaData


@wf_data_class()
class OutputEngine:
    calculator: Optional[callable] = field(
        default=None, metadata=wfMetaData(log_level=0)
    )
    engine_id: Optional[int] = field(default=None, metadata=wfMetaData(log_level=0))
    parameters: Optional[wf_data_class] = field(
        default=None, metadata=wfMetaData(log_level=10)
    )
    _do_not_serialize: bool = True
