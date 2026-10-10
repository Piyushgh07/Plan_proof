
from sqlalchemy import text

from app.collector.models import QueryStats
from app.db.connections import target_engine


STATISTICS_QUERY = text("""
    SELECT
        queryid,
        calls,
        total_exec_time,
        mean_exec_time,
        rows,
        query
    FROM pg_stat_statements
    WHERE queryid IS NOT NULL
      AND query IS NOT NULL
      AND query <> '<insufficient privilege>'
      AND calls > 0
      AND upper(left(ltrim(query), 6)) = 'SELECT'
      AND position(' FOR UPDATE' IN upper(query)) = 0
      AND position(' FOR SHARE' IN upper(query)) = 0
      AND position(' FOR KEY SHARE' IN upper(query)) = 0
      AND position(' FOR NO KEY UPDATE' IN upper(query)) = 0
    ORDER BY total_exec_time DESC
    LIMIT :limit
""")


async def collect_query_stats(limit: int = 100) -> list[QueryStats]:
    """Collect eligible SELECT query statistics from the target database."""
    if not 1 <= limit <= 1000:
        raise ValueError("Limit must be between 1 and 1000.")

    async with target_engine.connect() as conn:
        result = await conn.execute(STATISTICS_QUERY, {"limit": limit})
        rows = result.mappings().all()

    return [
        QueryStats(
            queryid=row["queryid"],
            calls=row["calls"],
            total_exec_time=row["total_exec_time"],
            mean_exec_time=row["mean_exec_time"],
            rows=row["rows"],
            query=row["query"],
        )
        for row in rows
    ]
