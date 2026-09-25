"""Sərbəst iş balının JURNALA körpüsü — registrar tərəfi OPSİONAL hook-dur.

Asılılıq istiqaməti: bu app registrar-ı STATİK idxal etmir (AST gate-ləri üçün
kənar yaranmır, registrar isə bu app-ı heç vaxt idxal etmir). Hook dinamik
tapılır::

    apps.registrar.public_services.selfwork_points.record_points(
        *, offering, enrollment, slot_index, slot_title, max_points, points, source_ref, by_user,
    ) -> (ok: bool, message: str)

``selfwork_points`` modul (kanonik forma) və ya ``record_points`` atributu olan
obyekt ola bilər; birbaşa çağırıla bilən funksiya da qəbul olunur.

Nəticənin göndərişə yazılması:
  * hook YOXDUR (registrar tərəfi hələ yazılmayıb) → ``pending`` + izah;
  * hook istisna atdı (müvəqqəti xəta) → ``pending`` — ``subject_folder_sync_journal``
    əmri / dövri tapşırıq yenidən cəhd edir;
  * hook ``(False, mesaj)`` qaytardı (jurnal bağlıdır və s.) → ``blocked`` + mesaj;
  * hook ``(True, mesaj)`` → ``synced``.

SEMANTİKA — SET, ARTIRMA DEYİL: eyni ``(enrollment, slot_index)`` üçün təkrar
çağırış balı YENİDƏN YAZIR (idempotent). ``source_ref`` =
``"subject_folder.submission:<uuid>"`` — registrar mənbəni audit/izləmə üçün saxlayır.
"""

from __future__ import annotations

import importlib
import logging

from django.db import transaction
from django.utils import timezone
from django.utils.translation import pgettext

from ..constants import EventKind, JournalSyncStatus, SubmissionStatus, TaskKind
from ..models import Submission
from .events import record_event

logger = logging.getLogger(__name__)

_CTX = "subject_folder.journal"
HOOK_MODULES = ("apps.registrar.public_services", "apps.registrar.public")
HOOK_ATTRIBUTE = "selfwork_points"
HOOK_FUNCTION = "record_points"
SOURCE_PREFIX = "subject_folder.submission:"


def resolve_journal_hook():
    """Registrar hook-u (çağırıla bilən) və ya ``None`` — import xətası «hook yoxdur» sayılır."""
    for module_path in HOOK_MODULES:
        try:
            module = importlib.import_module(module_path)
        except Exception:  # pragma: no cover — registrar yarımçıq redaktədədirsə
            logger.warning("subject_folder: %s import edilmədi, jurnal hook-u yoxdur", module_path)
            continue
        target = getattr(module, HOOK_ATTRIBUTE, None)
        if target is None:
            continue
        func = getattr(target, HOOK_FUNCTION, None)
        if callable(func):
            return func
        if callable(target):
            return target
    return None


def resolve_preview_hook():
    """OPSİONAL: ``selfwork_points.preview(*, offering, enrollment, slot_index, points) -> dict`` və ya ``None``."""
    for module_path in HOOK_MODULES:
        try:
            module = importlib.import_module(module_path)
        except Exception:  # pragma: no cover
            continue
        func = getattr(getattr(module, HOOK_ATTRIBUTE, None), "preview", None)
        if callable(func):
            return func
    return None


def journal_side_preview(submission, points) -> dict | None:
    """Jurnal tərəfinin baxış məlumatı (kilid, mövcud bal) — hook yoxdursa/xəta verirsə ``None``.

    Heç vaxt istisna atmır: bu, baxış zolağının ƏLAVƏ məlumatıdır, qəbulu bloklamır.
    """
    func = resolve_preview_hook()
    if func is None:
        return None
    try:
        with transaction.atomic():
            result = func(
                offering=submission.assignment.offering,
                enrollment=submission.enrollment,
                slot_index=submission.task.slot_index,
                points=points,
            )
    except Exception:  # pragma: no cover — jurnal tərəfi yarımçıqdırsa
        logger.warning("subject_folder: jurnal preview hook-u xəta verdi (%s)", submission.pk, exc_info=True)
        return None
    return result if isinstance(result, dict) else None


def source_ref(submission) -> str:
    return f"{SOURCE_PREFIX}{submission.pk}"


def slot_label(slot_index) -> str:
    return pgettext(_CTX, "Sərbəst iş %(n)s") % {"n": slot_index}


def _normalize_result(result) -> tuple[bool, str]:
    if isinstance(result, tuple) and len(result) >= 1:
        return bool(result[0]), str(result[1] if len(result) > 1 else "")[:500]
    return bool(result), ""


def _apply(submission, status, message, *, synced: bool = False) -> None:
    submission.journal_sync_status = status
    submission.journal_sync_message = (message or "")[:500]
    submission.journal_sync_attempts = (submission.journal_sync_attempts or 0) + 1
    fields = ["journal_sync_status", "journal_sync_message", "journal_sync_attempts", "updated_at"]
    if synced:
        submission.journal_synced_at = timezone.now()
        fields.append("journal_synced_at")
    submission.save(update_fields=fields)


def is_syncable(submission) -> bool:
    return submission.kind == TaskKind.SELFWORK and submission.status == SubmissionStatus.ACCEPTED


def sync_submission_to_journal(submission, *, hook=None) -> dict:
    """Qəbul edilmiş sərbəst iş balını jurnala ötürür → ``{"status", "message"}``.

    Qəbul edilməmiş/ev tapşırığı üçün heç nə etmir (``status="none"``).
    Artıq ``synced`` olan göndəriş yenidən göndərilmir.
    """
    if not is_syncable(submission):
        return {"status": JournalSyncStatus.NONE.value, "message": ""}
    if submission.journal_sync_status == JournalSyncStatus.SYNCED:
        return {"status": JournalSyncStatus.SYNCED.value, "message": submission.journal_sync_message}
    hook = hook or resolve_journal_hook()
    if hook is None:
        message = pgettext(_CTX, "Jurnal inteqrasiyası hələ aktiv deyil — bal növbədədir.")
        with transaction.atomic():
            _apply(submission, JournalSyncStatus.PENDING, message)
        return {"status": JournalSyncStatus.PENDING.value, "message": message}
    task = submission.task
    assignment = submission.assignment
    try:
        # Hook öz tranzaksiyasında işləyir: jurnal yazısı sınsa da bizim göndəriş yazımız qalır.
        with transaction.atomic():
            result = hook(
                offering=assignment.offering,
                enrollment=submission.enrollment,
                slot_index=task.slot_index,
                slot_title=task.title or slot_label(task.slot_index),
                max_points=task.max_points,
                points=submission.points,
                source_ref=source_ref(submission),
                by_user=submission.reviewed_by,
            )
    except Exception as exc:  # müvəqqəti xəta — yenidən cəhd ediləcək
        logger.exception("subject_folder: jurnal hook-u xəta verdi (submission=%s)", submission.pk)
        message = pgettext(_CTX, "Jurnala ötürmə alınmadı, yenidən cəhd ediləcək: %(error)s") % {
            "error": exc.__class__.__name__
        }
        with transaction.atomic():
            _apply(submission, JournalSyncStatus.PENDING, message)
            record_event(submission, EventKind.JOURNAL_PENDING, payload={"message": message}, audit=False)
        return {"status": JournalSyncStatus.PENDING.value, "message": message}
    ok, message = _normalize_result(result)
    with transaction.atomic():
        if ok:
            _apply(submission, JournalSyncStatus.SYNCED, message, synced=True)
            record_event(
                submission,
                EventKind.JOURNAL_SYNCED,
                payload={"points": submission.points, "slot": task.slot_index, "message": message},
            )
            return {"status": JournalSyncStatus.SYNCED.value, "message": message}
        blocked = message or pgettext(_CTX, "Jurnal balı qəbul etmədi.")
        _apply(submission, JournalSyncStatus.BLOCKED, blocked)
        record_event(submission, EventKind.JOURNAL_BLOCKED, payload={"message": blocked})
    return {"status": JournalSyncStatus.BLOCKED.value, "message": blocked}


def sync_submission_by_id(submission_id) -> dict:
    """Commit-dən sonra çağırılan forma (təzə sətir oxunur)."""
    submission = (
        Submission.objects.filter(pk=submission_id)
        .select_related("task", "assignment__offering", "enrollment", "reviewed_by")
        .first()
    )
    if submission is None:
        return {"status": JournalSyncStatus.NONE.value, "message": ""}
    return sync_submission_to_journal(submission)


def schedule_journal_sync(submission) -> None:
    """Qəbuldan dərhal sonra (commit-də) jurnala ötürmə; xəta baxış əməliyyatını geri qaytarmır."""
    submission_id = submission.pk

    def _run():
        try:
            sync_submission_by_id(submission_id)
        except Exception:  # pragma: no cover — növbəti yenidən cəhd tutacaq
            logger.exception("subject_folder: commit-sonrası jurnal sinxronu alınmadı (%s)", submission_id)

    transaction.on_commit(_run)


def retry_pending(*, organization_id=None, include_blocked: bool = False, limit: int = 500, apply: bool = True) -> dict:
    """``pending`` (istəyə görə ``blocked``) qəbul edilmiş balları yenidən ötürür.

    ``apply=False`` — yalnız say (dry-run). Nəticə: ``{"candidates", "synced", "pending", "blocked"}``.
    """
    statuses = [JournalSyncStatus.PENDING]
    if include_blocked:
        statuses.append(JournalSyncStatus.BLOCKED)
    rows = Submission.objects.filter(
        kind=TaskKind.SELFWORK, status=SubmissionStatus.ACCEPTED, journal_sync_status__in=statuses
    ).select_related("task", "assignment__offering", "enrollment", "reviewed_by")
    if organization_id is not None:
        rows = rows.filter(organization_id=organization_id)
    rows = list(rows.order_by("reviewed_at")[: max(1, int(limit))])
    summary = {"candidates": len(rows), "synced": 0, "pending": 0, "blocked": 0}
    if not apply:
        return summary
    hook = resolve_journal_hook()
    for submission in rows:
        if submission.journal_sync_status == JournalSyncStatus.BLOCKED:
            # Yenidən cəhd üçün blok vəziyyəti SIFIRLANIR (əks halda «synced deyil» qısa yolu işləmir).
            submission.journal_sync_status = JournalSyncStatus.PENDING
        result = sync_submission_to_journal(submission, hook=hook)
        summary[result["status"]] = summary.get(result["status"], 0) + 1
    return summary


__all__ = [
    "journal_side_preview",
    "resolve_preview_hook",
    "HOOK_ATTRIBUTE",
    "HOOK_FUNCTION",
    "HOOK_MODULES",
    "SOURCE_PREFIX",
    "is_syncable",
    "resolve_journal_hook",
    "retry_pending",
    "schedule_journal_sync",
    "slot_label",
    "source_ref",
    "sync_submission_by_id",
    "sync_submission_to_journal",
]
