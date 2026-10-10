
from sqlalchemy import event
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.settings import settings


def async_database_url(url: str) -> str:
    """Use asyncpg for asynchronous PostgreSQL connections."""
    parsed_url = make_url(url)
    return parsed_url.set(drivername="postgresql+asyncpg").render_as_string(
        hide_password=False
    )


target_engine = create_async_engine(
    async_database_url(settings.target_database_url),
    pool_pre_ping=True,
    connect_args={
        "server_settings": {
            "statement_timeout": "30000",
        }
    },
)

sandbox_engine = create_async_engine(
    async_database_url(settings.sandbox_database_url),
    pool_pre_ping=True,
    connect_args={
        "server_settings": {
            "statement_timeout": "30000",
        }
    },
)


@event.listens_for(target_engine.sync_engine, "connect")
def set_target_read_only(dbapi_connection, connection_record) -> None:
    """Default target transactions to read-only."""
    dbapi_connection.execute("SET default_transaction_read_only = on")
