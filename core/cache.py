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

    from core.cache import get_cached_session_settings, invalidate_session_settings_cache

    # Read (returns dict, never None)
    settings = get_cached_session_settings(session)

    # Invalidate after host updates settings
    invalidate_session_settings_cache(session)
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from django.core.cache import cache

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# Key builders
# ──────────────────────────────────────────────────────────────────────────────

_PREFIX = "emsarena"


def _safe_cache_get(key: str):
    try:
        return cache.get(key)
    except Exception:
        logger.warning("Redis unavailable; cache lookup failed for key %s", key)
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


def get_cached_session_settings(session) -> dict[str, Any]:
    """
    Return the normalised session settings for *session*, reading from the
    cache first and falling through to the DB on a miss.

    The result is always a fully normalised settings dict (never ``None``).
    """
    key = _session_settings_key(session)
    cached = _safe_cache_get(key)
    if cached is not None:
        return cached

    from apps.live_exam.session_settings import get_session_settings  # avoid circular import

    settings = get_session_settings(session)
    try:
        cache.set(key, settings, timeout=SESSION_SETTINGS_TTL)
    except Exception:
        logger.warning("Redis unavailable; session settings cache not populated for session %s", session.pk)
    return settings


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


def get_cached_exam_question_ids(session) -> list[int]:
    """
    Return the ordered list of question IDs for the exam attached to *session*,
    reading from the cache on a hit.

    Safe to call frequently; the list only changes when an exam author adds or
    removes questions (which should invalidate this cache).
    """
    key = _exam_question_ids_key(session)
    cached = _safe_cache_get(key)
    if cached is not None:
        return cached

    from apps.live_exam.domain.session import get_exam_question_ids  # avoid circular import

    ids = get_exam_question_ids(session)
    try:
        cache.set(key, ids, timeout=EXAM_QUESTION_IDS_TTL)
    except Exception:
        logger.warning("Redis unavailable; exam question IDs cache not populated for exam %s", session.exam_id)
    return ids


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
