"""Admin jurnal-düzəliş interfeysi (üzrlü qayıb / sənədli bal korreksiyası).

Yalnız ``corrections.can_correct_journal`` (superadmin / təşkilat admini) girə
bilir. Admin müəllim/fənn seçir → jurnal düzəliş rejimində açılır (müəllimdəki
kimi grid) → xanaya klik → modal (sahə, yeni dəyər, səbəb, qeyd, PDF sənəd) →
təsdiq. Bütün dəyişikliklər :func:`corrections.apply_correction` üzərindən gedir
(audit + sənəd + bildiriş).
"""

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils.translation import pgettext
from django.views.decorators.http import require_POST

from . import corrections, gradebook
from .models import AttendanceStatus, CorrectionReason, CourseOffering, Lesson, LessonMark


def _require_corrector(request):
    if not corrections.can_correct_journal(request):
        raise Http404


def _active_org(request):
    org = getattr(request, "organization", None)
    if org is None:
        raise Http404
    return org


@login_required
def correction_offering_list(request):
    """DEPRECATED — ayrı düzəliş siyahısı ləğv edildi. Korrektor jurnal siyahısından
    (bütün offering-lər) istənilən jurnalı açıb yerində "Jurnal düzəlişi" toggle ilə
    düzəldir. Köhnə URL jurnal siyahısına yönləndirir."""
    _require_corrector(request)
    _active_org(request)
    return redirect("registrar:journal_list")


def build_correction_context(offering, request) -> dict:
    """Jurnal-düzəliş editoru üçün paylaşılan kontekst — HƏM standalone
    ``correction_journal`` səhifəsi, HƏM DƏ ``journal_detail``-in yerində düzəliş
    rejimi (``?correct=1``) eyni audited editoru göstərsin deyə. Bütün yazma
    ``corrections.apply_correction`` (audit + sənəd) üzərindəndir."""
    return {
        "journal": gradebook.get_offering_journal(offering=offering, newest_first=True),
        "corrections_map": corrections.corrections_map_for_offering(offering, include_document=True),
        "correction_reasons": CorrectionReason.choices,
        "attendance_choices": [
            (AttendanceStatus.PRESENT, pgettext("registrar.correction", "İştirak (iə)")),
            (AttendanceStatus.ABSENT, pgettext("registrar.correction", "Qayıb (qb)")),
            (AttendanceStatus.EXCUSED, pgettext("registrar.correction", "Üzrlü qayıb (üq)")),
        ],
        "apply_url": reverse("registrar:correction_apply", args=[offering.pk]),
        "delete_url": reverse("registrar:correction_delete", args=[offering.pk]),
        "corrector_name": request.user.get_full_name() or request.user.username,
    }


@login_required
def correction_journal(request, offering_id):
    """DEPRECATED — ayrı düzəliş səhifəsi ləğv edildi; yerində düzəliş rejiminə
    (journal_detail ?correct=1, normal grid-in özündə) yönləndirir."""
    _require_corrector(request)
    org = _active_org(request)
    offering = get_object_or_404(CourseOffering, pk=offering_id, organization=org)
    return redirect(reverse("registrar:journal_detail", args=[offering.pk]) + "?correct=1")


@login_required
@require_POST
def correction_apply(request, offering_id):
    """Bir jurnal xanasına rəsmi düzəliş tətbiq et (multipart: PDF sənəd daxil)."""
    _require_corrector(request)
    org = _active_org(request)
    offering = get_object_or_404(CourseOffering, pk=offering_id, organization=org)

    mark = get_object_or_404(
        LessonMark.objects.select_related("lesson", "enrollment", "organization"),
        pk=request.POST.get("mark_id"),
        lesson__offering=offering,
    )
    field = request.POST.get("field")
    try:
        corrections.apply_correction(
            mark=mark,
            field=field,
            new_status=request.POST.get("new_status"),
            new_score=request.POST.get("new_score"),
            reason=request.POST.get("reason"),
            note=request.POST.get("note"),
            document=request.FILES.get("document"),
            by_user=request.user,
            request=request,
        )
    except ValidationError as exc:
        message = "; ".join(exc.messages) if hasattr(exc, "messages") else str(exc)
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse({"ok": False, "error": message}, status=400)
        messages.error(request, message)
        return redirect(reverse("registrar:journal_detail", args=[offering.pk]) + "?correct=1")

    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return JsonResponse({"ok": True})
    messages.success(request, pgettext("registrar.correction", "Düzəliş yadda saxlanıldı."))
    return redirect(reverse("registrar:journal_detail", args=[offering.pk]) + "?correct=1")


@login_required
@require_POST
def correction_delete(request, offering_id):
    """Səhvən edilmiş SON düzəlişi geri al (revert): dəyər köhnəyə qayıdır, sarı itir."""
    _require_corrector(request)
    org = _active_org(request)
    offering = get_object_or_404(CourseOffering, pk=offering_id, organization=org)
    ctype = (request.POST.get("type") or "grade").strip()

    if ctype == "lesson":
        lesson = get_object_or_404(Lesson, pk=request.POST.get("lesson_id"), offering=offering)
        ok = corrections.revert_last_lesson_correction(lesson=lesson, by_user=request.user, request=request)
    else:  # grade (davamiyyət/bal xanası)
        mark = get_object_or_404(
            LessonMark.objects.select_related("lesson", "enrollment", "organization"),
            pk=request.POST.get("mark_id"),
            lesson__offering=offering,
        )
        ok = corrections.revert_last_grade_correction(mark=mark, by_user=request.user, request=request)

    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return JsonResponse({"ok": ok})
    if ok:
        messages.success(request, pgettext("registrar.correction", "Düzəliş geri alındı."))
    else:
        messages.error(request, pgettext("registrar.correction", "Geri alınacaq düzəliş tapılmadı."))
    return redirect(reverse("registrar:journal_detail", args=[offering.pk]) + "?correct=1")
