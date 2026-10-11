"""End-to-end slow-query analysis workflow."""

from app.collector.candidate_generation import generate_candidates
from app.collector.llm_candidates import propose_candidates
from app.collector.plans import capture_plan
from app.collector.statistics import collect_query_stats
from app.collector.validator import contains_parameter_reference, validate_select
from app.db.persistence import persist_verification
from app.verifier.decision import decide_index
from app.verifier.hypopg import compare_hypothetical_index


async def analyze_query(sql: str) -> dict:
    """Analyze one submitted SELECT without guessing parameter values."""
    validation = validate_select(sql)
    if not validation.accepted:
        return {"status": "unsupported", "reason": validation.reason, "candidates": []}
    if contains_parameter_reference(sql):
        return {
            "status": "unsupported",
            "reason": "Unresolved SQL parameters such as $1 cannot be safely planned.",
            "candidates": [],
        }

    plan_result = await capture_plan(sql)
    if plan_result.status != "captured":
        return {
            "status": plan_result.status,
            "reason": plan_result.reason,
            "proposal_plan": plan_result.plan,
            "candidates": [],
        }

    batch = await propose_candidates(
        sql, plan_result.plan, generate_candidates(plan_result.plan)
    )
    results = []
    for proposal in batch.proposals:
        candidate = proposal.candidate
        comparison = await compare_hypothetical_index(sql, candidate)
        decision = decide_index(comparison)
        await persist_verification(
            sql,
            candidate,
            comparison,
            decision,
            source=proposal.source,
            proposal_rationale=proposal.rationale,
        )
        results.append(
            {
                "table": candidate.table_name,
                "columns": list(candidate.columns),
                "source": proposal.source,
                "proposal_rationale": proposal.rationale,
                "comparison_status": comparison.status,
                "comparison_reason": comparison.reason,
                "baseline_cost": comparison.baseline_cost,
                "candidate_cost": comparison.candidate_cost,
                "baseline_plan": comparison.baseline_plan,
                "candidate_plan": comparison.candidate_plan,
                "candidate_index_used": comparison.candidate_index_used,
                "decision": decision.status,
                "reason": decision.reason,
                "decision_explanation": decision.explanation,
                "improvement_percent": decision.improvement_percent,
            }
        )

    return {
        "status": "analyzed" if batch.proposals else "unsupported",
        "reason": None
        if batch.proposals
        else "No supported index candidates were generated.",
        "proposal_plan": plan_result.plan,
        "candidates": results,
        "proposal_source": batch.source,
        "proposal_status": batch.status,
        "proposal_reason": batch.reason,
    }


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

        batch = await propose_candidates(
            stats.query,
            plan_result.plan,
            generate_candidates(plan_result.plan),
        )
        item["proposal_source"] = batch.source
        item["proposal_status"] = batch.status
        item["proposal_reason"] = batch.reason

        if not batch.proposals:
            item["reason"] = "No supported index candidates were generated."
            results.append(item)
            continue

        for proposal in batch.proposals:
            candidate = proposal.candidate
            comparison = await compare_hypothetical_index(stats.query, candidate)
            decision = decide_index(comparison)

            await persist_verification(
                stats.query,
                candidate,
                comparison,
                decision,
                source=proposal.source,
                proposal_rationale=proposal.rationale,
                calls=stats.calls,
                total_exec_time_ms=stats.total_exec_time,
                mean_exec_time_ms=stats.mean_exec_time,
            )

            item["candidates"].append(
                {
                    "table": candidate.table_name,
                    "columns": list(candidate.columns),
                    "source": proposal.source,
                    "proposal_rationale": proposal.rationale,
                    "comparison_status": comparison.status,
                    "comparison_reason": comparison.reason,
                    "baseline_plan": comparison.baseline_plan,
                    "candidate_plan": comparison.candidate_plan,
                    "baseline_cost": comparison.baseline_cost,
                    "candidate_cost": comparison.candidate_cost,
                    "decision": decision.status,
                    "reason": decision.reason,
                    "decision_explanation": decision.explanation,
                    "improvement_percent": decision.improvement_percent,
                    "candidate_index_used": comparison.candidate_index_used,
                }
            )

        results.append(item)

    return {
        "queries_collected": len(stats_list),
        "queries_analyzed": sum(
            result["plan_status"] == "captured" for result in results
        ),
        "results": results,
    }
