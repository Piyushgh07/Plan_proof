from dataclasses import dataclass


@dataclass(frozen=True)
class BenchmarkConfig:
    seed: int = 42

    users: int = 500_000
    products: int = 100_000
    orders: int = 2_000_000
    order_items: int = 5_000_000
    events: int = 5_000_000


BENCHMARK_CONFIG = BenchmarkConfig()