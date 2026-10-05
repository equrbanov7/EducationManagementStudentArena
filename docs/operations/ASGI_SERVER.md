# ASGI server switch — Daphne (default) / Uvicorn workers (opt-in)

`docker/prod-entrypoint.sh` reads two env vars (passed by the `app` service in
`docker-compose.prod.yml`):

| Var | Default | Meaning |
|---|---|---|
| `ASGI_SERVER` | `daphne` | `daphne` = one Daphne process per container (prod as before). `uvicorn` = Uvicorn supervisor + `ASGI_WORKERS` worker processes. |
| `ASGI_WORKERS` | `1` | Uvicorn worker processes per container. `>1` with `daphne` is rejected (exit 64). |
| `UVICORN_ACCESS_LOG` | `true` | Daphne (verbosity 1) writes an access log too; `false` saves CPU. |
| `UVICORN_WORKER_HEALTHCHECK_TIMEOUT` | `60` | Supervisor SIGKILLs a worker whose pipe ping is not answered in time. Uvicorn's 5 s default could kill a worker mid exam-submit during a CPU spike. |

Anything else unset → nothing changes in production.

## Parity with the Daphne flags

| Daphne | Uvicorn | Notes |
|---|---|---|
| `--proxy-headers` (trusts every peer, first XFF element, port 0) | `--proxy-headers --forwarded-allow-ips '*'` | Same `scope["client"]` / `REMOTE_ADDR` (checked by `tests/test_asgi_server_switch.py` against `daphne.utils.parse_x_forwarded_for`). HTTP code reads the client IP from `X-Forwarded-For` via `core.utils.get_client_ip` either way; nginx overwrites XFF with `$remote_addr`. Port 8000 must stay unpublished. |
| websocket max message 1 MiB, ping 20 s / timeout 30 s, no permessage-deflate | `--ws-max-size 1048576 --ws-ping-interval 20 --ws-ping-timeout 30 --ws-per-message-deflate false --ws websockets-sansio` | Deflate off keeps per-socket memory flat (5000 WS target). |
| `--application-close-timeout ${DAPHNE_APPLICATION_CLOSE_TIMEOUT:-120}` | `--timeout-graceful-shutdown ${DAPHNE_APPLICATION_CLOSE_TIMEOUT:-120}` | `stop_grace_period` 130 s invariant unchanged. On SIGTERM open WebSockets get close code 1012 at once, in-flight HTTP finishes (verified locally: WS closed 0.4 s after SIGTERM, all workers exited 0). |
| `--http-timeout 900` | — | No uvicorn equivalent; nginx `proxy_read_timeout` (≤ 900 s) bounds requests. |
| `ASGI_THREADS` (default executor of Daphne's loop) | same, applied in `config/asgi.py` when `ASGI_SERVER=uvicorn` | Sync views still get one thread per request (`ThreadSensitiveContext`); see `core/middleware_concurrency.py`. |
| — | `--lifespan off` | Django/Channels do not implement the lifespan scope. |

`daphne` stays in `INSTALLED_APPS`; under uvicorn it only imports `daphne.server`
(installs an idle Twisted reactor), harmless.

## Per-process state — what multiplies by `ASGI_WORKERS`

Everything below is **per process**, so the container total is `× ASGI_WORKERS`
and the fleet total is `× APP_REPLICAS × ASGI_WORKERS`:

- `MAX_INFLIGHT_REQUESTS` / `MAX_INFLIGHT_LOGIN_REQUESTS` (`ConcurrencyLimitMiddleware` semaphores);
- `REQUEST_QUEUE_GLOBAL_UNSAFE_LIMIT` (write semaphore in `RequestQueueMiddleware`);
- Redis cache connection pool (`REDIS_CACHE_MAX_CONNECTIONS`) and channels_redis connections;
- memory: each worker is a full Django process (≈ 200–400 MB RSS; locally 180 MB after warm-up). Parent ≈ 12 MB.

Not affected: per-user request locks, rate limits, sessions, channel layer (all Redis/DB); Prometheus —
`PROMETHEUS_MULTIPROC_DIR` was already set, every worker writes its own `*_<pid>.db` file and `/metrics/`
(served by whichever worker) aggregates the whole container. `django_app_info` (Info) is not exported in
multiprocess mode — that was already true under Daphne.

Admission is not pooled across sibling workers: the kernel hands each new connection to one worker
(shared listen socket, no `SO_REUSEPORT`), and a full worker answers 503 even if its sibling is idle.
Keep per-worker `MAX_INFLIGHT_REQUESTS` reasonably large rather than splitting it into small pieces.

## DB connection math (PgBouncer session mode, `DATABASE_CONN_MAX_AGE=0`)

Each admitted HTTP request holds at most one server connection for its duration, so the HTTP ceiling is

    APP_REPLICAS × ASGI_WORKERS × MAX_INFLIGHT_REQUESTS  ≤  DEFAULT_POOL_SIZE + RESERVE_POOL_SIZE − (WS + Celery + health)

Today: `8 × 1 × 24 = 192` against `150 + 50 = 200` (`max_db_connections 230 ≤ 250`). Keep the product at 192.

## A/B recipe (`.env` on the server, then normal deploy)

**B1 — same process count, isolates the server change (run first):**

    ASGI_SERVER=uvicorn
    ASGI_WORKERS=2
    APP_REPLICAS=4
    MAX_INFLIGHT_REQUESTS=24          # 4 × 2 × 24 = 192 (unchanged)
    MAX_INFLIGHT_LOGIN_REQUESTS=4     # 8 processes × 4 = 32 (unchanged)
    APP_MEM_LIMIT=3072M               # two Django workers per container

**B2 — more processes for CPU (only if B1 is healthy and the box has CPU headroom):**

    ASGI_SERVER=uvicorn
    ASGI_WORKERS=2
    APP_REPLICAS=8
    MAX_INFLIGHT_REQUESTS=12          # 8 × 2 × 12 = 192
    MAX_INFLIGHT_LOGIN_REQUESTS=2     # 16 × 2 = 32
    REQUEST_QUEUE_GLOBAL_UNSAFE_LIMIT=4
    APP_MEM_LIMIT=3072M

**Rollback:** remove `ASGI_SERVER`/`ASGI_WORKERS` (or set `daphne`/`1`) and restore the previous
`APP_REPLICAS`, `MAX_INFLIGHT_*`, `APP_MEM_LIMIT`; redeploy.

Compare under the same k6 scenario: p95/p99 latency, 503 rate (`X-Concurrency-Limited`), PgBouncer
`cl_waiting`, app container CPU/RSS (cAdvisor), live-exam WS connect success.

## Risks / watch list

- The container healthcheck (`/ping/`) reaches one worker; a wedged-but-alive worker is not detected
  (same as a wedged Daphne today). A worker that dies is restarted by the uvicorn supervisor.
- A worker that crashes while importing the app is restarted in a loop rather than failing the container;
  the Docker healthcheck still marks it unhealthy.
- Uneven distribution between workers of one container under bursty load (see admission note above).
