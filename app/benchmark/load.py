import asyncio
import os

import asyncpg

from app.benchmark.config import BENCHMARK_CONFIG
from app.benchmark.generator import (
    create_random,
    generate_batches,
    generate_event,
    generate_order,
    generate_order_item,
    generate_product,
    generate_user,
)


DATABASE_URL = os.getenv(
    "BENCHMARK_DATABASE_URL",
    "postgresql://target_admin:target_admin_password@localhost:5433/target_db",
)

BATCH_SIZE = 10_000


SCHEMA_PATH = "docker/benchmark/schema.sql"


async def create_schema(connection: asyncpg.Connection) -> None:
    with open(SCHEMA_PATH, encoding="utf-8") as file:
        schema_sql = file.read()

    await connection.execute(schema_sql)


async def load_users(connection: asyncpg.Connection) -> None:
    rng = create_random()

    for batch in generate_batches(
        BENCHMARK_CONFIG.users,
        BATCH_SIZE,
        generate_user,
        rng,
    ):
        await connection.copy_records_to_table(
            "users",
            records=batch,
            columns=[
                "id",
                "email",
                "country",
                "is_active",
                "created_at",
            ],
        )


async def load_products(connection: asyncpg.Connection) -> None:
    rng = create_random()

    for batch in generate_batches(
        BENCHMARK_CONFIG.products,
        BATCH_SIZE,
        generate_product,
        rng,
    ):
        await connection.copy_records_to_table(
            "products",
            records=batch,
            columns=[
                "id",
                "category",
                "name",
                "price",
                "stock_quantity",
                "created_at",
            ],
        )


async def load_orders(connection: asyncpg.Connection) -> None:
    rng = create_random()

    for batch in generate_batches(
        BENCHMARK_CONFIG.orders,
        BATCH_SIZE,
        lambda random_generator, order_id: generate_order(
            random_generator,
            order_id,
            BENCHMARK_CONFIG.users,
        ),
        rng,
    ):
        await connection.copy_records_to_table(
            "orders",
            records=batch,
            columns=[
                "id",
                "user_id",
                "status",
                "total_amount",
                "created_at",
            ],
        )


async def load_order_items(connection: asyncpg.Connection) -> None:
    rng = create_random()

    for batch in generate_batches(
        BENCHMARK_CONFIG.order_items,
        BATCH_SIZE,
        lambda random_generator, item_id: generate_order_item(
            random_generator,
            item_id,
            BENCHMARK_CONFIG.orders,
            BENCHMARK_CONFIG.products,
        ),
        rng,
    ):
        await connection.copy_records_to_table(
            "order_items",
            records=batch,
            columns=[
                "id",
                "order_id",
                "product_id",
                "quantity",
                "unit_price",
            ],
        )


async def load_events(connection: asyncpg.Connection) -> None:
    rng = create_random()

    for batch in generate_batches(
        BENCHMARK_CONFIG.events,
        BATCH_SIZE,
        lambda random_generator, event_id: generate_event(
            random_generator,
            event_id,
            BENCHMARK_CONFIG.users,
        ),
        rng,
    ):
        await connection.copy_records_to_table(
            "events",
            records=batch,
            columns=[
                "id",
                "user_id",
                "event_type",
                "occurred_at",
                "payload",
            ],
        )


async def main() -> None:
    print("Connecting to benchmark database...")

    connection = await asyncpg.connect(DATABASE_URL)

    try:
        print("Creating benchmark schema...")
        await create_schema(connection)

        print("Loading users...")
        await load_users(connection)

        print("Loading products...")
        await load_products(connection)

        print("Loading orders...")
        await load_orders(connection)

        print("Loading order_items...")
        await load_order_items(connection)

        print("Loading events...")
        await load_events(connection)

        print("Running ANALYZE...")
        await connection.execute("ANALYZE")

        print("Benchmark dataset loaded successfully.")

    finally:
        await connection.close()


if __name__ == "__main__":
    asyncio.run(main())