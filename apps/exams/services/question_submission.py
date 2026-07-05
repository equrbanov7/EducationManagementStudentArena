"""
Müəllim → İmtahan mərkəzi sual göndərişi servisi.

Bütün axın burada mərkəzləşir: parse + xəbərdarlıq snapshot-u, göndərmə,
yenidən göndərmə, mərkəzin qəbul/rədd qərarları və hər iki tərəfə bildirişlər.
Qəbul zamanı suallar mövcud ``_save_bank_questions`` köməkçisi ilə banka
yazılır — sual bankı importu ilə eyni kod yolu (fingerprint, variantlar).
"""

import logging

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import pgettext

from apps.exams.models import QuestionBank, QuestionSubmission
from apps.exams.services.access_policy import is_exam_center_user

logger = logging.getLogger(__name__)

MIN_RAW_TEXT_LENGTH = 20


# ---------------------------------------------------------------------------
# Parse + snapshot
# ---------------------------------------------------------------------------
def analyze_submission_text(raw_text):
    """
    Göndəriş mətnini parse edib (parsed, counts) qaytarır.

    counts: {"questions": n, "errors": n, "warnings": n} — errors yalnız
    ``severity == "error"`` xəbərdarlıqlarıdır (müəllimə qırmızı görünənlər).
    """
    from apps.exams.services.parsing import parse_bulk_mcq

    parsed = parse_bulk_mcq(raw_text or "")
    error_count = 0
    warning_count = 0
    for question in parsed:
        for warning in question.get("warnings") or []:
            if (warning.get("severity") or "warning") == "error":
                error_count += 1
            else:
                warning_count += 1
    counts = {"questions": len(parsed), "errors": error_count, "warnings": warning_count}
    return parsed, counts


_SNAPSHOT_KEYS = ("q_no", "text", "options", "correct", "answer_mode", "warnings", "points")


def clean_snapshot_entries(parsed):
    """
    Workbench analizindən gələn sualları snapshot üçün təmizləyir: UI-yə xas
    ``meta`` annotasiyaları atılır, yalnız JSON-sabit açarlar saxlanır.
    """
    cleaned = []
    for question in parsed or []:
        entry = {key: question.get(key) for key in _SNAPSHOT_KEYS if question.get(key) is not None}
        entry.setdefault("warnings", question.get("warnings") or [])
        cleaned.append(entry)
    return cleaned


def _snapshot_counts(parsed):
    error_count = 0
    warning_count = 0
    for question in parsed:
        for warning in question.get("warnings") or []:
            if (warning.get("severity") or "warning") == "error":
                error_count += 1
            else:
                warning_count += 1
    return error_count, warning_count


def _apply_snapshot(submission, raw_text, *, parsed=None):
    """``parsed`` verilərsə (workbench-də seçilmiş alt-çoxluq) yenidən parse edilmir."""
    if parsed is None:
        parsed, _counts = analyze_submission_text(raw_text)
    parsed = clean_snapshot_entries(parsed)
    if not parsed:
        raise ValidationError(
            pgettext("exams.service.question_submission.error", "Mətndən heç bir sual çıxarıla bilmədi.")
        )
    error_count, warning_count = _snapshot_counts(parsed)
    submission.raw_text = raw_text
    submission.parsed_snapshot = parsed
    submission.question_count = len(parsed)
    submission.error_count = error_count
    submission.warning_count = warning_count
    return submission


# ---------------------------------------------------------------------------
# Müəllim tərəfi
# ---------------------------------------------------------------------------
@transaction.atomic
def submit_question_set(
    *, teacher, organization, title, subject, group_label, language, raw_text, student_group=None, parsed=None
):
    """Yeni göndəriş yaradır (pending) və mərkəz üzvlərinə bildiriş göndərir."""
    title = (title or "").strip()
    if not title:
        raise ValidationError(pgettext("exams.service.question_submission.error", "Mövzu/başlıq boş ola bilməz."))
    subject = (subject or "").strip()
    if not subject:
        raise ValidationError(pgettext("exams.service.question_submission.error", "Fənn qeyd olunmalıdır."))
    group_label = (group_label or "").strip()
    if not group_label:
        raise ValidationError(
            pgettext("exams.service.question_submission.error", "Hansı qrup üçün olduğu qeyd olunmalıdır.")
        )
    if len((raw_text or "").strip()) < MIN_RAW_TEXT_LENGTH:
        raise ValidationError(pgettext("exams.service.question_submission.error", "Sual mətni çox qısadır."))

    submission = QuestionSubmission(
        teacher=teacher,
        organization=organization,
        title=title,
        subject=subject,
        student_group=student_group,
        group_label=group_label,
        language=language,
    )
    _apply_snapshot(submission, raw_text, parsed=parsed)
    submission.save()
    _notify_exam_center_new_submission(submission, resubmitted=False)
    return submission


@transaction.atomic
def resubmit_question_set(
    submission,
    *,
    title=None,
    subject=None,
    group_label=None,
    language=None,
    raw_text=None,
    student_group=...,
    parsed=None,
):
    """
    Müəllim pending/rejected göndərişi düzəldib yenidən göndərir: snapshot
    yenilənir, status yenidən ``pending`` olur, köhnə qərar sahələri təmizlənir.
    """
    if not submission.can_be_edited_by_teacher:
        raise ValidationError(
            pgettext("exams.service.question_submission.error", "Bu göndəriş artıq yekunlaşıb — dəyişdirilə bilməz.")
        )

    was_rejected = submission.status == QuestionSubmission.STATUS_REJECTED
    if title is not None and title.strip():
        submission.title = title.strip()
    if subject is not None and subject.strip():
        submission.subject = subject.strip()
    if group_label is not None and group_label.strip():
        submission.group_label = group_label.strip()
    if student_group is not ...:
        submission.student_group = student_group
    if language:
        submission.language = language
    _apply_snapshot(submission, raw_text if raw_text is not None else submission.raw_text, parsed=parsed)

    submission.status = QuestionSubmission.STATUS_PENDING
    if was_rejected:
        submission.resubmission_count += 1
    submission.reviewer = None
    submission.reviewed_at = None
    # Rəyçi qeydini saxlamırıq — yeni versiya köhnə qərardan asılı deyil;
    # tarixçə lazım olsa audit log-dadır.
    submission.reviewer_note = ""
    submission.accepted_bank = None
    submission.save()
    _notify_exam_center_new_submission(submission, resubmitted=was_rejected)
    return submission


# ---------------------------------------------------------------------------
# İmtahan mərkəzi tərəfi
# ---------------------------------------------------------------------------
def ensure_can_review_submission(user, submission):
    if not is_exam_center_user(user):
        raise PermissionDenied(
            pgettext("exams.service.access.permission", "question_submission_review_exam_center_only")
        )


@transaction.atomic
def accept_submission(submission, *, reviewer, bank=None, new_bank_name="", note=""):
    """
    Göndərişi qəbul edir və snapshot-dakı sualları banka yazır.

    ``bank`` verilməyibsə ``new_bank_name`` ilə (təşkilat daxilində, paylaşılan)
    yeni bank yaradılır. Qaytarır: (bank, yazılmış sual sayı).
    """
    submission = QuestionSubmission.objects.select_for_update().get(pk=submission.pk)
    if not submission.is_pending:
        raise ValidationError(pgettext("exams.service.question_submission.error", "Bu göndərişə artıq baxılıb."))

    if bank is None:
        bank_name = (new_bank_name or "").strip() or submission.title
        bank = QuestionBank.objects.create(
            name=bank_name,
            subject=submission.subject or submission.title,
            language=submission.language,
            default_question_type="test",
            organization=submission.organization,
            created_by=reviewer,
            is_shared=True,
        )
    elif bank.organization_id != submission.organization_id:
        raise ValidationError(pgettext("exams.service.question_submission.error", "Bank başqa təşkilata aiddir."))

    from apps.exams.views.teacher.question_library._shared import _save_bank_questions

    parsed = list(submission.parsed_snapshot or [])
    # Müəllimin workbench-də təyin etdiyi ballar snapshot-da saxlanır — banka
    # eyni ballarla yazılır (boş/qeyri-müəyyən → 1).
    points_payload = {str(index): str(question.get("points") or "") for index, question in enumerate(parsed, start=1)}
    created_count = _save_bank_questions(
        bank=bank,
        parsed=parsed,
        selected=set(range(1, len(parsed) + 1)),
        language=submission.language,
        q_format="test",
        points_payload=points_payload,
        created_by=reviewer,
    )
    if created_count == 0:
        raise ValidationError(
            pgettext(
                "exams.service.question_submission.error",
                "Snapshot-dan heç bir sual banka yazıla bilmədi (A–D variantları natamamdır).",
            )
        )

    submission.status = QuestionSubmission.STATUS_ACCEPTED
    submission.reviewer = reviewer
    submission.reviewed_at = timezone.now()
    submission.reviewer_note = (note or "").strip()
    submission.accepted_bank = bank
    submission.save(update_fields=["status", "reviewer", "reviewed_at", "reviewer_note", "accepted_bank", "updated_at"])
    _notify_teacher_decision(submission)
    return bank, created_count


@transaction.atomic
def reject_submission(submission, *, reviewer, note=""):
    submission = QuestionSubmission.objects.select_for_update().get(pk=submission.pk)
    if not submission.is_pending:
        raise ValidationError(pgettext("exams.service.question_submission.error", "Bu göndərişə artıq baxılıb."))
    submission.status = QuestionSubmission.STATUS_REJECTED
    submission.reviewer = reviewer
    submission.reviewed_at = timezone.now()
    submission.reviewer_note = (note or "").strip()
    submission.save(update_fields=["status", "reviewer", "reviewed_at", "reviewer_note", "updated_at"])
    _notify_teacher_decision(submission)
    return submission


# ---------------------------------------------------------------------------
# Bildirişlər (xəta axını pozmur)
# ---------------------------------------------------------------------------
def _exam_center_members(organization):
    from apps.organizations.models import Membership

    return [
        membership.user
        for membership in Membership.objects.filter(
            organization=organization,
            role__name="exam_center",
            is_active=True,
        ).select_related("user")
    ]


def _notify_exam_center_new_submission(submission, *, resubmitted):
    try:
        from apps.notifications.public import create_notification

        teacher_display = submission.teacher.get_full_name() or submission.teacher.username
        if resubmitted:
            message = pgettext(
                "exams.notification.question_submission",
                '{teacher} "{title}" sual göndərişini düzəldib yenidən göndərdi ({subject} · {group}, {count} sual).',
            )
        else:
            message = pgettext(
                "exams.notification.question_submission",
                '{teacher} "{title}" adlı yeni sual göndərişi etdi ({subject} · {group}, {count} sual).',
            )
        link = reverse("exams:question_submission_review", kwargs={"submission_id": submission.id})
        for member in _exam_center_members(submission.organization):
            if member.pk == submission.teacher_id:
                continue
            create_notification(
                recipient=member,
                title=pgettext("exams.notification.question_submission", "Yeni sual göndərişi"),
                message=message.format(
                    teacher=teacher_display,
                    title=submission.title,
                    subject=submission.subject,
                    group=submission.group_label,
                    count=submission.question_count,
                ),
                link=link,
                notification_type="exam",
                metadata={"question_submission_id": submission.id},
                organization=submission.organization,
            )
    except Exception:
        logger.warning("Question submission notification (exam center) failed.", exc_info=True)


def _notify_teacher_decision(submission):
    try:
        from apps.notifications.public import create_notification

        if submission.status == QuestionSubmission.STATUS_ACCEPTED:
            message = pgettext(
                "exams.notification.question_submission",
                '"{title}" sual göndərişiniz qəbul edildi və sual bankına əlavə olundu.',
            )
        else:
            message = pgettext(
                "exams.notification.question_submission",
                '"{title}" sual göndərişiniz rədd edildi. Qeydə baxıb düzəldərək yenidən göndərə bilərsiniz.',
            )
        create_notification(
            recipient=submission.teacher,
            title=pgettext("exams.notification.question_submission", "Sual göndərişinə baxıldı"),
            message=message.format(title=submission.title),
            link=reverse("exams:question_submission_detail", kwargs={"submission_id": submission.id}),
            notification_type="exam",
            metadata={"question_submission_id": submission.id},
            organization=submission.organization,
        )
    except Exception:
        logger.warning("Question submission notification (teacher) failed.", exc_info=True)


__all__ = [
    "accept_submission",
    "analyze_submission_text",
    "clean_snapshot_entries",
    "ensure_can_review_submission",
    "reject_submission",
    "resubmit_question_set",
    "submit_question_set",
]
