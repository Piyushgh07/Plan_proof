import pytest

from app.verifier.candidates import (
    IndexCandidate,
    validate_index_candidate,
)


@pytest.mark.parametrize(
    "candidate",
    [
        IndexCandidate("orders", ("user_id",)),
        IndexCandidate("orders", ("status", "created_at")),
        IndexCandidate("events", ("user_id", "occurred_at")),
        IndexCandidate(
            "products", ("name",), ("text_pattern_ops",)
        ),
    ],
)
def test_accepts_valid_candidates(candidate):
    assert validate_index_candidate(candidate).accepted is True


@pytest.mark.parametrize(
    "candidate",
    [
        IndexCandidate("unknown_table", ("id",)),
        IndexCandidate("orders", ("unknown_column",)),
        IndexCandidate("orders", ()),
        IndexCandidate("orders", ("status", "status")),
        IndexCandidate("orders; DROP TABLE users", ("id",)),
        IndexCandidate("orders", ("id); DROP TABLE users; --",)),
        IndexCandidate("orders", ("users.id",)),
        IndexCandidate("orders", ("ID",)),
        IndexCandidate(
            "products", ("name",), ("btree_products_name",)
        ),
        IndexCandidate(
            "orders", ("user_id",), ("text_pattern_ops",)
        ),
        IndexCandidate(
            "products", ("name",), ("text_pattern_ops", "text_pattern_ops")
        ),
    ],
)
def test_rejects_invalid_candidates(candidate):
    assert validate_index_candidate(candidate).accepted is False


def test_rejects_non_candidate_input():
    assert validate_index_candidate("CREATE INDEX anything").accepted is False


def test_rejects_column_from_another_table():
    candidate = IndexCandidate("orders", ("email",))
    result = validate_index_candidate(candidate)

    assert result.accepted is False
    assert result.reason == "Column is not allowlisted for table 'orders'."


def test_rejects_non_string_column_without_crashing():
    candidate = IndexCandidate("orders", (["user_id"],))
    result = validate_index_candidate(candidate)

    assert result.accepted is False
    assert result.reason == "Invalid column identifier."


def test_rejects_operator_class_count_mismatch():
    candidate = IndexCandidate(
        "products", ("name", "category"), ("text_pattern_ops",)
    )
    result = validate_index_candidate(candidate)

    assert result.accepted is False
    assert result.reason == "Operator classes must match the number of columns."
