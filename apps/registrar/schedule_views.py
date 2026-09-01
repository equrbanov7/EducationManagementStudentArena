"""Dərs cədvəli (U4) və akademik təqvim (U11) — müəllim/tələbə üzü.

Bu görünüşlər ``views.py``-dan ayrılıb: jurnal/ballama axını ilə ortaq heç nəyi
yoxdur (yalnız `_current_period` və redaktə hüququ köməkçilərini paylaşır) və
birlikdə modulu ölçü budcəsinin (SOFT_CAP=600) kənarında saxlayırdılar.

Təhlükəsizlik dəyişməyib: slot əlavəsi/silinməsi yalnız dərsi APARAN müəllim
(və ya org sahibi/superuser) üçündür — düzəlişçi (corrector) slot yaza bilməz.
Tenant izolyasiyası aktiv-org RLS kontekstindən gəlir.
"""

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _

from . import schedule
from .journal_access import is_direct_editor as _is_direct_editor
from .journal_access import schedule_slot_or_404 as _schedule_slot_or_404
from .models import CourseOffering, SlotKind, WeekType
from .views import _current_period


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
    if offering is None or not _is_direct_editor(request.user, offering):
        raise Http404  # only the teaching instructor / org owner may schedule (NOT the corrector)

    from django.utils.dateparse import parse_time

    try:
        weekday = int(request.POST.get("weekday") or 0)
    except (TypeError, ValueError):
        weekday = 0
    # Standart dərs saatı seçimi (üstünlük); köhnə sərbəst vaxt sahələri fallback.
    start_time, end_time = schedule.parse_time_slot(request.POST.get("time_slot"))
    if start_time is None:
        start_time = parse_time(request.POST.get("start_time") or "")
        end_time = parse_time(request.POST.get("end_time") or "")
    week_type = request.POST.get("week_type")
    if week_type not in dict(WeekType.choices):
        week_type = WeekType.ALL
    slot_kind = request.POST.get("slot_kind")
    if slot_kind not in dict(SlotKind.choices):
        slot_kind = SlotKind.LECTURE
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
            kind=slot_kind,
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
    slot = _schedule_slot_or_404(request, slot_id)
    if request.method == "POST" and _is_direct_editor(request.user, slot.offering):
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
