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

from . import gradebook
from .models import AttendanceStatus, CourseOffering, LessonKind


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
        return _handle_save_marks(request, offering)

    journal = gradebook.get_offering_journal(offering=offering)
    return render(
        request,
        "registrar/journal_detail.html",
        {
            "offering": offering,
            "journal": journal,
            "can_edit": not journal["scheme"].is_published,
            "lesson_kinds": LessonKind.choices,
            "active_main_nav": "journal",
        },
    )


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
