
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class QueryStats:
    queryid: int
    calls: int
    total_exec_time: float
    mean_exec_time: float
    rows: int
    query: str
