"""Tests for hypothetical PostgreSQL index verification."""

import pytest
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import create_async_engine
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

@pytest.mark.asyncio
async def test_real_sandbox_connection_failure_is_reported_safely(
    monkeypatch,
):
    # Port 1 should not have a PostgreSQL server listening.
    engine = create_async_engine(
        "postgresql+asyncpg://test_user:test_password"
        "@127.0.0.1:1/test_db",
        connect_args={"timeout": 1},
        pool_pre_ping=False,
    )
    monkeypatch.setattr(
        "app.verifier.hypopg.sandbox_engine",
        engine,
    )

    try:
        result = await compare_hypothetical_index(
            "SELECT * FROM orders WHERE user_id = 12345",
            IndexCandidate("orders", ("user_id",)),
        )

        assert result.status == "failed"
        assert "ConnectionRefusedError" in result.reason
        assert "test_password" not in result.reason
        assert "127.0.0.1" not in result.reason
    finally:
        await engine.dispose()


# --- Failure-path tests for every verifier step ---


class StepFailConnection:
    """Configurable connection that fails at a specific verifier step."""

    def __init__(self, *, fail_at, error_class=SQLAlchemyError):
        self.statements = []
        self.ddls = []
        self.explain_count = 0
        self.reset_count = 0
        self.invalidated = False
        self.fail_at = fail_at
        self.error_class = error_class

    async def execute(self, statement, params=None):
        sql = str(statement)
        self.statements.append(sql)

        if "hypopg_reset" in sql:
            self.reset_count += 1
            if self.fail_at == "cleanup_reset" and self.reset_count == 2:
                raise SQLAlchemyError("Simulated cleanup failure.")
            return FakeResult(None)

        if "hypopg_create_index" in sql:
            if self.fail_at == "create_index":
                raise self.error_class("Simulated create-index failure.")
            self.ddls.append(params["ddl"])
            return FakeResult(FAKE_INDEX_NAME)

        return FakeResult(None)

    async def exec_driver_sql(self, sql):
        self.explain_count += 1

        if self.fail_at == "baseline_explain" and self.explain_count == 1:
            raise self.error_class("Simulated baseline failure.")
        if self.fail_at == "candidate_explain" and self.explain_count == 2:
            raise self.error_class("Simulated candidate failure.")

        if self.explain_count == 1:
            plan = {"Total Cost": 20.0, "Node Type": "Seq Scan"}
        else:
            plan = {
                "Total Cost": 12.0,
                "Node Type": "Index Scan",
                "Index Name": FAKE_INDEX_NAME,
            }
        return FakeResult([{"Plan": plan}])

    async def invalidate(self):
        self.invalidated = True


@pytest.mark.asyncio
async def test_baseline_explain_failure_returns_failed(monkeypatch):
    """Baseline EXPLAIN failure prevents comparison."""
    conn = StepFailConnection(fail_at="baseline_explain")
    monkeypatch.setattr(
        "app.verifier.hypopg.sandbox_engine", FakeEngine(conn),
    )

    result = await compare_hypothetical_index(
        "SELECT * FROM orders WHERE user_id = 12345",
        IndexCandidate("orders", ("user_id",)),
    )

    assert result.status == "failed"
    assert "SQLAlchemyError" in result.reason
    assert conn.explain_count == 1


@pytest.mark.asyncio
async def test_hypopg_create_index_failure_returns_failed(monkeypatch):
    """HypoPG create-index failure returns a failed result."""
    conn = StepFailConnection(fail_at="create_index")
    monkeypatch.setattr(
        "app.verifier.hypopg.sandbox_engine", FakeEngine(conn),
    )

    result = await compare_hypothetical_index(
        "SELECT * FROM orders WHERE user_id = 12345",
        IndexCandidate("orders", ("user_id",)),
    )

    assert result.status == "failed"
    assert "SQLAlchemyError" in result.reason
    assert conn.explain_count == 1


@pytest.mark.asyncio
async def test_candidate_explain_failure_returns_failed(monkeypatch):
    """Candidate EXPLAIN failure after successful baseline returns failed."""
    conn = StepFailConnection(fail_at="candidate_explain")
    monkeypatch.setattr(
        "app.verifier.hypopg.sandbox_engine", FakeEngine(conn),
    )

    result = await compare_hypothetical_index(
        "SELECT * FROM orders WHERE user_id = 12345",
        IndexCandidate("orders", ("user_id",)),
    )

    assert result.status == "failed"
    assert "SQLAlchemyError" in result.reason
    assert conn.explain_count == 2


@pytest.mark.asyncio
async def test_malformed_explain_json_returns_failed(monkeypatch):
    """Malformed EXPLAIN JSON structure returns a failed result."""
    class MalformedPlanConnection:
        def __init__(self):
            self.statements = []
            self.invalidated = False

        async def execute(self, stmt, params=None):
            self.statements.append(str(stmt))
            return FakeResult(None)

        async def exec_driver_sql(self, sql):
            return FakeResult({"unexpected": "structure"})

        async def invalidate(self):
            self.invalidated = True

    conn = MalformedPlanConnection()
    monkeypatch.setattr(
        "app.verifier.hypopg.sandbox_engine", FakeEngine(conn),
    )

    result = await compare_hypothetical_index(
        "SELECT * FROM orders WHERE user_id = 12345",
        IndexCandidate("orders", ("user_id",)),
    )

    assert result.status == "failed"
    assert "ValueError" in result.reason


@pytest.mark.asyncio
async def test_missing_total_cost_returns_failed(monkeypatch):
    """Plan missing Total Cost key returns a failed result."""
    class MissingCostConnection:
        def __init__(self):
            self.statements = []
            self.ddls = []
            self.explain_count = 0
            self.invalidated = False

        async def execute(self, stmt, params=None):
            sql = str(stmt)
            self.statements.append(sql)
            if "hypopg_create_index" in sql:
                self.ddls.append(params["ddl"])
                return FakeResult(FAKE_INDEX_NAME)
            return FakeResult(None)

        async def exec_driver_sql(self, sql):
            self.explain_count += 1
            return FakeResult([{"Plan": {"Node Type": "Seq Scan"}}])

        async def invalidate(self):
            self.invalidated = True

    conn = MissingCostConnection()
    monkeypatch.setattr(
        "app.verifier.hypopg.sandbox_engine", FakeEngine(conn),
    )

    result = await compare_hypothetical_index(
        "SELECT * FROM orders WHERE user_id = 12345",
        IndexCandidate("orders", ("user_id",)),
    )

    assert result.status == "failed"
    assert "KeyError" in result.reason


@pytest.mark.asyncio
async def test_cleanup_failure_returns_failed_and_invalidates_connection(
    monkeypatch,
):
    """Cleanup failure must fail verification and invalidate the connection."""
    conn = StepFailConnection(fail_at="cleanup_reset")
    monkeypatch.setattr(
        "app.verifier.hypopg.sandbox_engine", FakeEngine(conn),
    )

    result = await compare_hypothetical_index(
        "SELECT * FROM orders WHERE user_id = 12345",
        IndexCandidate("orders", ("user_id",)),
    )

    assert result.status == "failed"
    assert "cleanup failure" in result.reason.lower()
    assert conn.invalidated is True


@pytest.mark.asyncio
async def test_python_timeout_returns_failed(monkeypatch):
    """A Python timeout during EXPLAIN returns a failed result."""
    conn = StepFailConnection(
        fail_at="baseline_explain",
        error_class=TimeoutError,
    )
    monkeypatch.setattr(
        "app.verifier.hypopg.sandbox_engine", FakeEngine(conn),
    )

    result = await compare_hypothetical_index(
        "SELECT * FROM orders WHERE user_id = 12345",
        IndexCandidate("orders", ("user_id",)),
    )

    assert result.status == "failed"
    assert "TimeoutError" in result.reason
    assert conn.invalidated is False
