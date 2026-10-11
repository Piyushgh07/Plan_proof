# Plan Proof

Plan Proof is a verified PostgreSQL query advisor. It collects slow query
statistics, explains supported queries, proposes conservative index candidates,
and checks every candidate with PostgreSQL's planner and HypoPG before making a
recommendation. The web dashboard displays live workload data, verification
history, plan evidence, benchmark results, and service readiness.

## Why it exists

A column appearing in a filter or join does not guarantee that an index will
help. A valid index can go unused, provide little estimated improvement, or
add write and storage costs. Plan Proof compares the baseline plan with a plan
that includes a hypothetical index, then applies a documented decision rule.
It never creates the proposed index in the target database.

## Architecture

```text
API client
   |
   v
FastAPI
   |--------------------|----------------------|
   v                    v                      v
Target PostgreSQL   Sandbox PostgreSQL    Application database
pg_stat_statements  HypoPG plan checks    Runs and decisions
read-only EXPLAIN   representative schema PostgreSQL / app_db
   |
   v
Collect -> capture plan -> heuristic candidates -> validate
                                      -> compare -> decide -> persist

Redis is included in Compose and reported by the system readiness check. The
application does not currently use Redis for job processing.
```

The target and sandbox should use matching schema, representative data,
statistics, and planner settings. The target is queried read-only. The sandbox
is the only database where HypoPG verification runs. The application stores
analysis and verification records in `app_db`.

## Stack

- Python 3.12, FastAPI, Pydantic, SQLAlchemy, asyncpg, Alembic
- PostgreSQL 16 with `pg_stat_statements`
- PostgreSQL 16 with HypoPG in the isolated sandbox
- Docker Compose and Redis 7
- `pglast` for SQL parsing and validation

## Requirements

- Docker Engine with the Compose plugin
- Python 3.12 for local commands and tests
- Node.js 22 for local frontend development (the Compose frontend is built in
  its own container)
- Approximately 12.6 million benchmark rows when following the complete
  benchmark setup (500k users, 100k products, 2M orders, 5M order items, and
  5M events)

## Setup

1. Copy the environment template and set local passwords:

   ```sh
   cp .env.example .env
   ```

   Set unique passwords for `TARGET_ADMIN_PASSWORD`, `APP_DB_PASSWORD`,
   `TARGET_READER_PASSWORD`, and `SANDBOX_PASSWORD`. Use the same password
   for each host-side URL and its matching `*_PASSWORD` variable. Keep `.env`
   private; it is ignored by Git. The example URLs use the published local
   ports.

2. Start the complete application. Compose initializes an empty target volume
   with the database roles and statistics extension, and an empty sandbox
   volume with HypoPG and the benchmark schema. The API applies its Alembic
   migration when it starts:

   ```sh
   docker compose up --build -d
   docker compose ps
   ```

   Open the dashboard at <http://localhost:3000>. The API is available at
   <http://localhost:8000> and its interactive documentation at
   <http://localhost:8000/docs>. Compose reuses existing named volumes; it does
   not reset or remove database data.

   Existing named volumes are reused. Initialization scripts run only when a
   PostgreSQL data directory is first created. If an existing target volume
   predates the reader-role setup, provision that role and its read-only
   grants manually before using `/api/v1/analyze`.

3. For local backend development and benchmark scripts, install Python 3.12:

   ```sh
   python3.12 -m venv .venv
   . .venv/bin/activate
   pip install -e '.[dev]'
   ```

   The Compose API runs migrations automatically. If running the API directly
   on the host, apply them with `.venv/bin/alembic upgrade head` before starting
   Uvicorn. The metadata database is `app_db`, separate from the workload
   database `target_db`.

4. Load the benchmark into the target database if it is empty:

   ```sh
   BENCHMARK_DATABASE_URL='postgresql://target_admin:<TARGET_ADMIN_PASSWORD>@localhost:5433/target_db' \
     .venv/bin/python -m app.benchmark.load
   ```

   Load the same deterministic dataset into the initialized sandbox if needed:

   ```sh
   SANDBOX_BENCHMARK_DATABASE_URL='postgresql://sandbox_admin:<SANDBOX_PASSWORD>@localhost:5434/sandbox_db' \
     .venv/bin/python -m app.benchmark.load_sandbox
   ```

   The target loader creates the benchmark schema and inserts rows. The
   sandbox schema is created during first-time Compose initialization; its
   loader inserts rows and refuses to append when any benchmark table already
   has rows. Do not run either loader against a database that already contains
   data.

5. Start the API and check health:

   ```sh
   docker compose up -d app
   curl http://localhost:8000/health
   ```

   This optional command starts only the API after the other services are
   ready. For the full stack, the earlier Compose command is sufficient. The
   `app` service reads Compose service addresses and credential values
   from `.env`. The host-side Alembic and benchmark commands use the local
   `localhost` URLs in the same file.

### Local frontend development

The web container serves the production build on port 3000. To run the Vite
development server instead, keep the Compose API and databases running, then:

```sh
cd frontend
npm ci
npm run dev
```

Open <http://localhost:5173>; Vite proxies `/api` and `/health` to the local API
on port 8000. `npm run typecheck` checks TypeScript, and `npm run build`
produces the same static frontend used by Compose. `frontend/.env.example`
contains the optional API base URL setting and no credentials.

## Environment variables

`.env.example` lists the variables used by the local tools and Compose. The
important values are:

- `APP_DATABASE_URL`: host-side SQLAlchemy URL for `app_db`.
- `TARGET_DATABASE_URL`: host-side read-only target URL for `target_db`.
- `SANDBOX_DATABASE_URL`: host-side sandbox URL for HypoPG verification.
- `TARGET_ADMIN_PASSWORD`: initial target administrator password.
- `APP_DB_PASSWORD`: app metadata role password.
- `TARGET_READER_PASSWORD`: read-only target role password.
- `SANDBOX_PASSWORD`: sandbox role password.
- `REDIS_URL`: Redis URL.

Compose uses the role and password variables to construct service-to-service
URLs. URL passwords with reserved characters should be percent-encoded in the
host-side URLs; use URL-safe passwords for the separate Compose values.

## API

### `GET /health`

Returns application health and the configured environment. This checks the
HTTP service, not the health of each database connection.

### `POST /api/v1/verify`

Validates a query and an index proposal, compares baseline and candidate plans
in the sandbox, persists the result, and returns the comparison and decision.

Example:

```sh
curl -sS http://localhost:8000/api/v1/verify \
  -H 'Content-Type: application/json' \
  -d '{
    "sql": "SELECT * FROM orders WHERE user_id = 12345",
    "table_name": "orders",
    "columns": ["user_id"]
  }'
```

The response includes `comparison.status`, estimated costs, whether the exact
hypothetical index was selected, plan summaries, and a decision. The current
policy accepts a candidate only when PostgreSQL selects it and the estimated
cost falls by at least 10 percent. It rejects unused or non-improving indexes
and returns an inconclusive decision when comparison fails or falls below the
threshold.

### `POST /api/v1/analyze`

Collects up to 100 top queries from `pg_stat_statements`, ranked by total
execution time, captures read-only target plans, generates deterministic
single-column candidates for supported filters and equality joins, verifies
them in the sandbox, persists outcomes, and returns per-query results.

```sh
curl -sS http://localhost:8000/api/v1/analyze \
  -H 'Content-Type: application/json' \
  -d '{"limit": 10}'
```

Each query reports its statistics and plan status. Candidate entries report
comparison status, decision, explanation, and estimated cost improvement.
Queries that fail validation or have no supported candidates receive a clear
reason instead of a fabricated verification.

The same endpoint accepts `{"sql":"SELECT ..."}` to analyze one submitted
query. It returns the captured plan, heuristic candidates, comparison evidence,
and decision. Queries with unresolved `$1` parameters remain unsupported; the
advisor never guesses values.

### Read APIs

- `GET /api/v1/workload?limit=100` returns actual `pg_stat_statements` query
  text, calls, execution-time statistics, row counts, and parameter eligibility.
- `GET /api/v1/history?limit=20&offset=0` lists persisted verification runs;
  `GET /api/v1/history/{run_id}` returns one run with its plans and outcomes.
- `GET /api/v1/benchmark` serves the checked-in benchmark evaluation report.
- `GET /api/v1/status` checks the application database, read-only target,
  sandbox HypoPG extension, and Redis. It returns generic errors only, never
  connection strings or credentials.

## How verification works

1. Parse the input with `pglast`; accept exactly one non-locking `SELECT`.
2. Check the table, columns, and optional operator class against the explicit
   schema allowlist.
3. Capture a baseline `EXPLAIN (FORMAT JSON)` plan.
4. Register the validated index definition with HypoPG in the sandbox.
5. Capture the candidate plan and check for the exact hypothetical index name.
6. Compare estimated planner costs and apply the 10 percent decision policy.
7. Reset HypoPG state and persist the outcome in one application transaction.

The target connection defaults to read-only transactions and both database
engines use a 30 second statement timeout. The API does not run
`EXPLAIN ANALYZE` and does not create physical indexes on the target.

## Reproducible demo

With the services, migrations, and matching benchmark data ready:

```sh
curl http://localhost:8000/health

curl -sS http://localhost:8000/api/v1/verify \
  -H 'Content-Type: application/json' \
  -d '{"sql":"SELECT * FROM orders WHERE user_id = 12345","table_name":"orders","columns":["user_id"]}'

curl -sS http://localhost:8000/api/v1/analyze \
  -H 'Content-Type: application/json' \
  -d '{"limit":10}'
```

The dashboard at <http://localhost:3000> includes Overview, Query workload,
Analyze query, Analysis history, Benchmark, and System status screens. The
Analyze screen accepts a SELECT and offers direct candidate verification with
baseline and candidate plan summaries. `/verify` demonstrates a direct
proposal. `/analyze` demonstrates collection, plan capture, candidate
generation, verification, and persistence. Its results
depend on actual query statistics in the target. `pg_stat_statements` commonly
normalizes constants to `$1`; those query entries are reported as unsupported
until the project has a safe way to bind representative parameter values.
The parameter-free demo query below records a query the current workflow can
plan:

```sh
.venv/bin/python scripts/record_demo_query.py
curl -sS http://localhost:8000/api/v1/analyze \
  -H 'Content-Type: application/json' \
  -d '{"limit":100}'
```

The captured health, verification, and analysis responses are in
[reports/api-demo-response.json](reports/api-demo-response.json).

## Tests

Run the unit and API tests:

```sh
.venv/bin/python -m pytest -q
```

The live sandbox test requires the Compose services and valid `.env` settings.
The test suite must be run with the database setup available; it does not
reset or recreate named volumes.

## Dataset and evaluation

`app/benchmark/config.py` defines the deterministic dataset size and seed.
`app/benchmark/workload.py` contains 40 workload queries; scripts under
`scripts/` compare plans and calculate candidate outcomes. Saved reports are
exploratory artifacts, not claims about general accuracy or production speed.

Run the current sandbox evaluation with:

```sh
.venv/bin/python scripts/evaluate_benchmark.py
```

The run recorded in [reports/benchmark-evaluation.json](reports/benchmark-evaluation.json)
on 11 October 2026 captured baseline plans for all 40 queries. The evaluator
compared 13 explicitly mapped index proposals: 8 were accepted, 4 were
rejected because PostgreSQL did not select the proposed hypothetical index,
and 1 was inconclusive because its estimated improvement was 4.28%, below the
10% threshold. That is a 4/13 (30.8%) rejection rate among these successfully
compared proposals; 1 additional proposal was inconclusive. Eight of the 13
outcomes agreed with the workload's provisional `CREATE_INDEX` labels. The
other 27 workload queries had no mapped proposal and are excluded from those
candidate rates.

This is one deterministic workload run, not a general accuracy estimate.
Workload labels are provisional annotations rather than ground truth, and the
evaluator uses explicit proposal mappings rather than comparing heuristic and
LLM generators. It records PostgreSQL planner estimates only; it does not
measure execution latency.

The evaluation scripts report planner estimates and plan selection. Estimated
cost is not measured latency. A real latency claim would require a separate
controlled benchmark with repeatable execution conditions, warm and cold cache
considerations, and measurement methodology.

## Known limitations

- Candidate generation supports a narrow set of simple filters and equality
  joins over an explicit allowlist.
- Queries containing unresolved parameters are rejected; values are not
  guessed or substituted.
- Target and sandbox schema, data, statistics, PostgreSQL settings, and
  extensions must be kept representative of one another.
- HypoPG results are planner estimates and do not measure execution time,
  write overhead, storage use, or operational impact.
- There is no authentication, background queue, automatic index application,
  or LLM candidate generator. Keep the dashboard on a trusted local network.
- `pg_stat_statements` eligibility and SQL AST validation are conservative
  safeguards, not a complete SQL security boundary.

## Future work

After the MVP is stable: safely handle parameterized query examples; add
structured LLM candidate generation through the same validation and
verification path; record controlled runtime benchmarks separately from
planner estimates; broaden query support; and add API authentication and
operational limits.
