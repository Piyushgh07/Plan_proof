import json

import httpx
import pytest

from app.collector import llm_candidates
from app.verifier.candidates import IndexCandidate


def test_valid_provider_json_is_allowlisted_and_bounded():
    content = json.dumps(
        {
            "candidates": [
                {
                    "table": "orders",
                    "columns": ["user_id"],
                    "method": "btree",
                    "rationale": "Supports the equality filter.",
                },
                {
                    "table": "unknown",
                    "columns": ["id"],
                    "method": "btree",
                    "rationale": "Unknown relation.",
                },
            ]
        }
    )

    proposals = llm_candidates._validate_response(
        content, {"orders": frozenset({"user_id"})}
    )

    assert len(proposals) == 1
    assert proposals[0].candidate == IndexCandidate("orders", ("user_id",))
    assert proposals[0].source == "llm"


def test_malformed_provider_json_is_rejected():
    schema = {"orders": frozenset({"user_id"})}
    with pytest.raises((ValueError, json.JSONDecodeError)):
        llm_candidates._validate_response("not json", schema)


@pytest.mark.parametrize(
    "table,columns",
    [("orders; DROP TABLE users", ["user_id"]), ("orders", ["missing"])],
)
def test_unsafe_or_unknown_proposals_are_discarded(table, columns):
    content = json.dumps(
        {
            "candidates": [
                {
                    "table": table,
                    "columns": columns,
                    "method": "btree",
                    "rationale": "Untrusted.",
                }
            ]
        }
    )
    assert (
        llm_candidates._validate_response(content, {"orders": frozenset({"user_id"})})
        == []
    )


def test_proposal_unrelated_to_plan_conditions_is_discarded():
    content = json.dumps(
        {
            "candidates": [
                {
                    "table": "orders",
                    "columns": ["status"],
                    "method": "btree",
                    "rationale": "Unrelated to the observed filter.",
                }
            ]
        }
    )

    assert (
        llm_candidates._validate_response(
            content,
            {"orders": frozenset({"user_id", "status"})},
            {"orders": frozenset({"user_id"})},
        )
        == []
    )


@pytest.mark.asyncio
async def test_provider_failure_uses_deterministic_candidates(monkeypatch):
    candidate = IndexCandidate("orders", ("user_id",))
    monkeypatch.setattr(llm_candidates, "provider_status", lambda: {"configured": True})

    async def schema(_tables):
        return {"orders": frozenset({"user_id"})}

    async def failure(*_args):
        raise httpx.TimeoutException("timeout")

    monkeypatch.setattr(llm_candidates, "load_actual_schema", schema)
    monkeypatch.setattr(llm_candidates, "_request_provider", failure)

    batch = await llm_candidates.propose_candidates(
        "SELECT * FROM orders WHERE user_id = 1",
        {
            "Plan": {
                "Node Type": "Seq Scan",
                "Relation Name": "orders",
                "Filter": "(user_id = 1)",
            }
        },
        [candidate],
    )

    assert batch.status == "fallback"
    assert batch.source == "heuristic"
    assert batch.proposals[0].candidate == candidate
    assert "fallback" in batch.reason


@pytest.mark.asyncio
async def test_valid_provider_proposal_is_used(monkeypatch):
    monkeypatch.setattr(llm_candidates, "provider_status", lambda: {"configured": True})

    async def schema(_tables):
        return {"orders": frozenset({"user_id"})}

    async def response(*_args):
        return json.dumps(
            {
                "candidates": [
                    {
                        "table": "orders",
                        "columns": ["user_id"],
                        "method": "btree",
                        "rationale": "Matches the filter.",
                    }
                ]
            }
        )

    monkeypatch.setattr(llm_candidates, "load_actual_schema", schema)
    monkeypatch.setattr(llm_candidates, "_request_provider", response)

    batch = await llm_candidates.propose_candidates(
        "SELECT * FROM orders WHERE user_id = 1",
        {
            "Plan": {
                "Node Type": "Seq Scan",
                "Relation Name": "orders",
                "Filter": "(user_id = 1)",
            }
        },
        [],
    )

    assert batch.status == "generated"
    assert batch.source == "llm"
    assert batch.proposals[0].candidate == IndexCandidate("orders", ("user_id",))
