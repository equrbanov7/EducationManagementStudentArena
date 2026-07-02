"""Canlı imtahan üçün oxu-tərəfli cache wrapper-ləri.

M3 (2026-07-02): core/cache.py-dən köçürülüb — get tərəfi live_exam
servislərini çağırdığı üçün core→live_exam kənarı yaradırdı. Açar qurucular
və invalidatorlar core.cache-də qalır (yazan tərəflər app-lardan onları
çağırır); TTL-lər də oradan gəlir.
"""

from __future__ import annotations

import logging
from typing import Any

from django.core.cache import cache

from apps.live_exam.domain.session import get_exam_question_ids
from apps.live_exam.models import LiveSession
from apps.live_exam.session_settings import get_session_settings
from core.cache import (
    EXAM_QUESTION_IDS_TTL,
    SESSION_SETTINGS_TTL,
    _exam_question_ids_key,
    _safe_cache_get,
    _session_settings_key,
)

logger = logging.getLogger(__name__)


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

    settings = get_session_settings(session)
    try:
        cache.set(key, settings, timeout=SESSION_SETTINGS_TTL)
    except Exception:
        logger.warning("Redis unavailable; session settings cache not populated for session %s", session.pk)
    return settings


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

    ids = get_exam_question_ids(session)
    try:
        cache.set(key, ids, timeout=EXAM_QUESTION_IDS_TTL)
    except Exception:
        logger.warning("Redis unavailable; exam question IDs cache not populated for exam %s", session.exam_id)
    return ids


def warm_session_settings_cache(session_pk: int) -> None:
    """
    Pre-load session settings into the cache after session creation.

    Avoids a cold-cache penalty on the first API poll from the host.
    """
    try:
        from core.rls import bypass_rls
        from core.rls_pooling import rls_worker_atomic

        # System cache warmer receives only a session PK, so it must look up any
        # tenant's live session under bypass; rls_worker_atomic makes it SET LOCAL
        # when transaction-scoped RLS is enabled.
        with rls_worker_atomic(), bypass_rls():
            session = LiveSession.objects.select_related("exam").get(pk=session_pk)
            get_session_settings(session)
    except Exception:
        logger.exception("warm_session_settings_cache failed for session %s", session_pk)
