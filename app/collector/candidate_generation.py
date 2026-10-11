"""Generate conservative index candidates from PostgreSQL EXPLAIN plans."""

import re
from typing import Any

from app.verifier.candidates import (
    IndexCandidate,
    validate_index_candidate,
)

_COMPARISON = re.compile(
    r'(?<![\w.])"?([a-z_][a-z0-9_]*)"?\s*'
    r'(?:=|<=|>=|<>|!=|<|>|~~\*|~~|!~~\*|!~~)(?!=)'
)

_QUALIFIED_EQUALITY = re.compile(
    r'(?<![\w.])'
    r'(?:(?:"?([a-z_][a-z0-9_]*)"?)[.])?'
    r'"?([a-z_][a-z0-9_]*)"?\s*=\s*'
    r'(?:(?:"?([a-z_][a-z0-9_]*)"?)[.])?'
    r'"?([a-z_][a-z0-9_]*)"?'
    r'(?![\w])'
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
    """Suggest allowlisted indexes from simple filters and equality joins."""
    nodes = list(_walk_plans(plan))
    alias_to_table = {}

    for node in nodes:
        table = node.get("Relation Name")
        alias = node.get("Alias")
        if isinstance(table, str):
            alias_to_table[alias or table] = table
            alias_to_table.setdefault(table, table)

    candidates = []
    seen = set()

    def add_candidate(table, column):
        candidate = IndexCandidate(table_name=table, columns=(column,))
        if not validate_index_candidate(candidate).accepted:
            return
        key = (table, (column,))
        if key not in seen:
            seen.add(key)
            candidates.append(candidate)

    for node in nodes:
        if node.get("Node Type") == "Seq Scan":
            table = node.get("Relation Name")
            filter_text = node.get("Filter")

            if isinstance(table, str) and isinstance(filter_text, str):
                columns = set(_COMPARISON.findall(filter_text))
                if len(columns) == 1:
                    add_candidate(table, next(iter(columns)))

        # Join conditions can justify considering indexes on either side.
        for key in ("Hash Cond", "Merge Cond"):
            condition = node.get(key)
            if not isinstance(condition, str):
                continue

            for match in _QUALIFIED_EQUALITY.finditer(condition):
                left_alias, left_column, right_alias, right_column = (
                    match.groups()
                )
                if not left_alias or not right_alias:
                    continue

                left_table = alias_to_table.get(left_alias)
                right_table = alias_to_table.get(right_alias)

                if not left_table or not right_table:
                    continue
                if left_table == right_table:
                    continue

                add_candidate(left_table, left_column)
                add_candidate(right_table, right_column)

    return candidates
