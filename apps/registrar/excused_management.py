"""Scoped, reason-only management of excused attendance through correction ledgers."""

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils.translation import pgettext

from core.permissions import request_has_permission

from . import corrections
from .correction_target_locks import lock_grade_for_apply
from .journal_scope import offering_in_actor_scope
from .models import AttendanceStatus, CorrectionField, CorrectionReason, CourseOffering, JournalCorrection, LessonMark

PERMISSION = "journal.excused.manage"
MIN_REASON = 3
MAX_REASON = 500
CTX = "registrar.excused_management"


def can_manage(request, offering):
    return bool(
        getattr(request, "user", None) is not None
        and request.user.is_authenticated
        and request.user.is_active
        and getattr(request, "organization", None) == offering.organization
        and offering.is_active
        and request_has_permission(request, PERMISSION)
        and offering_in_actor_scope(request.user, offering.organization, offering, permission=PERMISSION)
    )


def reason_text(raw):
    text = " ".join(str(raw or "").split())
    if not MIN_REASON <= len(text) <= MAX_REASON:
        raise ValidationError(pgettext(CTX, "Səbəb 3–500 simvol olmalıdır."))
    return text


def _latest(mark):
    return (
        JournalCorrection.objects.filter(lesson_mark=mark, reversal__isnull=True).order_by("-created_at", "-id").first()
    )


def _excused_correction(correction):
    return bool(
        correction
        and correction.field == CorrectionField.ATTENDANCE
        and AttendanceStatus.EXCUSED in (correction.old_status, correction.new_status)
    )


def reversal_reason(request, offering, correction, raw=""):
    # HTTP callers with the narrow permission must also explain a reversal
    # reached through the older generic correction endpoint.
    if (
        request is not None
        and offering is not None
        and _excused_correction(correction)
        and can_manage(request, offering)
    ):
        return reason_text(raw or request.POST.get("reason"))
    return raw or ""


def _stale():
    return ValidationError(pgettext(CTX, "Xana dəyişib. Jurnalı yeniləyib təkrar edin."))


def _reason_document(*, request, reason):
    """Technical reason record, explicitly not an uploaded medical/official document."""
    import uuid

    from django.conf import settings
    from django.core.files.base import ContentFile
    from django.utils import timezone

    import fitz

    actor = corrections.correction_author_name(request.user, request)
    text = (
        "Üzrlü qayıb düzəlişi — səbəb qeydi\n\n"
        "Rəsmi əsas sənədi yüklənməyib. Bu PDF sistemin saxladığı səbəb qeydidir.\n\n"
        f"Aktor: {actor}\nTarix: {timezone.localtime():%d.%m.%Y %H:%M}\n\nSəbəb: {reason}"
    )
    document = fitz.open()
    try:
        page = document.new_page()
        page.insert_font(fontname="reason", fontfile=str(settings.BASE_DIR / "static/fonts/DejaVuSans.ttf"))
        remaining = page.insert_textbox(fitz.Rect(48, 48, 547, 790), text, fontname="reason", fontsize=11)
        if remaining < 0:
            raise ValidationError(pgettext(CTX, "Səbəb qeydini saxlamaq mümkün olmadı."))
        document.subset_fonts()
        return ContentFile(document.tobytes(garbage=4, deflate=True), name=f"reason-{uuid.uuid4().hex[:16]}.pdf")
    finally:
        document.close()


@transaction.atomic
def manage(*, request, offering, mark_id, operation, reason, expected_status, expected_correction_id="", new_status=""):
    """Only current üq edits or exact latest üq-related reversal; no score writes."""
    if not can_manage(request, offering):
        raise PermissionDenied
    offering = CourseOffering.objects.select_for_update().get(pk=offering.pk, organization=offering.organization)
    if not can_manage(request, offering):
        raise PermissionDenied
    reason = reason_text(reason)
    mark = (
        LessonMark.objects.filter(
            pk=mark_id, organization=offering.organization, lesson__offering=offering, enrollment__offering=offering
        )
        .select_related("lesson", "enrollment", "organization")
        .first()
    )
    if mark is None:
        previous = (
            JournalCorrection.objects.filter(
                pk=expected_correction_id, lesson_mark_ref=mark_id, organization=offering.organization
            ).first()
            if operation == "reverse" and expected_correction_id
            else None
        )
        if _excused_correction(previous) and hasattr(previous, "reversal"):
            if previous.reversal.reason_note != reason:
                raise _stale()
            return corrections.revert_last_grade_correction(
                mark=None,
                by_user=request.user,
                request=request,
                offering=offering,
                correction_id=previous.pk,
                reason_note=reason,
            )
        raise _stale()
    correction = _latest(mark)
    current_id = str(correction.pk) if correction else ""
    if str(expected_correction_id or "") != current_id or expected_status != mark.status:
        # An exact already-reversed request may safely retry through the existing
        # reversal service, whose stable locators retain the old correction.
        if operation == "reverse" and expected_correction_id:
            previous = JournalCorrection.objects.filter(
                pk=expected_correction_id, lesson_mark_ref=mark.pk, organization=offering.organization
            ).first()
            if _excused_correction(previous) and hasattr(previous, "reversal"):
                if previous.reversal.reason_note != reason:
                    raise _stale()
                return corrections.revert_last_grade_correction(
                    mark=mark,
                    by_user=request.user,
                    request=request,
                    offering=offering,
                    correction_id=previous.pk,
                    reason_note=reason,
                )
        raise _stale()
    if operation == "reverse":
        if not _excused_correction(correction):
            raise _stale()
        return corrections.revert_last_grade_correction(
            mark=mark,
            by_user=request.user,
            request=request,
            offering=offering,
            correction_id=correction.pk,
            reason_note=reason,
        )
    if operation != "change" or new_status not in (AttendanceStatus.PRESENT, AttendanceStatus.ABSENT):
        raise ValidationError(pgettext(CTX, "Yeni davamiyyəti seçin: iştirak və ya qayıb."))
    mark, _, _ = lock_grade_for_apply(mark, expected_empty=False)
    correction = _latest(mark)
    if mark.status != AttendanceStatus.EXCUSED or current_id != (str(correction.pk) if correction else ""):
        raise _stale()
    return corrections.apply_correction(
        mark=mark,
        field=CorrectionField.ATTENDANCE,
        new_status=new_status,
        reason=CorrectionReason.TECHNICAL,
        note=reason,
        audit_reason=reason,
        document=_reason_document(request=request, reason=reason),
        by_user=request.user,
        request=request,
    )


def page_context(request, offering, context):
    """Annotate only already-visible cells; teacher/student requests receive no controls."""
    if not can_manage(request, offering):
        return {}
    from django.urls import reverse

    latest = {}
    for correction in JournalCorrection.objects.filter(
        organization=offering.organization, lesson_mark__lesson__offering=offering, reversal__isnull=True
    ).order_by("created_at", "id"):
        latest[correction.lesson_mark_id] = correction
    for row in context.get("journal", {}).get("rows", []):
        for cell in row.get("cells", []):
            mark = cell.get("mark")
            if mark is None:
                continue
            correction = latest.get(mark.pk)
            reversible = _excused_correction(correction) and mark.status == correction.new_status
            if mark.status == AttendanceStatus.EXCUSED or reversible:
                cell["excused_action"] = {
                    "reverse_id": str(correction.pk) if reversible else "",
                    "expected_id": str(correction.pk) if correction else "",
                    "can_change": mark.status == AttendanceStatus.EXCUSED,
                }
    return {"excused_management_url": reverse("registrar:excused_management", args=[offering.pk])}
