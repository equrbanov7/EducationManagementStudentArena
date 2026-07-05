"""Elektron jurnal — müəllim üzü (U3, UNEC modeli).

Müəllim öz tədris etdiyi offering-lərin siyahısını görür, birini seçib dərs
(``Lesson``) əlavə edir və hər tələbə üçün iştirak/qayıb (iə/qb), seminarda isə
bal yazır. Təhlükəsizlik: ``@login_required`` + hər offering üçün
``_can_edit_journal`` (müəllim / org sahibi / superuser) + tenant-izolyasiya RLS
→ başqa müəllimin/təşkilatın jurnalına giriş yoxdur (IDOR qorunması). Kilid və
klamp servis qatında (``gradebook.save_marks``) yenidən tətbiq olunur.
"""

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _

from . import approval, finals, grade_audit, gradebook, schedule
from .models import (
    ApprovalStatus,
    AttendanceStatus,
    CourseOffering,
    LessonKind,
    ScheduleSlot,
    WeekType,
)


def _current_period(organization):
    """Current AcademicPeriod for the org (app-registry lookup — no static import)."""
    from django.apps import apps as django_apps

    AcademicPeriod = django_apps.get_model("organizations", "AcademicPeriod")
    return (
        AcademicPeriod.objects.filter(organization=organization, is_current=True).first()
        or AcademicPeriod.objects.filter(organization=organization).order_by("-start_date").first()
    )


def _can_edit_journal(user, offering) -> bool:
    """Only the offering's instructor, the org owner, or a superuser may edit."""
    if not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_superuser", False):
        return True
    if offering.instructor_id and offering.instructor_id == user.id:
        return True
    return offering.organization.owner_id == user.id


@login_required
def journal_list(request):
    """The teacher's own offerings — entry points into each journal."""
    from apps.registrar import page_contexts

    context = page_contexts.journal_list_context(request.user)
    context["active_main_nav"] = "journal"
    return render(request, "registrar/journal_list.html", context)


@login_required
def journal_detail(request, offering_id):
    """Lesson-by-lesson journal for one offering: view (GET) + edit (POST).

    Access: the offering instructor / org owner / superuser may edit; a chair
    (kafedra müdiri) or dean (dekan) may *review* a submitted journal (read-only)
    to approve or return it via the grade-approval chain (U7.2)."""
    offering = get_object_or_404(
        CourseOffering.objects.select_related("subject", "period", "group", "organization"),
        pk=offering_id,
    )
    appr = approval.approval_context(offering=offering, user=request.user)
    can_edit_perm = _can_edit_journal(request.user, offering)
    can_review = approval.can_chair_approve(request.user, offering.organization) or approval.can_dean_approve(
        request.user, offering.organization
    )
    # Do not leak existence: only editors, or reviewers of an already-submitted
    # journal, may open the page.
    if not can_edit_perm and not (can_review and appr["status"] != ApprovalStatus.DRAFT):
        raise Http404

    if request.method == "POST":
        action = request.POST.get("action")
        # Grade-approval chain actions (services enforce their own RBAC).
        if action == "submit_approval":
            return _handle_approval(request, offering, approval.submit_for_approval, _("Jurnal təsdiqə göndərildi."))
        if action == "chair_approve":
            return _handle_approval(request, offering, approval.chair_approve, _("Kafedra təsdiqi verildi."))
        if action == "dean_approve":
            return _handle_approval(
                request, offering, approval.dean_approve, _("Dekan təsdiqi verildi — qiymətlər rəsmiləşdi.")
            )
        if action == "return_revision":
            return _handle_return(request, offering)
        # Editing actions require instructor/owner edit rights.
        if not can_edit_perm:
            raise Http404
        if action == "add_lesson":
            return _handle_add_lesson(request, offering)
        if action == "save_finals":
            return _handle_save_finals(request, offering)
        if action == "save_components":
            return _handle_save_components(request, offering)
        if action == "save_component_scores":
            return _handle_save_component_scores(request, offering)
        if action == "publish":
            finals.publish_offering(offering=offering, by_user=request.user)
            messages.success(request, _("Jurnal yekunlaşdırıldı."))
            return redirect(reverse("registrar:journal_detail", args=[offering.pk]))
        return _handle_save_marks(request, offering)

    journal = gradebook.get_offering_journal(offering=offering)
    return render(
        request,
        "registrar/journal_detail.html",
        {
            "offering": offering,
            "journal": journal,
            "finals": finals.get_offering_results(offering=offering),
            "component_grid": gradebook.get_component_grid(offering=offering),
            "can_edit": can_edit_perm and not appr["is_locked"],
            "approval": appr,
            "grade_history": grade_audit.get_grade_history(offering=offering),
            "lesson_kinds": LessonKind.choices,
            "active_main_nav": "journal",
        },
    )


def _handle_approval(request, offering, action_fn, success_msg):
    """Run an approval-chain transition; surface a permission error as a message."""
    from django.core.exceptions import PermissionDenied

    try:
        action_fn(offering=offering, by_user=request.user)
        messages.success(request, success_msg)
    except PermissionDenied as exc:
        messages.error(request, str(exc) or _("Bu əməliyyat üçün icazəniz yoxdur."))
    return redirect(reverse("registrar:journal_detail", args=[offering.pk]))


def _handle_return(request, offering):
    """Chair/dean returns the journal to the teacher with an optional reason."""
    from django.core.exceptions import PermissionDenied

    reason = (request.POST.get("return_reason") or "").strip()
    try:
        approval.return_for_revision(offering=offering, by_user=request.user, reason=reason)
        messages.success(request, _("Jurnal düzəliş üçün geri qaytarıldı."))
    except PermissionDenied as exc:
        messages.error(request, str(exc) or _("Bu əməliyyat üçün icazəniz yoxdur."))
    return redirect(reverse("registrar:journal_detail", args=[offering.pk]))


@login_required
def approvals_inbox(request):
    """Chair/dean inbox: journals awaiting the current user's approval step."""
    from apps.registrar import page_contexts

    organization = getattr(request, "organization", None)
    if organization is None:
        return render(request, "registrar/approvals_inbox.html", {"has_context": False, "active_main_nav": "approvals"})

    context = page_contexts.approvals_context(request.user, organization)
    if not context["is_approver"]:
        raise Http404  # not an approver in this org
    context["active_main_nav"] = "approvals"
    return render(request, "registrar/approvals_inbox.html", context)


def _handle_save_components(request, offering):
    """Define/upsert the offering's assessment components (name + max_score)."""
    if getattr(offering, "assessment_scheme", None) and offering.assessment_scheme.is_published:
        messages.warning(request, _("Jurnal yekunlaşdırılıb — komponent redaktəsi bağlıdır."))
        return redirect(reverse("registrar:journal_detail", args=[offering.pk]))

    definitions = []
    index = 0
    while f"comp_name__{index}" in request.POST:
        definitions.append(
            {
                "id": request.POST.get(f"comp_id__{index}") or None,
                "name": request.POST.get(f"comp_name__{index}"),
                "max_score": request.POST.get(f"comp_max__{index}"),
            }
        )
        index += 1
    gradebook.save_components(offering=offering, definitions=definitions, by_user=request.user)
    messages.success(request, _("Qiymətləndirmə komponentləri yadda saxlanıldı."))
    return redirect(reverse("registrar:journal_detail", args=[offering.pk]))


def _handle_save_component_scores(request, offering):
    """Persist per-(component, enrollment) component scores (cscore__C__E keys)."""
    entries = []
    for key, raw in request.POST.items():
        if not key.startswith("cscore__"):
            continue
        parts = key.split("__", 2)
        if len(parts) != 3:
            continue
        _prefix, component_id, enrollment_id = parts
        entries.append({"component_id": component_id, "enrollment_id": enrollment_id, "score": raw})
    written = gradebook.save_component_scores(offering=offering, entries=entries, by_user=request.user)
    messages.success(request, _("Komponent balları yadda saxlanıldı (%(n)s xana).") % {"n": written})
    return redirect(reverse("registrar:journal_detail", args=[offering.pk]))


def _handle_save_finals(request, offering):
    """Persist final-exam + resit scores per student (exam__<enr> / resit__<enr>)."""
    if getattr(offering, "assessment_scheme", None) and offering.assessment_scheme.is_published:
        messages.warning(request, _("Jurnal yekunlaşdırılıb — nəticə redaktəsi bağlıdır."))
        return redirect(reverse("registrar:journal_detail", args=[offering.pk]))

    enrollments = {str(e.id): e for e in offering.enrollments.all()}
    extras: dict = {}
    for key, raw in request.POST.items():
        if key.startswith("exam__"):
            enrollment = enrollments.get(key[len("exam__") :])
            if enrollment is not None:
                finals.set_exam_score(enrollment=enrollment, score=raw, by_user=request.user)
        elif key.startswith("resit__"):
            enrollment = enrollments.get(key[len("resit__") :])
            if enrollment is not None and raw.strip() != "":
                finals.set_resit_score(enrollment=enrollment, score=raw, by_user=request.user)
        elif key.startswith("bonus__"):
            enrollment = enrollments.get(key[len("bonus__") :])
            if enrollment is not None:
                extras.setdefault(enrollment.id, {"enrollment": enrollment})["bonus"] = raw or "0"
        elif key.startswith("fcomment__"):
            enrollment = enrollments.get(key[len("fcomment__") :])
            if enrollment is not None:
                extras.setdefault(enrollment.id, {"enrollment": enrollment})["comment"] = raw
    # Bonus/cərimə + rəy (U15) — bal daxil edilməsindən SONRA yazılır ki,
    # evaluate_resit yekun vəziyyəti bonuslu total ilə görsün.
    for data in extras.values():
        finals.set_final_extras(
            enrollment=data["enrollment"],
            bonus=data.get("bonus"),
            comment=data.get("comment"),
            by_user=request.user,
        )
    messages.success(request, _("Yekun nəticələr yadda saxlanıldı."))
    return redirect(reverse("registrar:journal_detail", args=[offering.pk]))


def _handle_add_lesson(request, offering):
    """Create a new lesson column (date + type + optional topic/hours)."""
    if getattr(offering, "assessment_scheme", None) and offering.assessment_scheme.is_published:
        messages.warning(request, _("Jurnal yekunlaşdırılıb — dərs əlavə etmək olmaz."))
        return redirect(reverse("registrar:journal_detail", args=[offering.pk]))

    date = request.POST.get("lesson_date") or None
    kind = request.POST.get("lesson_kind")
    if kind not in dict(LessonKind.choices):
        kind = LessonKind.LECTURE
    if not date:
        messages.error(request, _("Dərs tarixi tələb olunur."))
        return redirect(reverse("registrar:journal_detail", args=[offering.pk]))

    hours_raw = (request.POST.get("lesson_hours") or "").strip()
    hours = int(hours_raw) if hours_raw.isdigit() and int(hours_raw) > 0 else None
    gradebook.create_lesson(
        offering=offering,
        date=date,
        kind=kind,
        topic=(request.POST.get("lesson_topic") or "").strip(),
        hours=hours,
        created_by=request.user,
    )
    messages.success(request, _("Dərs əlavə edildi."))
    return redirect(reverse("registrar:journal_detail", args=[offering.pk]))


def _handle_save_marks(request, offering):
    """Parse editable grid cells (hidden ``cell__L__E`` markers) → save_marks."""
    entries = []
    for key in request.POST:
        if not key.startswith("cell__"):
            continue
        # cell__<lesson_id>__<enrollment_id>
        parts = key.split("__", 2)
        if len(parts) != 3:
            continue
        _prefix, lesson_id, enrollment_id = parts
        absent = f"absent__{lesson_id}__{enrollment_id}" in request.POST
        entries.append(
            {
                "lesson_id": lesson_id,
                "enrollment_id": enrollment_id,
                "status": AttendanceStatus.ABSENT if absent else AttendanceStatus.PRESENT,
                "score": request.POST.get(f"score__{lesson_id}__{enrollment_id}"),
            }
        )

    written = gradebook.save_marks(offering=offering, entries=entries, by_user=request.user)
    messages.success(request, _("Jurnal yadda saxlanıldı (%(n)s xana).") % {"n": written})
    return redirect(reverse("registrar:journal_detail", args=[offering.pk]))


# ── Dərs cədvəli (timetable, U4) ─────────────────────────────────────────────


@login_required
def schedule_view(request):
    """Role-aware weekly timetable: student → group schedule, teacher → own slots.

    Teachers/org-owners may add slots for the offerings they teach (conflicts are
    rejected in the service). Tenant scoping comes from the active-org RLS context.
    Context building is shared with the profile cabinet section (page_contexts)."""
    from apps.registrar import page_contexts

    organization = getattr(request, "organization", None)
    if organization is None:
        return render(request, "registrar/schedule.html", {"has_context": False, "active_main_nav": "schedule"})

    if request.method == "POST":
        return _handle_add_slot(request, organization, _current_period(organization))

    context = page_contexts.schedule_context(request, organization)
    context["active_main_nav"] = "schedule"
    return render(request, "registrar/schedule.html", context)


def _redirect_after_schedule(request):
    """Redirect back to the caller: the profile shell (`next`, same-host only)
    or the standalone schedule page. Keeps the sidebar context after slot POSTs."""
    from django.utils.http import url_has_allowed_host_and_scheme

    nxt = request.POST.get("next") or ""
    if nxt and url_has_allowed_host_and_scheme(
        nxt, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return redirect(nxt)
    return redirect(reverse("registrar:schedule"))


def _handle_add_slot(request, organization, period):
    offering = (
        CourseOffering.objects.filter(pk=request.POST.get("offering_id"), organization=organization)
        .select_related("organization")
        .first()
    )
    if offering is None or not _can_edit_journal(request.user, offering):
        raise Http404  # only the teaching instructor / org owner may schedule

    from django.utils.dateparse import parse_time

    try:
        weekday = int(request.POST.get("weekday") or 0)
    except (TypeError, ValueError):
        weekday = 0
    start_time = parse_time(request.POST.get("start_time") or "")
    end_time = parse_time(request.POST.get("end_time") or "")
    week_type = request.POST.get("week_type")
    if week_type not in dict(WeekType.choices):
        week_type = WeekType.ALL
    if not (1 <= weekday <= 7) or start_time is None or end_time is None or start_time >= end_time:
        messages.error(request, _("Gün və düzgün başlama/bitmə vaxtı tələb olunur."))
        return _redirect_after_schedule(request)

    try:
        schedule.create_slot(
            offering=offering,
            weekday=weekday,
            start_time=start_time,
            end_time=end_time,
            room=(request.POST.get("room") or "").strip(),
            week_type=week_type,
            created_by=request.user,
        )
        messages.success(request, _("Dərs cədvəlinə slot əlavə edildi."))
    except schedule.ScheduleConflict as exc:
        clash = exc.conflict
        messages.error(
            request,
            _("Konflikt: bu vaxt %(subject)s ilə üst-üstə düşür (qrup/müəllim/otaq).")
            % {"subject": clash.offering.subject.code},
        )
    return _redirect_after_schedule(request)


@login_required
def schedule_slot_delete(request, slot_id):
    """Delete a slot (only the teaching instructor / org owner / superuser)."""
    slot = get_object_or_404(ScheduleSlot.objects.select_related("offering", "offering__organization"), pk=slot_id)
    if request.method == "POST" and _can_edit_journal(request.user, slot.offering):
        slot.delete()
        messages.success(request, _("Slot silindi."))
    return _redirect_after_schedule(request)


# ── Akademik təqvim (U11) ────────────────────────────────────────────────────


@login_required
def calendar_view(request):
    """Academic calendar: semesters with their registration + exam-session windows.

    Read-only and open to every authenticated member of the active organization
    (students plan around these dates as much as staff). Window editing lives in
    the AcademicPeriod admin — tenant-configurable, per the variable-structure rule."""
    from apps.registrar import page_contexts

    organization = getattr(request, "organization", None)
    if organization is None:
        return render(request, "registrar/calendar.html", {"has_context": False, "active_main_nav": "calendar"})

    context = page_contexts.calendar_context(organization)
    context["active_main_nav"] = "calendar"
    return render(request, "registrar/calendar.html", context)


# The registrar console (K3) views live in ``apps.registrar.console_views`` to
# keep this module focused (journal + timetable) and under the size budget.
