
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import app.main as main


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

    monkeypatch.setattr(
        main, "compare_hypothetical_index", fake_compare
    )


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
    response = client.post(
        "/api/v1/verify", json=valid_request()
    )

    assert response.status_code == 200
    assert response.json()["decision"]["status"] == "accept"


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
    data["sql"] = (
        "SELECT * FROM orders; SELECT * FROM users"
    )

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

    monkeypatch.setattr(
        main, "compare_hypothetical_index", failed_comparison
    )

    response = client.post(
        "/api/v1/verify", json=valid_request()
    )

    assert response.status_code == 200
    assert response.json()["comparison"]["status"] == "failed"
    assert response.json()["decision"]["status"] == "inconclusive"

def test_unexpected_comparison_error_returns_safe_response(monkeypatch):
    async def unexpected_failure(sql, candidate):
        raise RuntimeError("Sensitive internal error details")

    monkeypatch.setattr(
        main, "compare_hypothetical_index", unexpected_failure
    )

    safe_client = TestClient(
        main.app, raise_server_exceptions=False
    )
    response = safe_client.post(
        "/api/v1/verify", json=valid_request()
    )

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
            "sql": (
                "SELECT * FROM orders "
                "WHERE user_id = 12345"
            ),
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
