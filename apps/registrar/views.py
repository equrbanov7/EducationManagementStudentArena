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

from . import finals, gradebook, schedule
from .models import AttendanceStatus, CourseOffering, LessonKind, ScheduleSlot, StudentAcademicRecord, WeekType


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
    offerings = (
        CourseOffering.objects.filter(instructor=request.user, is_active=True)
        .select_related("subject", "period", "group")
        .order_by("-period__start_date", "subject__code")
    )
    return render(
        request,
        "registrar/journal_list.html",
        {"offerings": offerings, "active_main_nav": "journal"},
    )


@login_required
def journal_detail(request, offering_id):
    """Lesson-by-lesson journal for one offering: view (GET) + edit (POST)."""
    offering = get_object_or_404(
        CourseOffering.objects.select_related("subject", "period", "group", "organization"),
        pk=offering_id,
    )
    if not _can_edit_journal(request.user, offering):
        raise Http404  # do not leak existence to unauthorised users

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "add_lesson":
            return _handle_add_lesson(request, offering)
        if action == "save_finals":
            return _handle_save_finals(request, offering)
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
            "can_edit": not journal["scheme"].is_published,
            "lesson_kinds": LessonKind.choices,
            "active_main_nav": "journal",
        },
    )


def _handle_save_finals(request, offering):
    """Persist final-exam + resit scores per student (exam__<enr> / resit__<enr>)."""
    if getattr(offering, "assessment_scheme", None) and offering.assessment_scheme.is_published:
        messages.warning(request, _("Jurnal yekunlaşdırılıb — nəticə redaktəsi bağlıdır."))
        return redirect(reverse("registrar:journal_detail", args=[offering.pk]))

    enrollments = {str(e.id): e for e in offering.enrollments.all()}
    for key, raw in request.POST.items():
        if key.startswith("exam__"):
            enrollment = enrollments.get(key[len("exam__") :])
            if enrollment is not None:
                finals.set_exam_score(enrollment=enrollment, score=raw, by_user=request.user)
        elif key.startswith("resit__"):
            enrollment = enrollments.get(key[len("resit__") :])
            if enrollment is not None and raw.strip() != "":
                finals.set_resit_score(enrollment=enrollment, score=raw, by_user=request.user)
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
    rejected in the service). Tenant scoping comes from the active-org RLS context."""
    organization = getattr(request, "organization", None)
    if organization is None:
        return render(request, "registrar/schedule.html", {"has_context": False, "active_main_nav": "schedule"})

    period = _current_period(organization)

    if request.method == "POST":
        return _handle_add_slot(request, organization, period)

    record = (
        StudentAcademicRecord.objects.filter(organization=organization, student=request.user)
        .select_related("group")
        .first()
    )
    teacher_offerings = []
    if record and record.group and period:
        role = "student"
        owner_label = record.group.name
        slots = schedule.get_group_schedule(organization=organization, group=record.group, period=period)
    else:
        role = "teacher"
        owner_label = request.user.get_full_name() or request.user.username
        slots = (
            schedule.get_teacher_schedule(organization=organization, teacher=request.user, period=period)
            if period
            else []
        )
        if period:
            teacher_offerings = list(
                CourseOffering.objects.filter(
                    organization=organization, instructor=request.user, period=period, is_active=True
                ).select_related("subject", "group")
            )

    return render(
        request,
        "registrar/schedule.html",
        {
            "has_context": True,
            "role": role,
            "owner_label": owner_label,
            "period": period,
            "week_grid": schedule.build_week_grid(slots),
            "teacher_offerings": teacher_offerings,
            "weekdays": schedule.WEEKDAYS,
            "week_types": WeekType.choices,
            "active_main_nav": "schedule",
        },
    )


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
        return redirect(reverse("registrar:schedule"))

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
    return redirect(reverse("registrar:schedule"))


@login_required
def schedule_slot_delete(request, slot_id):
    """Delete a slot (only the teaching instructor / org owner / superuser)."""
    slot = get_object_or_404(ScheduleSlot.objects.select_related("offering", "offering__organization"), pk=slot_id)
    if request.method == "POST" and _can_edit_journal(request.user, slot.offering):
        slot.delete()
        messages.success(request, _("Slot silindi."))
    return redirect(reverse("registrar:schedule"))
