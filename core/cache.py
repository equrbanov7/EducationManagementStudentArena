"""
core/cache.py
─────────────
Redis-backed caching helpers for EMS Arena.

Strategy
--------
Redis database 1 is used for application-level caching (database 0 is used
by Django Channels for WebSocket pub/sub).  See ``REDIS_CACHE_URL`` in
``config/settings/base.py``.

Cache key naming convention
---------------------------
``emsarena:<app>:<resource>:<pk_or_identifier>``

TTL guidance
------------
| Resource                      | TTL     | Rationale                          |
|-------------------------------|---------|------------------------------------|
| Live session settings         | 120 s   | Changed rarely; host edits trigger |
|                               |         | invalidation.                      |
| Exam question ID list         | 300 s   | Questions don't change mid-session.|
| Exam metadata (title, type)   | 600 s   | Low mutation rate.                  |
| Player count for a session    | 5 s     | High-frequency; small staleness OK.|

Invalidation
------------
Each helper that writes to the cache exposes a companion ``_invalidate_*``
function.  Call the invalidation helper from the code that mutates the
underlying data.

Usage
-----
::

    # Oxu tərəfi app-dadır: apps/live_exam/cache.py → get_cached_session_settings
    from core.cache import invalidate_session_settings_cache  # yazan tərəf üçün

    invalidate_session_settings_cache(session)
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from django.core.cache import cache

from core.logging_utils import safe_log_value

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# Key builders
# ──────────────────────────────────────────────────────────────────────────────

_PREFIX = "emsarena"


def _safe_cache_get(key: str):
    try:
        return cache.get(key)
    except Exception:
        # Açar istifadəçi filtrindən (məs. dil seçimi) hissə daşıya bilir —
        # log sətrinə xam getməməlidir (CodeQL py/log-injection).
        logger.warning("Redis unavailable; cache lookup failed for key %s", safe_log_value(key))
        return None


def _session_settings_key(session) -> str:
    return f"{_PREFIX}:live_exam:session_settings:{session.pk}"


def _exam_question_ids_key(session) -> str:
    return f"{_PREFIX}:live_exam:exam_question_ids:{session.exam_id}"


def _exam_metadata_key(exam_pk: int) -> str:
    return f"{_PREFIX}:exams:metadata:{exam_pk}"


# ──────────────────────────────────────────────────────────────────────────────
# Session settings
# ──────────────────────────────────────────────────────────────────────────────

SESSION_SETTINGS_TTL = 120  # seconds


def invalidate_session_settings_cache(session) -> None:
    """Remove the session settings cache entry for *session*."""
    try:
        cache.delete(_session_settings_key(session))
    except Exception:
        logger.warning("Redis unavailable; could not invalidate session settings cache for session %s", session.pk)


# ──────────────────────────────────────────────────────────────────────────────
# Exam question ID list
# ──────────────────────────────────────────────────────────────────────────────

EXAM_QUESTION_IDS_TTL = 300  # seconds


def invalidate_exam_question_ids_cache(exam_pk: int) -> None:
    """
    Invalidate the cached question ID list for the exam identified by
    *exam_pk*.  Call this whenever questions are added or removed.
    """
    try:
        cache.delete(f"{_PREFIX}:live_exam:exam_question_ids:{exam_pk}")
    except Exception:
        logger.warning("Redis unavailable; could not invalidate exam question IDs cache for exam %s", exam_pk)


# ──────────────────────────────────────────────────────────────────────────────
# Exam metadata
# ──────────────────────────────────────────────────────────────────────────────

EXAM_METADATA_TTL = 600  # seconds


def get_cached_exam_metadata(exam_pk: int) -> dict[str, Any] | None:
    """
    Return a lightweight metadata dict for the exam identified by *exam_pk*.

    Returns ``None`` on a cache miss so that the caller can fetch from the DB
    and populate the cache.
    """
    key = _exam_metadata_key(exam_pk)
    return _safe_cache_get(key)


def set_cached_exam_metadata(exam_pk: int, metadata: dict[str, Any]) -> None:
    """Store *metadata* in the cache for exam *exam_pk*."""
    try:
        cache.set(_exam_metadata_key(exam_pk), metadata, timeout=EXAM_METADATA_TTL)
    except Exception:
        logger.warning("Redis unavailable; exam metadata cache not populated for exam %s", exam_pk)


def invalidate_exam_metadata_cache(exam_pk: int) -> None:
    """Remove the cached metadata for exam *exam_pk*."""
    try:
        cache.delete(_exam_metadata_key(exam_pk))
    except Exception:
        logger.warning("Redis unavailable; could not invalidate exam metadata cache for exam %s", exam_pk)


# ──────────────────────────────────────────────────────────────────────────────
# Dashboard statistics (FAZA 12)
# ──────────────────────────────────────────────────────────────────────────────
# The statistics_selectors functions run ~44 aggregate/annotate/count queries.
# Statistics do not need to be real-time, so the result is cached briefly per
# (role, scope, filters) combination. A short TTL keeps the data fresh enough
# while absorbing repeated dashboard opens / refreshes.

STATISTICS_TTL = 180  # seconds — small staleness is acceptable for dashboards


def _statistics_key(*, role: str, scope_id, filters: dict | None) -> str:
    """Build a cache key unique to a role + scope + filter combination.

    *scope_id* is the user id (student/teacher) or organization id (org admin),
    or "global" for superadmin. *filters* (date ranges, content-type, etc.) are
    hashed so different filter sets never collide.
    """
    try:
        filters_blob = json.dumps(filters or {}, sort_keys=True, default=str)
    except (TypeError, ValueError):
        filters_blob = repr(filters)
    filters_hash = hashlib.sha1(filters_blob.encode("utf-8"), usedforsecurity=False).hexdigest()[:12]
    return f"{_PREFIX}:accounts:statistics:{role}:{scope_id}:{filters_hash}"


# ──────────────────────────────────────────────────────────────────────────────
# Signup lookup payload (countries + joinable organizations)
# ──────────────────────────────────────────────────────────────────────────────
# The register page (GET and POST) needs the full list of active countries and
# joinable organizations. These change very rarely, but the query scanned both
# tables on every request. Cache the assembled payload and invalidate it from
# Country / Organization mutations (see apps.organizations.signals).

SIGNUP_LOOKUP_TTL = 600  # seconds


def _signup_lookup_key() -> str:
    return f"{_PREFIX}:accounts:signup_lookup_payload"


def get_or_set_cached_signup_lookup(compute):
    """Return the cached signup lookup payload, computing + caching on a miss.

    *compute* is a zero-arg callable returning the payload dict. Degrades
    gracefully to a direct ``compute()`` call if Redis is unavailable.
    """
    key = _signup_lookup_key()
    cached = _safe_cache_get(key)
    if cached is not None:
        return cached
    payload = compute()
    try:
        cache.set(key, payload, timeout=SIGNUP_LOOKUP_TTL)
    except Exception:
        logger.warning("Redis unavailable; signup lookup cache not populated")
    return payload


def invalidate_signup_lookup_cache() -> None:
    """Drop the cached signup lookup payload (call on Country/Organization change)."""
    try:
        cache.delete(_signup_lookup_key())
    except Exception:
        logger.warning("Redis unavailable; could not invalidate signup lookup cache")


def get_or_set_cached_statistics(*, role: str, scope_id, filters: dict | None, compute):
    """Return cached statistics for the given key, computing + caching on a miss.

    Args:
        role: "student" | "teacher" | "org_admin" | "superadmin".
        scope_id: user id, organization id, or "global".
        filters: the filter dict passed to the statistics selector.
        compute: zero-arg callable that runs the expensive selector and returns
            the statistics payload. Only called on a cache miss.

    On any Redis error this degrades gracefully — it just calls *compute*.
    """
    key = _statistics_key(role=role, scope_id=scope_id, filters=filters)
    cached = _safe_cache_get(key)
    if cached is not None:
        return cached
    payload = compute()
    try:
        cache.set(key, payload, timeout=STATISTICS_TTL)
    except Exception:
        logger.warning("Redis unavailable; statistics cache not populated for %s", key)
    return payload


# ──────────────────────────────────────────────────────────────────────────────
# Profile sidebar badge counts (P3)
# ──────────────────────────────────────────────────────────────────────────────
# The profile page (`/accounts/profile/`) rebuilds the sidebar badge counters on
# every load *and* on every AJAX section swap. For a student that is ~13 COUNT(*)
# queries (assigned tasks / results / pending answers); for a reviewer it adds 4
# aggregate queries over the large attempt/submission tables. Under concurrent
# dashboard load this path dominated the "normal" request latency (k6: normal
# p95 ≈ 5.2 s). The numbers are the user's own data and tolerate small staleness,
# so they are cached briefly per (user, active org). Keyed by org because the
# underlying querysets are tenant-scoped to the active organization.

PROFILE_BADGE_COUNTS_TTL = 45  # seconds — badges tolerate small staleness


def _profile_badge_counts_key(user_id, org_id) -> str:
    return f"{_PREFIX}:accounts:profile_badges:{user_id}:{org_id if org_id is not None else 'none'}"


def get_or_set_cached_profile_badge_counts(*, user_id, org_id, compute) -> dict[str, int]:
    """Return cached profile sidebar badge counts, computing + caching on a miss.

    Args:
        user_id: primary key of the user whose badges are being rendered.
        org_id: active organization id (or ``None``); part of the key because
            the badge querysets are tenant-scoped.
        compute: zero-arg callable that runs the badge COUNT/aggregate queries
            and returns a ``{badge_name: int}`` dict. Only called on a miss.

    Degrades gracefully to a direct ``compute()`` call when Redis is down.
    """
    key = _profile_badge_counts_key(user_id, org_id)
    cached = _safe_cache_get(key)
    if cached is not None:
        return cached
    payload = compute()
    try:
        cache.set(key, payload, timeout=PROFILE_BADGE_COUNTS_TTL)
    except Exception:
        logger.warning("Redis unavailable; profile badge counts cache not populated for %s", key)
    return payload


def invalidate_profile_badge_counts_cache(user_id, org_id=None) -> None:
    """Drop a user's cached profile badge counts.

    Pass *org_id* to clear a specific tenant scope; omit it to clear the
    org-less ("none") scope. The short TTL is the primary freshness guarantee,
    so explicit invalidation is optional — call it from grading/submission
    mutations when near-instant badge updates matter.
    """
    try:
        cache.delete(_profile_badge_counts_key(user_id, org_id))
    except Exception:
        logger.warning("Redis unavailable; could not invalidate profile badge counts for user %s", user_id)


# --------------------------------------------------------------------------- #
# Sual bankı keyfiyyət analizi
# --------------------------------------------------------------------------- #

BANK_ANALYSIS_TTL = 900  # saniyə — barmaq izi onsuz da təzəliyi təmin edir


def _bank_analysis_key(bank_id, language: str, fingerprint: str) -> str:
    return f"{_PREFIX}:exams:bank_analysis:{bank_id}:{language or 'all'}:{fingerprint}"


def get_or_set_cached_bank_analysis(*, bank_id, language: str, fingerprint: str, compute):
    """Sual bankı analizinin nəticəsini MƏZMUN barmaq izi ilə keşləyir.

    Analiz bankın bütün test suallarını variantları ilə yaddaşa yükləyib
    dublikat/struktur/balans yoxlaması aparır — bahalıdır və detal səhifəsinin
    hər GET-ində (səhifələmə, filtr, sıralama, dil dəyişmə) təkrarlanırdı.

    Açar ``fingerprint``-i (sual sayı + ən son ``updated_at``) daşıyır: dəst
    dəyişən kimi açar da dəyişir, yəni ayrıca invalidasiya çağırışı lazım deyil
    və köhnəlmiş nəticə göstərilmir. TTL yalnız keşin şişməməsi üçündür.

    Redis əlçatmaz olsa birbaşa ``compute()``-a düşür.
    """
    key = _bank_analysis_key(bank_id, language, fingerprint)
    cached = _safe_cache_get(key)
    if cached is not None:
        return cached
    payload = compute()
    try:
        cache.set(key, payload, timeout=BANK_ANALYSIS_TTL)
    except Exception:
        logger.warning("Redis unavailable; bank analysis cache not populated for %s", safe_log_value(key))
    return payload
