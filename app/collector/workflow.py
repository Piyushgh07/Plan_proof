"""End-to-end slow-query analysis workflow."""

from app.collector.candidate_generation import generate_candidates
from app.collector.plans import capture_plan
from app.collector.statistics import collect_query_stats
from app.db.persistence import persist_verification
from app.verifier.decision import decide_index
from app.verifier.hypopg import compare_hypothetical_index


async def analyze_slow_queries(limit: int = 10) -> dict:
    """Collect, analyze, verify, and persist eligible slow-query candidates."""
    if not 1 <= limit <= 100:
        raise ValueError("Limit must be between 1 and 100.")

    stats_list = await collect_query_stats(limit)
    results = []

    for stats in stats_list:
        item = {
            "queryid": stats.queryid,
            "calls": stats.calls,
            "total_exec_time_ms": stats.total_exec_time,
            "mean_exec_time_ms": stats.mean_exec_time,
            "plan_status": None,
            "candidates": [],
        }

        plan_result = await capture_plan(stats.query)
        item["plan_status"] = plan_result.status

        if plan_result.status != "captured":
            item["reason"] = plan_result.reason
            results.append(item)
            continue

        candidates = generate_candidates(plan_result.plan)

        if not candidates:
            item["reason"] = "No supported index candidates were generated."
            results.append(item)
            continue

        for candidate in candidates:
            comparison = await compare_hypothetical_index(
                stats.query, candidate
            )
            decision = decide_index(comparison)

            await persist_verification(
                stats.query,
                candidate,
                comparison,
                decision,
                source="heuristic",
                calls=stats.calls,
                total_exec_time_ms=stats.total_exec_time,
                mean_exec_time_ms=stats.mean_exec_time,
            )

            item["candidates"].append({
                "table": candidate.table_name,
                "columns": list(candidate.columns),
                "comparison_status": comparison.status,
                "decision": decision.status,
                "reason": decision.reason,
                "improvement_percent": decision.improvement_percent,
            })

        results.append(item)

    return {
        "queries_collected": len(stats_list),
        "queries_analyzed": sum(
            result["plan_status"] == "captured" for result in results
        ),
        "results": results,
    }
