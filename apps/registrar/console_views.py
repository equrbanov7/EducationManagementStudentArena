"""Registrar console (K3) — web management of the academic catalogue.

Programs, subjects, curricula (study plans), semester offerings and student
assignments were previously creatable only via Django admin + seed. This is the
registrar/dean-facing web console. Authorisation is self-contained (superuser /
org owner / an admin-ish membership role) so registrar keeps no static import of
the accounts RBAC (which would create a module cycle). Every view is
tenant-scoped (``request.organization`` + ``organization=`` filters) and
IDOR-safe (cross-tenant objects 404).
"""

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _

from . import gradebook, services
from .forms import (
    CurriculumForm,
    CurriculumSubjectForm,
    OfferingForm,
    ProgramForm,
    StudentRecordForm,
    SubjectForm,
)
from .models import (
    CourseOffering,
    Curriculum,
    CurriculumSubject,
    Program,
    StudentAcademicRecord,
    Subject,
)
from .views import _current_period

# Roles that may manage the registrar catalogue (besides superuser + org owner).
_REGISTRAR_ADMIN_ROLES = ("org_admin", "org_owner", "rector", "vice_rector", "dean")


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
            "student_records": (
                StudentAcademicRecord.objects.filter(organization=organization)
                .select_related("student", "program", "group")
                .order_by("-created_at")[:25]
            ),
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


@login_required
def student_record_form_view(request, pk=None):
    """Assign a student to a program/curriculum/group; optionally auto-enroll them
    in the current semester's mandatory subjects."""
    organization = getattr(request, "organization", None)
    if not _can_manage_registrar(request.user, organization):
        raise Http404

    instance = get_object_or_404(StudentAcademicRecord, pk=pk, organization=organization) if pk else None
    if request.method == "POST":
        form = StudentRecordForm(request.POST, instance=instance, organization=organization)
        if form.is_valid():
            record = form.save(commit=False)
            record.organization = organization
            record.save()
            if form.cleaned_data.get("auto_enroll"):
                period = _current_period(organization)
                if period is not None:
                    semester = form.cleaned_data.get("enroll_semester") or 1
                    created = services.enroll_mandatory_subjects(record=record, period=period, semester_number=semester)
                    messages.success(
                        request,
                        _("Tələbə təyin olundu və %(n)s məcburi fənnə yazıldı.") % {"n": created},
                    )
                else:
                    messages.success(
                        request, _("Tələbə təyin olundu (aktiv semestr olmadığı üçün auto-enroll atlanıldı).")
                    )
            else:
                messages.success(request, _("Tələbə təyin olundu."))
            return redirect(reverse("registrar:console"))
    else:
        form = StudentRecordForm(instance=instance, organization=organization)

    return render(
        request,
        "registrar/student_record_form.html",
        {"form": form, "instance": instance, "active_main_nav": "registrar_console"},
    )
