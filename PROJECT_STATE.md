# Project State

## Project

Plan Proof — verified PostgreSQL query advisor.

## Current Part

Part 0 — Infrastructure: COMPLETE

## Environment

- OS: Ubuntu
- Python: 3.12.3
- Docker: 29.8.2
- Docker Compose: 5.5.1
- PostgreSQL: 16.15
- pg_stat_statements: 1.10
- HypoPG: 1.4.3
- Redis: 7

## Python Packages Currently Installed

- FastAPI: 0.142.2
- Uvicorn: 0.54.0
- Pydantic: 2.13.5
- pydantic-settings: 2.15.0
- SQLAlchemy: 2.1.3
- asyncpg: 0.31.0
- pytest: 9.1.1
- pytest-asyncio: 1.4.0
- ruff: 0.16.10

## Completed

- Git repository initialized.
- Docker Compose infrastructure created.
- Target PostgreSQL container created.
- `pg_stat_statements` enabled and verified.
- Sandbox PostgreSQL container created.
- HypoPG 1.4.3 installed and verified.
- Redis 7 container created and verified.
- `app_db` created.
- `app_user` created.
- `app_user` blocked from connecting to `target_db`.
- FastAPI application created.
- `/health` endpoint created.
- FastAPI Docker image created.
- FastAPI container started successfully.
- App-to-PostgreSQL connectivity verified for `app_db`, `target_db`, and `sandbox_db`.

## Current Structure

```text
plan-proof/
├── app/
│   ├── core/
│   │   └── settings.py
│   └── main.py
├── docker/
│   ├── sandbox/
│   │   └── Dockerfile
│   └── target/
│       └── init.sql
├── docker-compose.yml
├── Dockerfile
├── .env.example
├── .gitignore
├── DECISIONS.md
├── PROJECT_STATE.md
├── pyproject.toml
├── README.md
├── tests/
└── .venv/

## Part 1 — Benchmark Dataset

Status: COMPLETE

### Dataset

- users: 500,000
- products: 100,000
- orders: 2,000,000
- order_items: 5,000,000
- events: 5,000,000
- Total rows: 12,600,000

### Generator

- `app/benchmark/config.py`
- `app/benchmark/generator.py`
- `app/benchmark/workload.py`
- `app/benchmark/load.py`

### Database

- Benchmark schema: `docker/benchmark/schema.sql`
- Target database: PostgreSQL 16.15
- Data loaded using asyncpg PostgreSQL COPY
- `ANALYZE` executed after loading

### Validation

- Expected row counts: PASS
- Foreign-key integrity: PASS
- Data distributions: PASS
- Baseline indexes: PASS
- PostgreSQL statistics: PASS

### Important Methodology

Workload expected fixes are provisional until verified experimentally using PostgreSQL execution plans and controlled measurements.

## Part 2 — Application Database

Status: VERIFIED

### Models
- `AnalysisRun`
- `QueryRecord`
- `Candidate`
- `Verification`

### Migration
- Initial revision: `0001_initial_app_schema`
- Alembic upgrade: PASS
- Alembic current revision: PASS
- Verified tables: alembic_version, analysis_runs, candidates, queries, verifications

## Part 3 — Safe Database Connections

Status: VERIFIED

- [x] Dedicated target reader role created.
- [x] Target read access verified.
- [x] Target write attempt rejected by PostgreSQL permissions.
- [x] Target connection verified with read-only mode enabled.
- [x] Sandbox connection verified.
- [x] Statement timeout verified at 30 seconds.
- [x] Target and sandbox credentials configured separately.
## Part 4 — Query Collection and Plan Capture

Status: INITIAL IMPLEMENTATION VERIFIED; HARDENING REMAINS

- [x] Query statistics collector implemented.
- [x] SQL validator tests pass, including nested row-locking cases.
- [x] JSON plan capture implemented using `EXPLAIN (FORMAT JSON)`.
- [x] Plan capture uses a read-only transaction.
- [x] Unresolved parameter references are rejected.
- [x] Live plan-capture smoke test succeeded.
- [x] Earlier milestone test suite: 25 passed; current full suite: 79 passed.
- [x] AST-based parameter detection implemented and tested.
- [x] Database connection failure is reported safely without leaking details.
- [ ] Add more plan-capture and parameter edge-case tests.
- [ ] Review query eligibility and planning-time side-effect risks before treating this as production-safe.
- [x] All 40 benchmark queries successfully produced JSON plans.


## Benchmark Validation Note — Q011 and Q031

- [x] Corrected expected index metadata for Q011 and Q031; both use provisional `NO_CHANGE` labels.
- [x] Confirmed PostgreSQL rejects a direct index on `DATE(timestamptz)` in the sandbox.
- [ ] Implement and verify query-rewrite candidates for these cases.


## Part 5 — API Verification and Error Handling

Status: INITIAL IMPLEMENTATION VERIFIED; FURTHER HARDENING REQUIRED

### Implemented
- `GET /health` health endpoint.
- `POST /api/v1/verify` index-verification endpoint.
- Request validation using Pydantic.
- SELECT-only SQL validation and rejection of multiple statements.
- Rejection of unresolved SQL parameters.
- Explicit table and column allowlists for index candidates.
- Hypothetical-index comparison using HypoPG in the sandbox.
- Conservative accept, reject, and inconclusive decision outcomes.
- Generic HTTP 503 response for unexpected comparison exceptions.
- Internal logging of unexpected comparison exceptions.
- API regression tests using a mocked comparison.

### Verification
- Useful hypothetical-index candidate accepted in a live API smoke test.
- Unselected hypothetical-index candidate rejected in a live API smoke test.
- Invalid SQL, unresolved parameters, unsupported columns, and multiple statements rejected.
- Failed comparison result produces an inconclusive decision.
- Unexpected comparison exception produces a generic HTTP 503 response.
- Latest automated test suite: 79 passed.

### Remaining Work
- Real database connection failure handling tested.
- HypoPG cleanup and connection invalidation tested.
- Expand API integration tests.
- Review query-planning side effects and resource limits.
- Document and benchmark actual query execution times separately from planner costs.

### Limitations
- Planner cost improvement is not measured runtime improvement.
- Hypothetical indexes are not permanent indexes.
- Passing tests do not establish production readiness.

## Current Verified Status — October 2026

### HypoPG Verifier Reliability
- Handles unexpected sandbox connection failures and returns a failed verification result.
- Error messages expose the exception type, not raw connection details.
- HypoPG cleanup is tested for both successful resets and cleanup failures.
- Failed cleanup invalidates the affected database connection.
- Real connection-refusal behavior is covered by a test.

### Verification
- Full test suite: 79 passed.
- HypoPG cleanup tests: 2 passed.
- Latest test run: 79 passed in 0.56 seconds.
- Latest relevant commit: `8a71679` — Handle real sandbox connection failures.
- Working tree was clean immediately after that commit; subsequent test runs do not modify tracked files.

### Next Steps
1. Review the overall project state and remove outdated test counts from earlier sections.
2. Identify the next incomplete Plan Proof milestone.
3. Continue development with tests for every new behavior.


## Latest Verified Status — 11 October 2026

- **Latest commit:** `970c09e` — Harden HypoPG verifier failure handling
- **Test suite:** 87 passed
- **HypoPG verifier tests:** 18 passed
- **Git working tree:** Clean
- **Verification:** `git diff --check` completed without errors before commit.
- **Failure handling:** HypoPG cleanup failures now cause verification to return `failed` and invalidate the connection, rather than reporting a successful comparison.

### Latest Changes

- Added HypoPG verifier failure-path tests.
- Covered baseline EXPLAIN failures, hypothetical index creation failures, candidate EXPLAIN failures, malformed plan output, missing total cost, cleanup failures, and Python timeout handling.
- Committed the changes as `970c09e`.

### Current Checkpoint

The latest test run completed successfully with **87 passing tests**, including **18 HypoPG tests**. The changes are committed, and the Git working tree was clean immediately after the commit.

### Next Step

Inspect the remaining application modules and tests, identify unfinished project-critical functionality, and prioritize completing the end-to-end Plan Proof workflow before final documentation and GitHub presentation.