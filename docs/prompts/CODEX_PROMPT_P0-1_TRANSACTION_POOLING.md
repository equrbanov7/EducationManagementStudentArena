# Codex Task — P0-1: PgBouncer transaction-pooling + RLS (SCALABILITY-001)

> Written in English (handed to Codex). **This is the highest-risk change in the project: getting it wrong silently breaks tenant isolation.** Do NOT enable it in production first. Follow the staged plan below and STOP at any failing isolation test.

## Why this matters

EMSArena enforces tenant isolation with PostgreSQL Row-Level Security. The tenant id is stored in a PostgreSQL run-time parameter (`app.current_org_id`). Today it is set at **session scope** (`SET`, not `SET LOCAL`), which forces PgBouncer into **session pooling** — every client connection is pinned to one backend. Under high concurrency (1000+ simultaneous exam-takers) session pooling exhausts the pool and starves the DB (the baseline load test already showed the dashboard collapsing at ~500 VU).

The fix is **transaction pooling**: run each request inside one atomic transaction and set the RLS context with `SET LOCAL` (transaction-scoped) so connections can be multiplexed. The plumbing is **already built** and gated behind a flag — this task is to *finish auditing, test, and roll it out safely*, not to build it.

## Existing infrastructure (do not rebuild — verify and use)

- **Flag:** `config/settings/production.py:278` → `RLS_TRANSACTION_SCOPED = _env_bool("RLS_TRANSACTION_SCOPED", False)`. When true it sets `ATOMIC_REQUESTS=True` + `DISABLE_SERVER_SIDE_CURSORS=True`.
- **Request path:** `apps/organizations/middleware.py` — when the flag is on, wraps the request in `connection.execute_wrapper(RLSTransactionGuard(...))` which issues `SET LOCAL` inside the request's atomic transaction.
- **Helpers:** `core/rls_pooling.py` → `RLSTransactionGuard`, `reset_txn_flags`, `rls_worker_atomic()`.
- **Request-external DB (consumers/tasks/commands):** must run their DB work inside `with rls_worker_atomic(): ...` (a no-op when the flag is off; wraps in `transaction.atomic()` so `SET LOCAL` is transaction-scoped when on).
- **PgBouncer:** `docker-compose.prod.yml:204` → `POOL_MODE: ${PGBOUNCER_POOL_MODE:-session}`. Transaction pooling = set `PGBOUNCER_POOL_MODE=transaction`.
- **Existing tests:** `apps/organizations/tests/test_rls_transaction_pooling.py` (`test_worker_atomic_sets_local_tenant_and_clears_after_block`, `test_reused_connection_gets_fresh_tenant_context`, `test_missing_tenant_context_fails_closed`), `core/tests/test_rls_pooling.py`.
- **Reference guide:** `docs/performance/FAZA2_3B_TRANSACTION_POOLING.md` (read it fully first).
- **Load tests:** `k6/{login-load-test,mixed-realistic-load-test,student-exam-flow-test,dashboard-navigation-test}.js`.

## Task 1 — Audit ALL request-external DB paths (code; Codex)

Every Channels consumer, Celery task, `manage.py` command, signal handler, and scheduled job that touches the DB **must** wrap its DB work in `with rls_worker_atomic():` (plus the correct tenant/bypass context). If it doesn't, under transaction pooling its `SET LOCAL` will not be transaction-scoped and it may leak or fail-closed incorrectly.

- Confirmed wrapped: `apps/live_exam/{auth,consumers,cache}.py`, `apps/exams/tasks.py`.
- **Known gap to verify/fix:** `apps/exams/consumers.py` does not appear to use `rls_worker_atomic` — audit it and wrap any DB access.
- Sweep the whole repo: `grep -rL rls_worker_atomic $(grep -rl "database_sync_to_async\|@shared_task\|BaseCommand\|@receiver" apps core --include=*.py)` and review each hit that performs queries.
- For each fix, add/extend a test proving isolation under the flag.

## Task 2 — Strengthen isolation tests under transaction pooling (tests; Codex, `-m postgres`)

Extend `test_rls_transaction_pooling.py`:
- Two sequential requests on the **same pooled connection** with different tenants → the second must NOT see the first's rows (both flag ON and OFF).
- A consumer/task path (Task 1 fixes) sees only its tenant's rows.
- Missing tenant context fails **closed** (zero rows), never open.
These must pass with `RLS_TRANSACTION_SCOPED=True` **and** `POOL_MODE=transaction` in the test DB.

## Task 3 — Staged rollout (ops; a human runs, Codex prepares configs + runbook)

**NEVER enable in production first.** Order:
1. **Staging:** set `RLS_TRANSACTION_SCOPED=true` + `PGBOUNCER_POOL_MODE=transaction`. Deploy.
2. **Isolation gate:** run `pytest -m postgres` against the staging DB — must be 100% green. If any tenant-isolation test fails, STOP and rollback.
3. **Load test:** run k6 `mixed-realistic-load-test.js` + `student-exam-flow-test.js` at 100 → 500 → 1000 VU. Watch PgBouncer `SHOW POOLS`/`SHOW STATS` and Postgres `pg_stat_activity` for connection saturation; watch Grafana p95 + error-rate. Compare against the session-pooling baseline (run both, document in `docs/`).
4. **Canary:** enable on one production replica; watch metrics for a full peak window.
5. **Full rollout** only after 2–4 pass.

**Rollback (instant, no code):** `RLS_TRANSACTION_SCOPED=false` + `PGBOUNCER_POOL_MODE=session`, redeploy.

## Guardrails / Definition of Done
- `pytest -m postgres` green under `RLS_TRANSACTION_SCOPED=True` + transaction pooling — **tenant isolation is non-negotiable**.
- Every request-external DB path wraps `rls_worker_atomic()` (Task 1), each with a test.
- k6 at 1000 VU: error-rate < 1%, p95 within target, no PgBouncer pool exhaustion; results documented vs the session-pooling baseline.
- Rollback path verified in staging.
- No change to application behavior other than pooling mode; RBAC/RLS semantics identical.
- `ruff`/`black`/`isort` clean; `python scripts/check_module_size.py --check` passes.
```
