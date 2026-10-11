
"""FastAPI application for Plan Proof."""
import logging
from typing import Any
from app.db.persistence import persist_verification
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from app.collector.validator import (
    contains_parameter_reference,
    validate_select,
)
from app.core.settings import settings
from app.verifier.candidates import (
    IndexCandidate,
    validate_index_candidate,
)
from app.verifier.decision import decide_index
from app.verifier.hypopg import compare_hypothetical_index
from app.verifier.plan_analysis import summarize_plan

logger = logging.getLogger(__name__)
app = FastAPI(
    title="Plan Proof",
    version="0.2.0",
    description=(
        "Validate proposed PostgreSQL indexes and compare estimated "
        "query plans using HypoPG in a sandbox database."
    ),
)


class VerifyRequest(BaseModel):
    """User-provided SQL and proposed index."""

    model_config = ConfigDict(extra="forbid")

    sql: str = Field(min_length=1, max_length=20000)
    table_name: str = Field(min_length=1, max_length=63)
    columns: list[str] = Field(min_length=1, max_length=4)
    operator_classes: list[str | None] | None = None


def summarize_or_none(
    plan: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Summarize a plan only when one is available."""
    if not isinstance(plan, dict):
        return None

    return summarize_plan(plan)


@app.get("/health")
async def health_check() -> dict[str, str]:
    """Report application health."""
    return {
        "status": "ok",
        "environment": settings.app_env,
    }


@app.post("/api/v1/verify")
async def verify_index(request: VerifyRequest) -> dict[str, Any]:
    """Validate a proposed index and compare plans in the sandbox."""

    query_validation = validate_select(request.sql)

    if not query_validation.accepted:
        raise HTTPException(
            status_code=422,
            detail=query_validation.reason,
        )

    if contains_parameter_reference(request.sql):
        raise HTTPException(
            status_code=422,
            detail="Unresolved SQL parameters such as $1 are unsupported.",
        )

    candidate = IndexCandidate(
        table_name=request.table_name,
        columns=tuple(request.columns),
        operator_classes=(
            tuple(request.operator_classes)
            if request.operator_classes is not None
            else ()
        ),
    )

    candidate_validation = validate_index_candidate(candidate)

    if not candidate_validation.accepted:
        raise HTTPException(
            status_code=422,
            detail=candidate_validation.reason,
        )

    if (
        request.operator_classes is not None
        and len(request.operator_classes) != len(request.columns)
    ):
        raise HTTPException(
            status_code=422,
            detail="Operator classes must match the number of columns.",
        )

    try:
        comparison = await compare_hypothetical_index(
        request.sql,
        candidate,
    )
    except Exception:
        logger.exception("Unexpected error during index verification.")
        raise HTTPException(
            status_code=503,
            detail="Verification service temporarily unavailable.",
    ) from None

    decision = decide_index(comparison)
    try:
        await persist_verification(
            request.sql,
            candidate,
            comparison,
            decision,
        )
    except Exception:
        logger.exception("Failed to persist verification result.")
        raise HTTPException(
            status_code=503,
            detail="Verification result could not be saved.",
        ) from None

    return {
        "query": {
            "sql": request.sql,
            "validation": "accepted",
        },
        "candidate": {
            "table": candidate.table_name,
            "columns": list(candidate.columns),
            "operator_classes": (
                list(candidate.operator_classes)
                if candidate.operator_classes
                else None
            ),
            "validation": "accepted",
        },
        "comparison": {
            "status": comparison.status,
            "reason": comparison.reason,
            "baseline_cost": comparison.baseline_cost,
            "candidate_cost": comparison.candidate_cost,
            "baseline_root_node": comparison.baseline_node_type,
            "candidate_root_node": comparison.candidate_node_type,
            "candidate_index_name": comparison.candidate_index_name,
            "candidate_index_used": comparison.candidate_index_used,
            "baseline_plan_summary": summarize_or_none(
                comparison.baseline_plan
            ),
            "candidate_plan_summary": summarize_or_none(
                comparison.candidate_plan
            ),
        },
        "decision": {
            "status": decision.status,
            "reason": decision.reason,
            "explanation": decision.explanation,
            "estimated_cost_improvement_percent": (
                decision.improvement_percent
            ),
            "minimum_improvement_percent": 10.0,
        },
        "limitations": [
            "Planner costs are estimates, not measured execution times.",
            "A hypothetical index is not a permanent database index.",
            "Acceptance does not prove an equivalent runtime speedup.",
        ],
    }
