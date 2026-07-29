"""İstifadə olunmadan qalmış private visual-import bundle-larının retention-u."""

from __future__ import annotations

import posixpath
from datetime import timedelta

from django.conf import settings
from django.core.files.storage import default_storage
from django.utils import timezone

from apps.exams.services.import_media import clear_stash

_ROOT = "question_imports"
_MANIFEST = "manifest.json"
_DEFAULT_RETENTION_HOURS = 48


def _token(value) -> str:
    value = str(value or "")
    return value if len(value) == 32 and all(char in "0123456789abcdef" for char in value) else ""


def purge_expired_import_stashes(*, now=None, retention_hours=None) -> int:
    """
    Yaşı keçmiş, aktiv submission-a bağlı olmayan bundle-ları sil.

    Funksiya global tenant sorğusu edir; yalnız periodic task-dakı
    ``bypass_rls`` daxilindən çağırılmalıdır.
    """

    from apps.exams.models import QuestionSubmission, TextExtractionJob

    now = now or timezone.now()
    hours = retention_hours
    if hours is None:
        hours = getattr(settings, "EXAM_IMPORT_STASH_RETENTION_HOURS", _DEFAULT_RETENTION_HOURS)
    try:
        hours = max(1, int(hours))
    except (TypeError, ValueError):
        hours = _DEFAULT_RETENTION_HOURS
    cutoff = now - timedelta(hours=hours)

    protected = set()
    for value in QuestionSubmission.objects.exclude(import_token="").values_list("import_token", flat=True):
        token = _token(value)
        if token:
            protected.add(token)
    old_jobs = []
    for job in TextExtractionJob.objects.only("pk", "created_at", "result_meta"):
        token = _token((job.result_meta or {}).get("math_token"))
        if not token:
            continue
        if job.created_at >= cutoff:
            protected.add(token)
        else:
            old_jobs.append((job, token))

    try:
        directories, _files = default_storage.listdir(_ROOT)
    except (FileNotFoundError, NotImplementedError):
        return 0

    purged: set[str] = set()
    for directory in directories:
        token = _token(directory)
        if not token or token in protected:
            continue
        manifest_name = posixpath.join(_ROOT, token, _MANIFEST)
        try:
            modified = default_storage.get_modified_time(manifest_name)
        except (NotImplementedError, OSError):
            continue
        if timezone.is_naive(modified):
            modified = timezone.make_aware(modified, timezone.get_current_timezone())
        if modified >= cutoff:
            continue
        clear_stash(token)
        if not default_storage.exists(manifest_name):
            purged.add(token)

    for job, token in old_jobs:
        if token not in purged:
            continue
        meta = dict(job.result_meta or {})
        meta.pop("math_token", None)
        meta["visual_import_expired"] = True
        job.result_meta = meta
        job.save(update_fields=["result_meta"])
    return len(purged)


__all__ = ["purge_expired_import_stashes"]
