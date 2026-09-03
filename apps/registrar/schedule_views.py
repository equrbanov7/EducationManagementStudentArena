"""Dərs cədvəli (U4) və akademik təqvim (U11) — müəllim/tələbə üzü.

Bu görünüşlər ``views.py``-dan ayrılıb: jurnal/ballama axını ilə ortaq heç nəyi
yoxdur (yalnız `_current_period` və redaktə hüququ köməkçilərini paylaşır) və
birlikdə modulu ölçü budcəsinin (SOFT_CAP=600) kənarında saxlayırdılar.

TƏHLÜKƏSİZLİK (2026-09 dəyişikliyi): slot əlavəsi/silinməsi artıq «dərsi aparan
müəllim» qapısında DEYİL. Kanonik icazə açarı ``schedule.manage``-dir (proqram
koordinatoru, RİM, dekan, kafedra müdiri) və əhatə UNIT rollarında
``Membership.scope_unit`` alt-ağacı ilə məhdudlaşır — bax
:mod:`apps.registrar.schedule_manage`. Adi müəllim öz cədvəlini YALNIZ GÖRÜR.
Tenant izolyasiyası aktiv-org RLS kontekstindən gəlir.
"""

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _

from . import schedule_manage, schedule_manage_actions
from .journal_access import schedule_slot_or_404 as _schedule_slot_or_404
from .models import CourseOffering
from .views import _current_period


@login_required
def schedule_view(request):
    """Role-aware weekly timetable: student → group schedule, teacher → own slots.

    Slot əlavəsi/silinməsi `schedule.manage` icazəsinə bağlıdır (bax modul
    başlığı); adi müəllim burada yalnız öz həftəsini görür. Tenant scoping
    aktiv-org RLS kontekstindən gəlir; kontekst profil kabineti bölməsi ilə
    paylaşılır (page_contexts)."""
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
    """Slot əlavəsi — `schedule.manage` + əhatə + saxlama-öncəsi validasiya.

    Sahə xətaları (gün, vaxt, təkrar slot, konflikt) SAXLAMADAN ƏVVƏL tutulur və
    `messages` ilə geri qaytarılır; heç bir yarımçıq slot yazılmır.
    """
    offering = (
        CourseOffering.objects.filter(pk=request.POST.get("offering_id"), organization=organization)
        .select_related("organization", "subject", "group", "period", "instructor")
        .first()
    )
    if offering is None:
        raise Http404
    if not schedule_manage.can_manage_offering(request.user, organization, offering):
        # 403 QƏSDƏN (404 yox): açılış onsuz da aktiv tenant daxilində süzülüb —
        # gizlədiləsi bir şey yoxdur, amma «niyə olmur» sualı aydın olmalıdır.
        # Dərsin MÜƏLLİMİ də bura düşür: açar olmadan cədvələ yazmaq yoxdur.
        raise PermissionDenied

    try:
        schedule_manage_actions.create_slot(
            actor=request.user,
            organization=organization,
            offering=offering,
            data=request.POST,
            request=request,
        )
    except schedule_manage_actions.ScheduleManageError as exc:
        if exc.status == 403:
            raise PermissionDenied from exc
        for key, text in exc.errors.items():
            if key == "conflict_slot" or not isinstance(text, str):
                continue
            messages.error(request, text)
        if not exc.errors:
            messages.error(request, exc.message)
    else:
        messages.success(request, _("Dərs cədvəlinə slot əlavə edildi."))
    return _redirect_after_schedule(request)


@login_required
def schedule_slot_delete(request, slot_id):
    """Delete a slot — `schedule.manage` + struktur əhatəsi (audit + bildiriş)."""
    slot = _schedule_slot_or_404(request, slot_id)
    organization = getattr(request, "organization", None)
    if request.method != "POST":
        return _redirect_after_schedule(request)
    if not schedule_manage.can_manage_offering(request.user, organization, slot.offering):
        raise PermissionDenied
    schedule_manage_actions.delete_slot(actor=request.user, organization=organization, slot=slot, request=request)
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
