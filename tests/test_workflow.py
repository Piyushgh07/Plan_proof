"""Tests for the slow-query analysis workflow."""

import pytest

from app.collector.llm_candidates import CandidateProposal, ProposalBatch
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

    monkeypatch.setattr("app.collector.workflow.collect_query_stats", fake_collect)
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

    monkeypatch.setattr("app.collector.workflow.collect_query_stats", fake_collect)
    monkeypatch.setattr("app.collector.workflow.capture_plan", fake_capture)
    monkeypatch.setattr("app.collector.workflow.generate_candidates", lambda plan: [])

    async def fake_proposals(sql, plan, candidates):
        return ProposalBatch((), "heuristic", "fallback")

    monkeypatch.setattr("app.collector.workflow.propose_candidates", fake_proposals)
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
            [
                {
                    "Plan": {
                        "Node Type": "Seq Scan",
                        "Relation Name": "orders",
                        "Filter": "(user_id = 12345)",
                    }
                }
            ],
        )

    async def fake_compare(sql, received_candidate):
        assert received_candidate == candidate
        return _compared_result()

    async def fake_persist(sql, received_candidate, comparison, decision, **kwargs):
        persist_calls.append((sql, received_candidate, comparison, decision, kwargs))

    monkeypatch.setattr("app.collector.workflow.collect_query_stats", fake_collect)
    monkeypatch.setattr("app.collector.workflow.capture_plan", fake_capture)
    monkeypatch.setattr(
        "app.collector.workflow.generate_candidates",
        lambda plan: [candidate],
    )

    async def fake_proposals(sql, plan, candidates):
        return ProposalBatch(
            (
                CandidateProposal(
                    candidate,
                    "Generated from supported plan evidence.",
                    "heuristic",
                ),
            ),
            "heuristic",
            "fallback",
        )

    monkeypatch.setattr("app.collector.workflow.propose_candidates", fake_proposals)
    monkeypatch.setattr(
        "app.collector.workflow.compare_hypothetical_index", fake_compare
    )
    monkeypatch.setattr("app.collector.workflow.persist_verification", fake_persist)
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
        "proposal_rationale": "Generated from supported plan evidence.",
        "calls": 12,
        "total_exec_time_ms": 240.0,
        "mean_exec_time_ms": 20.0,
    }


@pytest.mark.asyncio
async def test_analysis_separates_proposal_plan_from_verification_plans(monkeypatch):
    from app.collector.workflow import analyze_query

    candidate = IndexCandidate("orders", ("user_id",))
    proposal_plan = [{"Plan": {"Node Type": "Seq Scan", "Total Cost": 99999.0}}]
    baseline_plan = {
        "Node Type": "Aggregate",
        "Total Cost": 20595.42,
        "Plans": [{"Node Type": "Index Scan", "Total Cost": 8.31}],
    }
    candidate_plan = {
        "Node Type": "Aggregate",
        "Total Cost": 19975.49,
        "Plans": [
            {
                "Node Type": "Index Scan",
                "Total Cost": 8.06,
                "Index Name": "hypothetical_orders_user_id",
            }
        ],
    }

    async def fake_capture(sql):
        return PlanResult("captured", "ok", proposal_plan)

    async def fake_propose(sql, plan, heuristic_candidates):
        assert plan == proposal_plan
        return ProposalBatch(
            (CandidateProposal(candidate, "Rationale", "heuristic"),),
            "heuristic",
            "fallback",
        )

    async def fake_compare(sql, received_candidate):
        return HypoPGResult(
            status="compared",
            reason="Selected exact hypothetical index",
            baseline_cost=baseline_plan["Total Cost"],
            candidate_cost=candidate_plan["Total Cost"],
            candidate_index_used=True,
            baseline_plan=baseline_plan,
            candidate_plan=candidate_plan,
        )

    async def fake_persist(*args, **kwargs):
        return None

    monkeypatch.setattr("app.collector.workflow.capture_plan", fake_capture)
    monkeypatch.setattr("app.collector.workflow.generate_candidates", lambda _: [])
    monkeypatch.setattr("app.collector.workflow.propose_candidates", fake_propose)
    monkeypatch.setattr(
        "app.collector.workflow.compare_hypothetical_index", fake_compare
    )
    monkeypatch.setattr(
        "app.collector.workflow.persist_verification",
        fake_persist,
    )

    result = await analyze_query("SELECT * FROM orders WHERE user_id = 12345")
    verified = result["candidates"][0]

    assert result["proposal_plan"] == proposal_plan
    assert verified["baseline_plan"] == baseline_plan
    assert verified["candidate_plan"] == candidate_plan
    assert verified["baseline_cost"] == baseline_plan["Total Cost"]
    assert verified["candidate_cost"] == candidate_plan["Total Cost"]
    assert verified["improvement_percent"] == pytest.approx(3.01, abs=0.01)
    assert verified["decision"] == "inconclusive"
    assert verified["decision_explanation"] == (
        "The candidate index was selected and estimated planner cost improved "
        "by 3.01%, but the configured minimum is 10.00%. The evidence is "
        "insufficient for acceptance under the current policy."
    )


@pytest.mark.asyncio
async def test_llm_proposal_is_sent_through_verifier_and_persisted(monkeypatch):
    candidate = IndexCandidate("orders", ("user_id",))
    persist_calls = []

    async def fake_capture(sql):
        return PlanResult("captured", "ok", [{"Plan": {"Relation Name": "orders"}}])

    async def fake_propose(sql, plan, heuristic_candidates):
        return ProposalBatch(
            (CandidateProposal(candidate, "LLM proposal rationale.", "llm"),),
            "llm",
            "generated",
        )

    async def fake_compare(sql, received_candidate):
        assert received_candidate == candidate
        return _compared_result()

    async def fake_persist(sql, received_candidate, comparison, decision, **kwargs):
        persist_calls.append(kwargs)

    monkeypatch.setattr("app.collector.workflow.capture_plan", fake_capture)
    monkeypatch.setattr("app.collector.workflow.propose_candidates", fake_propose)
    monkeypatch.setattr(
        "app.collector.workflow.compare_hypothetical_index", fake_compare
    )
    monkeypatch.setattr("app.collector.workflow.persist_verification", fake_persist)

    from app.collector.workflow import analyze_query

    result = await analyze_query("SELECT * FROM orders WHERE user_id = 12345")

    assert result["candidates"][0]["source"] == "llm"
    assert result["candidates"][0]["decision"] == "accept"
    assert persist_calls[0]["source"] == "llm"
    assert persist_calls[0]["proposal_rationale"] == "LLM proposal rationale."
