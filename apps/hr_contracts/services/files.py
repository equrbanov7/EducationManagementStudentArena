"""Yetim fayl qalmasın (rəy A5, 2026-10-19) — ``apps/registrar/retake_files.py`` ilə eyni naxış.

* Yeni fayl storage-ə ``save()`` anında yazılır, DB sətri isə tranzaksiya bitəndə qalır. Servis xəta ilə geri
  qayıdırsa (``discard_on_error`` bloku istisna görür) blokda :func:`track` ilə qeydə alınan fayllar silinir.
* Əvəz olunan KÖHNƏ fayl yalnız tranzaksiya COMMIT olandan sonra silinir (:func:`delete_after_commit`) — geri
  qayıdışda köhnə sətir köhnə fayla işarə etməkdə davam edir. Başqa sətir həmin yola işarə edirsə silinmir.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from contextvars import ContextVar

from django.db import transaction

logger = logging.getLogger(__name__)

_tracked: ContextVar = ContextVar("hr_contracts_tracked_files", default=None)


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
                logger.warning("hr_contracts: could not delete orphan file %s", name, exc_info=True)
        raise
    finally:
        _tracked.reset(token)


def delete_after_commit(storage, name: str) -> None:
    if not name:
        return

    def _drop():
        from core.rls import bypass_rls

        from ..models import EmploymentContract

        try:
            with bypass_rls():
                referenced = EmploymentContract.objects.filter(file=name).exists()
            if referenced:
                return
            storage.delete(name)
        except Exception:  # noqa: BLE001
            logger.warning("hr_contracts: could not delete replaced file %s", name, exc_info=True)

    transaction.on_commit(_drop)


__all__ = ["delete_after_commit", "discard_on_error", "track"]
