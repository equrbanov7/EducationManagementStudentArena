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

from . import finals, gradebook, schedule, services
from .forms import CurriculumForm, CurriculumSubjectForm, OfferingForm, ProgramForm, SubjectForm
from .models import (
    AttendanceStatus,
    CourseOffering,
    Curriculum,
    CurriculumSubject,
    LessonKind,
    Program,
    ScheduleSlot,
    StudentAcademicRecord,
    Subject,
    WeekType,
)

# Roles that may manage the registrar catalogue (besides superuser + org owner).
_REGISTRAR_ADMIN_ROLES = ("org_admin", "org_owner", "rector", "vice_rector", "dean")


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

    try:
        week_offset = max(-8, min(16, int(request.GET.get("w") or 0)))
    except (TypeError, ValueError):
        week_offset = 0
    week_context = schedule.build_week_context(period, offset=week_offset)

    record = (
        StudentAcademicRecord.objects.filter(organization=organization, student=request.user)
        .select_related("group")
        .first()
    )
    teacher_offerings = []
    exam_author = None
    course_ids = []
    if record and record.group and period:
        role = "student"
        owner_label = record.group.name
        slots = schedule.get_group_schedule(organization=organization, group=record.group, period=period)
        course_ids = list(
            CourseOffering.objects.filter(organization=organization, group=record.group, period=period).values_list(
                "course_id", flat=True
            )
        )
    else:
        role = "teacher"
        owner_label = request.user.get_full_name() or request.user.username
        exam_author = request.user
        if period:
            slots = schedule.get_teacher_schedule(organization=organization, teacher=request.user, period=period)
            teacher_offerings = list(
                CourseOffering.objects.filter(
                    organization=organization, instructor=request.user, period=period, is_active=True
                ).select_related("subject", "group")
            )
            course_ids = [off.course_id for off in teacher_offerings]
        else:
            slots = []

    exams_by_day = schedule.get_week_exams(
        organization=organization,
        course_ids=course_ids,
        monday=week_context["monday"],
        author=exam_author,
    )

    return render(
        request,
        "registrar/schedule.html",
        {
            "has_context": True,
            "role": role,
            "owner_label": owner_label,
            "period": period,
            "week": week_context,
            "week_days": schedule.build_week_view(slots, week_context=week_context, exams_by_day=exams_by_day),
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


# ── Registrar console (K3): web management of the academic catalogue ─────────
#
# Programs + subjects were previously creatable only via Django admin + seed.
# This is the registrar/dean-facing web console. Authorisation is self-contained
# (superuser / org owner / an admin-ish membership role) so registrar keeps no
# static import of the accounts RBAC (which would create a module cycle).


def _can_manage_registrar(user, organization) -> bool:
    """Only the org owner, an admin-ish role membership, or a superuser may manage."""
    if not getattr(user, "is_authenticated", False) or organization is None:
        return False
    if getattr(user, "is_superuser", False):
        return True
    if getattr(organization, "owner_id", None) == user.id:
        return True
    from django.apps import apps as django_apps

    Membership = django_apps.get_model("organizations", "Membership")
    return Membership.objects.filter(
        organization=organization,
        user=user,
        is_active=True,
        role__name__in=_REGISTRAR_ADMIN_ROLES,
    ).exists()


@login_required
def registrar_console(request):
    """Registrar landing: the org's programs + subjects with create/edit entries."""
    organization = getattr(request, "organization", None)
    if not _can_manage_registrar(request.user, organization):
        raise Http404  # do not leak the console to unauthorised users

    period = _current_period(organization)
    offerings = []
    if period is not None:
        offerings = list(
            CourseOffering.objects.filter(organization=organization, period=period)
            .select_related("subject", "group", "instructor")
            .order_by("subject__code")
        )

    return render(
        request,
        "registrar/console.html",
        {
            "programs": Program.objects.filter(organization=organization).order_by("name"),
            "subjects": Subject.objects.filter(organization=organization).order_by("code"),
            "curricula": (
                Curriculum.objects.filter(organization=organization)
                .select_related("program")
                .order_by("-admission_year", "program__name")
            ),
            "offerings": offerings,
            "current_period": period,
            "active_main_nav": "registrar_console",
        },
    )


def _catalogue_form_view(request, *, model, form_class, template, pk, success_msg):
    """Shared create/edit flow for a tenant-scoped catalogue model."""
    organization = getattr(request, "organization", None)
    if not _can_manage_registrar(request.user, organization):
        raise Http404

    instance = get_object_or_404(model, pk=pk, organization=organization) if pk else None
    if request.method == "POST":
        form = form_class(request.POST, instance=instance, organization=organization)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.organization = organization
            obj.save()
            messages.success(request, success_msg)
            return redirect(reverse("registrar:console"))
    else:
        form = form_class(instance=instance, organization=organization)

    return render(
        request,
        template,
        {"form": form, "instance": instance, "active_main_nav": "registrar_console"},
    )


@login_required
def program_form_view(request, pk=None):
    """Create or edit a Program (ixtisas)."""
    return _catalogue_form_view(
        request,
        model=Program,
        form_class=ProgramForm,
        template="registrar/program_form.html",
        pk=pk,
        success_msg=_("Proqram yadda saxlanıldı."),
    )


@login_required
def subject_form_view(request, pk=None):
    """Create or edit a Subject (fənn)."""
    return _catalogue_form_view(
        request,
        model=Subject,
        form_class=SubjectForm,
        template="registrar/subject_form.html",
        pk=pk,
        success_msg=_("Fənn yadda saxlanıldı."),
    )


@login_required
def curriculum_form_view(request, pk=None):
    """Create or edit a Curriculum (tədris planı); success → its detail page."""
    organization = getattr(request, "organization", None)
    if not _can_manage_registrar(request.user, organization):
        raise Http404

    instance = get_object_or_404(Curriculum, pk=pk, organization=organization) if pk else None
    if request.method == "POST":
        form = CurriculumForm(request.POST, instance=instance, organization=organization)
        if form.is_valid():
            curriculum = form.save(commit=False)
            curriculum.organization = organization
            curriculum.save()
            messages.success(request, _("Tədris planı yadda saxlanıldı."))
            return redirect(reverse("registrar:curriculum_detail", args=[curriculum.pk]))
    else:
        form = CurriculumForm(instance=instance, organization=organization)

    return render(
        request,
        "registrar/curriculum_form.html",
        {"form": form, "instance": instance, "active_main_nav": "registrar_console"},
    )


@login_required
def curriculum_detail(request, pk):
    """A study plan's rows grouped by semester + an add-row form."""
    organization = getattr(request, "organization", None)
    if not _can_manage_registrar(request.user, organization):
        raise Http404
    curriculum = get_object_or_404(Curriculum.objects.select_related("program"), pk=pk, organization=organization)

    if request.method == "POST":
        form = CurriculumSubjectForm(request.POST, curriculum=curriculum)
        if form.is_valid():
            row = form.save(commit=False)
            row.organization = organization
            row.curriculum = curriculum
            row.save()
            messages.success(request, _("Plan sətri əlavə edildi."))
            return redirect(reverse("registrar:curriculum_detail", args=[curriculum.pk]))
    else:
        form = CurriculumSubjectForm(curriculum=curriculum)

    rows = list(
        CurriculumSubject.objects.filter(organization=organization, curriculum=curriculum)
        .select_related("subject")
        .order_by("semester_number", "order", "subject__code")
    )
    semesters: dict = {}
    for row in rows:
        semesters.setdefault(row.semester_number, []).append(row)
    semester_groups = [{"semester": num, "rows": semesters[num]} for num in sorted(semesters)]

    return render(
        request,
        "registrar/curriculum_detail.html",
        {
            "curriculum": curriculum,
            "form": form,
            "semester_groups": semester_groups,
            "total_rows": len(rows),
            "active_main_nav": "registrar_console",
        },
    )


@login_required
def curriculum_subject_delete(request, pk):
    """Remove a plan row from its curriculum."""
    row = get_object_or_404(CurriculumSubject.objects.select_related("curriculum", "organization"), pk=pk)
    organization = getattr(request, "organization", None)
    if (
        request.method == "POST"
        and organization is not None
        and row.organization_id == organization.id
        and _can_manage_registrar(request.user, organization)
    ):
        curriculum_id = row.curriculum_id
        row.delete()
        messages.success(request, _("Plan sətri silindi."))
        return redirect(reverse("registrar:curriculum_detail", args=[curriculum_id]))
    raise Http404


@login_required
def offering_form_view(request, pk=None):
    """Open (or edit) a semester offering: subject × period × group + instructor.

    On save the linked LMS course + journal scheme are ensured so the teacher's
    electronic journal is immediately usable."""
    organization = getattr(request, "organization", None)
    if not _can_manage_registrar(request.user, organization):
        raise Http404

    instance = get_object_or_404(CourseOffering, pk=pk, organization=organization) if pk else None
    if request.method == "POST":
        form = OfferingForm(request.POST, instance=instance, organization=organization)
        if form.is_valid():
            offering = form.save(commit=False)
            offering.organization = organization
            offering.save()
            # Make the offering immediately teachable: link a course + journal scheme.
            services.ensure_offering_course(offering=offering)
            gradebook.ensure_assessment_scheme(offering=offering)
            messages.success(request, _("Semestr fənni (offering) yadda saxlanıldı."))
            return redirect(reverse("registrar:console"))
    else:
        form = OfferingForm(instance=instance, organization=organization)

    return render(
        request,
        "registrar/offering_form.html",
        {"form": form, "instance": instance, "active_main_nav": "registrar_console"},
    )
