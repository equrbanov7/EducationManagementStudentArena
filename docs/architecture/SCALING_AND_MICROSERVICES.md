# Scaling & Microservices — recommendation (2026-07-19)

**Question:** everything (electronic exam, journal, student cabinet, live exam) runs on ONE
server in ONE program. If all are used at once, will the server crash or run very weak? Do we
need to split into microservices?

**Answer: no crash, no microservices needed.** Scale the modular monolith. This is grounded in
this session's on-server stress tests + the fixes shipped.

---

## 1. Shared resources & why combined load is safe

The four surfaces share CPU, the Postgres connection pool, and Redis — but each has a different
profile, and the crash risks were removed:

| Surface | Type | Heavy resource | Status |
|---|---|---|---|
| Exam start | short DB write | DB connections | Capacity gate + auto-retry page → no thread pin, no crash |
| Exam autosave/submit | frequent DB write | DB write | Transaction pooling raised the ceiling |
| Journal read | heavy DB read | DB read + CPU | Batched (per-subject N+1 removed, ~2×→1× per request) |
| Student cabinet | light read | low | fine |
| Live exam | WebSocket | Channels + Redis fan-out | event-driven, does not hold worker threads |
| Login (shared) | PBKDF2 | CPU | shared ceiling ~200/s |

Measured breaking points (single-source on-server k6, login-bound, so conservative):
- **Login:** ~200 successful/s sustained; no collapse to 12000 VUs (graceful degradation).
- **Exam full-flow (one exam):** ~500 concurrent OK (slow, start-queue), ~1000 collapsed
  **before the fix** (ASGI thread exhaustion from a 30s busy-wait). Fixed.
- **Journal read:** load hit 141 at 500 concurrent (~2× login-only) → per-subject N+1. Fixed
  (batched); query count no longer scales with subject count.

The one true crash risk was the exam-start stampede pinning threads — now it returns a
self-refreshing 503 page and drains in waves. The other historical crash cause was the Docker
CPU cap, already removed. See `docs/performance/OPTIMIZATION_5000_USERS.md`.

---

## 2. Microservices — why NOT (at 5000–10000 users)

- **The transactional core cannot be split.** Exam → journal → cabinet → registrar share
  Postgres **RLS** (row-level tenant isolation) — a single-Postgres-session mechanism. Splitting
  them fractures RLS (a security control) and turns cross-app writes that today commit inside one
  `@transaction.atomic` (e.g. the exam→journal grade bridge) into distributed transactions.
- **Team size.** Microservices need multiple teams + DevOps to operate. A 1–2 person team cannot
  run ~10 services.
- **New failure modes.** Service discovery, network latency, distributed tracing — added
  complexity, not a solved problem.

**What MAY be extracted (only async/stateless leaves), and already is:** OCR, AI grading (Gemini),
Excel export, the Piston code sandbox, email — these run as separate Celery workers/containers
(`celery_worker_heavy`). **Do NOT extract** the RLS-bound core.

---

## 3. Microservice-free scaling ladder (in order, as needed)

1. **More app replicas** — currently 12; can go 20–24 (`.env` one-liner). ✅ available
2. **Transaction pooling** — DB ceiling ~300 → thousands. ✅ live
3. **Journal-read batching** — removes the per-subject N+1. ✅ shipped
4. **Postgres read-replica** — route dashboard/analytics/journal reads to a replica (master keeps
   writes). This is the biggest 10k+ win and gives a "read service" effect **without** microservices.
5. **Login CPU** — Argon2 tuning or a login cache to lift the ~200/s ceiling.
6. **Second server** — only for **high availability** (one dies → the other serves) → then a
   lightweight k3s. This is for **redundancy, not capacity.**

---

## Verdict

The current disciplined modular monolith is the **right** architecture for 5000–10000 concurrent
users. The bottleneck was never the architecture — it was the Docker CPU cap (fixed) and the
exam-start thread-pin (fixed). Moving to microservices now would add technical debt and cost with
no benefit. Related: `project_architecture_modular_monolith` memory,
`docs/performance/OPTIMIZATION_5000_USERS.md`, `docs/architecture/RLS_POLICY_OWNERSHIP.md`.

_A direct combined-load check (`k6/exam-day-5000-test.js` — simultaneous login+cabinet+exam+
autosave) remains available to validate the "all at once" scenario end-to-end._
