"""Tələbənin göndərişi: qaralama, göndərmə, qaytarılandan sonra YENİ cəhd.

Zəncir qaydası (bir tapşırıq × bir qeydiyyat):
  * cari cəhd yoxdur → 1-ci cəhd;
  * cari cəhd qaralamadır → həmin sətir tamamlanır;
  * cari cəhd yoxlanılır (``submitted``) → ``submission.pending``;
  * cari cəhd qaytarılıb (``returned``) → köhnə sətir tarixçəyə keçir
    (``is_current=False``), ``attempt_no + 1`` ilə yeni sətir; son tarix keçsə də
    icazəlidir (müəllim özü qaytarıb), amma ``is_late`` qeyd olunur;
  * yekun (qəbul/yoxlama/rədd) → ``submission.closed``.

YARIŞ YOXDUR: cəhd nömrəsi «count + 1» ilə hesablanmır — zəncir advisory kilidlə
serializasiya olunur, cari sətir ``select_for_update`` ilə oxunur; DB-də
``(task, enrollment, attempt_no)`` və «bir cari cəhd» UNİKALDIR (son qat).
Fayllar əvvəlcə HAMISI yoxlanır, sonra yazılır — pis 3-cü fayl yarımçıq
göndəriş qoymur.
"""

from __future__ import annotations

import hashlib

from django.db import IntegrityError, transaction
from django.utils import timezone

from ..constants import (
    FINAL_STATUSES,
    MAX_TEXT_ANSWER_CHARS,
    SUBMISSION_EXTENSIONS,
    SUBMISSION_MAX_MB_CAP,
    EventKind,
    FolderStatus,
    JournalSyncStatus,
    PlagiarismStatus,
    SubmissionStatus,
    TaskKind,
)
from ..errors import FolderError
from ..models import Submission, SubmissionFile
from . import lookups, notify
from .assignments import WINDOW_CLOSED, WINDOW_LATE, WINDOW_NOT_OPEN, deadline_for, window_state
from .events import record_event
from .locks import advisory_lock
from .plagiarism.dispatch import schedule_similarity_check
from .plagiarism.normalize import normalize_text
from .uploads import prepare_upload


def resolve_enrollment(task, assignment, student):
    """Göndərişin bütün ön şərtləri; uğurda tələbənin AKTİV qeydiyyatı."""
    if task.folder_id != assignment.folder_id:
        raise FolderError.of("task.not_in_folder")
    if not assignment.is_active:
        raise FolderError.of("assignment.inactive")
    if assignment.folder.status != FolderStatus.ACTIVE:
        raise FolderError.of("folder.not_active")
    if task.is_archived:
        raise FolderError.of("task.archived")
    if not task.is_published:
        raise FolderError.of("task.not_published")
    if task.kind == TaskKind.SELFWORK and not assignment.grades_selfwork:
        raise FolderError.of("assignment.selfwork_elsewhere")
    enrollment = lookups.active_enrollment(assignment.offering_id, student)
    if enrollment is None:
        raise FolderError.of("audience.not_enrolled")
    return enrollment


def _allowed_extensions(task) -> set:
    chosen = {str(ext).lower() for ext in (task.allowed_extensions or [])}
    return (chosen & SUBMISSION_EXTENSIONS) or set(SUBMISSION_EXTENSIONS)


def _prepare_files(task, files, *, existing: int) -> list:
    files = [item for item in (files or []) if item is not None]
    if files and not task.allow_files:
        raise FolderError.of("submission.files_not_allowed")
    if existing + len(files) > task.max_files:
        raise FolderError.of("submission.too_many_files", max=task.max_files)
    limit = min(int(task.max_file_mb or 1), SUBMISSION_MAX_MB_CAP)
    allowed = _allowed_extensions(task)
    return [(uploaded, prepare_upload(uploaded, allowed_extensions=allowed, max_mb=limit)) for uploaded in files]


def _clean_answer(task, text):
    if text is None:
        return None
    value = str(text)
    if value.strip() and not task.allow_text_answer:
        raise FolderError.of("submission.text_not_allowed")
    if len(value) > MAX_TEXT_ANSWER_CHARS:
        raise FolderError.of("text.too_long", max=MAX_TEXT_ANSWER_CHARS)
    return value


def _window(task, assignment, *, resubmission: bool) -> bool:
    """Pəncərəni yoxlayır → ``is_late``. Qaytarılmış işin yeni cəhdi son tarixdən sonra da açıqdır."""
    state = window_state(deadline_for(assignment, task))["state"]
    if state == WINDOW_NOT_OPEN:
        raise FolderError.of("deadline.not_open")
    if state == WINDOW_CLOSED and not resubmission:
        raise FolderError.of("deadline.passed")
    return state in (WINDOW_LATE, WINDOW_CLOSED)


def _locked_chain(task, enrollment):
    advisory_lock("sf", "chain", task.pk, enrollment.pk)
    return Submission.objects.select_for_update().filter(task=task, enrollment=enrollment, is_current=True).first()


def _open_attempt(task, assignment, enrollment, student):
    """``(sətir, yeni_mi, qaytarılmış_əvvəlki)`` — qaralama təkrar istifadə olunur."""
    current = _locked_chain(task, enrollment)
    if current is None:
        return None, 1, None
    if current.status == SubmissionStatus.DRAFT:
        return current, current.attempt_no, None
    if current.status == SubmissionStatus.SUBMITTED:
        raise FolderError.of("submission.pending")
    if current.status in FINAL_STATUSES:
        raise FolderError.of("submission.closed")
    return None, current.attempt_no + 1, current  # RETURNED


def _new_row(task, assignment, enrollment, student, attempt_no, previous, status) -> Submission:
    if previous is not None:
        previous.is_current = False
        previous.save(update_fields=["is_current", "updated_at"])
    return Submission.objects.create(
        organization_id=task.organization_id,
        task=task,
        assignment=assignment,
        enrollment=enrollment,
        student=student,
        kind=task.kind,
        attempt_no=attempt_no,
        is_current=True,
        status=status,
    )


def _store_files(submission, prepared, uploaded_by) -> list:
    rows = []
    for uploaded, meta in prepared:
        row = SubmissionFile(
            organization_id=submission.organization_id,
            submission=submission,
            original_name=meta["original_name"],
            size=meta["size"],
            content_type=meta["content_type"],
            sha256=meta["sha256"],
            uploaded_by=uploaded_by,
        )
        row.file = uploaded
        row.save()
        rows.append(row)
    return rows


def content_hash(text_answer: str, file_hashes) -> str:
    """Normallaşdırılmış mətn + sıralanmış fayl heşləri → SHA-256 (eyni işin sürətli tanınması)."""
    payload = normalize_text(text_answer) + "\n" + "\n".join(sorted(file_hashes))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _guarded(callable_):
    try:
        with transaction.atomic():
            return callable_()
    except IntegrityError as exc:  # iki paralel göndəriş — kilidə baxmayaraq son qat işə düşdü
        raise FolderError.of("submission.concurrent") from exc


def save_draft(*, task, assignment, student, text=None, files=(), request=None) -> Submission:
    """Qaralama: mətn (verilibsə) əvəzlənir, fayllar ƏLAVƏ olunur. Müəllim görmür."""
    enrollment = resolve_enrollment(task, assignment, student)
    answer = _clean_answer(task, text)

    def _do():
        row, attempt_no, previous = _open_attempt(task, assignment, enrollment, student)
        _window(task, assignment, resubmission=previous is not None or attempt_no > 1)
        existing = row.files.count() if row is not None else 0
        prepared = _prepare_files(task, files, existing=existing)
        if row is None:
            row = _new_row(task, assignment, enrollment, student, attempt_no, previous, SubmissionStatus.DRAFT)
        if answer is not None:
            row.text_answer = answer
            row.save(update_fields=["text_answer", "updated_at"])
        stored = _store_files(row, prepared, student)
        record_event(
            row, EventKind.DRAFT_SAVED, actor=student, payload={"files": len(stored)}, request=request, audit=False
        )
        return row

    return _guarded(_do)


def submit(*, task, assignment, student, text=None, files=(), request=None) -> Submission:
    """Göndərir (qaralama varsa onu tamamlayır). Commit-dən sonra: plagiat yoxlaması + müəllimə xülasə."""
    enrollment = resolve_enrollment(task, assignment, student)
    answer = _clean_answer(task, text)

    def _do():
        row, attempt_no, previous = _open_attempt(task, assignment, enrollment, student)
        is_late = _window(task, assignment, resubmission=previous is not None or attempt_no > 1)
        existing = row.files.count() if row is not None else 0
        prepared = _prepare_files(task, files, existing=existing)
        if row is None:
            row = _new_row(task, assignment, enrollment, student, attempt_no, previous, SubmissionStatus.DRAFT)
        if answer is not None:
            row.text_answer = answer
        _store_files(row, prepared, student)
        hashes = list(row.files.values_list("sha256", flat=True))
        if not row.text_answer.strip() and not hashes:
            raise FolderError.of("submission.empty")
        row.status = SubmissionStatus.SUBMITTED
        row.submitted_at = timezone.now()
        row.is_late = is_late
        row.content_sha256 = content_hash(row.text_answer, hashes)
        row.plagiarism_status = PlagiarismStatus.PENDING
        row.journal_sync_status = JournalSyncStatus.NONE
        row.teacher_notified_at = None
        row.save()
        kind = EventKind.RESUBMITTED if row.attempt_no > 1 else EventKind.SUBMITTED
        record_event(
            row,
            kind,
            actor=student,
            payload={"attempt": row.attempt_no, "files": len(hashes), "late": is_late},
            request=request,
        )
        schedule_similarity_check(row)
        notify.submission_received(row)
        return row

    return _guarded(_do)


def remove_draft_file(file_row, *, student, request=None) -> None:
    """Qaralamadakı faylı silir (göndərilmiş işin faylı dəyişdirilmir)."""
    submission = file_row.submission
    if submission.student_id != getattr(student, "pk", None):
        raise FolderError.of("permission.denied")
    if submission.status != SubmissionStatus.DRAFT:
        raise FolderError.of("submission.not_draft")
    name = file_row.original_name
    storage_file = file_row.file
    with transaction.atomic():
        file_row.delete()
        record_event(
            submission, EventKind.FILE_REMOVED, actor=student, payload={"file": name}, request=request, audit=False
        )
    try:
        storage_file.delete(save=False)
    except Exception:  # pragma: no cover — saxlama yeri əlçatmazdırsa sətir onsuz da silinib
        pass


__all__ = ["content_hash", "remove_draft_file", "resolve_enrollment", "save_draft", "submit"]
