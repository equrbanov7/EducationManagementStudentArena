"""Təsdiqdən SONRA işləyən qarmaqlar (sahib 2026-11-08: «təsdiqlənmiş sillabus müəllimin başqa qrupunda da»).

``apps.syllabus`` registrar-ı İDXAL ETMİR — açılış tərəfi (məs. ``apps.registrar.syllabus_carry``) öz funksiyasını
``AppConfig.ready``-də :func:`register` ilə qeyd edir.  :func:`fire` təsdiq keçidindən (``workflow.approve`` /
``auto_approve``) çağırılır: hər qarmaq tranzaksiya COMMIT olandan SONRA, öz ``atomic`` blokunda işləyir və
xətası keçidi heç vaxt geri qaytarmır (bildirişlərlə eyni konvensiya — try/except + logger).
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from contextvars import ContextVar

from django.db import transaction

logger = logging.getLogger(__name__)

_HOOKS: list = []
_REVIEWED_BATCH = ContextVar("syllabus_reviewed_batch_hooks", default=False)


@contextmanager
def reviewed_batch_without_carry():
    """A reviewed receipt owns its explicit carry writes, including rollback."""
    token = _REVIEWED_BATCH.set(True)
    try:
        yield
    finally:
        _REVIEWED_BATCH.reset(token)


def register(hook) -> None:
    """``hook(syllabus_id=...)`` — təkrar qeyd edilmir (``ready`` iki dəfə çağırılsa belə)."""
    if hook not in _HOOKS:
        _HOOKS.append(hook)


def _run(hook, syllabus_id) -> None:
    try:
        with transaction.atomic():
            hook(syllabus_id=syllabus_id)
    except Exception:  # noqa: BLE001 — qarmaq təsdiqi geri qaytarmır
        logger.exception("syllabus approval hook failed: %s", getattr(hook, "__name__", hook))


def fire(syllabus_id) -> None:
    """Təsdiqlənmiş dosye üçün qarmaqları commit-dən sonraya planlaşdırır."""
    if syllabus_id is None or _REVIEWED_BATCH.get():
        return
    for hook in tuple(_HOOKS):
        transaction.on_commit(lambda hook=hook: _run(hook, syllabus_id))


__all__ = ["fire", "register"]
