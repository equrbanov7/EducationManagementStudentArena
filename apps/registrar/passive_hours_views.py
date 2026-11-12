"""«Passiv saat» — HTTP səthi (adi POST formu → jurnala qayıdış; sahib 2026-11-12, MR-000303).

Zəncir (fail-closed): tenant (``offering_or_404``) → bayraq/redaktor/kilid (``passive_hours.can_edit``; yoxdursa 404,
mövcudluq sızmasın) → servis. Açar (``switch``) — ``passive_hours.can_switch`` (kafedra müdiri / RİM).
Qaydalar :mod:`apps.registrar.passive_hours`-dadır. JS yoxdur (CSP-təhlükəsiz forma).
"""

from __future__ import annotations

import uuid

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.translation import pgettext
from django.views.decorators.http import require_POST

from . import passive_hours
from .journal_access import offering_or_404

_CTX = "registrar.passive_hours"


def _guarded(request, offering_id):
    offering = offering_or_404(request, offering_id)
    if not passive_hours.can_edit(request.user, offering):
        raise Http404
    return offering


def _back(offering):
    return redirect(reverse("registrar:journal_detail", args=[offering.pk]))


@login_required
@require_POST
def add(request, offering_id):
    offering = _guarded(request, offering_id)
    try:
        row = passive_hours.add(
            offering=offering,
            user=request.user,
            day=request.POST.get("date", ""),
            hours=request.POST.get("hours", ""),
            note=request.POST.get("note", ""),
        )
    except passive_hours.PassiveHourError as exc:
        messages.error(request, exc.text)
    else:
        messages.success(
            request,
            pgettext(_CTX, "Passiv saat əlavə olundu: %(date)s · %(hours)s saat.")
            % {"date": f"{row.date:%d.%m.%Y}", "hours": row.hours},
        )
    return _back(offering)


@login_required
@require_POST
def delete(request, offering_id):
    offering = _guarded(request, offering_id)
    try:
        entry_id = uuid.UUID(str(request.POST.get("entry", "")).strip())
    except (TypeError, ValueError):
        entry_id = None
    if entry_id is not None and passive_hours.remove(offering=offering, user=request.user, entry_id=entry_id):
        messages.success(request, pgettext(_CTX, "Passiv saat qeydi silindi."))
    else:
        messages.error(request, pgettext(_CTX, "Qeyd tapılmadı."))
    return _back(offering)


@login_required
@require_POST
def switch(request, offering_id):
    offering = offering_or_404(request, offering_id)
    if not passive_hours.can_switch(request.user, offering):
        raise Http404
    on = request.POST.get("on") == "1"
    passive_hours.switch(offering=offering, user=request.user, on=on)
    if on:
        messages.success(request, pgettext(_CTX, "Bu jurnalda «Passiv saat» qeydi açıldı."))
    else:
        messages.success(request, pgettext(_CTX, "Bu jurnalda «Passiv saat» qeydi bağlandı."))
    return _back(offering)


__all__ = ["add", "delete", "switch"]
