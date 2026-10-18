"""«Alt qrupa tələbə əlavə et» — AKTOR qapısı (açar ``retake.manage``; rol adı yoxlanılmır).

* açar yoxdursa → 403 (``forbidden``);
* tələbə / yerləşdirmə aktorun struktur əhatəsindən kənardır → 404 (mövcudluq sızmasın);
* «Başqasının adından» (view-as) rejimində alət YALNIZ OXUNUR — yazı endpoint-ləri 403 qaytarır.

Menyu qapısı ``_helpers/rbac_sections.py``-dadır (eyni açar); bu modul onu HƏR endpoint-də təkrarlayır, registrar
servisi isə yazıda üçüncü dəfə yoxlayır (``subgroup_placement.evaluate``).
"""

from __future__ import annotations

from dataclasses import dataclass

from django.http import JsonResponse
from django.utils.translation import pgettext

from apps.registrar.public import subgroup_access


@dataclass(frozen=True)
class PlacementActor:
    user: object
    organization: object | None
    has_access: bool
    can_write: bool
    view_as: bool


def resolve_actor(request) -> PlacementActor:
    """Sorğudan aktoru qurur; heç vaxt exception atmır (fail-closed)."""
    from apps.accounts.views._helpers.tenant import _get_active_organization

    user = getattr(request, "user", None)
    view_as = bool(getattr(request, "is_view_as", False))
    if user is None or not getattr(user, "is_authenticated", False):
        return PlacementActor(user=None, organization=None, has_access=False, can_write=False, view_as=view_as)
    organization = _get_active_organization(request)
    has_access = organization is not None and subgroup_access.has_placement_key(user, organization)
    return PlacementActor(
        user=user,
        organization=organization,
        has_access=has_access,
        can_write=has_access and not view_as,
        view_as=view_as,
    )


def forbidden() -> JsonResponse:
    return JsonResponse(
        {
            "ok": False,
            "error": "forbidden",
            "message": pgettext("accounts.subgroup_placement", "Bu alət üçün «retake.manage» səlahiyyəti lazımdır."),
        },
        status=403,
    )


def view_as_blocked() -> JsonResponse:
    return JsonResponse(
        {
            "ok": False,
            "error": "view_as",
            "message": pgettext(
                "accounts.subgroup_placement", "«Başqasının adından» rejimində yerləşdirmə edilmir — yalnız baxış."
            ),
        },
        status=403,
    )


def not_found(message=None) -> JsonResponse:
    return JsonResponse(
        {
            "ok": False,
            "error": "not_found",
            "message": str(message or pgettext("accounts.subgroup_placement", "Tapılmadı.")),
        },
        status=404,
    )


__all__ = ["PlacementActor", "forbidden", "not_found", "resolve_actor", "view_as_blocked"]
