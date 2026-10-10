
import json
from dataclasses import dataclass
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.collector.validator import (
    contains_parameter_reference,
    validate_select,
)
from app.db.connections import target_engine


@dataclass(frozen=True, slots=True)
class PlanResult:
    status: str
    reason: str
    plan: dict[str, Any] | list[Any] | None = None


async def capture_plan(sql: str) -> PlanResult:
    """Capture a JSON plan without executing the query itself."""
    validation = validate_select(sql)

    if not validation.accepted:
        return PlanResult("rejected", validation.reason)

    if contains_parameter_reference(sql):
        return PlanResult(
            "rejected",
            "Unresolved parameter references are not supported yet.",
        )

    try:
        async with target_engine.connect() as conn:
            async with conn.begin():
                await conn.execute(text("SET TRANSACTION READ ONLY"))
                result = await conn.exec_driver_sql(
                    f"EXPLAIN (FORMAT JSON) {sql}"
                )
                raw_plan = result.scalar_one()

        # PostgreSQL returns JSON EXPLAIN output as a JSON value.
        if isinstance(raw_plan, str):
            raw_plan = json.loads(raw_plan)

        return PlanResult(
            "captured",
            "Plan captured successfully.",
            raw_plan,
        )

    except (SQLAlchemyError, ValueError, TypeError) as exc:
        return PlanResult(
            "failed",
            f"Plan capture failed: {type(exc).__name__}.",
        )
