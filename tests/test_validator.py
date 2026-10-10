
import pytest

from app.collector.validator import validate_select


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT id FROM users",
        "SELECT COUNT(*) FROM orders",
        "WITH recent AS (SELECT id FROM orders) SELECT id FROM recent",
        "SELECT id FROM users UNION SELECT id FROM users",
    ],
)
def test_accepts_select_queries(sql):
    assert validate_select(sql).accepted is True


@pytest.mark.parametrize(
    "sql",
    [
        "INSERT INTO users (id) VALUES (1)",
        "UPDATE users SET is_active = false",
        "DELETE FROM users",
        "CREATE INDEX test_idx ON users (id)",
        "SELECT 1; SELECT 2",
        "SELECT id FROM users FOR UPDATE",
        "SELECT FROM",
        "",
    ],
)
def test_rejects_unsupported_queries(sql):
    assert validate_select(sql).accepted is False


def test_rejects_locking_inside_cte():
    sql = """
        WITH locked AS (
            SELECT id FROM users FOR UPDATE
        )
        SELECT id FROM locked
    """
    assert validate_select(sql).accepted is False


def test_rejects_locking_in_from_subquery():
    sql = """
        SELECT u.id
        FROM (SELECT id FROM users FOR UPDATE) AS u
    """
    assert validate_select(sql).accepted is False


def test_rejects_locking_in_scalar_subquery():
    sql = """
        SELECT (SELECT id FROM users FOR UPDATE) AS locked_id
    """
    assert validate_select(sql).accepted is False

from app.collector.validator import contains_parameter_reference


@pytest.mark.parametrize(
    ("sql", "expected"),
    [
        ("SELECT id FROM users WHERE id = $1", True),
        ("SELECT '$1' AS value", False),
        ("SELECT 1 /* $1 */", False),
        ("SELECT id FROM users", False),
        (
            "SELECT id FROM users WHERE id = $1 "
            "UNION SELECT id FROM users WHERE id = $2",
            True,
        ),
    ],
)
def test_detects_actual_parameter_references(sql, expected):
    assert contains_parameter_reference(sql) is expected
