"""Compare PostgreSQL plans using HypoPG hypothetical indexes."""

import json
import math
from dataclasses import dataclass
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.collector.validator import (
    contains_parameter_reference,
    validate_select,
)
from app.db.connections import sandbox_engine
from app.verifier.candidates import (
    IndexCandidate,
    validate_index_candidate,
)


@dataclass(frozen=True, slots=True)
class HypoPGResult:
    """Result of comparing baseline and hypothetical-index plans."""

    status: str
    reason: str
    baseline_cost: float | None = None
    candidate_cost: float | None = None
    baseline_node_type: str | None = None
    candidate_node_type: str | None = None
    baseline_index_names: tuple[str, ...] = ()
    candidate_index_names: tuple[str, ...] = ()
    candidate_index_name: str | None = None
    candidate_index_used: bool = False
    baseline_plan: dict[str, Any] | None = None
    candidate_plan: dict[str, Any] | None = None


def _index_ddl(candidate: IndexCandidate) -> str:
    """Build index DDL from validated identifiers and operator classes."""
    validation = validate_index_candidate(candidate)
    if not validation.accepted:
        raise ValueError(validation.reason)

    definitions: list[str] = []
    operator_classes = candidate.operator_classes or (
        None,
    ) * len(candidate.columns)

    for column, operator_class in zip(
        candidate.columns, operator_classes
    ):
        definition = f'"{column}"'
        if operator_class is not None:
            definition += f" {operator_class}"
        definitions.append(definition)

    columns = ", ".join(definitions)
    return f'CREATE INDEX ON "{candidate.table_name}" ({columns})'


def _extract_plan(raw_plan: Any) -> dict[str, Any]:
    """Extract the root plan from PostgreSQL EXPLAIN JSON."""
    if isinstance(raw_plan, str):
        raw_plan = json.loads(raw_plan)

    if (
        not isinstance(raw_plan, list)
        or not raw_plan
        or not isinstance(raw_plan[0], dict)
        or not isinstance(raw_plan[0].get("Plan"), dict)
    ):
        raise ValueError("Unexpected EXPLAIN JSON structure.")

    return raw_plan[0]["Plan"]


def _plan_total_cost(plan: dict[str, Any]) -> float:
    """Read and validate the root node's estimated total cost."""
    cost = plan.get("Total Cost")
    if isinstance(cost, bool) or not isinstance(cost, (int, float)):
        raise TypeError("EXPLAIN root plan has no valid Total Cost.")
    value = float(cost)
    if not math.isfinite(value) or value < 0:
        raise ValueError("EXPLAIN root plan has no valid Total Cost.")
    return value


def _collect_index_names(plan: dict[str, Any]) -> tuple[str, ...]:
    """Collect index names from actual PostgreSQL index scan nodes."""
    names: set[str] = set()
    index_scan_nodes = {
        "Index Scan",
        "Index Only Scan",
        "Bitmap Index Scan",
    }

    def visit(node: dict[str, Any]) -> None:
        index_name = node.get("Index Name")
        if (
            node.get("Node Type") in index_scan_nodes
            and isinstance(index_name, str)
        ):
            names.add(index_name)

        children = node.get("Plans", [])
        if isinstance(children, list):
            for child in children:
                if isinstance(child, dict):
                    visit(child)

    visit(plan)
    return tuple(sorted(names))


def _candidate_index_was_used(
    baseline_plan: dict[str, Any],
    candidate_plan: dict[str, Any],
    candidate_index_name: str,
) -> bool:
    """Require the exact proposed hypothetical index in the candidate plan."""
    baseline_indexes = set(_collect_index_names(baseline_plan))
    candidate_indexes = set(_collect_index_names(candidate_plan))

    return (
        candidate_index_name not in baseline_indexes
        and candidate_index_name in candidate_indexes
    )


async def compare_hypothetical_index(
    sql: str,
    candidate: IndexCandidate,
) -> HypoPGResult:
    """Compare estimated costs and verify the exact hypothetical index."""
    validation = validate_index_candidate(candidate)
    if not validation.accepted:
        return HypoPGResult("rejected", validation.reason)

    query_validation = validate_select(sql)
    if not query_validation.accepted:
        return HypoPGResult("rejected", query_validation.reason)

    if contains_parameter_reference(sql):
        return HypoPGResult(
            "rejected",
            "Unresolved parameter references are not supported.",
        )

    result: HypoPGResult | None = None
    cleanup_failed = False

    try:
        async with sandbox_engine.connect() as conn:
            try:
                # Start from a clean hypothetical-index state.
                await conn.execute(text("SELECT hypopg_reset()"))

                baseline_result = await conn.exec_driver_sql(
                    f"EXPLAIN (FORMAT JSON) {sql}"
                )
                baseline_plan = _extract_plan(
                    baseline_result.scalar_one()
                )

                hypothetical_result = await conn.execute(
                    text(
                        "SELECT indexname "
                        "FROM hypopg_create_index(:ddl)"
                    ),
                    {"ddl": _index_ddl(candidate)},
                )
                candidate_index_name = hypothetical_result.scalar_one()

                if not isinstance(candidate_index_name, str):
                    raise TypeError(
                        "HypoPG did not return a valid hypothetical index name."
                    )

                candidate_result = await conn.exec_driver_sql(
                    f"EXPLAIN (FORMAT JSON) {sql}"
                )
                candidate_plan = _extract_plan(
                    candidate_result.scalar_one()
                )

                candidate_used = _candidate_index_was_used(
                    baseline_plan,
                    candidate_plan,
                    candidate_index_name,
                )
                baseline_cost = _plan_total_cost(baseline_plan)
                candidate_cost = _plan_total_cost(candidate_plan)

                result = HypoPGResult(
                    status="compared",
                    reason=(
                        "The exact proposed hypothetical index appears "
                        "in the candidate plan."
                        if candidate_used
                        else (
                            "Plans compared, but the exact proposed "
                            "hypothetical index was not selected."
                        )
                    ),
                    baseline_cost=baseline_cost,
                    candidate_cost=candidate_cost,
                    baseline_node_type=baseline_plan.get("Node Type"),
                    candidate_node_type=candidate_plan.get("Node Type"),
                    baseline_index_names=_collect_index_names(
                        baseline_plan
                    ),
                    candidate_index_names=_collect_index_names(
                        candidate_plan
                    ),
                    candidate_index_name=candidate_index_name,
                    candidate_index_used=candidate_used,
                    baseline_plan=baseline_plan,
                    candidate_plan=candidate_plan,
                )

            finally:
                # Cleanup failure must not be reported as successful verification.
                try:
                    await conn.execute(text("SELECT hypopg_reset()"))
                except SQLAlchemyError:
                    cleanup_failed = True
                    await conn.invalidate()

    except Exception as exc:
        return HypoPGResult(
            status="failed",
            reason=f"Plan comparison failed: {type(exc).__name__}.",
        )

    if cleanup_failed:
        return HypoPGResult(
            status="failed",
            reason="Plan comparison failed: HypoPG cleanup failure.",
        )

    if result is None:
        return HypoPGResult(
            status="failed",
            reason="Plan comparison failed: missing result.",
        )

    return result
