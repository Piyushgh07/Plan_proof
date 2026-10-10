from decimal import Decimal
import random
from datetime import datetime, timedelta
from collections.abc import Callable, Iterator
from typing import TypeVar

from app.benchmark.config import BENCHMARK_CONFIG


COUNTRIES = (
    "IN",
    "US",
    "GB",
    "DE",
    "CA",
    "AU",
    "SG",
)

PRODUCT_CATEGORIES = (
    "electronics",
    "clothing",
    "books",
    "home",
    "sports",
    "beauty",
    "grocery",
)


def create_random() -> random.Random:
    return random.Random(BENCHMARK_CONFIG.seed)


def generate_user_id(rng: random.Random, user_count: int) -> int:
    return rng.randint(1, user_count)


def random_datetime(
    rng: random.Random,
    start: datetime,
    end: datetime,
) -> datetime:
    seconds = int((end - start).total_seconds())
    return start + timedelta(seconds=rng.randint(0, seconds))


def generate_user(
    rng: random.Random,
    user_id: int,
) -> tuple[int, str, str, bool, datetime]:
    country = rng.choices(
        COUNTRIES,
        weights=(35, 25, 10, 8, 8, 7, 7),
        k=1,
    )[0]

    is_active = rng.random() < 0.92

    created_at = random_datetime(
        rng,
        datetime(2024, 1, 1),
        datetime(2026, 9, 30),
    )

    email = f"user{user_id}@example.com"

    return (
        user_id,
        email,
        country,
        is_active,
        created_at,
    )


def generate_product(
    rng: random.Random,
    product_id: int,
) -> tuple[int, str, str, float, int, datetime]:
    category = rng.choice(PRODUCT_CATEGORIES)

    name_prefix = rng.choices(
        (
            "phone",
            "laptop",
            "tablet",
            "headphones",
            "camera",
            "chair",
            "book",
        ),
        weights=(15, 15, 10, 10, 10, 20, 20),
        k=1,
    )[0]

    name = f"{name_prefix} model {product_id}"

    price = round(rng.uniform(5, 5000), 2)
    stock_quantity = rng.randint(0, 1000)

    created_at = random_datetime(
        rng,
        datetime(2024, 1, 1),
        datetime(2026, 9, 30),
    )

    return (
        product_id,
        category,
        name,
        price,
        stock_quantity,
        created_at,
    )

T = TypeVar("T")


def generate_batches(
    count: int,
    batch_size: int,
    generator: Callable[[random.Random, int], T],
    rng: random.Random,
) -> Iterator[list[T]]:
    batch: list[T] = []

    for item_id in range(1, count + 1):
        batch.append(generator(rng, item_id))

        if len(batch) == batch_size:
            yield batch
            batch = []

    if batch:
        yield batch



ORDER_STATUSES = (
    "completed",
    "shipped",
    "processing",
    "pending",
    "cancelled",
    "returned",
)

ORDER_STATUS_WEIGHTS = (
    55,
    15,
    10,
    10,
    5,
    5,
)

EVENT_TYPES = (
    "login",
    "view_product",
    "add_to_cart",
    "purchase",
    "logout",
    "search",
)

EVENT_TYPE_WEIGHTS = (
    25,
    30,
    15,
    10,
    10,
    10,
)


def generate_order(
    rng: random.Random,
    order_id: int,
    user_count: int,
) -> tuple[int, int, str, Decimal, datetime]:
    user_id = rng.randint(1, user_count)

    status = rng.choices(
        ORDER_STATUSES,
        weights=ORDER_STATUS_WEIGHTS,
        k=1,
    )[0]

    total_amount = Decimal(rng.randint(500, 500_000)) / Decimal("100")

    created_at = random_datetime(
        rng,
        datetime(2024, 1, 1),
        datetime(2026, 9, 30),
    )

    return (
        order_id,
        user_id,
        status,
        total_amount,
        created_at,
    )


def generate_order_item(
    rng: random.Random,
    item_id: int,
    order_count: int,
    product_count: int,
) -> tuple[int, int, int, int, Decimal]:
    order_id = rng.randint(1, order_count)
    product_id = rng.randint(1, product_count)

    quantity = rng.randint(1, 5)

    unit_price = Decimal(rng.randint(500, 500_000)) / Decimal("100")

    return (
        item_id,
        order_id,
        product_id,
        quantity,
        unit_price,
    )


def generate_event(
    rng: random.Random,
    event_id: int,
    user_count: int,
) -> tuple[int, int, str, datetime, str]:
    user_id = rng.randint(1, user_count)

    event_type = rng.choices(
        EVENT_TYPES,
        weights=EVENT_TYPE_WEIGHTS,
        k=1,
    )[0]

    occurred_at = random_datetime(
        rng,
        datetime(2024, 1, 1),
        datetime(2026, 9, 30),
    )

    payload = "{}"

    return (
        event_id,
        user_id,
        event_type,
        occurred_at,
        payload,
    )