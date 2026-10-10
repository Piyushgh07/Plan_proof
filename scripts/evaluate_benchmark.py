
"""Evaluate the Plan Proof workload against the sandbox database."""

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy.exc import SQLAlchemyError

from app.benchmark.workload import WORKLOAD
from app.collector.validator import contains_parameter_reference, validate_select
from app.db.connections import sandbox_engine
from app.verifier.candidates import IndexCandidate
from app.verifier.decision import decide_index
from app.verifier.hypopg import compare_hypothetical_index
from app.verifier.plan_analysis import summarize_plan


# Explicit mapping: benchmark case ID -> proposed index.
CANDIDATES: dict[str, IndexCandidate] = {
    "Q001": IndexCandidate("orders", ("user_id",)),
    "Q002": IndexCandidate("order_items", ("order_id",)),
    "Q005": IndexCandidate("events", ("user_id",)),
    "Q008": IndexCandidate("events", ("user_id",)),
    "Q012": IndexCandidate("products", ("name",), ("text_pattern_ops",)),
    "Q015": IndexCandidate("order_items", ("order_id",)),
    "Q021": IndexCandidate("order_items", ("order_id",)),
    "Q025": IndexCandidate("orders", ("status", "total_amount")),
    "Q026": IndexCandidate("users", ("country", "is_active")),
    "Q027": IndexCandidate("orders", ("user_id", "status")),
    "Q033": IndexCandidate("products", ("name",), ("text_pattern_ops",)),
    "Q035": IndexCandidate("events", ("user_id",)),
    "Q039": IndexCandidate("users", ("country", "is_active")),
}


def extract_root_plan(raw: Any) -> dict[str, Any]:
    """Extract the root plan from EXPLAIN FORMAT JSON output."""
    if isinstance(raw, str):
        raw = json.loads(raw)

    if (
        not isinstance(raw, list)
        or not raw
        or not isinstance(raw[0], dict)
        or not isinstance(raw[0].get("Plan"), dict)
    ):
        raise ValueError("Unexpected EXPLAIN JSON structure.")

    return raw[0]["Plan"]


async def capture_baseline(sql: str) -> dict[str, Any]:
    """Capture a read-only estimated plan from the sandbox."""
    validation = validate_select(sql)

    if not validation.accepted:
        return {
            "status": "invalid",
            "reason": validation.reason,
            "estimated_cost": None,
            "root_node": None,
        }

    if contains_parameter_reference(sql):
        return {
            "status": "skipped",
            "reason": "Unresolved parameter references are unsupported.",
            "estimated_cost": None,
            "root_node": None,
        }

    try:
        async with sandbox_engine.connect() as conn:
            result = await conn.exec_driver_sql(
                f"EXPLAIN (FORMAT JSON) {sql}"
            )
            plan = extract_root_plan(result.scalar_one())

        return {
            "status": "captured",
            "reason": "Baseline plan captured successfully.",
            "estimated_cost": float(plan["Total Cost"]),
            "root_node": plan.get("Node Type"),
            "plan": plan,
            "plan_summary": summarize_plan(plan),
        }

    except (SQLAlchemyError, ValueError, TypeError, KeyError) as exc:
        return {
            "status": "failed",
            "reason": f"Baseline capture failed: {type(exc).__name__}.",
            "estimated_cost": None,
            "root_node": None,
        }


async def evaluate_case(case: Any) -> dict[str, Any]:
    """Evaluate one workload case without creating a permanent index."""
    baseline = await capture_baseline(case.sql)
    candidate = CANDIDATES.get(case.query_id)

    row: dict[str, Any] = {
        "query_id": case.query_id,
        "category": case.category,
        "sql": " ".join(case.sql.split()),
        "expected_action": case.expected_action,
        "problem_exists": case.problem_exists,
        "expected_index_columns": (
            list(case.expected_index_columns)
            if case.expected_index_columns is not None
            else None
        ),
        "baseline": baseline,
        "candidate": None,
        "decision": None,
        "label_comparison": "not_evaluated",
    }

    if candidate is None:
        row["candidate"] = {
            "status": "not_tested",
            "reason": "No candidate is explicitly mapped for this case.",
        }
        return row

    if baseline["status"] != "captured":
        row["candidate"] = {
            "status": "not_tested",
            "reason": "Candidate skipped because baseline capture failed.",
        }
        return row

    comparison = await compare_hypothetical_index(case.sql, candidate)
    decision = decide_index(comparison)

    baseline_plan = comparison.baseline_plan
    candidate_plan = comparison.candidate_plan

    row["candidate"] = {
        "table": candidate.table_name,
        "columns": list(candidate.columns),
        "status": comparison.status,
        "reason": comparison.reason,
        "estimated_cost": comparison.candidate_cost,
        "root_node": comparison.candidate_node_type,
        "hypothetical_index_name": comparison.candidate_index_name,
        "index_used": comparison.candidate_index_used,
        "baseline_cost_from_comparison": comparison.baseline_cost,
        "baseline_plan": baseline_plan,
        "candidate_plan": candidate_plan,
        "baseline_plan_summary": (
            summarize_plan(baseline_plan)
            if isinstance(baseline_plan, dict)
            else None
        ),
        "candidate_plan_summary": (
            summarize_plan(candidate_plan)
            if isinstance(candidate_plan, dict)
            else None
        ),
    }

    row["decision"] = {
    "status": decision.status,
    "reason": decision.reason,
    "explanation": decision.explanation,
    "estimated_cost_improvement_percent": decision.improvement_percent,
}

    if case.expected_action == "CREATE_INDEX":
        if decision.status == "accept":
            row["label_comparison"] = "agrees_with_expected_action"
        elif decision.status == "reject":
            row["label_comparison"] = "disagrees_with_expected_action"
        else:
            row["label_comparison"] = "inconclusive"

    return row


async def main() -> None:
    try:
        rows = []

        for case in WORKLOAD:
            print(f"Evaluating {case.query_id}...", flush=True)

            try:
                row = await evaluate_case(case)
            except Exception as exc:
                # Preserve remaining results if one case unexpectedly fails.
                row = {
                    "query_id": case.query_id,
                    "category": case.category,
                    "expected_action": case.expected_action,
                    "baseline": {"status": "failed"},
                    "candidate": {
                        "status": "failed",
                        "reason": f"Unexpected error: {type(exc).__name__}.",
                    },
                    "decision": None,
                    "label_comparison": "not_evaluated",
                }

            rows.append(row)

        decisions = [
            row["decision"]["status"]
            for row in rows
            if row.get("decision") is not None
        ]

        comparisons = [
            row["label_comparison"]
            for row in rows
            if row.get("label_comparison") != "not_evaluated"
        ]

        summary = {
            "total_cases": len(rows),
            "baseline_captured": sum(
                row["baseline"]["status"] == "captured"
                for row in rows
            ),
            "baseline_invalid": sum(
                row["baseline"]["status"] == "invalid"
                for row in rows
            ),
            "baseline_failed": sum(
                row["baseline"]["status"] == "failed"
                for row in rows
            ),
            "candidates_mapped": len(CANDIDATES),
            "candidate_comparisons": len(decisions),
            "accepted": decisions.count("accept"),
            "rejected": decisions.count("reject"),
            "inconclusive": decisions.count("inconclusive"),
            "expected_create_index_cases_evaluated": len(comparisons),
            "agreements_with_create_index_labels": comparisons.count(
                "agrees_with_expected_action"
            ),
            "disagreements_with_create_index_labels": comparisons.count(
                "disagrees_with_expected_action"
            ),
            "inconclusive_create_index_labels": comparisons.count(
                "inconclusive"
            ),
            "notes": [
                "Planner costs are estimates, not measured execution times.",
                "Expected labels are benchmark annotations, not ground-truth proof.",
                "NO_CHANGE cases without a mapped candidate are not classified.",
                "No permanent indexes are created by this runner.",
            ],
        }

        report = {
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "database": "sandbox",
            "summary": summary,
            "results": rows,
        }

        output = Path("reports/benchmark-evaluation.json")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(report, indent=2) + "\n",
            encoding="utf-8",
        )

        print("\n=== BENCHMARK SUMMARY ===")
        print(json.dumps(summary, indent=2))
        print(f"\nFull report written to: {output}")

    finally:
        # Dispose of the engine in the same event loop used by main().
        await sandbox_engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
