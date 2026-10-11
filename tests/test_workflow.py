"""Tests for the slow-query analysis workflow."""

import pytest

from app.collector.models import QueryStats
from app.collector.plans import PlanResult
from app.collector.workflow import analyze_slow_queries
from app.verifier.candidates import IndexCandidate
from app.verifier.decision import VerificationDecision
from app.verifier.hypopg import HypoPGResult


def _stats(query="SELECT * FROM orders WHERE user_id = 12345"):
    return QueryStats(
        queryid=101,
        calls=12,
        total_exec_time=240.0,
        mean_exec_time=20.0,
        rows=12,
        query=query,
    )


def _compared_result():
    return HypoPGResult(
        status="compared",
        reason="The exact proposed hypothetical index appears in the candidate plan.",
        baseline_cost=100.0,
        candidate_cost=20.0,
        candidate_index_used=True,
    )


@pytest.mark.asyncio
async def test_skips_queries_that_fail_plan_capture(monkeypatch):
    persist_calls = []

    async def fake_collect(limit):
        return [_stats("SELECT * FROM orders WHERE user_id = $1")]

    async def fake_capture(sql):
        return PlanResult("rejected", "Unresolved parameter references.")

    async def unexpected_compare(sql, candidate):
        pytest.fail("Verifier should not run for rejected queries.")

    async def unexpected_persist(*args, **kwargs):
        persist_calls.append(kwargs)

    monkeypatch.setattr(
        "app.collector.workflow.collect_query_stats", fake_collect
    )
    monkeypatch.setattr("app.collector.workflow.capture_plan", fake_capture)
    monkeypatch.setattr(
        "app.collector.workflow.compare_hypothetical_index",
        unexpected_compare,
    )
    monkeypatch.setattr(
        "app.collector.workflow.persist_verification", unexpected_persist
    )

    result = await analyze_slow_queries(1)

    assert result["queries_collected"] == 1
    assert result["queries_analyzed"] == 0
    assert result["results"][0]["plan_status"] == "rejected"
    assert persist_calls == []


@pytest.mark.asyncio
async def test_reports_when_no_candidates_are_generated(monkeypatch):
    persist_calls = []

    async def fake_collect(limit):
        return [_stats()]

    async def fake_capture(sql):
        return PlanResult("captured", "ok", [{"Plan": {"Node Type": "Seq Scan"}}])

    monkeypatch.setattr(
        "app.collector.workflow.collect_query_stats", fake_collect
    )
    monkeypatch.setattr("app.collector.workflow.capture_plan", fake_capture)
    monkeypatch.setattr(
        "app.collector.workflow.generate_candidates", lambda plan: []
    )
    monkeypatch.setattr(
        "app.collector.workflow.persist_verification",
        lambda *args, **kwargs: persist_calls.append(kwargs),
    )

    result = await analyze_slow_queries(3)

    assert result["queries_analyzed"] == 1
    assert result["results"][0]["candidates"] == []
    assert "No supported index candidates" in result["results"][0]["reason"]
    assert persist_calls == []


@pytest.mark.asyncio
async def test_verifies_and_persists_heuristic_candidates(monkeypatch):
    persist_calls = []
    candidate = IndexCandidate("orders", ("user_id",))

    async def fake_collect(limit):
        return [_stats()]

    async def fake_capture(sql):
        return PlanResult(
            "captured",
            "ok",
            [{
                "Plan": {
                    "Node Type": "Seq Scan",
                    "Relation Name": "orders",
                    "Filter": "(user_id = 12345)",
                }
            }],
        )

    async def fake_compare(sql, received_candidate):
        assert received_candidate == candidate
        return _compared_result()

    async def fake_persist(sql, received_candidate, comparison, decision, **kwargs):
        persist_calls.append((sql, received_candidate, comparison, decision, kwargs))

    monkeypatch.setattr(
        "app.collector.workflow.collect_query_stats", fake_collect
    )
    monkeypatch.setattr("app.collector.workflow.capture_plan", fake_capture)
    monkeypatch.setattr(
        "app.collector.workflow.generate_candidates",
        lambda plan: [candidate],
    )
    monkeypatch.setattr(
        "app.collector.workflow.compare_hypothetical_index", fake_compare
    )
    monkeypatch.setattr(
        "app.collector.workflow.persist_verification", fake_persist
    )
    monkeypatch.setattr(
        "app.collector.workflow.decide_index",
        lambda comparison: VerificationDecision(
            status="accept",
            reason="Hypothetical index was selected.",
            improvement_percent=80.0,
        ),
    )

    result = await analyze_slow_queries(10)

    assert result["queries_collected"] == 1
    assert result["queries_analyzed"] == 1
    assert result["results"][0]["candidates"][0]["decision"] == "accept"
    assert persist_calls[0][4] == {
        "source": "heuristic",
        "calls": 12,
        "total_exec_time_ms": 240.0,
        "mean_exec_time_ms": 20.0,
    }
