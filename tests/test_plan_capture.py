
import pytest

from app.collector.plans import capture_plan


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "sql",
    [
        "UPDATE users SET is_active = false",
        "SELECT id FROM users FOR UPDATE",
        "SELECT 1; SELECT 2",
    ],
)
async def test_rejects_unsupported_queries(sql):
    result = await capture_plan(sql)

    assert result.status == "rejected"
    assert result.plan is None


@pytest.mark.asyncio
async def test_rejects_unresolved_parameters():
    result = await capture_plan("SELECT id FROM users WHERE id = $1")

    assert result.status == "rejected"
    assert "parameter" in result.reason.lower()
    assert result.plan is None

from sqlalchemy.exc import SQLAlchemyError


class FailingConnection:
    async def __aenter__(self):
        raise SQLAlchemyError("sensitive database details")

    async def __aexit__(self, exc_type, exc_value, traceback):
        return False


class FailingEngine:
    def connect(self):
        return FailingConnection()


@pytest.mark.asyncio
async def test_database_connection_failure_is_reported_safely(monkeypatch):
    monkeypatch.setattr(
        "app.collector.plans.target_engine",
        FailingEngine(),
    )

    result = await capture_plan("SELECT id FROM users LIMIT 5")

    assert result.status == "failed"
    assert result.plan is None
    assert "SQLAlchemyError" in result.reason
    assert "sensitive database details" not in result.reason
