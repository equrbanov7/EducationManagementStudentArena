"""İstifadə olunmadan qalmış private visual-import bundle-larının retention-u.

Fon işi tutumu 2026-10-07:

* saatlıq stash süpürgəsi HƏR ``TextExtractionJob`` sətrini (``result_meta`` ilə)
  Python-a yükləyirdi — cədvəl hər idxal/AI/export ilə böyüyür və heç vaxt
  təmizlənmirdi. İndi yalnız ``math_token`` daşıyan işlər oxunur (``?`` operatoru);
* :func:`purge_finished_extraction_jobs` — bitmiş (success/failed) işlər
  ``EXAM_EXTRACTION_JOB_RETENTION_DAYS`` (defolt 14, ``0`` → söndürülür) gündən
  sonra fayl(lar)ı ilə birlikdə silinir. İş sətri yalnız status-poll / bir dəfəlik
  yükləmə üçündür (çıxarılmış mətn ``text``-də, export faylı ``result_file``-da qalırdı).
"""

from __future__ import annotations

import logging
import posixpath
from datetime import timedelta

from django.conf import settings
from django.core.files.storage import default_storage
from django.utils import timezone

from apps.exams.services.import_media import clear_stash
from core.batch_purge import purge_in_batches

logger = logging.getLogger(__name__)

_ROOT = "question_imports"
_MANIFEST = "manifest.json"
_DEFAULT_RETENTION_HOURS = 48
DEFAULT_EXTRACTION_JOB_RETENTION_DAYS = 14


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
    for value in QuestionSubmission.objects.exclude(import_token="").order_by().values_list("import_token", flat=True):
        token = _token(value)
        if token:
            protected.add(token)
    old_jobs = []
    jobs_with_token = (
        TextExtractionJob.objects.filter(result_meta__has_key="math_token")
        .order_by()
        .values_list("pk", "created_at", "result_meta")
    )
    for pk, created_at, result_meta in jobs_with_token:
        token = _token((result_meta or {}).get("math_token"))
        if not token:
            continue
        if created_at >= cutoff:
            protected.add(token)
        else:
            old_jobs.append((pk, result_meta, token))

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

    for pk, result_meta, token in old_jobs:
        if token not in purged:
            continue
        meta = dict(result_meta or {})
        meta.pop("math_token", None)
        meta["visual_import_expired"] = True
        TextExtractionJob.objects.filter(pk=pk).update(result_meta=meta)
    return len(purged)


def extraction_job_retention_days() -> int:
    try:
        value = int(getattr(settings, "EXAM_EXTRACTION_JOB_RETENTION_DAYS", DEFAULT_EXTRACTION_JOB_RETENTION_DAYS))
    except (TypeError, ValueError):
        value = DEFAULT_EXTRACTION_JOB_RETENTION_DAYS
    return max(value, 0)


def _delete_job_files(ids) -> None:
    from apps.exams.models import TextExtractionJob

    for job in TextExtractionJob.objects.filter(pk__in=ids).only("pk", "file", "result_file"):
        for field in (job.file, job.result_file):
            if not field:
                continue
            try:
                field.delete(save=False)
            except Exception:  # noqa: BLE001 — fayl yoxdursa / storage xətası sətrin silinməsini dayandırmır
                logger.warning("extraction job %s: fayl silinmədi (%s)", job.pk, field.name, exc_info=True)


def purge_finished_extraction_jobs(*, now=None, scope=None, batch_size=1000, time_budget=180.0) -> int:
    """Saxlama müddəti keçmiş bitmiş ``TextExtractionJob`` sətirlərini (faylları ilə) sil → say.

    Yalnız periodic task-dakı ``bypass_rls`` scope-u ilə çağırılmalıdır (bütün tenant-lar).
    PENDING/PROCESSING işlərə toxunulmur (onları ``reap_stuck_extraction_jobs`` bağlayır).
    """
    from apps.exams.models import TextExtractionJob

    days = extraction_job_retention_days()
    if days <= 0:
        return 0
    cutoff = (now or timezone.now()) - timedelta(days=days)
    finished = TextExtractionJob.objects.filter(
        status__in=[TextExtractionJob.STATUS_SUCCESS, TextExtractionJob.STATUS_FAILED], created_at__lt=cutoff
    )
    return purge_in_batches(
        finished,
        batch_size=batch_size,
        time_budget=time_budget,
        scope=scope,
        before_delete=_delete_job_files,
        label="exams_textextractionjob",
    )


__all__ = [
    "DEFAULT_EXTRACTION_JOB_RETENTION_DAYS",
    "extraction_job_retention_days",
    "purge_expired_import_stashes",
    "purge_finished_extraction_jobs",
]
