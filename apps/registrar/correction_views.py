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
    JournalCorrection,
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


def _resolve_grade_mark(request, offering):
    """Bal/davamiyyət xanasının LessonMark-ını tap. BOŞ xana (mark_id yox) →
    lesson+enrollment-dan YARADILACAQ obyekt qaytar (hələ SAXLANMIR) ki, İKT
    işarəsi olmayan xanaya da dəyər verə bilsin. Qaytarır (mark, was_empty).

    Boş xanada mark məhz ``apply_correction`` daxilində — validasiyadan SONRA, onun
    atomik blokunda — saxlanır; düzəliş rədd olunsa audit olunmamış sətir qalmaz."""
    mark_id = (request.POST.get("mark_id") or "").strip()
    if mark_id:
        mark = get_object_or_404(
            LessonMark.objects.select_related("lesson", "enrollment", "organization"),
            pk=mark_id,
            lesson__offering=offering,
        )
        return mark, False
    lesson = get_object_or_404(Lesson, pk=request.POST.get("lesson_id"), offering=offering)
    enrollment = get_object_or_404(Enrollment, pk=request.POST.get("enrollment_id"), offering=offering)
    existing = LessonMark.objects.filter(lesson=lesson, enrollment=enrollment).select_related("lesson").first()
    if existing is not None:
        return existing, False
    mark = LessonMark(
        organization=offering.organization, lesson=lesson, enrollment=enrollment, status=AttendanceStatus.PRESENT
    )
    return mark, True


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
            mark, was_empty = _resolve_grade_mark(request, offering)
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
                was_empty=was_empty,
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
    """Append-only ledger ilə seçilmiş son düzəlişi geri al."""
    _require_corrector(request)
    org = _active_org(request)
    offering = get_object_or_404(CourseOffering, pk=offering_id, organization=org)
    try:
        ok = _revert_requested_correction(request, offering)
    except ValidationError as exc:
        message = "; ".join(exc.messages) if hasattr(exc, "messages") else str(exc)
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse({"ok": False, "error": message}, status=409)
        messages.error(request, message)
        return redirect(reverse("registrar:journal_detail", args=[offering.pk]) + "?correct=1")

    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return JsonResponse({"ok": ok})
    if ok:
        messages.success(request, pgettext("registrar.correction", "Düzəliş geri alındı."))
    else:
        messages.error(request, pgettext("registrar.correction", "Geri alınacaq düzəliş tapılmadı."))
    return redirect(reverse("registrar:journal_detail", args=[offering.pk]) + "?correct=1")


def _revert_requested_correction(request, offering):
    ctype = (request.POST.get("type") or "grade").strip()
    correction_id = (request.POST.get("correction_id") or "").strip() or None
    if correction_id is None:
        raise ValidationError(
            pgettext(
                "registrar.correction",
                "Select the exact correction to reverse and reload the journal if it changed.",
            )
        )
    common = {"by_user": request.user, "request": request, "correction_id": correction_id}
    if ctype == "lesson":
        lesson = get_object_or_404(Lesson, pk=request.POST.get("lesson_id"), offering=offering)
        return corrections.revert_last_lesson_correction(lesson=lesson, **common)
    if ctype in ("selfwork", "coursework", "component"):
        from . import item_corrections

        enrollment = get_object_or_404(Enrollment, pk=request.POST.get("enrollment_id"), offering=offering)
        if ctype == "selfwork":
            topic = get_object_or_404(SelfWorkTopic, pk=request.POST.get("topic_id"), offering=offering)
            return item_corrections.revert_last_selfwork_correction(
                topic=topic,
                enrollment=enrollment,
                **common,
            )
        if ctype == "component":
            component = get_object_or_404(
                AssessmentComponent,
                pk=request.POST.get("component_id"),
                offering=offering,
            )
            return item_corrections.revert_last_component_correction(
                component=component,
                enrollment=enrollment,
                **common,
            )
        return item_corrections.revert_last_coursework_correction(enrollment=enrollment, **common)

    if correction_id:
        expected = get_object_or_404(
            JournalCorrection.objects.select_related("lesson_mark", "lesson_mark__lesson", "lesson_mark__enrollment"),
            pk=correction_id,
            organization=offering.organization,
        )
        get_object_or_404(Lesson, pk=expected.lesson_ref, offering=offering)
        return corrections.revert_last_grade_correction(
            mark=expected.lesson_mark,
            offering=offering,
            **common,
        )
    mark = get_object_or_404(
        LessonMark.objects.select_related("lesson", "enrollment", "organization"),
        pk=request.POST.get("mark_id"),
        lesson__offering=offering,
    )
    return corrections.revert_last_grade_correction(mark=mark, offering=offering, **common)
