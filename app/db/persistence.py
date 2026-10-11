"""Persist Plan Proof verification results atomically."""

import hashlib

from sqlalchemy.engine import make_url

from app.core.settings import settings
from app.db.models import AnalysisRun, Candidate, QueryRecord, Verification
from app.db.session import AsyncSessionLocal


async def persist_verification(
    sql,
    candidate,
    comparison,
    decision,
    *,
    source: str = "user",
    proposal_rationale: str | None = None,
    calls: int = 0,
    total_exec_time_ms: float = 0,
    mean_exec_time_ms: float = 0,
) -> None:
    """Save a verification and its related records in one transaction."""

    fingerprint = hashlib.sha256(sql.encode("utf-8")).hexdigest()
    database_name = make_url(settings.target_database_url).database or "unknown"

    index_name = ("idx_" + candidate.table_name + "_" + "_".join(candidate.columns))[
        :63
    ]

    index_columns = []
    for column, operator_class in zip(
        candidate.columns,
        candidate.operator_classes or (None,) * len(candidate.columns),
    ):
        index_columns.append(column + (f" {operator_class}" if operator_class else ""))

    proposal_sql = (
        f"CREATE INDEX {index_name} ON {candidate.table_name} "
        f"({', '.join(index_columns)})"
    )

    details = {
        "comparison_status": comparison.status,
        "comparison_reason": comparison.reason,
        "baseline_node_type": comparison.baseline_node_type,
        "candidate_node_type": comparison.candidate_node_type,
        "candidate_index_name": comparison.candidate_index_name,
        "candidate_index_used": comparison.candidate_index_used,
        "baseline_plan": comparison.baseline_plan,
        "candidate_plan": comparison.candidate_plan,
        "decision_reason": decision.reason,
        "decision_explanation": decision.explanation,
        "improvement_percent": decision.improvement_percent,
    }

    async with AsyncSessionLocal() as session, session.begin():
        run = AnalysisRun(
            status=decision.status,
            target_database=database_name,
        )
        session.add(run)
        await session.flush()

        query = QueryRecord(
            analysis_run_id=run.id,
            query_fingerprint=fingerprint,
            sql_text=sql,
            calls=calls,
            total_exec_time_ms=total_exec_time_ms,
            mean_exec_time_ms=mean_exec_time_ms,
            plan=comparison.baseline_plan,
        )
        session.add(query)
        await session.flush()

        stored_candidate = Candidate(
            query_id=query.id,
            source=source,
            action="create_index",
            proposal_sql=proposal_sql,
            rationale=proposal_rationale or decision.reason,
        )
        session.add(stored_candidate)
        await session.flush()

        verification = Verification(
            candidate_id=stored_candidate.id,
            verifier="hypopg",
            verdict=decision.status,
            baseline_cost=comparison.baseline_cost,
            candidate_cost=comparison.candidate_cost,
            details=details,
        )
        session.add(verification)
