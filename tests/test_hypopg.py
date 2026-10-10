"""Tests for hypothetical PostgreSQL index verification."""

import pytest
from sqlalchemy.exc import SQLAlchemyError

from app.verifier.candidates import IndexCandidate
from app.verifier.hypopg import compare_hypothetical_index


FAKE_INDEX_NAME = "<12345>btree_orders_user_id"
FAKE_PATTERN_INDEX_NAME = "<12346>btree_products_name"


class FakeResult:
    def __init__(self, value):
        self.value = value

    def scalar_one(self):
        if self.value is None:
            raise ValueError("No hypothetical index returned.")
        return self.value


class FakeConnection:
    def __init__(
        self,
        fail=False,
        missing_index=False,
        use_candidate_index=True,
        fail_reset=False,
    ):
        self.statements = []
        self.ddls = []
        self.explain_count = 0
        self.fail = fail
        self.missing_index = missing_index
        self.use_candidate_index = use_candidate_index
        self.fail_reset = fail_reset
        self.invalidated = False

    async def exec_driver_sql(self, sql):
        if self.fail:
            raise SQLAlchemyError("Simulated database failure.")

        self.statements.append(sql)
        self.explain_count += 1

        if self.explain_count == 1:
            plan = {
                "Total Cost": 20.0,
                "Node Type": "Seq Scan",
            }
        elif self.use_candidate_index:
            plan = {
                "Total Cost": 12.0,
                "Node Type": "Index Scan",
                "Index Name": (
                    FAKE_PATTERN_INDEX_NAME
                    if any("text_pattern_ops" in ddl for ddl in self.ddls)
                    else FAKE_INDEX_NAME
                ),
            }
        else:
            plan = {
                "Total Cost": 22.0,
                "Node Type": "Seq Scan",
            }

        return FakeResult([{"Plan": plan}])

    async def execute(self, statement, params=None):
        sql = str(statement)
        self.statements.append(sql)

        if "hypopg_reset" in sql and self.fail_reset:
            raise SQLAlchemyError("Simulated HypoPG cleanup failure.")

        if "hypopg_create_index" in sql:
            ddl = params["ddl"]
            self.ddls.append(ddl)

            allowed_ddls = {
                'CREATE INDEX ON "orders" ("user_id")',
                'CREATE INDEX ON "products" ("name" text_pattern_ops)',
            }
            assert ddl in allowed_ddls

            if self.missing_index:
                return FakeResult(None)

            index_name = (
                FAKE_PATTERN_INDEX_NAME
                if "text_pattern_ops" in ddl
                else FAKE_INDEX_NAME
            )
            return FakeResult(index_name)

        return FakeResult(None)

    async def invalidate(self):
        self.invalidated = True


class FakeConnectionContext:
    def __init__(self, connection):
        self.connection = connection

    async def __aenter__(self):
        return self.connection

    async def __aexit__(self, exc_type, exc, traceback):
        return False


class FakeEngine:
    def __init__(self, connection):
        self.connection = connection

    def connect(self):
        return FakeConnectionContext(self.connection)


@pytest.mark.asyncio
async def test_compares_baseline_and_hypothetical_plan(monkeypatch):
    connection = FakeConnection()
    monkeypatch.setattr(
        "app.verifier.hypopg.sandbox_engine",
        FakeEngine(connection),
    )

    result = await compare_hypothetical_index(
        "SELECT * FROM orders WHERE user_id = 12345",
        IndexCandidate("orders", ("user_id",)),
    )

    assert result.status == "compared"
    assert result.baseline_cost == 20.0
    assert result.candidate_cost == 12.0
    assert result.baseline_node_type == "Seq Scan"
    assert result.candidate_node_type == "Index Scan"
    assert result.baseline_index_names == ()
    assert result.candidate_index_names == (FAKE_INDEX_NAME,)
    assert result.candidate_index_name == FAKE_INDEX_NAME
    assert result.candidate_index_used is True
    assert any("hypopg_reset" in s for s in connection.statements)
    assert connection.invalidated is False


@pytest.mark.asyncio
async def test_supports_pattern_operator_class(monkeypatch):
    connection = FakeConnection()
    monkeypatch.setattr(
        "app.verifier.hypopg.sandbox_engine",
        FakeEngine(connection),
    )

    result = await compare_hypothetical_index(
        "SELECT * FROM products WHERE name LIKE 'phone%'",
        IndexCandidate(
            "products",
            ("name",),
            ("text_pattern_ops",),
        ),
    )

    assert result.status == "compared"
    assert result.candidate_index_used is True
    assert result.candidate_index_name == FAKE_PATTERN_INDEX_NAME
    assert (
        'CREATE INDEX ON "products" ("name" text_pattern_ops)'
        in connection.ddls
    )


@pytest.mark.asyncio
async def test_reports_when_candidate_index_is_not_used(monkeypatch):
    connection = FakeConnection(use_candidate_index=False)
    monkeypatch.setattr(
        "app.verifier.hypopg.sandbox_engine",
        FakeEngine(connection),
    )

    result = await compare_hypothetical_index(
        "SELECT * FROM orders WHERE user_id = 12345",
        IndexCandidate("orders", ("user_id",)),
    )

    assert result.status == "compared"
    assert result.candidate_index_used is False
    assert result.candidate_node_type == "Seq Scan"
    assert "exact proposed" in result.reason


@pytest.mark.asyncio
async def test_rejects_invalid_candidate_before_connecting(monkeypatch):
    def unexpected_connect():
        pytest.fail("Database should not be contacted.")

    monkeypatch.setattr(
        "app.verifier.hypopg.sandbox_engine",
        type("Engine", (), {"connect": staticmethod(unexpected_connect)})(),
    )

    result = await compare_hypothetical_index(
        "SELECT * FROM orders",
        IndexCandidate("unknown_table", ("user_id",)),
    )

    assert result.status == "rejected"


@pytest.mark.asyncio
async def test_rejects_non_select_query(monkeypatch):
    connection = FakeConnection()
    monkeypatch.setattr(
        "app.verifier.hypopg.sandbox_engine",
        FakeEngine(connection),
    )

    result = await compare_hypothetical_index(
        "DELETE FROM orders",
        IndexCandidate("orders", ("user_id",)),
    )

    assert result.status == "rejected"
    assert connection.explain_count == 0


@pytest.mark.asyncio
async def test_rejects_unresolved_parameter_reference(monkeypatch):
    connection = FakeConnection()
    monkeypatch.setattr(
        "app.verifier.hypopg.sandbox_engine",
        FakeEngine(connection),
    )

    result = await compare_hypothetical_index(
        "SELECT * FROM orders WHERE user_id = $1",
        IndexCandidate("orders", ("user_id",)),
    )

    assert result.status == "rejected"
    assert connection.explain_count == 0


@pytest.mark.asyncio
async def test_database_failure_is_reported_safely(monkeypatch):
    connection = FakeConnection(fail=True)
    monkeypatch.setattr(
        "app.verifier.hypopg.sandbox_engine",
        FakeEngine(connection),
    )

    result = await compare_hypothetical_index(
        "SELECT * FROM orders",
        IndexCandidate("orders", ("user_id",)),
    )

    assert result.status == "failed"
    assert "SQLAlchemyError" in result.reason
    assert "Simulated database failure" not in result.reason


@pytest.mark.asyncio
async def test_missing_hypothetical_index_fails_safely(monkeypatch):
    connection = FakeConnection(missing_index=True)
    monkeypatch.setattr(
        "app.verifier.hypopg.sandbox_engine",
        FakeEngine(connection),
    )

    result = await compare_hypothetical_index(
        "SELECT * FROM orders WHERE user_id = 12345",
        IndexCandidate("orders", ("user_id",)),
    )

    assert result.status == "failed"
    assert connection.explain_count == 1
    assert any("hypopg_reset" in s for s in connection.statements)


@pytest.mark.asyncio
async def test_cleanup_failure_invalidates_connection(monkeypatch):
    connection = FakeConnection(fail_reset=True)
    monkeypatch.setattr(
        "app.verifier.hypopg.sandbox_engine",
        FakeEngine(connection),
    )

    result = await compare_hypothetical_index(
        "SELECT * FROM orders WHERE user_id = 12345",
        IndexCandidate("orders", ("user_id",)),
    )

    assert connection.invalidated is True
    assert result.status == "failed"
    assert "SQLAlchemyError" in result.reason


@pytest.mark.asyncio
async def test_successful_cleanup_does_not_invalidate_connection(monkeypatch):
    connection = FakeConnection()
    monkeypatch.setattr(
        "app.verifier.hypopg.sandbox_engine",
        FakeEngine(connection),
    )

    result = await compare_hypothetical_index(
        "SELECT * FROM orders WHERE user_id = 12345",
        IndexCandidate("orders", ("user_id",)),
    )

    assert result.status == "compared"
    assert connection.invalidated is False
