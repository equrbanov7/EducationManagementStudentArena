# EMS Arena — API Architecture Roadmap

## 1. Overview

EMS Arena is a multi-tenant EdTech platform serving students, teachers, and
organization administrators.  As mobile and SPA front-ends are planned, a
well-versioned, discoverable REST API is required.  This document describes
the proposed architecture, endpoint inventory, and versioning strategy.

---

## 2. Guiding Principles

| Principle | Detail |
|---|---|
| **REST first** | Standard HTTP verbs; JSON request/response bodies |
| **Versioned from day one** | All endpoints live under `/api/v<N>/`; breaking changes require a new version |
| **JWT + session support** | Session cookies for browser clients; JWT Bearer tokens for mobile / SPA |
| **Tenant-aware** | Every request that touches tenant data must carry an `X-Organization-Slug` header or derive the org from the authenticated user |
| **Consistent errors** | `{"error": "<code>", "detail": "<human message>"}` envelope for all 4xx/5xx responses |
| **OpenAPI documentation** | Schemas generated with `drf-spectacular` or `drf-yasg` |

---

## 3. Technology Stack

| Component | Choice |
|---|---|
| Framework | **Django REST Framework (DRF)** 3.15+ |
| Authentication | `rest_framework_simplejwt` for JWT; `SessionAuthentication` for browser |
| Schema generation | `drf-spectacular` (OpenAPI 3.1) |
| Rate limiting | Reuse existing `django-ratelimit` integration |
| Permissions | Custom DRF permission classes wrapping `core.permissions` |

---

## 4. Versioning Strategy

```
/api/v1/   ← Current stable version (partial, see §6)
/api/v2/   ← Future; introduced for breaking changes only
```

**Rules:**

- **Non-breaking additions** (new optional response fields, new optional query
  parameters) are allowed in the current version without a bump.
- **Breaking changes** (removed or renamed fields, changed semantics, new
  *required* parameters) require a new `/api/v<N+1>/` prefix while `/api/v<N>/`
  continues to be served for a minimum deprecation window of **6 months**.
- Version sunset dates are communicated via a `Deprecation` response header
  and published in this document.

---

## 5. Authentication

### 5.1 Session (browser / SSR)

Existing cookie-based sessions continue to work.  DRF's `SessionAuthentication`
class is included in `DEFAULT_AUTHENTICATION_CLASSES`.

### 5.2 JWT (mobile / SPA)

```
POST /api/v1/auth/token/          → obtain access + refresh tokens
POST /api/v1/auth/token/refresh/  → exchange refresh for new access token
POST /api/v1/auth/token/verify/   → verify a token is valid
```

Access tokens expire in **15 minutes**; refresh tokens in **7 days** (matching
the existing `SESSION_COOKIE_AGE` default).

---

## 6. Endpoint Inventory

### 6.1 Already Implemented (v1)

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/v1/live/<pin>/state/` | Live session state (rate-limited, 120/min) |
| `GET` | `/health/` | Detailed health check (DB + Redis) |
| `GET` | `/ping/` | Liveness probe |
| `GET` | `/metrics/` | Prometheus metrics scrape endpoint |

### 6.2 Planned — Authentication

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/v1/auth/token/` | Obtain JWT pair |
| `POST` | `/api/v1/auth/token/refresh/` | Refresh JWT access token |
| `POST` | `/api/v1/auth/token/verify/` | Verify JWT |
| `POST` | `/api/v1/auth/register/` | Self-registration (if enabled) |
| `POST` | `/api/v1/auth/password/reset/` | Request password reset OTP |
| `POST` | `/api/v1/auth/password/reset/confirm/` | Confirm reset with OTP |

### 6.3 Planned — Organizations

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/v1/organizations/` | List organizations the current user belongs to |
| `GET` | `/api/v1/organizations/<slug>/` | Organization detail |
| `GET` | `/api/v1/organizations/<slug>/members/` | Member list (admin only) |

### 6.4 Planned — Courses

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/v1/courses/` | List accessible courses |
| `GET` | `/api/v1/courses/<id>/` | Course detail |
| `GET` | `/api/v1/courses/<id>/dashboard/` | Student dashboard for course |

### 6.5 Planned — Assignments

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/v1/assignments/` | List assignments (scoped to org/course) |
| `GET` | `/api/v1/assignments/<id>/` | Assignment detail |
| `POST` | `/api/v1/assignments/<id>/submit/` | Student submission |

### 6.6 Planned — Exams

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/v1/exams/` | List exams |
| `GET` | `/api/v1/exams/<id>/` | Exam detail |
| `POST` | `/api/v1/exams/<id>/attempts/` | Start attempt |
| `PATCH` | `/api/v1/exams/<id>/attempts/<attempt_id>/` | Submit answers |

### 6.7 Planned — Live Exam

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/v1/live/join/` | Join a live session by PIN |
| `GET` | `/api/v1/live/<pin>/state/` | ✅ Already implemented |
| `POST` | `/api/v1/live/<pin>/answer/` | Submit answer (WebSocket preferred) |
| `GET` | `/api/v1/live/<pin>/results/` | Results after session ends |

### 6.8 Planned — Notifications

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/v1/notifications/` | List notifications for current user |
| `PATCH` | `/api/v1/notifications/<id>/read/` | Mark as read |
| `POST` | `/api/v1/notifications/read-all/` | Mark all as read |

---

## 7. Request / Response Conventions

### 7.1 Request headers

| Header | Required | Description |
|---|---|---|
| `Authorization` | JWT clients | `Bearer <access_token>` |
| `Content-Type` | mutation requests | `application/json` |
| `X-Organization-Slug` | multi-tenant endpoints | Active organization context |
| `X-Request-ID` | optional | Client-supplied correlation ID (echoed back) |
| `Accept-Language` | optional | Preferred response language (`az`, `en`, `ru`, `tr`) |

### 7.2 Pagination

All list endpoints use cursor-based pagination:

```json
{
  "count": 42,
  "next": "/api/v1/courses/?cursor=abc123",
  "previous": null,
  "results": [...]
}
```

Default page size: **25**.  Maximum: **100** (via `?page_size=`).

### 7.3 Error envelope

```json
{
  "error": "permission_denied",
  "detail": "You do not have permission to perform this action.",
  "request_id": "4f3a1b9c"
}
```

The `request_id` field is always present and matches the `X-Request-ID`
response header for log correlation.

---

## 8. DRF Configuration (proposed `settings/base.py` addition)

```python
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.CursorPagination",
    "PAGE_SIZE": 25,
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "EXCEPTION_HANDLER": "core.api.exception_handler",
}

SPECTACULAR_SETTINGS = {
    "TITLE": "EMS Arena API",
    "DESCRIPTION": "Multi-tenant EdTech platform REST API",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
}
```

---

## 9. Implementation Phases

| Phase | Scope | Priority |
|---|---|---|
| **P0** | JWT auth endpoints, OpenAPI schema generation | 🔴 High |
| **P1** | Courses, Assignments, Exams read endpoints | 🟠 Medium |
| **P2** | Live Exam join + answer submission | 🟠 Medium |
| **P3** | Notifications, full CRUD for teacher actions | 🟡 Low |
| **P4** | Admin management endpoints, bulk operations | 🟢 Future |

---

## 10. Security Considerations

- All API endpoints require authentication (except `/api/v1/auth/token/` and
  `/api/v1/auth/register/`).
- Rate limiting applied to auth endpoints:
  - Token obtain: **5 requests per 10 minutes** (matches `LOGIN_RATE_LIMIT`).
  - Token refresh: **30 requests per minute**.
- CORS is disabled by default; enable with `django-cors-headers` only for
  trusted SPA origins, configured via `CORS_ALLOWED_ORIGINS` environment
  variable.
- JWT tokens must **not** be stored in `localStorage`; recommended storage is
  `HttpOnly` cookies for SPAs or secure device storage for mobile apps.
- Sensitive fields (passwords, OTPs, tokens) are stripped from logs by
  `core.logging_filters.SensitiveDataFilter`.

---

## 11. OpenAPI / Documentation URLs (proposed)

| URL | Description |
|---|---|
| `/api/v1/schema/` | Raw OpenAPI 3.1 schema (JSON/YAML) |
| `/api/v1/docs/` | Swagger UI (DEBUG only) |
| `/api/v1/redoc/` | ReDoc (DEBUG only) |
