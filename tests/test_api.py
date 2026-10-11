import asyncio
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app import main

client = TestClient(main.app)


def fake_comparison(**kwargs):
    return SimpleNamespace(
        status="compared",
        reason="The proposed hypothetical index was selected.",
        baseline_cost=100.0,
        candidate_cost=10.0,
        baseline_node_type="Seq Scan",
        candidate_node_type="Index Scan",
        candidate_index_name="hypo_test_index",
        candidate_index_used=True,
        baseline_plan=None,
        candidate_plan=None,
    )


@pytest.fixture
def mock_comparison(monkeypatch):
    async def fake_compare(sql, candidate):
        return fake_comparison()

    async def fake_persist(sql, candidate, comparison, decision, **kwargs):
        return None

    monkeypatch.setattr(main, "compare_hypothetical_index", fake_compare)
    monkeypatch.setattr(main, "persist_verification", fake_persist)


def valid_request():
    return {
        "sql": "SELECT * FROM orders WHERE user_id = 12345",
        "table_name": "orders",
        "columns": ["user_id"],
    }


def test_health_endpoint():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_valid_candidate_is_accepted(mock_comparison):
    response = client.post("/api/v1/verify", json=valid_request())

    assert response.status_code == 200
    assert response.json()["decision"]["status"] == "accept"


def test_verify_response_costs_match_root_plans_and_threshold(monkeypatch):
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
                "Index Name": "hypo_test_index",
            }
        ],
    }

    async def fake_compare(sql, candidate):
        return SimpleNamespace(
            status="compared",
            reason="The exact proposed hypothetical index was selected.",
            baseline_cost=baseline_plan["Total Cost"],
            candidate_cost=candidate_plan["Total Cost"],
            baseline_node_type="Aggregate",
            candidate_node_type="Aggregate",
            candidate_index_name="hypo_test_index",
            candidate_index_used=True,
            baseline_plan=baseline_plan,
            candidate_plan=candidate_plan,
        )

    async def fake_persist(*args, **kwargs):
        return None

    monkeypatch.setattr(main, "compare_hypothetical_index", fake_compare)
    monkeypatch.setattr(main, "persist_verification", fake_persist)

    body = asyncio.run(
        main.verify_index(main.VerifyRequest(**valid_request()))
    )
    comparison = body["comparison"]

    assert comparison["baseline_plan_summary"]["total_cost"] == comparison[
        "baseline_cost"
    ]
    assert comparison["candidate_plan_summary"]["total_cost"] == comparison[
        "candidate_cost"
    ]
    assert comparison["baseline_cost"] == 20595.42
    assert comparison["candidate_cost"] == 19975.49
    assert comparison["baseline_plan"] == baseline_plan
    assert comparison["candidate_plan"] == candidate_plan
    assert comparison["baseline_plan"]["Total Cost"] == comparison[
        "baseline_cost"
    ]
    assert comparison["candidate_plan"]["Total Cost"] == comparison[
        "candidate_cost"
    ]
    assert body["decision"]["estimated_cost_improvement_percent"] == pytest.approx(
        3.01, abs=0.01
    )
    assert body["decision"]["status"] == "inconclusive"
    assert body["decision"]["minimum_improvement_percent"] == 10.0


def test_delete_statement_is_rejected():
    data = valid_request()
    data["sql"] = "DELETE FROM orders"

    response = client.post("/api/v1/verify", json=data)

    assert response.status_code == 422
    assert "SELECT" in response.json()["detail"]


def test_unresolved_parameter_is_rejected():
    data = valid_request()
    data["sql"] = "SELECT * FROM orders WHERE user_id = $1"

    response = client.post("/api/v1/verify", json=data)

    assert response.status_code == 422
    assert "Unresolved SQL parameters" in response.json()["detail"]


def test_multiple_statements_are_rejected():
    data = valid_request()
    data["sql"] = "SELECT * FROM orders; SELECT * FROM users"

    response = client.post("/api/v1/verify", json=data)

    assert response.status_code == 422
    assert "Exactly one SQL statement" in response.json()["detail"]


def test_non_allowlisted_column_is_rejected():
    data = valid_request()
    data["columns"] = ["password_hash"]

    response = client.post("/api/v1/verify", json=data)

    assert response.status_code == 422
    assert "allowlisted" in response.json()["detail"]


def test_invalid_table_is_rejected():
    data = valid_request()
    data["table_name"] = "private_table"

    response = client.post("/api/v1/verify", json=data)

    assert response.status_code == 422
    assert "allowlisted" in response.json()["detail"]


def test_operator_class_count_must_match_columns():
    data = valid_request()
    data["operator_classes"] = ["text_pattern_ops", None]

    response = client.post("/api/v1/verify", json=data)

    assert response.status_code == 422


def test_sandbox_failure_does_not_accept_candidate(monkeypatch):
    async def failed_comparison(sql, candidate):
        return SimpleNamespace(
            status="failed",
            reason="Sandbox connection failed",
            baseline_cost=None,
            candidate_cost=None,
            baseline_node_type=None,
            candidate_node_type=None,
            candidate_index_name=None,
            candidate_index_used=False,
            baseline_plan=None,
            candidate_plan=None,
        )

    monkeypatch.setattr(main, "compare_hypothetical_index", failed_comparison)

    async def fake_persist(sql, candidate, comparison, decision, **kwargs):
        return None

    monkeypatch.setattr(main, "persist_verification", fake_persist)

    response = client.post("/api/v1/verify", json=valid_request())

    assert response.status_code == 200
    assert response.json()["comparison"]["status"] == "failed"
    assert response.json()["decision"]["status"] == "inconclusive"


def test_unexpected_comparison_error_returns_safe_response(monkeypatch):
    async def unexpected_failure(sql, candidate):
        raise RuntimeError("Sensitive internal error details")

    monkeypatch.setattr(main, "compare_hypothetical_index", unexpected_failure)

    safe_client = TestClient(main.app, raise_server_exceptions=False)
    response = safe_client.post("/api/v1/verify", json=valid_request())

    assert response.status_code == 503
    assert response.json()["detail"] == (
        "Verification service temporarily unavailable."
    )
    assert "Sensitive internal error details" not in response.text


def test_live_verification_uses_real_sandbox():
    """Exercise the API and HypoPG against the configured sandbox."""
    response = client.post(
        "/api/v1/verify",
        json={
            "sql": ("SELECT * FROM orders WHERE user_id = 12345"),
            "table_name": "orders",
            "columns": ["user_id"],
        },
    )

    assert response.status_code == 200, response.text

    body = response.json()
    assert body["query"]["validation"] == "accepted"
    assert body["candidate"]["validation"] == "accepted"

    comparison = body["comparison"]
    assert comparison["status"] == "compared"
    assert comparison["baseline_cost"] is not None
    assert comparison["candidate_cost"] is not None
    assert comparison["candidate_index_used"] is True

    assert body["decision"]["status"] == "accept"


def test_persistence_failure_returns_safe_response(monkeypatch):
    async def fake_compare(sql, candidate):
        return fake_comparison()

    async def failed_persist(sql, candidate, comparison, decision):
        raise RuntimeError("Sensitive database details")

    monkeypatch.setattr(main, "compare_hypothetical_index", fake_compare)
    monkeypatch.setattr(main, "persist_verification", failed_persist)

    safe_client = TestClient(main.app, raise_server_exceptions=False)
    response = safe_client.post("/api/v1/verify", json=valid_request())

    assert response.status_code == 503
    assert response.json()["detail"] == ("Verification result could not be saved.")
    assert "Sensitive database details" not in response.text


def test_analyze_endpoint_returns_workflow_result(monkeypatch):
    async def fake_analyze(limit):
        assert limit == 5
        return {
            "queries_collected": 1,
            "queries_analyzed": 1,
            "results": [],
        }

    monkeypatch.setattr(main, "analyze_slow_queries", fake_analyze)

    response = client.post("/api/v1/analyze", json={"limit": 5})

    assert response.status_code == 200
    assert response.json()["queries_collected"] == 1


def test_analyze_unexpected_error_returns_safe_response(monkeypatch):
    async def unexpected_failure(limit):
        raise RuntimeError("Sensitive analysis internals")

    monkeypatch.setattr(main, "analyze_slow_queries", unexpected_failure)

    safe_client = TestClient(main.app, raise_server_exceptions=False)
    response = safe_client.post("/api/v1/analyze", json={})

    assert response.status_code == 503
    assert response.json()["detail"] == (
        "Slow-query analysis service temporarily unavailable."
    )
    assert "Sensitive analysis internals" not in response.text


def test_analyze_rejects_invalid_limit():
    response = client.post("/api/v1/analyze", json={"limit": 0})

    assert response.status_code == 422


def test_single_query_analysis_endpoint_uses_real_workflow(monkeypatch):
    async def fake_analyze(sql):
        assert sql == "SELECT * FROM orders WHERE user_id = 12345"
        return {
            "status": "unsupported",
            "reason": "No supported index candidates were generated.",
            "candidates": [],
        }

    monkeypatch.setattr(main, "analyze_query", fake_analyze)
    response = client.post("/api/v1/analyze", json={"sql": valid_request()["sql"]})

    assert response.status_code == 200
    assert response.json()["status"] == "unsupported"
    assert response.json()["candidates"] == []


def test_single_query_analysis_returns_sanitized_capture_reason(monkeypatch):
    async def failed_capture(sql):
        return {
            "status": "failed",
            "reason": "Target plan capture failed (OperationalError).",
            "candidates": [],
        }

    monkeypatch.setattr(main, "analyze_query", failed_capture)
    response = client.post("/api/v1/analyze", json={"sql": valid_request()["sql"]})

    assert response.status_code == 503
    assert response.json()["detail"] == (
        "Target plan capture failed (OperationalError)."
    )
    assert "password" not in response.text.lower()


def test_workload_endpoint_returns_actual_collection(monkeypatch):
    from app.collector.models import QueryStats

    async def fake_collect(limit):
        assert limit == 3
        return [
            QueryStats(42, 2, 30.0, 15.0, 3, "SELECT * FROM orders WHERE user_id = $1")
        ]

    monkeypatch.setattr(main, "collect_query_stats", fake_collect)
    response = client.get("/api/v1/workload?limit=3")

    assert response.status_code == 200
    query = response.json()["queries"][0]
    assert query["queryid"] == "42"
    assert query["calls"] == 2
    assert query["analyzable"] is False
    assert "parameters" in query["reason"]


def test_benchmark_endpoint_serves_checked_in_report():
    response = client.get("/api/v1/benchmark")

    assert response.status_code == 200
    assert response.json()["summary"]["total_cases"] == 40


def test_system_status_reports_dependency_readiness(monkeypatch):
    async def ready_database(db_engine, *, hypopg=False):
        return {"status": "ready", "detail": "Connected"}

    async def ready_redis():
        return {"status": "ready", "detail": "Connected"}

    monkeypatch.setattr(main, "_bounded_database_status", ready_database)
    monkeypatch.setattr(main, "_redis_status", ready_redis)
    response = client.get("/api/v1/status")

    assert response.status_code == 200
    assert response.json()["status"] == "ready"
    assert set(response.json()["checks"]) == {
        "application_database",
        "target_database",
        "sandbox_hypopg",
        "redis",
    }
