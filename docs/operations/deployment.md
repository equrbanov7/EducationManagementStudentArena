# EMS Arena — Production Deployment Guide

> **Audience:** Engineers performing a first-time or update deployment of EMS Arena.
> After reading this document you should be able to deploy the application from
> scratch using only Docker Compose and the environment variables listed here.

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Prerequisites](#2-prerequisites)
3. [Environment Variables Reference](#3-environment-variables-reference)
   - [Build-time vs. Runtime Variables](#build-time-vs-runtime-variables)
4. [First-Time Deployment](#4-first-time-deployment)
5. [Update / Re-deploy](#5-update--re-deploy)
   - [5.2 2026-09-14 dəyişikliklər — ilk deploy yoxlama siyahısı](#52-2026-09-14-dəyişikliklər--sahibin-ilk-deploy-u-üçün-yoxlama-siyahısı)
6. [Static & Private Media Handling](#6-static--private-media-handling)
7. [Health Check & Smoke Test Verification](#7-health-check--smoke-test-verification)
8. [Rollback Plan](#8-rollback-plan)
9. [Secrets Management Checklist](#9-secrets-management-checklist)

---

## 1. Architecture Overview

```
Internet
│  HTTPS (443)
▼
┌──────────────────────────────────────────────────┐
│  Docker host (emsarena-network bridge)           │
│                                                  │
│  ┌─────────┐   HTTP   ┌─────────────────────┐   │
│  │  Nginx  │ ──────▶  │  Daphne (port 8000) │   │
│  │ :80/443 │          │  Django ASGI app     │   │
│  └────┬────┘          └─────────┬───────────┘   │
│       │                         │                │
│  Static / Media            ┌────┴────┐  ┌──────┐ │
│  (Docker volumes)          │Postgres │  │Redis │ │
└──────────────────────────────────────────────────┘
```

**SSL termination strategy — direct edge:**
- Public DNS points directly to this host; there is no CDN/load balancer.
- Nginx listens on ports **80/443** and terminates TLS with a public-CA
  certificate stored outside Git.
- Nginx discards inbound `X-Forwarded-For` / `X-Forwarded-Proto` and derives
  both from the direct TCP connection, so clients cannot spoof exam-center IP
  allowlists or rate-limit identity.

---

## 2. Prerequisites

| Tool | Minimum version | Notes |
|------|----------------|-------|
| Docker Engine | 24.x | `docker --version` |
| Docker Compose plugin | 2.20 | `docker compose version` |
| Git | 2.x | For pulling the repository |
| Public DNS + public IPv4/IPv6 | — | A/AAAA must point directly to the Docker host/NAT |
| Public-CA TLS certificate | — | Full chain + matching private key for `HEALTHCHECK_HOST` |

No Python, PostgreSQL, or Redis installation is needed on the host — all
services run inside Docker containers.

### Host sizing (infra audit 2026-09-14, P3-10)

Compose `deploy.resources.limits.memory` defaults add up to **≈ 33.5 GB for one
replica of everything**; with the deploy script defaults `APP_REPLICAS=8`
(2 GB each) and `CELERY_REPLICAS=2` (1 GB each) the ceiling is **≈ 48.5 GB**.
Limits are ceilings, not reservations, but the host must be able to honour the
steady-state sum of the big ones or the kernel OOM-kills the wrong container.

| Service (env knob) | Default limit | Note |
|---|---|---|
| `postgres` (`POSTGRES_MEM_LIMIT`) | 16 GB | `shared_buffers` 2 GB + `effective_cache_size` 6 GB defaults assume ≥ 8 GB really available |
| `app` × `APP_REPLICAS` (`APP_MEM_LIMIT`) | 2 GB × 8 | Daphne + `ASGI_THREADS`; 2 replicas per vCPU is plenty |
| `piston` (`PISTON_MEM_LIMIT`) | 4 GB | code-runner sandbox; drop to 1 GB if lab tasks are off |
| `redis` (`REDIS_MEM_LIMIT`) | 4 GB | must stay above `REDIS_MAXMEMORY` (default 3 GB) |
| `celery_worker_heavy` / `celery_worker` × `CELERY_REPLICAS` | 2 GB / 1 GB × 2 | exports, imports, AI |
| observability (prometheus, loki, grafana, cadvisor, exporters, alertmanager, promtail) | ≈ 2 GB | |
| nginx, pgbouncer, backup, beat, arp-agent | ≈ 1.6 GB | |

Rule of thumb for a **32 GB** host: `POSTGRES_MEM_LIMIT=10G`,
`POSTGRES_SHARED_BUFFERS=2GB`, `POSTGRES_EFFECTIVE_CACHE_SIZE=5GB`,
`APP_REPLICAS=4`, `PISTON_MEM_LIMIT=1G`, `REDIS_MAXMEMORY=2gb`,
`REDIS_MEM_LIMIT=2560M` → ≈ 26 GB ceiling. For a **64 GB** host the defaults are
fine. Check the running picture with `docker stats --no-stream` after the first
exam session and tighten from there.

---

## 3. Environment Variables Reference

Create a `.env` file in the repository root (next to `docker-compose.prod.yml`)
before running any `docker compose` command.  Never commit this file.

### Required variables

| Variable | Example | Description |
|----------|---------|-------------|
| `SECRET_KEY` | `<50+ random chars>` | Django secret key. Generate with `python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"` |
| `POSTGRES_DB` | `emsarena` | PostgreSQL database name |
| `POSTGRES_USER` | `emsarena` | PostgreSQL username |
| `POSTGRES_PASSWORD` | `<strong password>` | PostgreSQL password |
| `DATABASE_URL` | `postgres://emsarena:<pw>@postgres:5432/emsarena` | Full database URL passed to Django |
| `REDIS_PASSWORD` | `<strong password>` | Redis `--requirepass` value |
| `REDIS_URL` | `redis://:${REDIS_PASSWORD}@redis:6379/0` | Full Redis URL (channel layer) |
| `ALLOWED_HOSTS` | `10.0.2.42,localhost,127.0.0.1` | Comma-separated list of valid `Host` headers (LAN IP-based; public domain retired) |
| `CSRF_TRUSTED_ORIGINS` | `https://10.0.2.42` | Comma-separated origins for CSRF validation |
| `SITE_URL` | `https://10.0.2.42` | Canonical site URL (used in emails, WebSocket CSP) |
| `EDGE_PROXY_MODE` | `lan` | `lan` (intranet, no public DNS — current production) or `direct` (public domain straight to this server); proxy/CDN values block deploy |
| `DIRECT_ORIGIN_IPS` | `<server-public-ip>` | `direct` mode only: exact comma/space-separated public DNS A/AAAA set; deploy fails on mismatch |
| `HEALTHCHECK_HOST` | `10.0.2.42` | Host header for deploy health probes; must be covered by the TLS cert SAN |
| `TLS_ALLOW_SELF_SIGNED_LOCAL` | `true` (lan) / `false` (direct) | lan mode accepts a self-signed cert whose SAN covers the LAN IP |
| `TLS_CERT_MIN_VALIDITY_SECONDS` | `604800` | Reject a certificate expiring inside this window |
| `ADMIN_URL_PREFIX` | `manage/` | Non-default Django admin path. Must not be `admin/` in production. |
| `ADMIN_ALLOWED_IPS` | `203.0.113.10,198.51.100.20` or blank | Comma-separated allowlist of source IPs permitted to access the admin panel. Leave blank to disable the IP restriction entirely. |

### Optional / feature variables

| Variable | Default | Description |
|----------|---------|-------------|
| `APP_IMAGE` | `emsarena-prod:latest` | Docker image tag used by `app`/`celery_*`. `remote_deploy.sh` exports `emsarena-prod:<git sha>` for the rollout and re-tags `latest` only after the health gate passes (§8); CI uses `emsarena-prod:ci` |
| `EMAIL_BACKEND` | `django.core.mail.backends.smtp.EmailBackend` | Email backend class. Override with `anymail` backend for SendGrid/SES |
| `EMAIL_HOST` | `smtp-relay.brevo.com` | SMTP server hostname |
| `EMAIL_PORT` | `587` | SMTP server port |
| `EMAIL_USE_SSL` | `False` | Keep `False` for Brevo STARTTLS |
| `EMAIL_USE_TLS` | `True` | Use explicit STARTTLS (port 587) |
| `EMAIL_TIMEOUT` | `10` | SMTP connection timeout in seconds |
| `BREVO_SMTP_LOGIN` | _(empty)_ | Brevo SMTP login like `xxxx@smtp-brevo.com` |
| `BREVO_SMTP_KEY` | _(empty)_ | Brevo SMTP key used as the password |
| `BREVO_EMAIL` | `no-reply@emsarena.com` | Visible sender mailbox |
| `BREVO_FROM_EMAIL` | `no-reply@emsarena.com` | Optional explicit sender override |
| `DEFAULT_FROM_EMAIL` | `no-reply@emsarena.com` | From address for system emails |
| `SENTRY_DSN` | _(empty)_ | Sentry error-tracking DSN. Leave blank to disable |
| `LIVE_EXAM_PUBLIC_HOST` | `emsarena.com` | Publicly reachable hostname for live-exam WebSocket connections |
| `LAN_HOST` | `emsarena.com` | Internal hostname used in certain generated links |
| `MEDIA_ACCEL_REDIRECT_URL` | `/internal_media` | Nginx X-Accel-Redirect prefix for private media |
| `DJANGO_LOG_LEVEL` | `INFO` | Log level for the Django logger (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |
| `SECURE_SSL_REDIRECT` | `True` | Set to `False` only in CI or behind a TLS-terminating proxy that already enforces HTTPS |
| `SESSION_COOKIE_SECURE` | `True` | Keep `True` in production |
| `CSRF_COOKIE_SECURE` | `True` | Keep `True` in production |
| `SECURE_HSTS_SECONDS` | `31536000` | HSTS max-age in seconds. Set to `0` only during initial TLS testing |
| `SECURE_HSTS_INCLUDE_SUBDOMAINS` | `True` | Include `includeSubDomains` in HSTS header |
| `SECURE_HSTS_PRELOAD` | `True` | Include `preload` in HSTS header |
| `ADMIN_LOGIN_RATE_LIMIT` | `3/15m` | Rate limit for admin password login attempts |
| `ADMIN_2FA_REQUIRED` | `True` | Keep admin OTP-based 2FA enabled in production |
| `ADMIN_OTP_VERIFY_RATE_LIMIT` | `5/10m` | Rate limit for admin OTP verification attempts |
| `ADMIN_OTP_RESEND_RATE_LIMIT` | `3/10m` | Rate limit for resending admin OTP codes |
| `APP_STOP_GRACE_PERIOD` | `130s` | Infra audit 2026-09-13 P2-3: SIGTERM→SIGKILL window for `app`. Must stay ≥ `DAPHNE_APPLICATION_CLOSE_TIMEOUT` + 10 s (Daphne drains in-flight exam submits/WebSockets). Workers use fixed 300 s / 900 s (task hard limits), Postgres 60 s |
| `EMSARENA_NETWORK_SUBNET` / `EMSARENA_NETWORK_GATEWAY` | `172.18.0.0/16` / `172.18.0.1` | Infra audit P2-4: bridge network IPAM pin. The gateway **must equal** `ARP_AGENT_BIND` (arp-agent binds there with `network_mode: host`) and `EXAM_ARP_AGENT_URL` — otherwise the exam-centre gate fails closed. See §5 note before changing |
| `ARP_AGENT_CPU_LIMIT` / `ARP_AGENT_MEM_LIMIT` | `0.1` / `64M` | Infra audit P2-4: arp-agent sidecar limits (stdlib http.server ≈ 15 MB RSS) |
| `WATCHDOG_REPEAT_INTERVAL` | `24h` | Infra audit P1-3: how often the always-firing `Watchdog` alert re-sends its "monitoring chain alive" heartbeat e-mail (`heartbeat` receiver). If the mail stops arriving, Prometheus→Alertmanager→SMTP is broken |
| `DEPLOY_CHECK_FAIL_LEVEL` | `WARNING` | Infra audit 2026-09-14 P3-16: level at which the in-image `manage.py check --deploy` preflight aborts the deploy. `WARNING` matches CI (`_security.yml`); set `ERROR` in `.env` only as a documented, temporary relaxation (warnings are still printed loudly) |
| `SKIP_PREDEPLOY_BACKUP` | `0` | Infra audit 2026-09-14 P2-5: `1` skips the pre-migration `postgres-backup /backup.sh` dump. A failing dump otherwise aborts the deploy before `release.sh` (fail-closed) |
| `DEPLOY_ROLLBACK_ON_FAILURE` | `true` | Infra audit P2-5: on a failed health/HTTP gate, recreate `app`/`celery_*` from the previously running image tag (captured before the rollout). `false` leaves the failed release running for inspection |
| `DEPLOY_KEEP_RELEASE_IMAGES` | `3` | Infra audit P2-5: how many older `emsarena-prod:<sha>` tags to keep besides the current and the rollback target; older ones are removed after a successful deploy |
| `HEALTHCHECK_HOST` | `127.0.0.1` (deploy) / `10.0.2.42` (blackbox) | Host header the deploy health-gate and the blackbox probes send to nginx (must be in `ALLOWED_HOSTS`). Infra audit 2026-09-14 P3-9: the blackbox config is rendered from this variable at container start instead of a hard-coded IP |
| `POSTGRES_JIT` | `off` | Perf measurement EX-12 (2026-09-14): passed to `postgres` as `-c jit=…`. RLS policies inflate plan cost past `jit_above_cost` (100 000) and JIT compilation turned a 2.7 ms OLTP query into 158 ms. Keep `off` for this OLTP profile; only set `on` for an explicit analytics experiment |

### Build-time vs. Runtime variables

Two categories of environment variables exist:

**Build-time ARGs** (only used during `docker build`, not present in the
running container):

| ARG | Purpose |
|-----|---------|
| `BUILD_SECRET_KEY` | Dummy SECRET_KEY so `collectstatic` can import production settings without real secrets |
| `BUILD_DATABASE_URL` | Dummy DB URL (`sqlite:////tmp/build.db`) so settings load cleanly |
| `BUILD_ALLOWED_HOSTS` | Dummy hosts (`localhost,127.0.0.1`) for the settings import |

These are passed via `build-args` in `docker compose build` or the CI
workflow.  They contain placeholder values and are **never written to the
final image's environment**.

**Runtime ENV variables** (injected at container start via `.env` or
orchestrator secrets):

All variables in the Required/Optional tables above are runtime variables.
They are read by `config/settings/production.py` when Django starts.
Never bake real secrets into the image; always inject them at runtime.

---

## 4. First-Time Deployment

### Step 1 — Clone and configure

```bash
git clone https://github.com/equrbanov7/EducationManagementStudentArena.git
cd EducationManagementStudentArena

# Create the runtime secrets file (never commit this)
cp /dev/null .env
```

Populate `.env` with all **required** variables from the table above, for example:

```dotenv
SECRET_KEY=<generate with the django command above>
POSTGRES_DB=emsarena
POSTGRES_USER=emsarena
POSTGRES_PASSWORD=<strong-password>
DATABASE_URL=postgres://emsarena:<strong-password>@postgres:5432/emsarena
REDIS_PASSWORD=<strong-redis-password>
REDIS_URL=redis://:<strong-redis-password>@redis:6379/0
ALLOWED_HOSTS=emsarena.com,www.emsarena.com
CSRF_TRUSTED_ORIGINS=https://emsarena.com,https://www.emsarena.com
SITE_URL=https://emsarena.com
LAN_HOST=emsarena.com
LIVE_EXAM_PUBLIC_HOST=emsarena.com
ADMIN_URL_PREFIX=manage/
ADMIN_ALLOWED_IPS=
ADMIN_LOGIN_RATE_LIMIT=3/15m
ADMIN_2FA_REQUIRED=True
ADMIN_OTP_VERIFY_RATE_LIMIT=5/10m
ADMIN_OTP_RESEND_RATE_LIMIT=3/10m
```

Leaving `ADMIN_ALLOWED_IPS` empty disables the admin IP allowlist, so
superadmins can sign in from any source address while still keeping the
custom admin URL, OTP challenge, and rate limits enabled.

### Step 2 — Build the production image

```bash
docker compose -f docker-compose.prod.yml build
```

Static files are collected inside the image during the build step using
dummy build-time ARGs (no real secrets needed for the build).

### Step 3 — Start the stack

```bash
docker compose -f docker-compose.prod.yml up -d
```

Docker Compose starts the services in dependency order:
`postgres` → `redis` → `app` (runs migrations and refreshes collected statics
via `prod-entrypoint.sh`) → `nginx`.

### Step 4 — Create the superuser

```bash
docker compose -f docker-compose.prod.yml exec app \
    python manage.py createsuperuser
```

### Step 5 — Verify the deployment

See [Section 7 — Health Check & Smoke Test Verification](#7-health-check--smoke-test-verification).

### Step 6 — Point the Load Balancer

Configure your external LB to:
- Accept HTTPS traffic on port 443 using your TLS certificate.
- Forward plain HTTP to the Docker host on **port 80**.
- Set the `X-Forwarded-Proto: https` header on forwarded requests.
- Set `X-Forwarded-For` to the real client IP.

---

## 5. Update / Re-deploy

### Pull new code and rebuild

```bash
# Fetch latest code
git pull origin main

# Rebuild the image (only changed layers are rebuilt thanks to layer caching)
docker compose -f docker-compose.prod.yml build

# Replace containers one by one without full downtime
docker compose -f docker-compose.prod.yml up -d --no-deps app nginx
```

The `prod-entrypoint.sh` script automatically runs `python manage.py migrate`
and `python manage.py collectstatic --noinput` before starting Daphne, so
database migrations and Docker-managed static assets stay current on every
restart.

## 5.1 Automatic CI deploy (self-hosted runner, 2026-07-07)

On every push to `main`, after `ci-success` passes, the `deploy-production` job
in `.github/workflows/ci.yml` auto-deploys to the production server. It runs on
the **self-hosted GitHub Actions runner** installed on the server itself
(`runs-on: [self-hosted]`), so the deploy executes locally on the box — no SSH,
no public IP, and the server's private LAN address does not matter.

The job:
1. `actions/checkout` into the runner workspace;
2. `rsync -a --delete --exclude-from scripts/deploy/rsync-excludes.txt ./ "$APP_DIR/"`
   — mirrors the code into `APP_DIR` (`/home/wcu/EducationManagementStudentArena`)
   while preserving runtime data (`.env`, `media/`, `docker/nginx/certs/`);
3. `bash scripts/deploy/remote_deploy.sh` — docker-compose build (tagged
   `emsarena-prod:<sha>`) + `check --deploy` preflight + pre-deploy DB dump +
   release (migrate/collectstatic) + `up -d` + health gate; on a failed gate
   it rolls the app/worker containers back to the previous tag, on success it
   promotes the tag to `latest` (§8).

Prerequisites on the server: the self-hosted runner service must be active, its
run-as user must be in the `docker` group and own `APP_DIR`, and `APP_DIR/.env`
must exist (never overwritten by the deploy). When the server changes, update
`APP_DIR`/`runs-on` in the `deploy-production` job (no vendor lock-in).

A manual deploy on the server is still possible:

```bash
cd /opt/emsarena/app        # server-side checkout / rsync destination
bash scripts/deploy/remote_deploy.sh   # host-agnostic: build + release + up + health-gate
```

`scripts/deploy/remote_deploy.sh` is host-agnostic (any Docker host works).
Remember: the server `.env` must contain `ALLOWED_HOSTS` including
`localhost,127.0.0.1` (app healthcheck and the nginx `/metrics/` scrape rely
on it) plus `GRAFANA_ADMIN_PASSWORD` and `ALERT_EMAIL_TO` (Faza 1 alerting).

### First-time server setup

Automatic deploys expect these items to exist once on the server:

- `/opt/emsarena/app` — the Docker Compose application directory
- `/opt/emsarena/app/.env` — persistent runtime environment variables
- Docker Engine with the Docker Compose plugin
- Nginx is managed by `docker-compose.prod.yml` and publishes ports `80` and `443`

The workflow never overwrites the application `.env`, so you only need to
set it up once. The live app environment file should remain at:

```bash
/opt/emsarena/app/.env
```

The SSH sync step excludes runtime data such as `.env`, `media/`, and
`docker/nginx/certs/`, so user uploads, public-CA TLS material, and server-side
secrets are preserved across deployments without requiring Git access from
the production host.

### Zero-downtime update checklist

1. Sync the latest application code into `/opt/emsarena/app`
2. Preserve `.env`, `media/`, Docker volumes, and `docker/nginx/certs/`
3. `docker compose -f docker-compose.prod.yml up -d --build`
4. Wait for `emsarena-app` to become healthy
5. Verify `/ping/` and `/health/` before considering the rollout complete.

### Network IPAM pin (infra audit 2026-09-13, P2-4) — one-time check

`docker-compose.prod.yml` now pins `emsarena-network` to `172.18.0.0/16`
(gateway `172.18.0.1`), because `arp-agent` binds to that gateway address and
`app` calls it at `EXAM_ARP_AGENT_URL`. Before the first deploy that carries
this change, confirm the existing network already uses that subnet:

```bash
docker network inspect emsarena_emsarena-network \
  --format '{{range .IPAM.Config}}{{.Subnet}} gw={{.Gateway}}{{end}}'
# expected: 172.18.0.0/16 gw=172.18.0.1
```

- Same subnet → nothing changes on `up -d` (Compose keeps the network).
- Different subnet → Compose never modifies an existing network in place
  (the pinned range only applies when the network is created). Outside exam
  hours run `docker compose -f docker-compose.prod.yml down` (volumes are
  kept) and `up -d` so the network is recreated with the pinned range, **or**
  set `EMSARENA_NETWORK_SUBNET` / `EMSARENA_NETWORK_GATEWAY` / `ARP_AGENT_BIND`
  / `EXAM_ARP_AGENT_URL` in `.env` to the range the host already uses. All
  four must agree (`tests/test_infra_compose_config.py` checks the defaults).

### Graceful stop windows (infra audit 2026-09-13, P2-3)

`stop_grace_period` is now set per service (`app` 130 s, `celery_worker`
300 s, `celery_worker_heavy` 900 s, `postgres` 60 s). A redeploy therefore
waits for in-flight exam submits / WebSockets and running OCR/export tasks
instead of SIGKILL-ing them after Docker's default 10 s. Expect
`docker compose up -d` / `stop` to take up to 15 min when a heavy task is
mid-flight — that is intended; do not shorten it on exam days.

### Postgres JIT off (perf measurement EX-12, 2026-09-14)

`docker-compose.prod.yml` starts `postgres` with `-c jit=${POSTGRES_JIT:-off}`.
With row-level security every policy subplan is added to the planner's cost
estimate; once that estimate crosses `jit_above_cost` (100 000) PostgreSQL
JIT-compiles the query, and on the 20 000-row `exams_examanswer` sandbox a
2.7 ms prefetch became **158 ms** (103 ms of it JIT emission). The ORM's real
queries sit below the threshold today, but a larger `IN (...)` list or more
options per question can cross it, so JIT is disabled for the OLTP profile.
The setting is applied on the next `postgres` container recreate (it is a
server start parameter, not a reload) — see the 2026-09-14 checklist in §5.2.

### Daphne proxy headers (infra audit 2026-09-14, P3-12)

`docker/prod-entrypoint.sh` starts Daphne with `--proxy-headers`, so the ASGI
`scope["client"]` (used by WebSocket consumers, e.g. the live-exam connect
rate limit in `apps/live_exam/consumers.py:_get_scope_ip`) and
`scope["scheme"]` are taken from `X-Forwarded-For` / `X-Forwarded-Proto`
instead of nginx's container IP. This is safe only because:

- nginx **overwrites** `X-Forwarded-For` with `$remote_addr` (never
  `$proxy_add_x_forwarded_for`; guarded by
  `tests/test_proxy_trust_configuration.py`) — Daphne takes the *first*
  element of a comma-separated list, so an appended client value would win;
- port 8000 is reachable only from the compose network (nginx, Prometheus
  scrapes, healthcheck). Anything that talks to `app:8000` directly can set
  those headers — keep it that way and never publish 8000 on the host.

HTTP requests already used `SECURE_PROXY_SSL_HEADER` / `USE_X_FORWARDED_HOST`
in Django; the flag only aligns the raw ASGI scope with that trust model.

### Secrets off the process command line (infra audit 2026-09-14, P3-3 / P3-8 / P3-9)

- **Redis** no longer receives `--requirepass` on argv (visible in `ps` /
  `docker inspect`). `docker/redis/entrypoint.sh` renders
  `docker/redis/redis.conf.tmpl` to `/tmp/redis.conf` (0400, owned by `redis`)
  and hands off to the image's own `docker-entrypoint.sh redis-server
  /tmp/redis.conf`, so the `gosu redis` privilege drop is unchanged. The
  healthcheck still authenticates through `REDISCLI_AUTH`.
- **Alertmanager** and **blackbox** templates are rendered by
  `docker/render-template.sh` (POSIX sh; the prom/* busybox images have no
  `envsubst`). Substitution is literal and `"`/`\` are escaped for
  double-quoted YAML scalars — SMTP keys or webhook tokens may contain `|`,
  `&`, `/`, `\` (the old `sed` render broke on them). A template change still
  needs a container recreate (`remote_deploy.sh` does it for alertmanager).

---

## 5.2 2026-09-14 dəyişikliklər — sahibin ilk deploy-u üçün yoxlama siyahısı

2026-09-13 auditinin düzəlişləri və 2026-09-14 gecə dalğaları (2–5) ilk dəfə
istehsala çıxanda aşağıdakılar **bir dəfə** edilməlidir. Mənbə: audit hesabatı
`docs/audits/2026-09-13-claude/FINAL_REPORT_AZ.md` §27 «MÜTLƏQ» siyahısı və
w2 infra agentinin xəbərdarlıqları. Sıra vacibdir — əvvəlcə `.env`, sonra deploy.

**A. Deploy-dan ƏVVƏL (prod `.env`)**

1. **DB tətbiq rolu** (Codex P0-01): `scripts/provision-app-db-role.sh` →
   `APP_DATABASE_USER=emsarena_app` + `EMS_DB_ROLE_ENFORCE=error` — addımlar
   [PROD_DB_ROLE_CHECKLIST.md](./PROD_DB_ROLE_CHECKLIST.md). Əvvəlcə staging
   klonunda final-mərkəz WS + `-m postgres` test dəsti ilə yoxlayın —
   2026-09-14 məşqi (28 rol × bütün bölmələr, 0 xəta):
   [rls_role_rehearsal_2026-09-14.md](./rls_role_rehearsal_2026-09-14.md).
   PgBouncer pool-ları rol × baza cütü üçündür — app rolu ayrılanda owner cütü
   ilə birlikdə iki pool olur; `PGBOUNCER_MAX_DB_CONNECTIONS` (audit P3-18)
   ümumi backend tavanıdır və **`POSTGRES_MAX_CONNECTIONS − 20`** saxlanmalıdır
   (compose defoltu 230/250, `.env.production.example` 180/200).
2. **TLS bayraqları**: `INSECURE_TRANSPORT_OK` prod `.env`-də **olmamalıdır**
   (varsa `check --deploy` dayandırır); `SECURE_SSL_REDIRECT` / HSTS dəyərləri
   §3 cədvəlindəki kimi.
3. **`ALLOWED_HOSTS`** mütləq `localhost` və `127.0.0.1`-i ehtiva etməlidir
   (app healthcheck, nginx `/metrics/` scrape, Alertmanager webhook və
   `HEALTHCHECK_HOST` hamısı ona söykənir): `ALLOWED_HOSTS=10.0.2.42,localhost,127.0.0.1`.
4. **`DEPLOY_CHECK_FAIL_LEVEL`** defoltu artıq `WARNING`-dir (CI ilə eyni). Prod
   `.env`-də `manage.py check --deploy` xəbərdarlığı varsa **ilk deploy dayanacaq** —
   ya xəbərdarlığı düzəldin, ya müvəqqəti və sənədləşdirilmiş şəkildə
   `DEPLOY_CHECK_FAIL_LEVEL=ERROR` yazın (sonra geri qaytarın).
5. **Redis**: `REDIS_PASSWORD` artıq argv-dən deyil, `docker/redis/redis.conf.tmpl`
   şablonundan oxunur; `REDIS_MAXMEMORY` (defolt `3gb`, `noeviction`) `.env`-də
   istənilən dəyərlə üst-üstə düşməlidir (drift yoxlayın: `redis-cli CONFIG GET maxmemory`).
6. **`ALERTMANAGER_WEBHOOK_TOKEN`** (app və Alertmanager eyni dəyər) və
   `GRAFANA_ADMIN_PASSWORD`, `ALERT_EMAIL_TO` mövcud olmalıdır.
7. **Parol rotasiyası**: klon/staging DB parolları və `b09cb19d` commit-indəki
   tarixi `.env` sızmasındakı dəyərlər hər hansı real mühitdə işlədilirsə dəyişdirin
   (`ALTER ROLE …`).

**A2. Məlumat hazırlığı — 2026-09-14 lokal real bazada (`emsarena_db`) ARTIQ EDİLİB**

Sahibin qərarı: «my.edu» izi qalmasın, istifadəçi adları ad.soyad olsun. İki
idempotent komanda (dry-run defolt) real bazada tətbiq olundu, ehtiyat nüsxələr
`backups/pre_username_rename/` (gitignored) — serverə məhz bu bazanın dump-ı gedir:

| Komanda | Nə etdi | Say |
|---|---|---|
| `rename_legacy_usernames --apply` | `myedu.student/worker.<id>` → `ad.soyad` (universitetin `…@wcu.edu.az` `ad.soyad` hesabı varsa o; təkrarda `2`,`3`…) | 8 431 |
| `finalize_university_identity --apply` | Təşkilat «MyEdu Universiteti (rehearsal)»/`myedu-univ` → «Qərbi Kaspi Universiteti»/`qku`; tələbə nömrəsi `myedu-student-N` → `N`; fənn kodu `MYEDU-LN` → `QKU-N` | 1 / 7 716 / 2 501 |

Plan CSV (köhnə → yeni istifadəçi adı) eyni qovluqdadır. Serverdə TƏKRAR
işlətmək lazım deyil (idempotentdir — işlədilsə «dəyişəcək: 0» verir). Qalan
daxili `myedu` açarları (`OrgUnit.slug myedu-dep-N`, `Program.code MYEDU-N`,
legacy ledger `source_system`) UI-da görünmür, idxal açarıdır — toxunulmur.

**A3. Real məlumatın serverə yüklənməsi (ilk deploy BOŞ bazaya getdi)**

2026-09-14 20:34 UTC: `main` (`89275d84`) push-u `wcuserver` self-hosted runner-i ilə
serverə deploy olundu — `.env` preflight, `check --deploy` (xəbərdarlıqsız),
miqrasiyalar sıfırdan (`contenttypes.0001` → baş), `build.sha` təsdiqi keçdi. Serverin
Postgres-i BOŞDUR. Lokal hazırlanmış real bazanın dump-ı (A2-dən sonra):
`backups/server_seed/emsarena_db_<tarix>.dump` (pg_dump `-Fc --no-owner --no-privileges`,
≈ 680 MB, 172 cədvəl). Serverdə (`/home/wcu/EducationManagementStudentArena`):

```bash
# 0. dump-ı serverə köçür (scp), sonra:
docker compose -f docker-compose.prod.yml stop app celery_worker celery_worker_heavy celery_beat
docker cp emsarena_db_<tarix>.dump emsarena-postgres:/tmp/seed.dump
# 1. boş sxemi at, təmiz bazaya bərpa et (owner rolu ilə; dump-da owner/privilege yoxdur)
docker exec emsarena-postgres psql -U "$POSTGRES_USER" -d postgres -c "DROP DATABASE \"$POSTGRES_DB\";" -c "CREATE DATABASE \"$POSTGRES_DB\" OWNER \"$POSTGRES_USER\";"
docker exec emsarena-postgres pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --no-owner --no-privileges -j 4 /tmp/seed.dump
docker exec emsarena-postgres rm /tmp/seed.dump
# 2. tətbiq rolunu yenidən provision et (yeni bazada GRANT-lar yoxdur) və başa miqrasiya et
APP_DATABASE_USER=… APP_DATABASE_PASSWORD='…' ./scripts/provision-app-db-role.sh
docker compose -f docker-compose.prod.yml run --rm -e RUN_RELEASE_ON_START=false app /app/docker/release.sh
# 3. tətbiqi qaldır və yoxla
docker compose -f docker-compose.prod.yml up -d app celery_worker celery_worker_heavy celery_beat
curl -k https://127.0.0.1/health/ ; docker exec emsarena-postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "select count(*) from auth_user;"   # 8443 gözlənilir
```

Dump lokal bazanın miqrasiya vəziyyətindədir (`exams 0067` və s.); `release.sh`
onu başa (`exams 0069`, `organizations 0053`, `registrar 0078`) gətirir — RİM `*`
icazəsi (0053) məhz bu addımda mövcud rola yazılır.

**B. Deploy-dan ƏVVƏL (server)**

8. `docker network inspect emsarena_emsarena-network` → subnet **172.18.0.0/16**,
   gateway **172.18.0.1** (`ARP_AGENT_BIND` ilə eyni) — bax §5 «Network IPAM pin».
9. Backup: son dump-ın mövcudluğu (`./backups/postgres/last/`) və off-site nüsxə;
   deploy skripti onsuz da release-dən əvvəl dump alır (uğursuz dump = deploy dayanır).
10. **İmtahan saatından kənar** vaxt seçin: bu deploy **redis, nginx, alertmanager,
    blackbox və postgres konteynerlərini yenidən yaradır** (command / volume /
    healthcheck / `jit=off` dəyişib) — Redis restart (AOF var, data itmir, amma
    WS/sessiya/broker qısa kəsilir), nginx bir neçə saniyəlik edge kəsilməsi,
    Postgres 60 s-ə qədər graceful stop.

**C. Deploy**

11. `bash scripts/deploy/remote_deploy.sh` (və ya `main`-ə push). Gözlənilən
    axın: **`.env` preflight** (A-1 `APP_DATABASE_USER` boş deyil, `EMS_DB_ROLE_ENFORCE`
    xəbərdarlığı; P3-18 `PGBOUNCER_MAX_DB_CONNECTIONS ≤ POSTGRES_MAX_CONNECTIONS−20` və
    pool+reserve ≤ cap; A-3 `ALLOWED_HOSTS`-da `localhost`; A-5 `REDIS_MAXMEMORY <
    REDIS_MEM_LIMIT` — hər hansı biri pozulubsa deploy heç bir konteynerə toxunmadan
    dayanır) → `emsarena-prod:<sha>` build → `check --deploy` → dump → migrate/collectstatic →
    `up -d` → health gate → `latest` teqi. **İlk** deploy-da rollback hədəfi
    `emsarena-prod:latest`-dir (köhnə konteynerlər ondan yaradılıb) — keçərlidir.
12. Miqrasiyalar bu dalğada: `organizations 0051–0052`, `registrar 0076–0078`,
    `exams 0067–0069`, `accounts 0023`, `appeals 0004`, `courses 0002` (dublikat
    indekslər `CONCURRENTLY` silinir, `registrar_lesson (org, date)` indeksi əlavə olunur).
    Geri alınmır — rollback yalnız konteynerləri əvvəlki image-ə qaytarır (§8).

**D. Deploy-dan SONRA**

13. `/ping/` 200, `/health/` 200/207, `build.sha` = deploy olunan SHA.
14. `docker exec emsarena-postgres psql -U … -c 'SHOW jit'` → `off`.
15. Redis: `docker exec emsarena-redis sh -c 'cat /proc/1/cmdline | tr "\0" " "'` —
    parol görünməməlidir; `redis-cli ping` → PONG.
16. **Brevo «Authorised IPs»**: serverin çıxış IP-sini Brevo panelində ağ siyahıya
    əlavə edin, sonra Watchdog heartbeat e-poçtunun (`WATCHDOG_REPEAT_INTERVAL`, 24 h)
    və bir test alertinin **xarici tərəfdə** çatdığını sübut edin — bax
    [SISTEM_MONITORINQI.md](./SISTEM_MONITORINQI.md) «Brevo».
17. Real ölçülü **restore məşqi** (§12 «Restore procedure») + off-site nüsxənin
    yoxlanması; RPO qərarı.
18. İmtahan Mərkəzi / TŞ qərarı: 349 `exam_score > 50` sətri (SQL `registrar 0075`
    docstring-də) → təmizləndikdən sonra `VALIDATE CONSTRAINT`; 1 ehtimal ikiqat tələbə.
19. Yeni funksiyaların ilk istifadəsi: RİM rəhbərinə «İmtahan balının daxil edilməsi»
    bölməsinin göründüyünü (`final_score.entry`, miqrasiya `organizations 0052`), sehrbazda
    reyestr qrupu seçicisinin işlədiyini, sual idxalında KaTeX aktivlərinin (CSP) 200
    qaytardığını bir dəfə brauzerdə yoxlayın — sənədlər `docs/features/`.

---

## 6. Static & Private Media Handling

### Static files

Static files (CSS, JS, images bundled with the application) are collected
into the `static_data` Docker volume during the image build step
(`python manage.py collectstatic --noinput`).  Nginx serves them directly
from this volume at `/static/` without touching Django.

### Public media files

Two media directories are served directly by Nginx without Django involvement:

| URL prefix | Nginx alias |
|------------|-------------|
| `/media/post_images/` | `/var/www/media/post_images/` |
| `/media/course_covers/` | `/var/www/media/course_covers/` |

### Private media files

All other files under `/media/` (avatars, exam files, submission attachments,
lab files, etc.) are **not** served directly.  Access is controlled by Django:

1. The browser requests `/media/<private_path>/`.
2. Nginx proxies the request to Django (the `app` container).
3. Django's `protected_media` view checks authentication/authorisation.
4. On success, Django responds with an `X-Accel-Redirect: /internal_media/<path>` header.
5. Nginx intercepts this header and serves the file from the `media_data` volume
   via the `location /internal_media/ { internal; ... }` block — the file data
   never passes through Django.
6. On failure, Django returns 403/404 directly.

The `MEDIA_ACCEL_REDIRECT_URL` environment variable controls the prefix
(default `/internal_media`) and must match the Nginx `location` block.

### Storage volume management

```bash
# List volumes
docker volume ls | grep emsarena

# Back up media files
docker run --rm \
  -v emsarena_media_data:/source:ro \
  -v $(pwd)/backup:/backup \
  alpine tar czf /backup/media-$(date +%Y%m%d).tar.gz -C /source .
```

---

## 7. Health Check & Smoke Test Verification

### Automated container health checks

Docker Compose defines health checks for every service.  Check their status:

```bash
docker compose -f docker-compose.prod.yml ps
```

All services should show `(healthy)`.

### HTTP endpoint checks

```bash
# Basic liveness ping — must return HTTP 200
curl -sf http://localhost/ping/ && echo "✅ Ping OK"

# Detailed health check — returns 200 (all OK) or 207 (some issues)
curl -sf http://localhost/health/ && echo "✅ Health OK"
```

From the internet (via the Load Balancer):

```bash
curl -sf https://emsarena.com/ping/ && echo "✅ Public ping OK"
curl -sf https://emsarena.com/health/ && echo "✅ Public health OK"
```

### Smoke test checklist (manual)

Run these steps in a browser to verify the core user flow:

- [ ] `https://emsarena.com/accounts/login/` — login page loads, form is visible.
- [ ] Log in with a test account — redirected to the dashboard.
- [ ] `https://emsarena.com/organizations/` — organisation dashboard renders.
- [ ] `https://emsarena.com/exams/` — exam list page loads.
- [ ] WebSocket test: open a live exam session; the WebSocket connection
      establishes (no browser console errors).

### Automated E2E smoke tests (optional)

The CI pipeline runs Playwright smoke tests against the production stack.
To run them locally against a deployed environment:

```bash
pip install pytest pytest-playwright playwright
playwright install chromium

BASE_URL=https://emsarena.com \
E2E_USERNAME=<your-test-user> \
E2E_PASSWORD=<your-test-password> \
    pytest tests/e2e/ -v
```

---

## 8. Rollback Plan

> Infra audit 2026-09-14 (P2-5): rollback is now built into
> `scripts/deploy/remote_deploy.sh`. The steps below describe what the script
> does and how to do the same by hand.

### How a deploy is tagged and gated

1. `resolve_build_git_sha` → `resolve_release_image` exports
   `APP_IMAGE=emsarena-prod:<sha>` (`manual-<UTC timestamp>` when no SHA is
   known). `docker compose build` writes **only** that tag — `latest` is
   untouched until the end.
2. `capture_previous_app_image` records the image tag of the currently running
   `app` container (`docker inspect --format '{{.Config.Image}}'`) as the
   rollback target, provided that tag still exists locally.
3. `postgres-backup /backup.sh` takes a pre-migration dump into
   `./backups/postgres/` (skip with `SKIP_PREDEPLOY_BACKUP=1`; a failing dump
   aborts the deploy before `release.sh`).
4. `release.sh` (migrate + collectstatic) runs from the new tag, then
   `app`/`celery_*` are recreated with it.
5. Health gate (container healthchecks → `/ping/` → `/health/` → `build.sha`
   drift check). **Any failure** → `rollback_to_previous_image` (unless
   `DEPLOY_ROLLBACK_ON_FAILURE=false`), then the deploy exits 1.
6. Success → `docker tag emsarena-prod:<sha> emsarena-prod:latest` and older
   release tags beyond `DEPLOY_KEEP_RELEASE_IMAGES` are removed (current tag
   and rollback target are always kept).

### Identify the previous working image

```bash
# Release tags, newest first (latest always points at the last HEALTHY release)
docker images emsarena-prod --format "table {{.Tag}}\t{{.CreatedAt}}\t{{.ID}}"

# What is running right now
docker inspect --format '{{.Config.Image}}' \
    "$(docker compose -f docker-compose.prod.yml ps -q app | head -n1)"
```

### Roll back the application containers (what the script does)

```bash
# Recreate only the image-bearing services from the previous tag; no migrate.
APP_IMAGE=emsarena-prod:<previous-sha> RUN_RELEASE_ON_START=false \
    docker compose -f docker-compose.prod.yml up -d --no-build \
    --scale app="${APP_REPLICAS:-8}" --scale celery_worker="${CELERY_REPLICAS:-2}" \
    app celery_worker celery_worker_heavy celery_beat

# nginx resolves upstream IPs at config load — refresh it after the recreate.
docker compose -f docker-compose.prod.yml exec -T nginx nginx -s reload

# Verify
curl -sk -H "Host: ${HEALTHCHECK_HOST}" https://127.0.0.1/health/
```

`RUN_RELEASE_ON_START=false` matters: the entrypoint would otherwise re-run
migrations from the old code. The automatic rollback **does not revert
migrations** — the old image runs against the new schema. Additive
migrations are normally harmless; for a destructive migration restore the
pre-deploy dump (below) or run the reverse migration first:

```bash
docker compose -f docker-compose.prod.yml exec app python manage.py showmigrations
docker compose -f docker-compose.prod.yml exec app python manage.py migrate <app_label> <migration_name>
```

### Roll back with git + full rebuild

Only needed when no release tag is available (first deploy after enabling
tagging, or tags pruned):

```bash
git checkout <good-commit-sha>
BUILD_GIT_SHA=<good-commit-sha> bash scripts/deploy/remote_deploy.sh
```

### Database rollback

The deploy script already dumps before every migration via the
`postgres-backup` sidecar (`./backups/postgres/last/`, plus the rotated
`daily/weekly/monthly` sets — see §12). Manual equivalent and restore:

```bash
# Manual pre-deploy dump (what remote_deploy.sh runs before release.sh)
docker compose -f docker-compose.prod.yml exec -T postgres-backup /backup.sh

# Restore the last dump (stops writers first; see §12 "Restore procedure")
docker compose -f docker-compose.prod.yml stop app celery_worker celery_worker_heavy celery_beat
gunzip -c backups/postgres/last/<dump-file>.sql.gz | \
    docker exec -i emsarena-postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"
APP_IMAGE=emsarena-prod:<previous-sha> RUN_RELEASE_ON_START=false \
    docker compose -f docker-compose.prod.yml up -d --no-build app celery_worker celery_worker_heavy celery_beat
```

---

## 9. Secrets Management Checklist

- [ ] `SECRET_KEY` is at least 50 random characters and unique per environment.
- [ ] `POSTGRES_PASSWORD` and `REDIS_PASSWORD` are strong random strings (≥32 chars).
- [ ] The `.env` file is listed in `.gitignore` and never committed.
- [ ] Secrets are rotated if they have ever been exposed in a commit or log.
- [ ] CI secrets (`E2E_USERNAME`, `E2E_PASSWORD`) are stored as repository
      Actions secrets, not hardcoded in workflow files.
- [ ] Gitleaks is enabled in CI to catch future accidental secret commits.
- [ ] Sentry DSN (if used) is treated as a secret and injected at runtime only.

---

## 10. Celery Background Tasks

EMS Arena uses **Celery with Redis** (DB 2) as the broker to offload heavy
operations (email delivery, audit logging, notifications) from the HTTP
request-response cycle.

### Services

The production Compose stack includes a `celery_worker` service alongside
the main `app` service.  Both share the same Docker image so no extra build
step is needed.

### Starting the worker

```bash
# The worker starts automatically via docker-compose.prod.yml.
# To start manually:
docker compose -f docker-compose.prod.yml up -d celery_worker

# Watch worker logs:
docker compose -f docker-compose.prod.yml logs -f celery_worker
```

### Local development

```bash
# Start the Celery worker in the background (requires Redis running):
celery -A config worker -l INFO

# Or run with the beat scheduler for periodic tasks:
celery -A config worker --beat -l INFO -S django
```

### Email delivery

All verification OTP emails and blog post subscriber notifications are
dispatched via Celery tasks defined in `core/email_tasks.py`.  Each task
retries up to 3 times with exponential back-off on transient SMTP errors.

### Email backend environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `EMAIL_BACKEND` | `django.core.mail.backends.smtp.EmailBackend` | Override for SendGrid/SES via django-anymail |
| `EMAIL_HOST` | `smtp-relay.brevo.com` | SMTP hostname |
| `EMAIL_PORT` | `587` | SMTP port |
| `EMAIL_USE_SSL` | `False` | Keep `False` for Brevo STARTTLS |
| `EMAIL_USE_TLS` | `True` | Explicit STARTTLS (port 587) |
| `EMAIL_TIMEOUT` | `10` | Connection timeout in seconds |
| `BREVO_SMTP_LOGIN` | _(empty)_ | Brevo SMTP login like `xxxx@smtp-brevo.com` |
| `BREVO_SMTP_KEY` | _(empty)_ | Brevo SMTP key used as the password |
| `BREVO_EMAIL` | `no-reply@emsarena.com` | Visible sender mailbox |
| `BREVO_FROM_EMAIL` | `no-reply@emsarena.com` | Optional explicit sender override |
| `DEFAULT_FROM_EMAIL` | `no-reply@emsarena.com` | Sender address |

---

## 11. Redis Caching Strategy

Redis DB 1 is used as the application cache backend.  The following data is
cached automatically:

| Cache key | TTL | Description |
|-----------|-----|-------------|
| `emsarena:blog:navbar_categories` | 300 s | Blog navbar categories (invalidated on post save/delete) |
| `emsarena:blog:sidebar_categories:<flag>` | 120 s | Blog sidebar categories (invalidated on post save/delete) |
| `emsarena:blog:popular_topics:<limit>` | 300 s | Blog popular topics (invalidated on post save/delete) |
| `emsarena:live_session:settings:<pk>` | 120 s | Live exam session settings |
| `emsarena:exam:questions:<pk>` | 300 s | Exam question ID list |
| `emsarena:exam:meta:<pk>` | 600 s | Exam metadata |

Cache entries are invalidated automatically by signals when the underlying
data changes (e.g. `post_save` / `post_delete` on the `Post` model).

---

## 12. Postgres Automatic Backups (audit step 5)

The `postgres-backup` service in `docker-compose.prod.yml`
(`prodrigestivill/postgres-backup-local`) produces a compressed `pg_dump`
on a schedule and rotates old dumps automatically.

| Env var | Default | Meaning |
|---------|---------|---------|
| `POSTGRES_BACKUP_SCHEDULE` | `@daily` | Cron-style schedule |
| `POSTGRES_BACKUP_KEEP_DAYS` | `7` | Daily dumps kept |
| `POSTGRES_BACKUP_KEEP_WEEKS` | `4` | Weekly dumps kept |
| `POSTGRES_BACKUP_KEEP_MONTHS` | `3` | Monthly dumps kept |

Dumps are written to `./backups/postgres/` on the host
(`daily/`, `weekly/`, `monthly/` subfolders, `.sql.gz`).

### Off-site copy (REQUIRED)

Local dumps do not survive a disk failure. Copy them off the server daily,
e.g. with rclone to any S3/B2 bucket (host cron):

```bash
# /etc/cron.d/emsarena-backup-offsite
30 3 * * * root rclone sync /opt/emsarena/backups/postgres remote:emsarena-db-backups --max-age 48h
```

### Restore procedure (tested!)

```bash
# 1. Stop app writers (keep postgres up)
docker compose -f docker-compose.prod.yml stop app celery-worker celery-beat

# 2. Restore (DROPS and recreates objects; use a scratch DB first if unsure)
gunzip -c backups/postgres/daily/<dump-file>.sql.gz | \
  docker exec -i emsarena-postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"

# 3. Restart the app
docker compose -f docker-compose.prod.yml up -d app celery-worker celery-beat
```

Run a real restore test against a scratch database after the first deploy
(acceptance criterion of audit step 5), e.g. restore into `emsarena_restore_test`
and run `SELECT COUNT(*) FROM exams_examattempt;` to validate.

---

## 13. Direct-edge DNS, firewall and TLS preflight

Production has one trusted proxy boundary: Nginx itself.

**Current production is `EDGE_PROXY_MODE=lan`** — an intranet deployment with no
public domain (emsarena.com is retired; users browse the LAN IP directly). In
lan mode the deploy skips the public-DNS preflight and accepts a self-signed
certificate whose SAN covers the LAN IP (`TLS_ALLOW_SELF_SIGNED_LOCAL=true`).
Regenerate it with:

```bash
openssl req -x509 -newkey rsa:2048 -nodes -days 730 \
  -keyout docker/nginx/certs/origin.key -out docker/nginx/certs/origin.crt \
  -subj "/O=WCU/CN=10.0.2.42" \
  -addext "subjectAltName=IP:10.0.2.42,IP:127.0.0.1,DNS:localhost"
docker compose -f docker-compose.prod.yml exec -T nginx nginx -s reload
```

The steps below apply only if production ever moves back to a public domain
(`EDGE_PROXY_MODE=direct`):

1. **DNS**: point the canonical domain A/AAAA records directly to the server
   public address(es), then put that exact set in `DIRECT_ORIGIN_IPS`. The
   deploy resolves `HEALTHCHECK_HOST` and requires exact equality; stale proxy
   or parking addresses block release.
2. **Firewall**: allow public TCP 80/443 to the host, restrict SSH/admin
   management ports to operator networks, and keep Postgres/Redis/Daphne
   unexposed. The deploy removes historical `EMSARENA-CF-WEB*` Docker chains;
   inspect `iptables -S DOCKER-USER` once after the first direct-edge rollout.
3. **TLS material**: provision a public-CA certificate outside Git. Copy the
   full chain to `docker/nginx/certs/origin.crt` and the matching private key to
   `docker/nginx/certs/origin.key` (`0600`, deploy user readable). The deploy
   does not generate a self-signed fallback; it checks expiry, SAN/hostname,
   public trust and key match before touching containers.
4. **Renewal**: configure the ACME client renewal hook to atomically refresh
   those two files and run `docker compose -f docker-compose.prod.yml exec -T
   nginx nginx -s reload`. Keep at least the
   `TLS_CERT_MIN_VALIDITY_SECONDS` window (default seven days).
5. **Verification**:

   ```bash
   dig +short A emsarena.com
   dig +short AAAA emsarena.com
   openssl s_client -connect emsarena.com:443 -servername emsarena.com </dev/null
   curl --fail --show-error https://emsarena.com/health/
   ```

   The resolved addresses must equal `DIRECT_ORIGIN_IPS`; the certificate chain
   and hostname must verify without `-k`.



## Backup RESTORE runbook (Faza 7, audit 2026-07-02)

Backuplar `postgres-backup` servisi ilə gündəlik `./backups/postgres/` altına
yazılır (`-Z6 --blobs`, custom format deyil — plain `pg_dump | gzip`).
**Aylıq drill:** aşağıdakı addımları staging-də icra edib nəticəni qeyd edin —
yoxlanılmamış backup = backup deyil.

```bash
# 1) Ən son dump-ı seç
LATEST=$(ls -t backups/postgres/daily/*.sql.gz | head -1); echo "$LATEST"

# 2) Boş bərpa bazası yarat (mövcud produksiyaya TOXUNMA)
docker exec -i emsarena-postgres createdb -U "$POSTGRES_USER" emsarena_restore_test

# 3) Bərpa et
gunzip -c "$LATEST" | docker exec -i emsarena-postgres psql -U "$POSTGRES_USER" -d emsarena_restore_test

# 4) Doğrulama sorğuları (say məntiqi produksiya ilə eyni miqyasda olmalıdır)
docker exec -i emsarena-postgres psql -U "$POSTGRES_USER" -d emsarena_restore_test -c \
  "SELECT (SELECT count(*) FROM exams_examattempt)  AS attempts,
          (SELECT count(*) FROM exams_examanswer)   AS answers,
          (SELECT count(*) FROM auth_user)          AS users,
          (SELECT count(*) FROM organizations_organization) AS orgs;"

# 5) Təmizlik
docker exec -i emsarena-postgres dropdb -U "$POSTGRES_USER" emsarena_restore_test
```

Tam fəlakət ssenarisində (host itirilib): yeni hostda repo + `.env` bərpa et →
`docker compose -f docker-compose.prod.yml up -d postgres` → yuxarıdakı 3-cü
addımı ƏSAS bazaya (`$POSTGRES_DB`) tətbiq et → sonra qalan stack-i qaldır.
**Off-site nüsxə hələ konfiqurasiya olunmayıb** (audit K-tapıntısı): `./backups/`
qovluğunu S3/B2-yə sync edən cron əlavə olunana qədər host itkisi = backup itkisi.
