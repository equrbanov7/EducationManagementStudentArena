"""Tranzaksiya geri qayıdanda yazılmış faylları sil — rəy 2026-10-18 (LOW-9).

Qəbz / qərar sənədi storage-ə ``save()`` anında yazılır, DB sətri isə tranzaksiya bitəndə qalır. Servis
xəta ilə geri qayıdırsa (məs. yerləşdirmə servisi imtina edir) fayl yetim qalırdı. :func:`discard_on_error`
servis gövdəsini sarır: blok daxilində :func:`track` ilə qeydə alınan fayllar istisna baş verərsə silinir,
xəta isə olduğu kimi yuxarı ötürülür (tranzaksiya onsuz da geri qayıdır).
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from contextvars import ContextVar

logger = logging.getLogger(__name__)

_tracked: ContextVar = ContextVar("retake_tracked_files", default=None)


def track(field_file) -> None:
    bucket = _tracked.get()
    name = getattr(field_file, "name", "")
    if bucket is not None and name:
        bucket.append((field_file.storage, name))


@contextmanager
def discard_on_error():
    bucket: list = []
    token = _tracked.set(bucket)
    try:
        yield bucket
    except BaseException:
        for storage, name in bucket:
            try:
                storage.delete(name)
            except Exception:  # noqa: BLE001 — təmizlik heç vaxt əsas xətanı gizlətmir
                logger.warning("retake: could not delete orphan file %s", name, exc_info=True)
        raise
    finally:
        _tracked.reset(token)


__all__ = ["discard_on_error", "track"]
