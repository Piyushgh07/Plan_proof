
"""Compare alternative hypothetical indexes for benchmark query Q035."""

import asyncio
import json

from sqlalchemy import text

from app.db.connections import sandbox_engine
from app.verifier.candidates import IndexCandidate
from app.verifier.hypopg import compare_hypothetical_index


SQL = """
SELECT e.id, e.event_type
FROM events AS e
JOIN users AS u ON u.id = e.user_id
WHERE u.country = 'IN';
"""

CANDIDATES = [
    ("existing_candidate", IndexCandidate("events", ("user_id",))),
    ("users_country", IndexCandidate("users", ("country",))),
    ("users_country_id", IndexCandidate("users", ("country", "id"))),
]


async def main() -> None:
    try:
        # Keep planner statistics current before comparing candidates.
        async with sandbox_engine.begin() as conn:
            await conn.execute(text("ANALYZE users"))
            await conn.execute(text("ANALYZE events"))

        results = []

        for label, candidate in CANDIDATES:
            print(f"Testing {label}...", flush=True)

            result = await compare_hypothetical_index(SQL, candidate)

            row = {
                "candidate": label,
                "table": candidate.table_name,
                "columns": list(candidate.columns),
                "status": result.status,
                "reason": result.reason,
                "baseline_cost": result.baseline_cost,
                "candidate_cost": result.candidate_cost,
                "candidate_index_used": result.candidate_index_used,
                "baseline_index_names": list(result.baseline_index_names),
                "candidate_index_names": list(result.candidate_index_names),
                "baseline_plan": result.baseline_plan,
                "candidate_plan": result.candidate_plan,
            }

            if (
                result.baseline_cost is not None
                and result.baseline_cost > 0
                and result.candidate_cost is not None
            ):
                row["estimated_improvement_percent"] = (
                    (
                        result.baseline_cost - result.candidate_cost
                    )
                    / result.baseline_cost
                    * 100
                )
            else:
                row["estimated_improvement_percent"] = None

            results.append(row)

            print(
                f"  status={result.status}, "
                f"index_used={result.candidate_index_used}, "
                f"baseline={result.baseline_cost}, "
                f"candidate={result.candidate_cost}"
            )

        output = {
            "query_id": "Q035",
            "description": "Exploratory hypothetical-index comparison",
            "results": results,
            "note": (
                "Planner cost is estimated cost, not measured runtime. "
                "No permanent indexes are created."
            ),
        }

        with open(
            "reports/q035-candidate-experiment.json",
            "w",
            encoding="utf-8",
        ) as f:
            json.dump(output, f, indent=2)
            f.write("\n")

        print("\nSaved: reports/q035-candidate-experiment.json")

    finally:
        await sandbox_engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
