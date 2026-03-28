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
Load Balancer  ← SSL/TLS terminates here (cert managed externally)
   │  HTTP (80)  + X-Forwarded-Proto: https
   ▼
┌──────────────────────────────────────────────────┐
│  Docker host (emsarena-network bridge)           │
│                                                  │
│  ┌─────────┐   HTTP   ┌─────────────────────┐   │
│  │  Nginx  │ ──────▶  │  Daphne (port 8000) │   │
│  │  :80    │          │  Django ASGI app     │   │
│  └────┬────┘          └─────────┬───────────┘   │
│       │                         │                │
│  Static / Media            ┌────┴────┐  ┌──────┐ │
│  (Docker volumes)          │Postgres │  │Redis │ │
└──────────────────────────────────────────────────┘
```

**SSL termination strategy — Option B (External Load Balancer):**
- The Load Balancer (AWS ALB, Cloudflare, HAProxy, …) handles all TLS.
- Nginx only listens on **port 80** inside the container.
- The LB adds `X-Forwarded-Proto: https` so Django and Nginx both know the
  original connection was secure.
- Django is pre-configured with `SECURE_PROXY_SSL_HEADER` and
  `USE_X_FORWARDED_HOST = True` to trust this header.

---

## 2. Prerequisites

| Tool | Minimum version | Notes |
|------|----------------|-------|
| Docker Engine | 24.x | `docker --version` |
| Docker Compose plugin | 2.20 | `docker compose version` |
| Git | 2.x | For pulling the repository |
| An external Load Balancer | — | Must support X-Forwarded-Proto |

No Python, PostgreSQL, or Redis installation is needed on the host — all
services run inside Docker containers.

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
| `ALLOWED_HOSTS` | `emsarena.com,www.emsarena.com` | Comma-separated list of valid `Host` headers |
| `CSRF_TRUSTED_ORIGINS` | `https://emsarena.com` | Comma-separated origins for CSRF validation |
| `SITE_URL` | `https://emsarena.com` | Canonical site URL (used in emails, WebSocket CSP) |
| `ADMIN_URL_PREFIX` | `manage/` | Non-default Django admin path. Must not be `admin/` in production. |
| `ADMIN_ALLOWED_IPS` | `203.0.113.10,198.51.100.20` | Comma-separated allowlist of source IPs permitted to access the admin panel. |

### Optional / feature variables

| Variable | Default | Description |
|----------|---------|-------------|
| `APP_IMAGE` | `emsarena-prod:latest` | Docker image tag. Set to `emsarena-prod:ci` during CI runs |
| `EMAIL_BACKEND` | `django.core.mail.backends.smtp.EmailBackend` | Email backend class. Override with `anymail` backend for SendGrid/SES |
| `EMAIL_HOST` | `smtp.gmail.com` | SMTP server hostname |
| `EMAIL_PORT` | `465` | SMTP server port |
| `EMAIL_USE_SSL` | `True` | Use implicit SSL (port 465). Set `False` and `EMAIL_USE_TLS=True` for port 587 |
| `EMAIL_USE_TLS` | `False` | Use explicit STARTTLS (port 587) |
| `EMAIL_TIMEOUT` | `10` | SMTP connection timeout in seconds |
| `EMAIL_HOST_USER` | _(empty)_ | SMTP username for outbound email |
| `EMAIL_HOST_PASSWORD` | _(empty)_ | SMTP password |
| `DEFAULT_FROM_EMAIL` | `noreply@emsarena.com` | From address for system emails |
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
ADMIN_ALLOWED_IPS=203.0.113.10,198.51.100.20
ADMIN_LOGIN_RATE_LIMIT=3/15m
ADMIN_2FA_REQUIRED=True
ADMIN_OTP_VERIFY_RATE_LIMIT=5/10m
ADMIN_OTP_RESEND_RATE_LIMIT=3/10m
```

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
`postgres` → `redis` → `app` (runs migrations via `prod-entrypoint.sh`) → `nginx`.

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
before starting Daphne, so database migrations are applied on every restart.

### Zero-downtime update checklist

1. `git pull origin main`
2. `docker compose -f docker-compose.prod.yml build`
3. `docker compose -f docker-compose.prod.yml up -d --no-deps app`
4. Wait for the new `app` container to pass its health check (see Step 7).
5. `docker compose -f docker-compose.prod.yml up -d --no-deps nginx` (if nginx config changed).

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

### Identify the previous working image

```bash
# List recent Docker images
docker images emsarena-prod --format "table {{.Tag}}\t{{.CreatedAt}}\t{{.ID}}"
```

Tag your images with the Git commit SHA when building for production:

```bash
docker compose -f docker-compose.prod.yml build
docker tag emsarena-prod:latest emsarena-prod:$(git rev-parse --short HEAD)
```

### Roll back the application container

```bash
# Replace the app container with the previous image tag
# (substitute <previous-sha> with the tag from the list above)
APP_IMAGE=emsarena-prod:<previous-sha> \
    docker compose -f docker-compose.prod.yml up -d --no-deps app
```

The entrypoint will re-run migrations on startup.  If the rollback involves
reverting a migration, run the reverse migration first:

```bash
# Check current migration state
docker compose -f docker-compose.prod.yml exec app \
    python manage.py showmigrations

# Revert to a specific migration (example)
docker compose -f docker-compose.prod.yml exec app \
    python manage.py migrate <app_label> <migration_name>
```

### Roll back with git + full rebuild

```bash
# Find the last known-good commit
git log --oneline -20

# Check out that commit
git checkout <good-commit-sha>

# Rebuild and redeploy
docker compose -f docker-compose.prod.yml build
docker compose -f docker-compose.prod.yml up -d
```

### Database rollback

> ⚠️ **Always back up the database before deploying a migration-heavy release.**

```bash
# Back up (run before every deployment)
docker compose -f docker-compose.prod.yml exec postgres \
    pg_dump -U ${POSTGRES_USER} ${POSTGRES_DB} \
    > backup-$(date +%Y%m%d-%H%M).sql

# Restore
docker compose -f docker-compose.prod.yml exec -T postgres \
    psql -U ${POSTGRES_USER} ${POSTGRES_DB} \
    < backup-<timestamp>.sql
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
| `EMAIL_HOST` | `smtp.gmail.com` | SMTP hostname |
| `EMAIL_PORT` | `465` | SMTP port |
| `EMAIL_USE_SSL` | `True` | Implicit TLS (port 465) |
| `EMAIL_USE_TLS` | `False` | Explicit STARTTLS (port 587) |
| `EMAIL_TIMEOUT` | `10` | Connection timeout in seconds |
| `EMAIL_HOST_USER` | _(empty)_ | SMTP username |
| `EMAIL_HOST_PASSWORD` | _(empty)_ | SMTP password |
| `DEFAULT_FROM_EMAIL` | `noreply@emsarena.com` | Sender address |

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
