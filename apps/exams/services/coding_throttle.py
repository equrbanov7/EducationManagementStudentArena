"""
Practical coding exam — Run Code throttling.

Two independent limits are enforced on every `/coding/run/` request:

1. **Per-user rate limit** — caps requests-per-minute for a single student
   so they can't accidentally hammer the executor by holding Ctrl+Enter.

2. **Per-user concurrency limit** — caps how many runs a student can have
   *in flight* simultaneously. This is what actually protects the executor
   from a 100-student classroom: even if every student clicks Run at the
   same instant, the pool stays bounded.

Both limits use Django's cache (Redis in production) so they work across
gunicorn/daphne workers. They never store student code or personally
identifiable information — only opaque counters keyed by user_id +
exam_attempt.

Why not django-ratelimit?
    django-ratelimit only does rate limits (not concurrency) and ties
    keys to HTTP request attributes. We need attempt-scoped tracking and
    a release-on-finish lifecycle, so a small dedicated helper is cleaner.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from typing import Optional

from django.conf import settings
from django.core.cache import cache

RATE_LIMIT_PREFIX = "coding:run:rl:"
CONCURRENCY_PREFIX = "coding:run:cc:"
SLOT_PREFIX = "coding:run:slot:"

# How long a concurrency slot may stay reserved before we forcibly free it.
# Real runs finish in seconds; this safety net only kicks in when a worker
# crashes mid-run and never calls release().
SLOT_TTL_SECONDS = 60


@dataclass
class ThrottleDecision:
    allowed: bool
    reason: str = ""
    retry_after_seconds: int = 0
    slot_token: Optional[str] = None


def _rate_limit_per_minute() -> int:
    raw = getattr(settings, "CODING_RUN_RATE_LIMIT_PER_MINUTE", 120)
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return 120
    return max(value, 0)


def _max_concurrent_per_user() -> int:
    raw = getattr(settings, "CODING_RUN_MAX_CONCURRENT_PER_USER", 2)
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return 2
    return max(value, 1)


def _bucket_key(user_id: int) -> str:
    # One-minute window — bucketed by wall-clock minute so users can't
    # game the limit by spacing requests across the rollover.
    minute = int(time.time() // 60)
    return f"{RATE_LIMIT_PREFIX}{user_id}:{minute}"


def _concurrency_key(user_id: int) -> str:
    return f"{CONCURRENCY_PREFIX}{user_id}"


def _slot_key(token: str) -> str:
    return f"{SLOT_PREFIX}{token}"


def acquire_run_slot(*, user_id: int) -> ThrottleDecision:
    """Reserve a concurrency slot and increment the rate-limit counter.

    Returns a ThrottleDecision the caller MUST inspect:
      - `allowed=False` → return 429 to the client; do not run the code.
      - `allowed=True`  → the caller now owns a slot identified by
        `slot_token`. Pass it to `release_run_slot()` in a finally-block,
        even when the run fails, so we don't leak slots on errors.
    """

    # --- Rate limit (token-bucket-ish, fixed minute window) ------------
    rpm = _rate_limit_per_minute()
    if rpm > 0:
        bucket = _bucket_key(user_id)
        # `cache.add` returns True only if the key didn't exist — we use it
        # to initialise the counter atomically without a race window.
        cache.add(bucket, 0, timeout=70)
        try:
            current = cache.incr(bucket)
        except ValueError:
            # Cache backend evicted the key between add() and incr() — fall
            # back to setting it to 1, accepting one extra request as the
            # cost of being lock-free.
            cache.set(bucket, 1, timeout=70)
            current = 1
        if current > rpm:
            return ThrottleDecision(
                allowed=False,
                reason="rate_limited",
                retry_after_seconds=60 - (int(time.time()) % 60),
            )

    # --- Concurrency limit --------------------------------------------
    max_cc = _max_concurrent_per_user()
    cc_key = _concurrency_key(user_id)
    cache.add(cc_key, 0, timeout=SLOT_TTL_SECONDS * 2)
    try:
        in_flight = cache.incr(cc_key)
    except ValueError:
        cache.set(cc_key, 1, timeout=SLOT_TTL_SECONDS * 2)
        in_flight = 1

    if in_flight > max_cc:
        # Roll back the increment so we don't poison future requests.
        try:
            cache.decr(cc_key)
        except ValueError:
            pass
        return ThrottleDecision(
            allowed=False,
            reason="too_many_concurrent",
            retry_after_seconds=2,
        )

    token = uuid.uuid4().hex
    cache.set(_slot_key(token), user_id, timeout=SLOT_TTL_SECONDS)
    return ThrottleDecision(allowed=True, slot_token=token)


def release_run_slot(token: Optional[str]) -> None:
    """Mark a previously-acquired slot as finished.

    Safe to call with `None` (acquire failed) or with an already-released
    token — both are no-ops. Always wrap the run in try/finally so this
    runs on the error path too.
    """

    if not token:
        return
    slot_key = _slot_key(token)
    user_id = cache.get(slot_key)
    if user_id is None:
        return  # Already released / expired.
    cache.delete(slot_key)
    try:
        remaining = cache.decr(_concurrency_key(user_id))
        if remaining is not None and remaining < 0:
            # Defensive: never let the counter go negative if something
            # else (cache eviction, manual flush) put it out of sync.
            cache.set(_concurrency_key(user_id), 0, timeout=SLOT_TTL_SECONDS * 2)
    except ValueError:
        cache.set(_concurrency_key(user_id), 0, timeout=SLOT_TTL_SECONDS * 2)
