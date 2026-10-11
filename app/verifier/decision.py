
"""Make a conservative decision from a hypothetical-index comparison."""

import math
from dataclasses import dataclass
from typing import Literal

from app.verifier.hypopg import HypoPGResult

DecisionStatus = Literal["accept", "reject", "inconclusive"]


@dataclass(frozen=True, slots=True)
class VerificationDecision:
    status: DecisionStatus
    reason: str
    improvement_percent: float | None = None
    explanation: str = ""


def decide_index(
    result: HypoPGResult,
    minimum_improvement_percent: float = 10.0,
) -> VerificationDecision:
    """Decide conservatively and provide a human-readable explanation."""

    if not 0 <= minimum_improvement_percent < 100:
        raise ValueError(
            "minimum_improvement_percent must be >= 0 and < 100."
        )

    if result.status != "compared":
        reason = f"Plan comparison did not complete: {result.status}."
        return VerificationDecision(
            status="inconclusive",
            reason=reason,
            explanation=(
                "No reliable recommendation can be made because "
                "the baseline and candidate plans were not compared "
                "successfully."
            ),
        )

    if result.baseline_cost is None or result.candidate_cost is None:
        return VerificationDecision(
            status="inconclusive",
            reason="Plan costs are missing.",
            explanation=(
                "The comparison did not provide both estimated planner "
                "costs, so the improvement cannot be calculated."
            ),
        )

    if not math.isfinite(result.baseline_cost) or not math.isfinite(
        result.candidate_cost
    ) or result.candidate_cost < 0:
        return VerificationDecision(
            status="inconclusive",
            reason="Plan costs are invalid.",
            explanation="The comparison returned an invalid planner cost.",
        )

    if result.baseline_cost <= 0:
        return VerificationDecision(
            status="inconclusive",
            reason="Baseline cost must be positive to calculate improvement.",
            explanation=(
                "The baseline planner cost is zero or negative. "
                "A percentage improvement cannot be calculated reliably."
            ),
        )

    improvement = (
        (result.baseline_cost - result.candidate_cost)
        / result.baseline_cost
        * 100.0
    )

    if not result.candidate_index_used:
        return VerificationDecision(
            status="reject",
            reason="PostgreSQL did not select the proposed hypothetical index.",
            improvement_percent=0.0,
            explanation=(
                "PostgreSQL did not choose the proposed index in the "
                "candidate plan. The index therefore fails the current "
                "verification policy, regardless of the cost estimate."
            ),
        )

    if improvement <= 0:
        return VerificationDecision(
            status="reject",
            reason="Estimated planner cost did not improve.",
            improvement_percent=improvement,
            explanation=(
                "PostgreSQL selected the proposed index, but the candidate "
                "plan's estimated cost was not lower than the baseline."
            ),
        )

    if improvement < minimum_improvement_percent:
        return VerificationDecision(
            status="inconclusive",
            reason="Estimated improvement is below the configured threshold.",
            improvement_percent=improvement,
            explanation=(
                f"The candidate index was selected and estimated planner "
                f"cost improved by {improvement:.2f}%, but the configured "
                f"minimum is {minimum_improvement_percent:.2f}%. "
                "The evidence is insufficient for acceptance under "
                "the current policy."
            ),
        )

    return VerificationDecision(
        status="accept",
        reason=(
            "Hypothetical index was selected and estimated cost improved "
            "above the configured threshold."
        ),
        improvement_percent=improvement,
        explanation=(
            f"PostgreSQL selected the proposed hypothetical index, and "
            f"estimated planner cost decreased by {improvement:.2f}%, "
            f"meeting the configured minimum of "
            f"{minimum_improvement_percent:.2f}%."
        ),
    )
