"""«Kənardan jurnal girişi» kabinet bölməsi — panel, namizəd axtarışı və əməllər (sahib 2026-11-20).

Sahib: «sistem tənzimləmələri yerində olsun, ordan mən bunları əlavə edib çıxara bilim — profil accessini belə
kiməsə verib çıxarmaq». Bölmə «Sistem tənzimləmələri» sidebar qrupundadır; qapı onunla EYNİDİR — menyu
``_helpers/rbac_sections.py`` (RİM rəhbəri / superadmin), hər endpoint-də ``runtime_settings_admin.can_manage``
(view-as altında bağlı). Panel server-render olunur (``{% remote_journal_access_panel %}``); seçici
``EMSSearchableSelect``-dir (:func:`remote_journal_access_candidates`), əməllər JSON POST-dur
(:func:`remote_journal_access_action`) — JS xarici fayldadır.
"""

from __future__ import annotations

import json

from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.urls import reverse
from django.utils.translation import pgettext
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from apps.accounts.services import remote_journal_access as service
from apps.accounts.services import runtime_settings_admin

SECTION = "remote-journal-access"
CTX = "accounts.remote_journal_access"
PAGE_SIZE = 20
MAX_PAGE_SIZE = 50


def _organization(request):
    from ._helpers.tenant import _get_active_organization

    try:
        return _get_active_organization(request)
    except Exception:  # noqa: BLE001 — təşkilat həll olunmasa əhatə bütün sistemdir (superadmin)
        return None


def _messages() -> dict:
    return {
        "not_found": pgettext(CTX, "Hesab tapılmadı və ya aktiv deyil."),
        "not_eligible": pgettext(CTX, "Bu hesaba kənardan jurnal girişi verilə bilməz (tələbə və ya üzvlüyü yoxdur)."),
        "already": pgettext(CTX, "Bu hesab artıq siyahıdadır."),
        "not_active": pgettext(CTX, "Bu icazə artıq geri alınıb."),
    }


def _forbidden():
    return JsonResponse(
        {"ok": False, "error": "forbidden", "message": pgettext(CTX, "Bu əməl yalnız RİM rəhbəri üçündür.")},
        status=403,
    )


def _row(user, labels, *, grant=None) -> dict:
    granted_by = getattr(grant, "granted_by", None)
    return {
        "grant_id": grant.pk if grant is not None else None,
        "user_id": user.pk,
        "name": service.display_name(user),
        "username": user.username,
        "role": labels.get(user.pk, ""),
        "note": getattr(grant, "note", ""),
        "granted_by": (granted_by.get_full_name() or granted_by.username) if granted_by is not None else "",
        "granted_at": getattr(grant, "granted_at", None),
        "from_env": grant is None,
        "needs_2fa": bool(user.is_staff or user.is_superuser),
    }


def build_panel_context(request) -> dict:
    """Panel datası; qapı burada YENİDƏN yoxlanır (fail-closed)."""
    if not runtime_settings_admin.can_manage(getattr(request, "user", None), request):
        return {
            "has_access": False,
            "access_denied_message": pgettext(CTX, "Kənardan jurnal girişi yalnız RİM rəhbəri üçündür."),
        }
    organization = _organization(request)
    grants = list(service.active_grants())
    env_ids = [int(value) for value in service.env_user_ids()]
    env_users = list(get_user_model().objects.filter(pk__in=env_ids).select_related("profile").order_by("last_name"))
    labels = service.role_labels(organization, [grant.user_id for grant in grants] + [user.pk for user in env_users])
    rows = [_row(user, labels) for user in env_users] + [_row(grant.user, labels, grant=grant) for grant in grants]
    return {
        "has_access": True,
        "rows": rows,
        "count": len(rows),
        "candidates_url": reverse("accounts:remote_journal_access_candidates"),
        "action_url": reverse("accounts:remote_journal_access_action"),
        # «%(name)s» brauzerdə seçilmiş şəxsin adı ilə əvəzlənir (remote_journal_access.js).
        "grant_body": pgettext(
            CTX, "%(name)s universitet şəbəkəsindən kənarda da jurnala girə biləcək. Digər icazələri dəyişmir."
        ),
        "revoke_body": pgettext(CTX, "%(name)s jurnala yalnız universitet şəbəkəsindən girə biləcək."),
    }


def _bounds(request) -> tuple[int, int]:
    try:
        offset = max(0, int(request.GET.get("offset", 0)))
    except (TypeError, ValueError):
        offset = 0
    try:
        limit = int(request.GET.get("limit", PAGE_SIZE))
    except (TypeError, ValueError):
        limit = PAGE_SIZE
    return offset, max(1, min(limit, MAX_PAGE_SIZE))


@never_cache
@login_required
@require_GET
def remote_journal_access_candidates(request):
    """``?q=`` / ``?offset=`` / ``?limit=`` — ``{"results": [...], "has_more": bool}``."""
    if not runtime_settings_admin.can_manage(request.user, request):
        return JsonResponse({"results": [], "has_more": False}, status=403)
    offset, limit = _bounds(request)
    rows, has_more = service.candidates(
        _organization(request),
        str(request.GET.get("q", ""))[:100],
        offset=offset,
        limit=limit,
        granted_hint=pgettext(CTX, "artıq siyahıdadır"),
    )
    return JsonResponse({"results": rows, "has_more": has_more})


def _payload(request) -> dict:
    if "application/json" in (request.content_type or "").lower():
        try:
            data = json.loads(request.body.decode("utf-8") or "{}")
        except ValueError:  # UnicodeDecodeError da ValueError-dur
            data = {}
    else:
        data = {key: value for key, value in request.POST.items()}
    return data if isinstance(data, dict) else {}


@never_cache
@login_required
@require_POST
def remote_journal_access_action(request):
    """``{"action": "grant", "user": <id>, "note": "…"}`` və ya ``{"action": "revoke", "grant": <id>}``."""
    if not runtime_settings_admin.can_manage(request.user, request):
        return _forbidden()
    data = _payload(request)
    action = str(data.get("action") or "")
    organization = _organization(request)
    try:
        if action == "grant":
            record = service.grant(
                actor=request.user,
                user_id=data.get("user"),
                note=str(data.get("note") or ""),
                request=request,
                organization=organization,
            )
            message = pgettext(CTX, "%(name)s kənardan jurnala girə bilər.") % {
                "name": service.display_name(record.user)
            }
        elif action == "revoke":
            record = service.revoke(
                actor=request.user, grant_id=data.get("grant"), request=request, organization=organization
            )
            message = pgettext(CTX, "%(name)s üçün kənardan jurnal girişi geri alındı.") % {
                "name": service.display_name(record.user)
            }
        else:
            return JsonResponse(
                {"ok": False, "error": "invalid", "message": pgettext(CTX, "Naməlum əməl.")}, status=400
            )
    except service.RemoteAccessError as exc:
        return JsonResponse(
            {"ok": False, "error": exc.code, "message": _messages().get(exc.code, "")},
            status=409 if exc.code in {"already", "not_active"} else 400,
        )
    return JsonResponse({"ok": True, "message": message})


__all__ = [
    "SECTION",
    "build_panel_context",
    "remote_journal_access_action",
    "remote_journal_access_candidates",
]
