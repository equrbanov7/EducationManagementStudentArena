"""«Lab qrupları» ekranı — HTTP səthi (sahib 2026-11-06).

Zəncir (fail-closed): tenant (``offering_or_404`` → 404) → səlahiyyət (:func:`lab_groups_manage.can_manage`;
yoxdursa **403**) → POST-da siyahı qapısı (bağlı jurnal / keçmiş dövr — mesaj, heç nə yazılmır) → servis.
Adi HTML formları (POST → redirect + mesaj); JS yalnız rahatlıqdır (seçim sayğacı, axtarış) —
``journal_lab_groups_manage.js``. Domen məntiqi :mod:`apps.registrar.lab_groups_manage`-dədir.
"""

from __future__ import annotations

import uuid

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.translation import pgettext
from django.views.decorators.cache import never_cache

from . import lab_groups
from . import lab_groups_manage as service
from .journal_access import offering_or_404

_CTX = "registrar.lab_groups"
#: «Qrupsuz et» seçiminin dəyəri (POST ``target``).
UNASSIGN = "none"


def _uuids(values) -> list:
    found = []
    for value in values:
        try:
            found.append(uuid.UUID(str(value or "").strip()))
        except (TypeError, ValueError, AttributeError):
            continue
    return found


def _create(request, offering):
    number = service.create_group(offering=offering, actor=request.user, name=request.POST.get("name"), request=request)
    message = pgettext(_CTX, "«%(label)s» qrupu yaradıldı — tələbələri aşağıda yerləşdirin.")
    messages.success(request, message % {"label": lab_groups.label(number, offering)})


def _rename(request, offering):
    number = service.parse_number(request.POST.get("group"))
    changed = service.rename_group(
        offering=offering, number=number, name=request.POST.get("name"), actor=request.user, request=request
    )
    if changed:
        message = pgettext(_CTX, "Qrupun adı yeniləndi: %(label)s.")
        messages.success(request, message % {"label": lab_groups.label(number, offering)})
    else:
        messages.info(request, pgettext(_CTX, "Ad dəyişmədi."))


def _assign(request, offering):
    raw_target = (request.POST.get("target") or "").strip()
    if not raw_target:
        raise service.LabGroupManageError("no_target", pgettext(_CTX, "Hansı qrupa köçürüləcəyini seçin."))
    target = None if raw_target == UNASSIGN else service.parse_number(raw_target)
    counts = service.assign(
        offering=offering,
        enrollment_ids=_uuids(request.POST.getlist("enrollment")),
        target=target,
        actor=request.user,
        request=request,
    )
    if counts["moved"]:
        where = lab_groups.label(target, offering) if target else pgettext(_CTX, "Qrupsuz")
        message = pgettext(_CTX, "%(n)s tələbə yerləşdirildi: %(group)s.")
        messages.success(request, message % {"n": counts["moved"], "group": where})
    if counts["locked"]:
        message = pgettext(
            _CTX,
            "%(n)s tələbənin öz qrupunun dərslərində qeydi var — onlar köçürülmədi (qeydlər itməsin deyə).",
        )
        messages.warning(request, message % {"n": counts["locked"]})
    if not counts["moved"] and not counts["locked"]:
        messages.info(request, pgettext(_CTX, "Seçilən tələbələr artıq bu qrupdadır."))


def _delete(request, offering):
    number = service.parse_number(request.POST.get("group"))
    label = lab_groups.label(number, offering)
    freed = service.delete_group(
        offering=offering,
        number=number,
        actor=request.user,
        confirmed=request.POST.get("confirm") == "1",
        request=request,
    )
    message = pgettext(_CTX, "«%(label)s» qrupu silindi — %(n)s tələbə qrupsuz qaldı.")
    messages.success(request, message % {"label": label, "n": freed})


_ACTIONS = {"create": _create, "rename": _rename, "assign": _assign, "delete": _delete}


@never_cache
@login_required
def manage(request, offering_id):
    offering = offering_or_404(request, offering_id)
    if not service.can_manage(request.user, offering):
        raise PermissionDenied
    here = reverse("registrar:journal_lab_groups", args=[offering.pk])
    blocked = service.block_reason(offering)
    if request.method == "POST":
        handler = _ACTIONS.get(request.POST.get("action") or "")
        if handler is None:
            messages.error(request, pgettext(_CTX, "Naməlum əməl."))
        elif blocked:
            messages.error(request, blocked)
        else:
            try:
                handler(request, offering)
            except service.LabGroupManageError as exc:
                messages.error(request, exc.message)
        return redirect(here)
    context = {
        "offering": offering,
        "panel": service.panel(offering),
        "blocked_reason": blocked,
        "unassign_value": UNASSIGN,
        "journal_url": reverse("registrar:journal_detail", args=[offering.pk]),
        "active_main_nav": "journal",
    }
    return render(request, "registrar/journal_lab_groups.html", context)


def link_context(user, offering) -> dict:
    """Jurnal başlığındakı «Lab qrupları» keçidi (yalnız idarə edə bilənlərə)."""
    if not service.can_manage(user, offering):
        return {}
    return {"lab_groups_url": reverse("registrar:journal_lab_groups", args=[offering.pk])}


__all__ = ["UNASSIGN", "link_context", "manage"]
