
"""Compare hypothetical index candidates for a selective country filter."""

import asyncio
import json

from app.db.connections import sandbox_engine
from app.verifier.candidates import IndexCandidate
from app.verifier.hypopg import compare_hypothetical_index


SQL = """
SELECT id, email
FROM users
WHERE country = 'AU';
"""

CANDIDATES = [
    ("country", IndexCandidate("users", ("country",))),
    ("country_id", IndexCandidate("users", ("country", "id"))),
    (
        "country_id_email",
        IndexCandidate("users", ("country", "id", "email")),
    ),
]


async def main() -> None:
    try:
        results = []

        for label, candidate in CANDIDATES:
            print(f"Testing {label}...", flush=True)
            result = await compare_hypothetical_index(SQL, candidate)

            improvement = None
            if (
                result.baseline_cost is not None
                and result.baseline_cost > 0
                and result.candidate_cost is not None
            ):
                improvement = (
                    (result.baseline_cost - result.candidate_cost)
                    / result.baseline_cost
                    * 100
                )

            row = {
                "candidate": label,
                "columns": list(candidate.columns),
                "status": result.status,
                "reason": result.reason,
                "baseline_cost": result.baseline_cost,
                "candidate_cost": result.candidate_cost,
                "improvement_percent": improvement,
                "index_used": result.candidate_index_used,
                "baseline_plan": result.baseline_plan,
                "candidate_plan": result.candidate_plan,
            }
            results.append(row)

            print(
                f"  used={result.candidate_index_used}, "
                f"baseline={result.baseline_cost}, "
                f"candidate={result.candidate_cost}, "
                f"improvement={improvement}"
            )

        with open(
            "reports/user-country-candidate-experiment.json",
            "w",
            encoding="utf-8",
        ) as f:
            json.dump({"results": results}, f, indent=2)
            f.write("\n")

        print("\nSaved reports/user-country-candidate-experiment.json")

    finally:
        await sandbox_engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
