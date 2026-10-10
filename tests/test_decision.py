
"""Tests for the index verification decision engine."""

import pytest

from app.verifier.decision import decide_index
from app.verifier.hypopg import HypoPGResult


def make_result(
    *,
    status="compared",
    baseline=100.0,
    candidate=50.0,
    index_used=True,
):
    return HypoPGResult(
        status=status,
        reason="Test result",
        baseline_cost=baseline,
        candidate_cost=candidate,
        candidate_index_used=index_used,
    )


def test_accepts_selected_index_with_sufficient_improvement():
    decision = decide_index(make_result())

    assert decision.status == "accept"
    assert decision.improvement_percent == 50.0
    assert "50.00%" in decision.explanation
    assert "10.00%" in decision.explanation
    assert "selected" in decision.explanation


def test_rejects_index_not_selected():
    decision = decide_index(make_result(index_used=False))

    assert decision.status == "reject"
    assert decision.improvement_percent == 0.0
    assert "did not choose" in decision.explanation


def test_rejects_selected_index_with_worse_cost():
    decision = decide_index(make_result(candidate=120.0))

    assert decision.status == "reject"
    assert decision.improvement_percent == -20.0
    assert "not lower" in decision.explanation


def test_inconclusive_when_improvement_is_below_threshold():
    decision = decide_index(
        make_result(candidate=95.0),
        minimum_improvement_percent=10.0,
    )

    assert decision.status == "inconclusive"
    assert decision.improvement_percent == 5.0
    assert "5.00%" in decision.explanation
    assert "10.00%" in decision.explanation


def test_inconclusive_when_comparison_failed():
    decision = decide_index(make_result(status="failed"))

    assert decision.status == "inconclusive"
    assert "not compared successfully" in decision.explanation


def test_inconclusive_when_cost_is_missing():
    decision = decide_index(make_result(candidate=None))

    assert decision.status == "inconclusive"
    assert decision.improvement_percent is None
    assert "estimated planner costs" in decision.explanation


def test_inconclusive_when_baseline_cost_is_not_positive():
    decision = decide_index(make_result(baseline=0.0))

    assert decision.status == "inconclusive"
    assert "zero or negative" in decision.explanation


def test_invalid_threshold_raises_value_error():
    with pytest.raises(ValueError):
        decide_index(make_result(), minimum_improvement_percent=100.0)


def test_zero_improvement_is_rejected():
    decision = decide_index(make_result(candidate=100.0))

    assert decision.status == "reject"
    assert decision.improvement_percent == 0.0
    assert "not lower" in decision.explanation


def test_custom_threshold_is_respected():
    decision = decide_index(
        make_result(candidate=92.0),
        minimum_improvement_percent=5.0,
    )

    assert decision.status == "accept"
    assert decision.improvement_percent == 8.0
    assert "5.00%" in decision.explanation
