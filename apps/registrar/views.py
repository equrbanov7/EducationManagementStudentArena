"""Elektron jurnal — müəllim üzü (U3, W3).

Müəllim öz tədris etdiyi offering-lərin siyahısını görür, birini seçib roster
grid-ində komponent ballarını + qayıb saatını daxil edir. Təhlükəsizlik:
``@login_required`` + hər offering üçün ``_can_edit_journal`` (müəllim / org
sahibi / superuser) + tenant-izolyasiya RLS (middleware org konteksti) → başqa
müəllimin/təşkilatın jurnalına giriş yoxdur (IDOR qorunması). Bal daxiletmə
servis qatında (``gradebook.save_journal_scores``) yenidən yoxlanır və klamplanır.
"""

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _

from . import gradebook
from .models import CourseOffering


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
    """Roster grid for one offering: view (GET) + save scores/absence (POST)."""
    offering = get_object_or_404(
        CourseOffering.objects.select_related("subject", "period", "group", "organization"),
        pk=offering_id,
    )
    if not _can_edit_journal(request.user, offering):
        raise Http404  # do not leak existence to unauthorised users

    if request.method == "POST":
        return _handle_journal_save(request, offering)

    journal = gradebook.get_offering_journal(offering=offering)
    return render(
        request,
        "registrar/journal_detail.html",
        {
            "offering": offering,
            "journal": journal,
            "can_edit": not journal["scheme"].is_published,
            "active_main_nav": "journal",
        },
    )


def _handle_journal_save(request, offering):
    """Parse the grid POST into cell/absence maps and delegate to the service."""
    scheme = gradebook.ensure_assessment_scheme(offering=offering)
    if scheme.is_published:
        messages.warning(request, _("Jurnal yekunlaşdırılıb — bal redaktəsi bağlıdır."))
        return redirect(reverse("registrar:journal_detail", args=[offering.pk]))

    cell_values: dict = {}
    absence_values: dict = {}
    for key, raw in request.POST.items():
        if key.startswith("score__"):
            # score__<enrollment_id>__<component_id>
            _prefix, enrollment_id, component_id = key.split("__", 2)
            if raw.strip() != "":
                cell_values[(enrollment_id, component_id)] = raw
        elif key.startswith("absence__"):
            _prefix, enrollment_id = key.split("__", 1)
            if raw.strip() != "":
                absence_values[enrollment_id] = raw

    written = gradebook.save_journal_scores(
        offering=offering,
        cell_values=cell_values,
        absence_values=absence_values,
        by_user=request.user,
    )
    messages.success(request, _("Jurnal yadda saxlanıldı (%(n)s bal xanası).") % {"n": written})
    return redirect(reverse("registrar:journal_detail", args=[offering.pk]))
