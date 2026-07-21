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
from django.utils.dateparse import parse_date
from django.utils.translation import pgettext
from django.views.decorators.http import require_POST

from . import corrections, gradebook
from .models import (
    AssessmentComponent,
    AttendanceStatus,
    CorrectionReason,
    CourseOffering,
    Enrollment,
    Lesson,
    LessonMark,
    SelfWorkTopic,
)


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
    from . import item_corrections, journal_extras

    sw_map = item_corrections.selfwork_corrections_map(offering, include_document=True)
    cw_map = item_corrections.coursework_corrections_map(offering, include_document=True)
    cm_map = item_corrections.component_corrections_map(offering, include_document=True)
    return {
        "journal": gradebook.get_offering_journal(offering=offering, newest_first=True),
        "corrections_map": corrections.corrections_map_for_offering(offering, include_document=True),
        # Sərbəst iş / kurs işi / kollokvium düzəliş rejimi: annotasiyalı board + sarı/tarixçə map-ları.
        "selfwork_board": item_corrections.annotate_selfwork_board(journal_extras.get_selfwork_board(offering), sw_map),
        "coursework_rows": item_corrections.annotate_coursework_rows(
            journal_extras.get_course_work_rows(offering), cw_map
        ),
        "kollokvium_grid": item_corrections.annotate_kollokvium_grid(
            journal_extras.get_kollokvium_grid(offering), cm_map
        ),
        "selfwork_corrections_map": sw_map,
        "coursework_corrections_map": cw_map,
        "component_corrections_map": cm_map,
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


def _apply_item_correction(request, offering):
    """Sərbəst iş / kurs işi xanasına sənədli düzəliş (bal xanası ilə eyni prosedur)."""
    from . import item_corrections

    target = (request.POST.get("target") or "").strip()
    common = dict(
        reason=request.POST.get("reason"),
        note=request.POST.get("note"),
        document=request.FILES.get("document"),
        by_user=request.user,
        request=request,
    )
    if target == "selfwork":
        topic = get_object_or_404(SelfWorkTopic, pk=request.POST.get("topic_id"), offering=offering)
        enrollment = get_object_or_404(Enrollment, pk=request.POST.get("enrollment_id"), offering=offering)
        item_corrections.apply_selfwork_correction(
            offering=offering,
            topic=topic,
            enrollment=enrollment,
            new_done=request.POST.get("new_done") == "1",
            **common,
        )
    elif target == "component":
        component = get_object_or_404(AssessmentComponent, pk=request.POST.get("component_id"), offering=offering)
        enrollment = get_object_or_404(Enrollment, pk=request.POST.get("enrollment_id"), offering=offering)
        item_corrections.apply_component_correction(
            component=component, enrollment=enrollment, new_score=request.POST.get("new_score_cm"), **common
        )
    else:  # coursework
        enrollment = get_object_or_404(Enrollment, pk=request.POST.get("enrollment_id"), offering=offering)
        item_corrections.apply_coursework_correction(
            enrollment=enrollment,
            new_score=request.POST.get("new_score_cw"),
            new_topic=request.POST.get("new_topic") or "",
            new_date=parse_date(request.POST.get("new_date") or "") or None,
            **common,
        )


@login_required
@require_POST
def correction_apply(request, offering_id):
    """Bir jurnal xanasına rəsmi düzəliş tətbiq et (multipart: PDF sənəd daxil)."""
    _require_corrector(request)
    org = _active_org(request)
    offering = get_object_or_404(CourseOffering, pk=offering_id, organization=org)

    target = (request.POST.get("target") or "grade").strip()
    try:
        if target in ("selfwork", "coursework", "component"):
            _apply_item_correction(request, offering)
        else:
            mark = get_object_or_404(
                LessonMark.objects.select_related("lesson", "enrollment", "organization"),
                pk=request.POST.get("mark_id"),
                lesson__offering=offering,
            )
            corrections.apply_correction(
                mark=mark,
                field=request.POST.get("field"),
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
    elif ctype in ("selfwork", "coursework", "component"):
        from . import item_corrections

        enrollment = get_object_or_404(Enrollment, pk=request.POST.get("enrollment_id"), offering=offering)
        if ctype == "selfwork":
            topic = get_object_or_404(SelfWorkTopic, pk=request.POST.get("topic_id"), offering=offering)
            ok = item_corrections.revert_last_selfwork_correction(
                topic=topic, enrollment=enrollment, by_user=request.user, request=request
            )
        elif ctype == "component":
            component = get_object_or_404(AssessmentComponent, pk=request.POST.get("component_id"), offering=offering)
            ok = item_corrections.revert_last_component_correction(
                component=component, enrollment=enrollment, by_user=request.user, request=request
            )
        else:
            ok = item_corrections.revert_last_coursework_correction(
                enrollment=enrollment, by_user=request.user, request=request
            )
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
