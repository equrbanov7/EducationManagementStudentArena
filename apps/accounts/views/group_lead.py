"""«Starosta təyin et / dəyiş / götür» — qrup reyestri çekmecəsinin JSON endpoint-i (2026-10-13 (gecə)).

QAPI (açar + əhatə, rol adı YOX):
  * tenant: aktiv təşkilat (sessiya konteksti);
  * açar: ``unit.group_manage`` (qrup reyestrinin yazı açarı) VƏ YA ``role.assign`` (rol təyini);
  * əhatə: hədəf qrup HƏMİN açarın struktur əhatəsində görünməlidir — kənar qrup 404 (IDOR);
  * qaydalar (yalnız qrupun qeydiyyatlı tələbəsi, bir qrupda bir starosta, audit, bildiriş) xidmətdədir —
    ``services/group_lead.py``.

Əməllər (``action``): ``assign`` (``record_id`` — qrupun tələbə qeydi; köhnə starosta varsa ƏVƏZ olunur)
və ``remove``. Səbəb opsionaldır (≤500), auditə yazılır.
"""

from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.utils.translation import pgettext
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from ..services.group_lead import GroupLeadError, assign_group_lead, remove_group_lead
from ._helpers import _get_active_organization

_CTX = "accounts.group_lead"

#: Starosta təyinatına icazə verən açarlar (hər biri ÖZ əhatəsi ilə yoxlanılır).
LEAD_MANAGE_PERMISSIONS = ("unit.group_manage", "role.assign")


def lead_manage_permissions(request) -> tuple:
    """QA-2 F-03 (2026-10-17): `role.assign` yalnız tələbə tərəfi açarı ilə birlikdə sayılır — HR (`role.assign`,
    tələbə açarı YOX) starostanı nə görür, nə dəyişir. Qanuni rollar `unit.group_manage` daşıyır."""
    from apps.organizations.public import request_holds_student_key

    if request_holds_student_key(request):
        return LEAD_MANAGE_PERMISSIONS
    return tuple(permission for permission in LEAD_MANAGE_PERMISSIONS if permission != "role.assign")


def _error(message, *, status=400, code="invalid", field=""):
    payload = {"ok": False, "error": code, "message": str(message)}
    if field:
        payload["field"] = field
    return JsonResponse(payload, status=status)


def manageable_group(request, organization, group_id):
    """Aktorun starosta açarlarından BİRİNİN əhatəsində görünən aktiv qrup və ya ``None``."""
    from apps.organizations.public import get_permission_scope, visible_group

    for permission in lead_manage_permissions(request):
        scope = get_permission_scope(request.user, organization, permission, request=request)
        if not scope.has_structure_access:
            continue
        group = visible_group(organization, scope, str(group_id or ""))
        if group is not None:
            return group
    return None


def can_manage_group_leads(request, organization) -> bool:
    """Bölmə səviyyəsində düymə bayrağı (qrup üzrə yoxlama ``manageable_group``-dadır)."""
    from apps.organizations.public import get_permission_scope

    if organization is None:
        return False
    return any(
        get_permission_scope(request.user, organization, permission, request=request).has_structure_access
        for permission in lead_manage_permissions(request)
    )


@never_cache
@login_required
@require_POST
def group_lead_action(request):
    organization = _get_active_organization(request)
    if organization is None:
        return _error(pgettext(_CTX, "Aktiv təşkilat tapılmadı."), status=403, code="forbidden")
    if not can_manage_group_leads(request, organization):
        return _error(
            pgettext(_CTX, "Starosta təyin etmək üçün `unit.group_manage` və ya `role.assign` səlahiyyəti lazımdır."),
            status=403,
            code="forbidden",
        )
    group = manageable_group(request, organization, (request.POST.get("group_id") or "").strip())
    if group is None:
        return _error(pgettext(_CTX, "Qrup tapılmadı və ya əhatənizdə deyil."), status=404, code="not_found")

    action = (request.POST.get("action") or "").strip()
    reason = request.POST.get("reason") or ""
    try:
        if action == "assign":
            result = assign_group_lead(
                organization=organization,
                group=group,
                record_id=(request.POST.get("record_id") or "").strip(),
                actor=request.user,
                reason=reason,
                request=request,
            )
            lead = result["lead"]
            if result["replaced"]:
                message = pgettext(_CTX, "«%(group)s» qrupunun starostası dəyişdi: %(old)s → %(new)s.") % {
                    "group": group.name,
                    "old": ", ".join(result["replaced"]),
                    "new": lead.name,
                }
            else:
                message = pgettext(_CTX, "%(name)s «%(group)s» qrupunun starostası təyin edildi.") % {
                    "name": lead.name,
                    "group": group.name,
                }
            return JsonResponse(
                {"ok": True, "message": message, "lead": {"username": lead.username, "name": lead.name}}
            )
        if action == "remove":
            result = remove_group_lead(
                organization=organization, group=group, actor=request.user, reason=reason, request=request
            )
            message = pgettext(_CTX, "%(name)s «%(group)s» qrupunun starostası vəzifəsindən götürüldü.") % {
                "name": ", ".join(result["removed"]),
                "group": group.name,
            }
            return JsonResponse({"ok": True, "message": message, "lead": None})
    except GroupLeadError as exc:
        return _error(exc.message, status=exc.status, code=exc.code, field=exc.field)
    return _error(pgettext(_CTX, "Naməlum əməl."), code="unknown_action")


__all__ = [
    "LEAD_MANAGE_PERMISSIONS",
    "can_manage_group_leads",
    "group_lead_action",
    "lead_manage_permissions",
    "manageable_group",
]
