"""«Lab qrupları» — HTTP səthi (sahib 2026-11-06; 2026-11-07 kabinet bölməsinə köçdü).

Sahib 2026-11-07: «sidebarda qruplar olan yerdə yerləşsin … belə yox» — idarəetmə artıq kabinetin «Lab qrupları»
bölməsidir (``?section=lab-groups``; jurnal seçimi :mod:`apps.registrar.lab_groups_section`). Bu modul:

* :func:`action` — bölmənin JSON yazı endpoint-i (``POST /jurnal/<id>/lab-qruplari/emel/``): yaratmaq, ad,
  yerləşdirmək / köçürmək / qrupsuz etmək, silmək. ``/jurnal/`` altında qalır ki, şəbəkə zonası qaydası (jurnal
  yalnız daxili şəbəkədən) köhnə ekranla EYNİ olsun;
* :func:`manage` — köhnə ünvan: GET kabinet bölməsinə yönləndirir (jurnal öncədən seçilmiş), POST köhnə formalar
  üçün işləyir və yenə bölməyə qayıdır.

Zəncir (fail-closed): tenant (``offering_or_404`` → 404) → səlahiyyət (:func:`lab_groups_manage.can_manage`;
yoxdursa **403**) → siyahı qapısı (bağlı jurnal / keçmiş dövr → 409, heç nə yazılmır) → servis. Domen məntiqi
:mod:`apps.registrar.lab_groups_manage`-dədir.
"""

from __future__ import annotations

import uuid
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.translation import pgettext
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from . import lab_groups
from . import lab_groups_manage as service
from .journal_access import offering_or_404

_CTX = "registrar.lab_groups"
#: Kabinet bölməsinin açarı (``apps/accounts`` — ``?section=lab-groups``).
SECTION = "lab-groups"
#: «Qrupsuz et» seçiminin dəyəri (POST ``target``).
UNASSIGN = "none"
SUCCESS, INFO = "success", "info"


def section_url(offering=None) -> str:
    """Kabinet bölməsinin ünvanı; ``offering`` verilibsə jurnal öncədən seçilir."""
    params = {"section": SECTION}
    if offering is not None:
        params["lg_offering"] = str(offering.pk)
    return f"{reverse('accounts:profile')}?{urlencode(params)}"


def _uuids(values) -> list:
    found = []
    for value in values:
        try:
            found.append(uuid.UUID(str(value or "").strip()))
        except (TypeError, ValueError, AttributeError):
            continue
    return found


def _create(request, offering) -> list:
    number = service.create_group(offering=offering, actor=request.user, name=request.POST.get("name"), request=request)
    message = pgettext(_CTX, "«%(label)s» qrupu yaradıldı — tələbələri aşağıda yerləşdirin.")
    return [(SUCCESS, message % {"label": lab_groups.label(number, offering)})]


def _rename(request, offering) -> list:
    number = service.parse_number(request.POST.get("group"))
    changed = service.rename_group(
        offering=offering, number=number, name=request.POST.get("name"), actor=request.user, request=request
    )
    if not changed:
        return [(INFO, pgettext(_CTX, "Ad dəyişmədi."))]
    message = pgettext(_CTX, "Qrupun adı yeniləndi: %(label)s.")
    return [(SUCCESS, message % {"label": lab_groups.label(number, offering)})]


def _assign(request, offering) -> list:
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
    result = []
    if counts["moved"]:
        where = lab_groups.label(target, offering) if target else pgettext(_CTX, "Qrupsuz")
        message = pgettext(_CTX, "%(n)s tələbə yerləşdirildi: %(group)s.")
        result.append((SUCCESS, message % {"n": counts["moved"], "group": where}))
    if not result:
        result.append((INFO, pgettext(_CTX, "Seçilən tələbələr artıq bu qrupdadır.")))
    return result


def _delete(request, offering) -> list:
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
    return [(SUCCESS, message % {"label": label, "n": freed})]


_ACTIONS = {"create": _create, "rename": _rename, "assign": _assign, "delete": _delete}


def _managed_offering(request, offering_id):
    offering = offering_or_404(request, offering_id)
    if not service.can_manage(request.user, offering):
        raise PermissionDenied
    return offering


def _run(request, offering) -> tuple[int, dict]:
    """Əməli icra et: ``(HTTP status, JSON gövdəsi)`` — həm JSON endpoint-i, həm köhnə forma işlədir."""
    handler = _ACTIONS.get(request.POST.get("action") or "")
    if handler is None:
        return 400, {"ok": False, "error": "unknown_action", "message": pgettext(_CTX, "Naməlum əməl.")}
    blocked = service.block_reason(offering)
    if blocked:
        return 409, {"ok": False, "error": "blocked", "message": blocked}
    try:
        result = handler(request, offering)
    except service.LabGroupManageError as exc:
        return 400, {"ok": False, "error": exc.code, "message": exc.message}
    return 200, {"ok": True, "messages": [{"level": level, "text": text} for level, text in result]}


@never_cache
@login_required
@require_POST
def action(request, offering_id):
    """Kabinet bölməsinin yazı endpoint-i (JSON)."""
    offering = _managed_offering(request, offering_id)
    status, payload = _run(request, offering)
    return JsonResponse(payload, status=status)


@never_cache
@login_required
def manage(request, offering_id):
    """Köhnə ünvan (/jurnal/<id>/lab-qruplari/): bölməyə yönləndirir; köhnə POST formaları da işləyir."""
    offering = _managed_offering(request, offering_id)
    if request.method == "POST":
        _status, payload = _run(request, offering)
        if payload["ok"]:
            for item in payload["messages"]:
                getattr(messages, item["level"])(request, item["text"])
        else:
            messages.error(request, payload["message"])
    return redirect(section_url(offering))


def link_context(user, offering) -> dict:
    """Jurnal başlığındakı kiçik «Lab qrupları» keçidi (yalnız idarə edə bilənlərə) — kabinet bölməsinə aparır."""
    if not service.can_manage(user, offering):
        return {}
    return {"lab_groups_url": section_url(offering)}


__all__ = ["SECTION", "UNASSIGN", "action", "link_context", "manage", "section_url"]
