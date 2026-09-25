"""Müəllimin baxışı: qəbul (bal) / qaytarma (rəy) / yoxlandı (ev tapşırığı) / rədd.

Sahibin qaydaları (2026-09-25):
  * sərbəst iş qəbul olunanda bal AVTOMATİK jurnala gedir; UI əvvəlcədən
    göstərir: «Bu bal jurnala düşəcək: Sərbəst iş 2 · 4/5 (cəmi 9/10)»
    (:func:`journal_preview`);
  * tələbənin artıq 10 balı varsa İKİNCİ bal yoxdur — cəm ≤ 10 (qeydiyyat üzrə
    BÜTÜN sərbəst işlər, bütün qovluqlar); slot başına bal ≤ slotun maksimumu;
  * bəyənilməyən iş rəylə QAYTARILIR — 0 yazılmır, tələbə yenidən göndərir;
  * ev tapşırığına bal verilmir — yalnız «yoxlanıldı».

Cəm qaydası: qeydiyyat üzrə advisory kilid (paralel iki qəbul eyni anda cəmi
keçə bilməsin) + 0003 miqrasiyasının PG trigger-i (servisdən kənar yazıya qarşı).
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from django.db import IntegrityError, transaction
from django.db.models import Sum
from django.utils import timezone
from django.utils.translation import pgettext

from ..constants import (
    MAX_FEEDBACK_CHARS,
    MIN_FEEDBACK_CHARS,
    POINTS_DECIMAL_PLACES,
    EventKind,
    JournalSyncStatus,
    RejectReason,
    SubmissionStatus,
    TaskKind,
)
from ..errors import FolderError, display_number
from ..models import Submission
from . import access, notify, syllabus_bridge
from .events import display_name, record_event
from .journal import journal_side_preview, schedule_journal_sync, slot_label
from .locks import advisory_lock

_STEP = Decimal(1).scaleb(-POINTS_DECIMAL_PLACES)


def parse_points(value) -> Decimal:
    try:
        points = Decimal(str(value).replace(",", ".").strip())
    except (InvalidOperation, AttributeError, ValueError) as exc:
        raise FolderError.of("review.points_invalid", max="—") from exc
    if not points.is_finite():
        raise FolderError.of("review.points_invalid", max="—")
    return points


def awarded_total(enrollment_id, *, exclude_pk=None) -> Decimal:
    """Qeydiyyatın bütün QƏBUL edilmiş sərbəst iş balları (bütün qovluqlar)."""
    rows = Submission.objects.filter(
        enrollment_id=enrollment_id, kind=TaskKind.SELFWORK, status=SubmissionStatus.ACCEPTED
    )
    if exclude_pk is not None:
        rows = rows.exclude(pk=exclude_pk)
    return rows.aggregate(total=Sum("points"))["total"] or Decimal("0")


def journal_preview(submission, points=None) -> dict:
    """Qəbuldan ƏVVƏL UI zolağı üçün hesab (yazı yoxdur).

    ``{"slot_index", "slot_label", "task_title", "points", "max_points", "total_before",
    "total_after", "max_total", "remaining", "can_award", "error": dict|None, "text",
    "journal": dict|None}`` — ``journal`` registrar ``selfwork_points.preview`` nəticəsidir
    (məs. ``{"blocked": True, "reason": "Jurnal bağlıdır"}``), hook yoxdursa ``None``.
    """
    task = submission.task
    max_total = Decimal(syllabus_bridge.selfwork_total())
    before = awarded_total(submission.enrollment_id, exclude_pk=submission.pk)
    remaining = max(Decimal("0"), max_total - before)
    error = None
    value = None
    if points is not None:
        try:
            value = parse_points(points)
            _validate_points(task, value, before, max_total)
        except FolderError as exc:
            error = exc.as_dict()
    after = before + (value if value is not None and error is None else Decimal("0"))
    label = slot_label(task.slot_index) if task.slot_index else task.title
    text = ""
    if value is not None and error is None:
        text = pgettext(
            "subject_folder.review",
            "Bu bal jurnala düşəcək: %(slot)s · %(points)s/%(max)s (cəmi %(total)s/%(max_total)s)",
        ) % {
            "slot": label,
            "points": display_number(value),
            "max": display_number(task.max_points),
            "total": display_number(after),
            "max_total": display_number(max_total),
        }
    return {
        "slot_index": task.slot_index,
        "slot_label": label,
        "task_title": task.title,
        "points": value,
        "max_points": task.max_points,
        "total_before": before,
        "total_after": after,
        "max_total": max_total,
        "remaining": min(remaining, task.max_points or remaining),
        "can_award": error is None and remaining > 0,
        "error": error,
        "text": text,
        # Registrar tərəfinin baxışı (kilid/mövcud bal) — hook yoxdursa None.
        "journal": journal_side_preview(submission, value) if task.slot_index else None,
    }


def _validate_points(task, points, before, max_total) -> None:
    if points <= 0 or points > task.max_points or points != points.quantize(_STEP):
        raise FolderError.of("review.points_invalid", max=task.max_points)
    if before + points > max_total:
        raise FolderError.of(
            "review.points_total_exceeded",
            max_total=max_total,
            already=before,
            remaining=max(Decimal("0"), max_total - before),
        )


def _clean_feedback(feedback, *, required: bool) -> str:
    text = str(feedback or "").strip()
    if required and len(text) < MIN_FEEDBACK_CHARS:
        raise FolderError.of("review.feedback_required", min=MIN_FEEDBACK_CHARS)
    if len(text) > MAX_FEEDBACK_CHARS:
        raise FolderError.of("text.too_long", max=MAX_FEEDBACK_CHARS)
    return text


def _lock_for_review(submission, by_user) -> Submission:
    """İcazə + cari sətrin kilidli oxunuşu; yalnız ``submitted`` baxılır."""
    access.ensure_can_review(by_user, submission.assignment)
    # ``of=("self",)``: select_related JOIN-dəki registrar sətirləri (Enrollment, CourseOffering)
    # və tələbənin User sətri KİLİDLƏNMƏSİN — PG ``FOR UPDATE`` default olaraq bütün JOIN cədvəllərini kilidləyir.
    locked = (
        Submission.objects.select_for_update(of=("self",))
        .select_related("task", "assignment", "assignment__offering", "enrollment", "student")
        .get(pk=submission.pk)
    )
    if locked.status != SubmissionStatus.SUBMITTED or not locked.is_current:
        raise FolderError.of("submission.not_reviewable")
    return locked


def _stamp(row, by_user, feedback) -> None:
    row.reviewed_by = by_user
    row.reviewer_name = display_name(by_user)
    row.reviewed_at = timezone.now()
    row.feedback = feedback


def _accept(submission, *, by_user, points, feedback, request) -> Submission:
    row = _lock_for_review(submission, by_user)
    if row.kind != TaskKind.SELFWORK:
        raise FolderError.of("review.homework_has_no_points")
    value = parse_points(points)
    # Qeydiyyat üzrə kilid: iki paralel qəbul eyni anda «cəmi 10»-u keçə bilməz.
    advisory_lock("sf", "selfwork_total", row.enrollment_id)
    # «İkinci bal yoxdur»: eyni açılışda eyni slot üçün (arxivlənmiş köhnə slot tapşırığı daxil) bir qəbul.
    if Submission.objects.filter(
        enrollment_id=row.enrollment_id,
        kind=TaskKind.SELFWORK,
        status=SubmissionStatus.ACCEPTED,
        assignment__offering_id=row.assignment.offering_id,
        task__slot_index=row.task.slot_index,
    ).exists():
        raise FolderError.of("review.already_awarded")
    max_total = Decimal(syllabus_bridge.selfwork_total())
    before = awarded_total(row.enrollment_id, exclude_pk=row.pk)
    _validate_points(row.task, value, before, max_total)
    _stamp(row, by_user, _clean_feedback(feedback, required=False))
    row.status = SubmissionStatus.ACCEPTED
    row.points = value
    row.points_max = row.task.max_points
    row.journal_sync_status = JournalSyncStatus.PENDING
    row.journal_sync_message = ""
    try:
        with transaction.atomic():
            row.save()
    except IntegrityError as exc:  # DB qatı (bir yekun / cəm ≤ 10 trigger-i) paralel yazını tutdu
        raise FolderError.of("submission.concurrent") from exc
    record_event(
        row,
        EventKind.ACCEPTED,
        actor=by_user,
        payload={"points": value, "max": row.points_max, "total": before + value},
        request=request,
    )
    schedule_journal_sync(row)
    return row


def _return(submission, *, by_user, feedback, request) -> Submission:
    row = _lock_for_review(submission, by_user)
    _stamp(row, by_user, _clean_feedback(feedback, required=True))
    row.status = SubmissionStatus.RETURNED  # bal YAZILMIR («0 düşmür»)
    row.save()
    record_event(row, EventKind.RETURNED, actor=by_user, payload={"feedback": row.feedback[:500]}, request=request)
    return row


def _check(submission, *, by_user, feedback, request) -> Submission:
    row = _lock_for_review(submission, by_user)
    if row.kind != TaskKind.HOMEWORK:
        raise FolderError.of("review.selfwork_needs_points")
    _stamp(row, by_user, _clean_feedback(feedback, required=False))
    row.status = SubmissionStatus.CHECKED
    row.save()
    record_event(row, EventKind.CHECKED, actor=by_user, request=request)
    return row


def _reject(submission, *, by_user, reason, feedback, request) -> Submission:
    row = _lock_for_review(submission, by_user)
    if reason not in RejectReason.values:
        raise FolderError.of("review.reason_invalid")
    _stamp(row, by_user, _clean_feedback(feedback, required=True))
    row.status = SubmissionStatus.REJECTED
    row.reject_reason = reason
    row.save()
    record_event(
        row,
        EventKind.REJECTED,
        actor=by_user,
        payload={"reason": reason, "feedback": row.feedback[:500]},
        request=request,
    )
    return row


def _finish(row):
    notify.review_outcomes([row])
    return row


@transaction.atomic
def accept(submission, *, by_user, points, feedback: str = "", request=None) -> Submission:
    """Sərbəst işi balla qəbul edir; commit-dən sonra bal jurnala ötürülür."""
    return _finish(_accept(submission, by_user=by_user, points=points, feedback=feedback, request=request))


@transaction.atomic
def return_for_revision(submission, *, by_user, feedback, request=None) -> Submission:
    """Rəylə qaytarır (rəy MƏCBURİDİR, bal yazılmır) — tələbə yeni cəhd göndərir."""
    return _finish(_return(submission, by_user=by_user, feedback=feedback, request=request))


@transaction.atomic
def check_homework(submission, *, by_user, feedback: str = "", request=None) -> Submission:
    """Ev tapşırığını «yoxlanıldı» qeyd edir (bal yoxdur)."""
    return _finish(_check(submission, by_user=by_user, feedback=feedback, request=request))


@transaction.atomic
def reject(submission, *, by_user, reason: str, feedback: str, request=None) -> Submission:
    """Yekun rədd (səbəb + rəy MƏCBURİDİR, bal yazılmır)."""
    return _finish(_reject(submission, by_user=by_user, reason=reason, feedback=feedback, request=request))


@transaction.atomic
def reopen(submission, *, by_user, feedback: str = "", request=None) -> Submission:
    """Rəddi ləğv edir → ``returned`` (tələbə yenidən göndərə bilər)."""
    access.ensure_can_review(by_user, submission.assignment)
    row = Submission.objects.select_for_update().get(pk=submission.pk)
    if row.status != SubmissionStatus.REJECTED:
        raise FolderError.of("review.not_rejected")
    _stamp(row, by_user, _clean_feedback(feedback, required=False) or row.feedback)
    row.status = SubmissionStatus.RETURNED
    row.reject_reason = ""
    row.save()
    record_event(row, EventKind.REOPENED, actor=by_user, request=request)
    return _finish(row)


BULK_ACTIONS = ("accept", "return", "check", "reject")


def bulk_review(submissions, *, by_user, action: str, points=None, feedback: str = "", reason: str = "", request=None):
    """Toplu baxış — HƏR göndəriş ayrıca savepoint-də (birinin xətası digərlərini dayandırmır).

    ``points`` — ``{submission_id: bal}`` və ya hamıya eyni bal. Nəticə:
    ``{"ok": [id…], "failed": {id: {"code","message","params"}}}``; bildirişlər qrup üzrə TOPLU gedir.
    """
    if action not in BULK_ACTIONS:
        raise FolderError.of("permission.denied")
    done, failed = [], {}
    # Sabit kilid ardıcıllığı (qeydiyyat → göndəriş): iki paralel toplu baxış bir-birini deadlock-a salmasın.
    for submission in sorted(submissions, key=lambda row: (str(row.enrollment_id), str(row.pk))):
        key = str(submission.pk)
        try:
            with transaction.atomic():
                if action == "accept":
                    value = points.get(key, points.get(submission.pk)) if isinstance(points, dict) else points
                    row = _accept(submission, by_user=by_user, points=value, feedback=feedback, request=request)
                elif action == "return":
                    row = _return(submission, by_user=by_user, feedback=feedback, request=request)
                elif action == "check":
                    row = _check(submission, by_user=by_user, feedback=feedback, request=request)
                else:
                    row = _reject(submission, by_user=by_user, reason=reason, feedback=feedback, request=request)
            done.append(row)
        except FolderError as exc:
            failed[key] = exc.as_dict()
    notify.review_outcomes(done)
    return {"ok": [str(row.pk) for row in done], "failed": failed}


__all__ = [
    "BULK_ACTIONS",
    "accept",
    "awarded_total",
    "bulk_review",
    "check_homework",
    "journal_preview",
    "parse_points",
    "reject",
    "reopen",
    "return_for_revision",
]
