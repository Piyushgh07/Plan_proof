"""Generate conservative index candidates from PostgreSQL EXPLAIN plans."""

import re
from typing import Any

from app.verifier.candidates import (
    IndexCandidate,
    validate_index_candidate,
)


# Deliberately support only simple comparisons for the first heuristic.
_COMPARISON = re.compile(
    r'(?<![\w.])"?([a-z_][a-z0-9_]*)"?\s*'
    r'(?:=|<=|>=|<>|!=|<|>|~~\*|~~|!~~\*|!~~)(?!=)'
)


def _walk_plans(value: Any):
    """Yield every plan node in PostgreSQL JSON EXPLAIN output."""
    if isinstance(value, list):
        for item in value:
            yield from _walk_plans(item)
    elif isinstance(value, dict):
        if isinstance(value.get("Node Type"), str):
            yield value
        for key, child in value.items():
            if key in {"Plans", "Plan"}:
                yield from _walk_plans(child)


def generate_candidates(plan: Any) -> list[IndexCandidate]:
    """Suggest validated single-column indexes for simple Seq Scan filters."""
    candidates = []
    seen = set()

    for node in _walk_plans(plan):
        if node.get("Node Type") != "Seq Scan":
            continue

        table = node.get("Relation Name")
        filter_text = node.get("Filter")

        if not isinstance(table, str) or not isinstance(filter_text, str):
            continue

        columns = set(_COMPARISON.findall(filter_text))
        if len(columns) != 1:
            continue

        column = next(iter(columns))
        candidate = IndexCandidate(table_name=table, columns=(column,))

        if not validate_index_candidate(candidate).accepted:
            continue

        key = (candidate.table_name, candidate.columns)
        if key not in seen:
            seen.add(key)
            candidates.append(candidate)

    return candidates
