## Part 0 — Infrastructure

- PostgreSQL 16.15 is used for the target and sandbox environments.
- The target PostgreSQL server hosts both `target_db` and `app_db` to keep the development stack compact; separate roles enforce the target read-only boundary.
- `target_db` uses `target_admin` and has `pg_stat_statements` 1.10 preloaded; `app_user` cannot CONNECT to `target_db`.
- The sandbox uses HypoPG 1.4.3 for hypothetical-index verification; no candidate DDL is executed against the target.
- FastAPI runs in its own Docker container and communicates through Compose service names (`target`, `sandbox`, `redis`) rather than `localhost`.
- Redis 7 is included for the future ARQ job queue.

## Part 1 — Benchmark Dataset

- The benchmark uses a deterministic seed (`42`) so dataset generation is reproducible.
- Benchmark data is generated in bounded batches and loaded with PostgreSQL `COPY` rather than millions of individual INSERT statements.
- The benchmark contains 500k users, 100k products, 2M orders, 5M order_items, and 5M events.
- Foreign-key integrity was validated after loading; all orphan checks returned zero.
- PostgreSQL statistics are explicitly refreshed with `ANALYZE` after dataset loading.
- Baseline indexes are intentionally incomplete so the workload contains realistic opportunities for index recommendations.
- Workload labels are treated as provisional until actual PostgreSQL plans and controlled experiments establish the best fix; labels are not assumed to be ground truth.

## Part 2 — Application Database and Migrations

- SQLAlchemy 2 models define `AnalysisRun`, `QueryRecord`, `Candidate`, and `Verification`.
- PostgreSQL stores query plans and verification details using JSONB.
- Alembic manages schema changes through versioned migrations.
- The initial migration, `0001_initial_app_schema`, was applied successfully.
- The application metadata database (`app_db`) remains separate from the benchmark target database (`target_db`).
- Database connections use the asynchronous SQLAlchemy engine with `asyncpg`.

## Part 3 — Safe Database Connections

- Created a dedicated `plan_proof_reader` role for target database analysis.
- Verified that the reader role can read benchmark data but cannot update target tables.
- Configured target connections to default to read-only transactions.
- Configured target and sandbox connections with a 30-second statement timeout.
- Verified target connection: `target_db`, user `plan_proof_reader`, read-only setting `on`.
- Verified sandbox connection: `sandbox_db`, user `sandbox_admin`, statement timeout `30s`.
- Kept the application, target, and sandbox database responsibilities separate.
- Database passwords are configured locally and excluded from version control.

## Part 4 — Query Collection and Plan Capture

- Query statistics are collected from `pg_stat_statements` using the dedicated `plan_proof_reader` role.
- Initial collection is limited to eligible SELECT statements; row-locking queries are excluded.
- `pglast` rejects non-SELECT statements, multiple statements, syntax errors, and detected row-locking clauses, including nested subqueries.
- Plan capture uses `EXPLAIN (FORMAT JSON)`, not `EXPLAIN ANALYZE`.
- Plan capture uses a read-only transaction and the existing 30-second target statement timeout.
- Queries containing unresolved parameter references are rejected.
- Parameter references are detected using pglast AST `ParamRef` nodes.
- Plan capture reports `captured`, `rejected`, or `failed` outcomes.
- Database connection failures are reported without exposing sensitive database error details.
- All 40 benchmark workload queries (Q001–Q040) successfully produced JSON plans in the target database.
- AST validation is a targeted safeguard, not a complete SQL security boundary. Database permissions, read-only transactions, and timeouts remain necessary.

## Benchmark Validation Note — Q011 and Q031

- PostgreSQL rejected an expression index on `DATE(timestamptz)` because the expression is not immutable.
- Q011 (`orders.created_at`) and Q031 (`events.occurred_at`) now use provisional `NO_CHANGE` expected-action labels, with no expected index expression.
- The original query SQL remains unchanged.
- `NO_CHANGE` is provisional; query-rewrite candidates still need implementation and verification.
- The expression-index experiment ran in the sandbox inside a transaction and was rolled back.
