"""Jurnal düzəlişi servisi — üzrlü qayıb / bal korreksiyası (rəsmi, sənədli).

Axın: superadmin / "journal.correct" icazəli admin müəllimi seçir → onun
jurnalına düzəliş rejimində baxır → xanaya klik → modal: sahə (davamiyyət|bal),
yeni dəyər, səbəb, qeyd və PDF sənəd (üçü də MƏCBURİ) → təsdiq. Düzəldənin adı
avtomatik profildən götürülür və dəyişdirilə bilməz.

Texniki: 2 saatlıq redaktə pəncərəsi və PG trigger-i (``trg_journal_mark_guard``)
``journal_unlock`` ilə rəsmi yoldan keçilir; ``Enrollment.absence_hours`` yenidən
hesablanır (EXCUSED limitə SAYILMIR); dəyişiklik həm :class:`JournalCorrection`
qeydinə, həm ``grade_audit``-ə, həm də ``core.audit``-ə yazılır; tələbəyə
bildiriş gedir. Bütün oxu/annotasiya köməkçiləri də buradadır.
"""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils.translation import pgettext

from core.audit import log_action
from core.constants import AuditAction
from core.permissions import request_has_permission
from core.rls import journal_unlock

from . import grade_audit
from .gradebook import LESSON_SCORE_MAX, lesson_allows_score, recompute_absence_hours
from .models import AttendanceStatus, CorrectionField, CorrectionReason, JournalCorrection, LessonMark

CORRECT_PERMISSION = "journal.correct"

_ATT_LABELS = {
    AttendanceStatus.PRESENT: "iə",
    AttendanceStatus.ABSENT: "qb",
    AttendanceStatus.EXCUSED: "üq",
}


def can_correct_journal(request) -> bool:
    """Düzəliş icazəsi: superadmin/superuser və ya ``journal.correct`` icazəsi.

    Wildcard (``*``) daşıyan admin-səviyyə rollar (rektor/owner/menecer)
    avtomatik əhatə olunur; gələcəkdə istənilən rola ``journal.correct``
    əlavə etməklə genişlənir (istifadəçi tələbi: hələlik yalnız admin səviyyə)."""
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return False
    if getattr(user, "is_superuser", False) or getattr(user, "is_superadmin", False):
        return True
    return request_has_permission(request, CORRECT_PERMISSION)


def _clean_int_score(raw) -> int:
    """Bal TAM ədəddir (float qadağandır) — 0..LESSON_SCORE_MAX aralığında."""
    try:
        value = int(str(raw).strip())
    except (TypeError, ValueError):
        raise ValidationError(pgettext("registrar.correction", "Score must be a whole number."))
    if not 0 <= value <= int(LESSON_SCORE_MAX):
        raise ValidationError(
            pgettext("registrar.correction", "Score must be between 0 and %(max)s.") % {"max": int(LESSON_SCORE_MAX)}
        )
    return value


@transaction.atomic
def apply_correction(
    *,
    mark: LessonMark,
    field: str,
    new_status: str | None = None,
    new_score=None,
    reason: str,
    note: str,
    document,
    by_user,
    request=None,
) -> JournalCorrection:
    """Bir jurnal xanasına rəsmi düzəliş tətbiq et (hamısı bir transaksiyada)."""
    if field not in CorrectionField.values:
        raise ValidationError(pgettext("registrar.correction", "Choose what to correct: attendance or score."))
    if reason not in CorrectionReason.values:
        raise ValidationError(pgettext("registrar.correction", "Choose a correction reason."))
    note = (note or "").strip()
    if not note:
        raise ValidationError(pgettext("registrar.correction", "A note explaining the correction is required."))
    if not document:
        raise ValidationError(pgettext("registrar.correction", "A justification document (PDF) is required."))

    lesson = mark.lesson
    correction = JournalCorrection(
        organization=mark.organization,
        lesson_mark=mark,
        field=field,
        reason=reason,
        note=note,
        document=document,
        corrected_by=by_user,
        corrected_by_name=(by_user.get_full_name() or by_user.username) if by_user else "",
    )

    if field == CorrectionField.ATTENDANCE:
        if new_status not in AttendanceStatus.values:
            raise ValidationError(pgettext("registrar.correction", "Choose the new attendance value."))
        correction.old_status = mark.status
        correction.new_status = new_status
        mark.status = new_status
    else:  # SCORE
        if not lesson_allows_score(lesson):
            raise ValidationError(
                pgettext("registrar.correction", "Lecture cells hold no score — only attendance can be corrected.")
            )
        score = _clean_int_score(new_score)
        correction.old_score = int(mark.score) if mark.score is not None else None
        correction.new_score = score
        mark.score = score

    correction.full_clean()  # PDF/ölçü validatorları burada işləyir

    # 2 saatlıq pəncərə + PG trigger rəsmi düzəliş yolunda keçilir.
    with journal_unlock():
        mark.save(update_fields=["status", "score", "updated_at"])
    correction.save()

    enrollment = mark.enrollment
    recompute_absence_hours(enrollment=enrollment)

    old_repr = (
        _ATT_LABELS.get(correction.old_status, correction.old_status)
        if field == CorrectionField.ATTENDANCE
        else str(correction.old_score if correction.old_score is not None else "—")
    )
    new_repr = (
        _ATT_LABELS.get(correction.new_status, correction.new_status)
        if field == CorrectionField.ATTENDANCE
        else str(correction.new_score)
    )
    grade_audit.log_grade_changes(
        offering=lesson.offering,
        by_user=by_user,
        kind="correction",
        changes=[
            {
                "student": grade_audit.student_label(enrollment),
                "item": f"{lesson.date} · {lesson.get_kind_display()}",
                "old": old_repr,
                "new": f"{new_repr} ({correction.get_reason_display()})",
            }
        ],
    )
    try:
        log_action(
            action=AuditAction.UPDATE,
            user=by_user,
            organization=mark.organization,
            obj=correction,
            reason=f"journal correction: {reason}",
            request=request,
            changes=[{"field": field, "old": old_repr, "new": new_repr}],
        )
    except Exception:  # audit heç vaxt axını sındırmır
        pass

    from apps.registrar import journal_notifications as jn

    transaction.on_commit(
        lambda: jn.send_journal_events(
            offering=lesson.offering,
            events=[{"enrollment": enrollment, "kind": jn.EVENT_CORRECTED}],
        )
    )
    return correction


# ── Oxu köməkçiləri (grid/tələbə annotasiyası) ───────────────────────────────


def _entry(c: JournalCorrection, *, include_document: bool) -> dict:
    data = {
        "date": c.created_at.strftime("%d.%m.%Y %H:%M"),
        "field": c.field,
        "field_display": c.get_field_display(),
        "old": (
            _ATT_LABELS.get(c.old_status, c.old_status)
            if c.field == CorrectionField.ATTENDANCE
            else (c.old_score if c.old_score is not None else "—")
        ),
        "new": (_ATT_LABELS.get(c.new_status, c.new_status) if c.field == CorrectionField.ATTENDANCE else c.new_score),
        "reason": c.get_reason_display(),
        "note": c.note,
        "by": c.corrected_by_name,
    }
    if include_document and c.document:
        data["document_url"] = c.document.url
    return data


def corrections_map_for_offering(offering, *, include_document: bool = False) -> dict[str, list[dict]]:
    """Grid annotasiyası: {mark_id: [düzəliş qeydləri]} (sarı xana + tarixçə)."""
    result: dict[str, list[dict]] = {}
    qs = JournalCorrection.objects.filter(lesson_mark__lesson__offering=offering).order_by("created_at")
    for c in qs:
        result.setdefault(str(c.lesson_mark_id), []).append(_entry(c, include_document=include_document))
    return result


def corrections_map_for_enrollment(enrollment) -> dict[str, list[dict]]:
    """Tələbə görünüşü üçün: öz xanalarının düzəliş tarixçəsi (sənədsiz)."""
    result: dict[str, list[dict]] = {}
    qs = JournalCorrection.objects.filter(lesson_mark__enrollment=enrollment).order_by("created_at")
    for c in qs:
        result.setdefault(str(c.lesson_mark_id), []).append(_entry(c, include_document=False))
    return result
