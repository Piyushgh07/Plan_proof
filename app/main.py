"""FastAPI application for Plan Proof."""

import asyncio
import json
import logging
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from uuid import UUID

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import selectinload

from app.collector.statistics import collect_query_stats
from app.collector.validator import (
    contains_parameter_reference,
    validate_select,
)
from app.collector.workflow import analyze_query, analyze_slow_queries
from app.core.settings import settings
from app.db.connections import sandbox_engine, target_engine
from app.db.models import AnalysisRun, Candidate, QueryRecord
from app.db.persistence import persist_verification
from app.db.session import AsyncSessionLocal
from app.db.session import engine as app_engine
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


class AnalyzeRequest(BaseModel):
    """Request a slow-query analysis of the current target workload."""

    model_config = ConfigDict(extra="forbid")

    limit: int = Field(default=10, ge=1, le=100)
    sql: str | None = Field(default=None, min_length=1, max_length=20000)


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


async def _database_status(db_engine, *, hypopg: bool = False) -> dict[str, str]:
    try:
        async with db_engine.connect() as conn:
            if hypopg:
                available = await conn.scalar(
                    text("SELECT extversion FROM pg_extension WHERE extname = 'hypopg'")
                )
                if available is None:
                    return {
                        "status": "unavailable",
                        "detail": "HypoPG extension is missing",
                    }
            else:
                await conn.execute(text("SELECT 1"))
        return {"status": "ready", "detail": "Connected"}
    except SQLAlchemyError:
        logger.info(
            "Readiness check failed for a configured dependency.", exc_info=True
        )
        return {"status": "unavailable", "detail": "Connection check failed"}


async def _bounded_database_status(
    db_engine, *, hypopg: bool = False
) -> dict[str, str]:
    try:
        return await asyncio.wait_for(
            _database_status(db_engine, hypopg=hypopg), timeout=3
        )
    except TimeoutError:
        return {"status": "unavailable", "detail": "Connection check timed out"}


async def _redis_status() -> dict[str, str]:
    parsed = urlparse(settings.redis_url)
    writer = None
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(
                parsed.hostname or "localhost", parsed.port or 6379
            ),
            timeout=2,
        )
        writer.write(b"PING\r\n")
        await writer.drain()
        response = await asyncio.wait_for(reader.readline(), timeout=2)
        if response.strip() == b"+PONG":
            return {"status": "ready", "detail": "Connected"}
        return {"status": "unavailable", "detail": "Health check failed"}
    except (OSError, TimeoutError, ValueError):
        return {"status": "unavailable", "detail": "Connection check failed"}
    finally:
        if writer is not None:
            writer.close()
            await writer.wait_closed()


@app.get("/api/v1/status")
async def system_status() -> dict[str, Any]:
    """Check configured dependencies without returning connection details."""
    app_db, target_db, sandbox_db, redis = await asyncio.gather(
        _bounded_database_status(app_engine),
        _bounded_database_status(target_engine),
        _bounded_database_status(sandbox_engine, hypopg=True),
        _redis_status(),
    )
    checks = {
        "application_database": app_db,
        "target_database": target_db,
        "sandbox_hypopg": sandbox_db,
        "redis": redis,
    }
    return {
        "status": "ready"
        if all(v["status"] == "ready" for v in checks.values())
        else "degraded",
        "checks": checks,
    }


@app.get("/api/v1/workload")
async def query_workload(limit: int = 100) -> dict[str, Any]:
    """Return actual pg_stat_statements entries, with safe plan eligibility."""
    if not 1 <= limit <= 100:
        raise HTTPException(status_code=422, detail="Limit must be between 1 and 100.")
    try:
        stats = await collect_query_stats(limit)
    except Exception:
        logger.exception("Query workload collection failed.")
        raise HTTPException(
            status_code=503, detail="Query workload is unavailable."
        ) from None
    return {
        "count": len(stats),
        "queries": [
            {
                "queryid": str(item.queryid),
                "sql": item.query,
                "calls": item.calls,
                "total_exec_time_ms": item.total_exec_time,
                "mean_exec_time_ms": item.mean_exec_time,
                "rows": item.rows,
                "analyzable": not contains_parameter_reference(item.query),
                "reason": (
                    "Unresolved SQL parameters cannot be safely planned."
                    if contains_parameter_reference(item.query)
                    else None
                ),
            }
            for item in stats
        ],
    }


def _run_json(run: AnalysisRun) -> dict[str, Any]:
    queries = []
    for query in run.queries:
        candidates = []
        for candidate in query.candidates:
            for verification in candidate.verifications:
                details = verification.details or {}
                candidates.append(
                    {
                        "id": str(candidate.id),
                        "source": candidate.source,
                        "proposal_sql": candidate.proposal_sql,
                        "rationale": candidate.rationale,
                        "decision": verification.verdict,
                        "baseline_cost": float(verification.baseline_cost)
                        if verification.baseline_cost is not None
                        else None,
                        "candidate_cost": float(verification.candidate_cost)
                        if verification.candidate_cost is not None
                        else None,
                        "details": details,
                    }
                )
        queries.append(
            {
                "id": str(query.id),
                "sql": query.sql_text,
                "fingerprint": query.query_fingerprint,
                "calls": query.calls,
                "total_exec_time_ms": float(query.total_exec_time_ms),
                "mean_exec_time_ms": float(query.mean_exec_time_ms),
                "plan": query.plan,
                "candidates": candidates,
            }
        )
    return {
        "id": str(run.id),
        "status": run.status,
        "target_database": run.target_database,
        "created_at": run.created_at.isoformat(),
        "queries": queries,
    }


def _history_load_options():
    return (
        selectinload(AnalysisRun.queries)
        .selectinload(QueryRecord.candidates)
        .selectinload(Candidate.verifications)
    )


@app.get("/api/v1/history")
async def analysis_history(limit: int = 20, offset: int = 0) -> dict[str, Any]:
    """List persisted verification runs with bounded pagination."""
    if not 1 <= limit <= 100 or not 0 <= offset <= 10000:
        raise HTTPException(status_code=422, detail="Invalid history pagination.")
    try:
        async with AsyncSessionLocal() as session:
            total = await session.scalar(select(func.count()).select_from(AnalysisRun))
            result = await session.scalars(
                select(AnalysisRun)
                .options(_history_load_options())
                .order_by(AnalysisRun.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
            runs = result.unique().all()
        return {
            "total": total or 0,
            "limit": limit,
            "offset": offset,
            "runs": [_run_json(run) for run in runs],
        }
    except Exception:
        logger.exception("Analysis history retrieval failed.")
        raise HTTPException(
            status_code=503, detail="Analysis history is unavailable."
        ) from None


@app.get("/api/v1/history/{run_id}")
async def analysis_history_detail(run_id: UUID) -> dict[str, Any]:
    """Return one persisted analysis run."""
    try:
        async with AsyncSessionLocal() as session:
            run = await session.scalar(
                select(AnalysisRun)
                .where(AnalysisRun.id == run_id)
                .options(_history_load_options())
            )
        if run is None:
            raise HTTPException(status_code=404, detail="Analysis run not found.")
        return _run_json(run)
    except HTTPException:
        raise
    except Exception:
        logger.exception("Analysis detail retrieval failed.")
        raise HTTPException(
            status_code=503, detail="Analysis history is unavailable."
        ) from None


@app.get("/api/v1/benchmark")
async def benchmark_report() -> dict[str, Any]:
    """Serve the checked in benchmark report as explicitly labelled evidence."""
    path = (
        Path(__file__).resolve().parent.parent / "reports" / "benchmark-evaluation.json"
    )
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise HTTPException(
            status_code=404, detail="No benchmark report is available."
        ) from None
    except (OSError, json.JSONDecodeError):
        logger.exception("Benchmark report could not be read.")
        raise HTTPException(
            status_code=503, detail="Benchmark report is unavailable."
        ) from None


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

    if request.operator_classes is not None and len(request.operator_classes) != len(
        request.columns
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
            source="user",
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
                list(candidate.operator_classes) if candidate.operator_classes else None
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
            "baseline_plan_summary": summarize_or_none(comparison.baseline_plan),
            "candidate_plan_summary": summarize_or_none(comparison.candidate_plan),
        },
        "decision": {
            "status": decision.status,
            "reason": decision.reason,
            "explanation": decision.explanation,
            "estimated_cost_improvement_percent": (decision.improvement_percent),
            "minimum_improvement_percent": 10.0,
        },
        "limitations": [
            "Planner costs are estimates, not measured execution times.",
            "A hypothetical index is not a permanent database index.",
            "Acceptance does not prove an equivalent runtime speedup.",
        ],
    }


@app.post("/api/v1/analyze")
async def analyze_queries(request: AnalyzeRequest) -> dict[str, Any]:
    """Analyze slow queries and verify generated index candidates."""
    try:
        if request.sql is not None:
            result = await analyze_query(request.sql)
            if result["status"] == "failed":
                raise HTTPException(
                    status_code=503, detail="Query plan capture failed."
                )
            return result
        return await analyze_slow_queries(request.limit)
    except HTTPException:
        raise
    except Exception:
        logger.exception("Slow-query analysis failed.")
        raise HTTPException(
            status_code=503,
            detail="Slow-query analysis service temporarily unavailable.",
        ) from None
