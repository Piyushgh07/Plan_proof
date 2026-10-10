import asyncio

from app.verifier.candidates import IndexCandidate
from app.verifier.hypopg import compare_hypothetical_index
from app.verifier.decision import decide_index


async def main():
    query = "SELECT * FROM orders WHERE user_id = 12345"
    candidate = IndexCandidate(
        table_name="orders",
        columns=("user_id",),
    )

    print("Running real HypoPG verification against sandbox...\n")

    result = await compare_hypothetical_index(query, candidate)

    print("=== PLAN COMPARISON ===")
    print(f"Status: {result.status}")
    print(f"Reason: {result.reason}")
    print(f"Baseline estimated cost: {result.baseline_cost}")
    print(f"Candidate estimated cost: {result.candidate_cost}")
    print(f"Baseline plan: {result.baseline_node_type}")
    print(f"Candidate plan: {result.candidate_node_type}")
    print(f"Hypothetical index: {result.candidate_index_name}")
    print(f"Candidate index used: {result.candidate_index_used}")

    decision = decide_index(result)

    print("\n=== VERIFICATION DECISION ===")
    print(f"Decision: {decision.status}")
    print(f"Reason: {decision.reason}")
    print(f"Estimated cost improvement: {decision.improvement_percent}%")

    if result.status != "compared":
        raise SystemExit("FAIL: PostgreSQL plan comparison did not complete.")

    if not result.candidate_index_used:
        raise SystemExit("FAIL: PostgreSQL did not select the proposed index.")

    if decision.status != "accept":
        raise SystemExit("FAIL: The decision layer did not accept the candidate.")

    print("\nPASS: Real sandbox verification succeeded.")


if __name__ == "__main__":
    asyncio.run(main())
