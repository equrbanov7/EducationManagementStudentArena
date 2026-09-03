"""
Müəllim → KAFEDRA MÜDİRİ → İmtahan Mərkəzi sual göndərişi servisi.

Sahibin qərarı (2026-09): göndəriş mərkəzə BİRBAŞA getmir — əvvəlcə kafedra
müdiri təsdiqləyir.  Kafedra mərhələsi (marşrut, qərarlar, hadisə lentı)
``question_chair_review.py``-dadır; bu modul müəllim tərəfini (parse +
snapshot, göndərmə/yenidən göndərmə) və MƏRKƏZ mərhələsini daşıyır.

Mərkəz qapısı FAIL-CLOSED-dur: kafedra təsdiqindən keçməmiş göndərişə mərkəz
nə baxa, nə də qərar verə bilər (``ensure_can_review_submission``).
Qəbul zamanı suallar mövcud ``_save_bank_questions`` köməkçisi ilə banka
yazılır — sual bankı importu ilə eyni kod yolu (fingerprint, variantlar).
"""

import logging

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import pgettext

from apps.exams.models import QuestionBank, QuestionSubmission, QuestionSubmissionEvent
from apps.exams.services.access_policy import is_exam_center_user
from apps.exams.services.question_chair_review import (
    MIN_REASON_LENGTH,
    record_event,
    route_submission_to_chair,
)

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
    error_count, warning_count = _snapshot_counts(parsed)
    counts = {"questions": len(parsed), "errors": error_count, "warnings": warning_count}
    return parsed, counts


_SNAPSHOT_KEYS = (
    "q_no",
    "text",
    "options",
    "correct",
    "answer_mode",
    "warnings",
    "points",
    "source_index",
)


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
    """
    SUAL-səviyyəli saylar: "Xətalı" = ən azı bir ERROR xəbərdarlığı olan sual
    sayı; "Xəbərdarlıq" = error olmayan xəbərdarlığı olan sual sayı. Sual
    idarəetmə səhifəsi ilə eyni semantika (491 sualda "509 xəta" çaşqınlığı
    yaranmasın).
    """
    error_count = 0
    warning_count = 0
    for question in parsed:
        severities = {(w.get("severity") or "warning") for w in (question.get("warnings") or [])}
        if "error" in severities:
            error_count += 1
        if severities - {"error"}:
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
    *,
    teacher,
    organization,
    title,
    subject,
    group_label,
    language,
    raw_text,
    student_group=None,
    subject_ref=None,
    exam_kind="",
    groups=None,
    parsed=None,
    teacher_note="",
    import_token="",
):
    """Yeni göndəriş yaradır və KAFEDRA MÜDİRİNƏ yönləndirir (mərkəzə yox)."""
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
        subject_ref=subject_ref,
        exam_kind=(exam_kind or "").strip().lower(),
        student_group=student_group,
        group_label=group_label,
        language=language,
        teacher_note=(teacher_note or "").strip(),
        import_token=(import_token or "").strip(),
    )
    submission.status = QuestionSubmission.STATUS_DRAFT
    _apply_snapshot(submission, raw_text, parsed=parsed)
    submission.save()
    if groups:
        submission.student_groups.set(groups)
    route_submission_to_chair(
        submission,
        actor=teacher,
        resubmitted=False,
        groups=list(groups) if groups else ([student_group] if student_group else []),
    )
    return submission


@transaction.atomic
def resubmit_question_set(
    submission,
    *,
    title=None,
    subject=None,
    subject_ref=...,
    exam_kind=None,
    group_label=None,
    language=None,
    raw_text=None,
    student_group=...,
    groups=None,
    parsed=None,
    teacher_note=None,
    import_token=None,
):
    """
    Müəllim düzəldib YENİDƏN göndərir — həmişə KAFEDRAYA (mərkəzə deyil).

    Snapshot yenilənir, köhnə kafedra/mərkəz qərar sahələri təmizlənir, status
    yenidən ``submitted_to_chair`` olur.  Müəllim kafedra mərhələsini ATLAYA
    BİLMİR: ``route_submission_to_chair`` yeganə yoldur.
    """
    if not submission.can_be_edited_by_teacher:
        raise ValidationError(
            pgettext("exams.service.question_submission.error", "Bu göndəriş artıq yekunlaşıb — dəyişdirilə bilməz.")
        )

    was_returned = submission.status in (
        QuestionSubmission.STATUS_REJECTED,
        QuestionSubmission.STATUS_CHAIR_REVISION,
        QuestionSubmission.STATUS_CENTER_REVISION,
    )
    previous_token = submission.import_token
    raw_text_changed = raw_text is not None and raw_text != submission.raw_text
    if title is not None and title.strip():
        submission.title = title.strip()
    if subject is not None and subject.strip():
        submission.subject = subject.strip()
    if subject_ref is not ...:
        submission.subject_ref = subject_ref
    if exam_kind is not None:
        submission.exam_kind = (exam_kind or "").strip().lower()
    if group_label is not None and group_label.strip():
        submission.group_label = group_label.strip()
    if student_group is not ...:
        submission.student_group = student_group
    if teacher_note is not None:
        submission.teacher_note = teacher_note.strip()
    if language:
        submission.language = language
    if import_token is not None:
        submission.import_token = (import_token or "").strip()
    elif raw_text_changed:
        # Mətn əl ilə dəyişdirilibsə köhnə PDF crop-ları artıq həmin məzmuna
        # uyğun deyil; qəbul zamanı yanlış vizual bağlanmasın.
        submission.import_token = ""
    snapshot_parsed = parsed
    if snapshot_parsed is None and submission.import_token and not raw_text_changed:
        # Eyni visual manifestlə yenidən göndərişdə əvvəlki source_index-lər
        # saxlanmalıdır; raw mətni yenidən parse etmək binding-i itirərdi.
        snapshot_parsed = submission.parsed_snapshot
    _apply_snapshot(
        submission,
        raw_text if raw_text is not None else submission.raw_text,
        parsed=snapshot_parsed,
    )

    if was_returned:
        submission.resubmission_count += 1
    submission.reviewer = None
    submission.reviewed_at = None
    # Rəyçi qeydini saxlamırıq — yeni versiya köhnə qərardan asılı deyil;
    # tam tarixçə ``QuestionSubmissionEvent`` lentındədir.
    submission.reviewer_note = ""
    submission.accepted_bank = None
    submission.reached_center_at = None
    submission.save()
    if groups:
        submission.student_groups.set(groups)
    if previous_token and previous_token != submission.import_token:
        from apps.exams.services.import_media import clear_stash

        transaction.on_commit(lambda token=previous_token: clear_stash(token))
    route_submission_to_chair(submission, actor=submission.teacher, resubmitted=True, groups=groups)
    return submission


# ---------------------------------------------------------------------------
# İmtahan mərkəzi tərəfi
# ---------------------------------------------------------------------------
def ensure_can_review_submission(user, submission):
    """Mərkəz qapısı — İKİ şərt, hər ikisi fail-closed.

    1. Aktor imtahan mərkəzi üzvü olmalıdır;
    2. Göndəriş KAFEDRA TƏSDİQİNDƏN keçmiş olmalıdır (``reached_center_at``).
       Kafedrada gözləyən/qaytarılan göndəriş mərkəz üçün MÖVCUD DEYİL —
       mövcudluq sızmasın deyə burada da 403 verilir.
    """
    if not is_exam_center_user(user):
        raise PermissionDenied(
            pgettext("exams.service.access.permission", "question_submission_review_exam_center_only")
        )
    if not submission.has_reached_center:
        raise PermissionDenied(
            pgettext("exams.service.access.permission", "question_submission_requires_chair_approval")
        )


def ensure_can_decide_as_center(submission):
    """Mərkəz YALNIZ kafedra təsdiqli və hələ qərar verilməmiş göndərişə qərar verir."""
    if not submission.is_at_center:
        raise ValidationError(pgettext("exams.service.question_submission.error", "Bu göndərişə artıq baxılıb."))


@transaction.atomic
def open_center_review(submission, *, reviewer):
    """``chair_approved`` → ``center_review``: mərkəz göndərişi açdı (izli, idempotent)."""
    if submission.status != QuestionSubmission.STATUS_CHAIR_APPROVED:
        return submission
    from_status = submission.status
    submission.status = QuestionSubmission.STATUS_CENTER_REVIEW
    submission.save(update_fields=["status", "updated_at"])
    record_event(
        submission,
        actor=reviewer,
        actor_role="exam_center",
        action=QuestionSubmissionEvent.ACTION_CENTER_OPENED,
        from_status=from_status,
        to_status=submission.status,
    )
    return submission


@transaction.atomic
def accept_submission(submission, *, reviewer, bank=None, new_bank_name="", note=""):
    """
    Göndərişi qəbul edir və snapshot-dakı sualları banka yazır.

    ``bank`` verilməyibsə ``new_bank_name`` ilə (təşkilat daxilində, paylaşılan)
    yeni bank yaradılır. Qaytarır: (bank, yazılmış sual sayı).
    """
    submission = QuestionSubmission.objects.select_for_update(of=("self",)).get(pk=submission.pk)
    ensure_can_decide_as_center(submission)

    if bank is None:
        bank_name = (new_bank_name or "").strip() or submission.title
        # Bank göndərişin meta-sı ilə yaradılır: fənn (kataloq bağlantısı ilə),
        # imtahan növü və mənbə müəllim — mərkəz sonra filtr/atribusiya üçün
        # istifadə edir. Banklar default gizlidir (paylaşım UI-dan çıxarılıb).
        bank = QuestionBank.objects.create(
            name=bank_name,
            subject=submission.subject or submission.title,
            subject_ref=submission.subject_ref,
            exam_kind=submission.exam_kind,
            source_teacher=submission.teacher,
            language=submission.language,
            default_question_type="test",
            organization=submission.organization,
            created_by=reviewer,
            is_shared=False,
        )
    elif bank.organization_id != submission.organization_id:
        raise ValidationError(pgettext("exams.service.question_submission.error", "Bank başqa təşkilata aiddir."))

    from apps.exams.views.teacher.question_library._shared import _save_bank_questions

    parsed = list(submission.parsed_snapshot or [])
    # Müəllimin workbench-də təyin etdiyi ballar snapshot-da saxlanır — banka
    # eyni ballarla yazılır (boş/qeyri-müəyyən → 1).
    points_payload = {str(index): str(question.get("points") or "") for index, question in enumerate(parsed, start=1)}
    try:
        created_count = _save_bank_questions(
            bank=bank,
            parsed=parsed,
            selected=set(range(1, len(parsed) + 1)),
            language=submission.language,
            q_format="test",
            points_payload=points_payload,
            created_by=reviewer,
            math_token=submission.import_token,
            media_owner_id=submission.teacher_id,
        )
    except (OSError, PermissionDenied, ValueError) as exc:
        logger.warning("Göndərişin visual media binding-i alınmadı: submission=%s", submission.pk, exc_info=True)
        raise ValidationError(
            pgettext(
                "exams.service.question_submission.error",
                "Vizual mənbə artıq əlçatan deyil və ya məzmunla uyğun gəlmir. Müəllim faylı yenidən yükləməlidir.",
            )
        ) from exc
    if created_count == 0:
        raise ValidationError(
            pgettext(
                "exams.service.question_submission.error",
                "Snapshot-dan heç bir sual banka yazıla bilmədi (A–D variantları natamamdır).",
            )
        )

    from_status = submission.status
    submission.status = QuestionSubmission.STATUS_ACCEPTED
    submission.reviewer = reviewer
    submission.reviewed_at = timezone.now()
    submission.reviewer_note = (note or "").strip()
    submission.accepted_bank = bank
    import_token = submission.import_token
    submission.import_token = ""
    submission.save(
        update_fields=[
            "status",
            "reviewer",
            "reviewed_at",
            "reviewer_note",
            "accepted_bank",
            "import_token",
            "updated_at",
        ]
    )
    if import_token:
        from apps.exams.services.import_media import clear_stash

        transaction.on_commit(lambda token=import_token: clear_stash(token))
    record_event(
        submission,
        actor=reviewer,
        actor_role="exam_center",
        action=QuestionSubmissionEvent.ACTION_CENTER_ACCEPTED,
        from_status=from_status,
        to_status=submission.status,
        reason=submission.reviewer_note,
        metadata={"bank_id": str(bank.pk), "question_count": created_count},
    )
    _notify_teacher_decision(submission)
    return bank, created_count


def _center_return(submission, *, reviewer, note, status, action):
    """Mərkəzin «geri qaytar» ailəsi: rədd və düzəliş eyni kod yolundadır."""
    submission = QuestionSubmission.objects.select_for_update(of=("self",)).get(pk=submission.pk)
    ensure_can_decide_as_center(submission)
    note = (note or "").strip()
    if len(note) < MIN_REASON_LENGTH:
        raise ValidationError(
            pgettext(
                "exams.service.question_submission.error",
                "Səbəb ən azı {count} simvol olmalıdır — müəllim nəyi düzəltməli olduğunu bilməlidir.",
            ).format(count=MIN_REASON_LENGTH)
        )
    from_status = submission.status
    submission.status = status
    submission.reviewer = reviewer
    submission.reviewed_at = timezone.now()
    submission.reviewer_note = note
    submission.save(update_fields=["status", "reviewer", "reviewed_at", "reviewer_note", "updated_at"])
    record_event(
        submission,
        actor=reviewer,
        actor_role="exam_center",
        action=action,
        from_status=from_status,
        to_status=status,
        reason=note,
    )
    _notify_teacher_decision(submission)
    return submission


@transaction.atomic
def reject_submission(submission, *, reviewer, note=""):
    return _center_return(
        submission,
        reviewer=reviewer,
        note=note,
        status=QuestionSubmission.STATUS_REJECTED,
        action=QuestionSubmissionEvent.ACTION_CENTER_REJECTED,
    )


@transaction.atomic
def request_center_revision(submission, *, reviewer, note=""):
    """Mərkəz düzəliş istəyir — müəllim düzəldib YENİDƏN kafedradan keçir."""
    return _center_return(
        submission,
        reviewer=reviewer,
        note=note,
        status=QuestionSubmission.STATUS_CENTER_REVISION,
        action=QuestionSubmissionEvent.ACTION_CENTER_REVISION,
    )


# ---------------------------------------------------------------------------
# Bildirişlər (xəta axını pozmur)
# ---------------------------------------------------------------------------
def _notify_teacher_decision(submission):
    try:
        from apps.notifications.public import create_notification

        if submission.status == QuestionSubmission.STATUS_ACCEPTED:
            message = pgettext(
                "exams.notification.question_submission",
                '"{title}" sual göndərişiniz qəbul edildi və sual bankına əlavə olundu.',
            )
        elif submission.status == QuestionSubmission.STATUS_CENTER_REVISION:
            message = pgettext(
                "exams.notification.question_submission",
                '"{title}" sual göndərişiniz İmtahan Mərkəzi tərəfindən düzəliş üçün qaytarıldı: {reason}',
            )
        else:
            message = pgettext(
                "exams.notification.question_submission",
                '"{title}" sual göndərişiniz rədd edildi: {reason}',
            )
        create_notification(
            recipient=submission.teacher,
            title=pgettext("exams.notification.question_submission", "Sual göndərişinə baxıldı"),
            message=message.format(title=submission.title, reason=submission.reviewer_note),
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
    "ensure_can_decide_as_center",
    "ensure_can_review_submission",
    "open_center_review",
    "reject_submission",
    "request_center_revision",
    "resubmit_question_set",
    "submit_question_set",
]
