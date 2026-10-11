"""Run a parameter-free query to populate pg_stat_statements for the demo."""

import asyncio

from sqlalchemy import text

from app.db.connections import target_engine

DEMO_QUERY = text(
    "SELECT count(*) FROM orders "
    "WHERE user_id = (SELECT min(id) FROM users)"
)


async def main() -> None:
    try:
        async with target_engine.connect() as connection, connection.begin():
            await connection.execute(text("SET TRANSACTION READ ONLY"))
            result = await connection.execute(DEMO_QUERY)
            count = result.scalar_one()

        print(
            "Recorded the parameter-free demo query in pg_stat_statements "
            f"(matching order count: {count})."
        )
    finally:
        await target_engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
