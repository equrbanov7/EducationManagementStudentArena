"""Köhnə müstəqil təşkilat səhifələrindən kabinet bölmələrinə körpü (sahib 2026-10-01).

«Bir səhifə, bir URL, kabinet qabığının içində» (bax ``accounts/views/search.py``
``_nav_targets``): ``/organizations/<slug>/``, ``…/members/`` və ``…/roles/``
indi kabinetin ``org-overview`` / ``org-members`` / ``org-roles`` bölmələrinə
yönləndirir — köhnə əlfəcinlər işləməyə davam edir.

NİYƏ RUNTIME HOOK? Bölmənin açıla bilib-bilməməsi (``allowed_sections``)
``apps.accounts``-da hesablanır, ``organizations → accounts`` importu isə
modul-sərhəd qapısında qadağandır (``scripts/module_deps.py``). Ona görə
accounts ``AppConfig.ready()``-də həlledicini QEYDİYYATDAN keçirir
(``register_student_transfer`` naxışı). Həlledici yoxdursa və ya xəta verirsə
cavab ``False``-dur (FAIL-CLOSED) — köhnə səhifə əvvəlki kimi render olunur.

Yönləndirmə YALNIZ URL-dəki təşkilat AKTİV təşkilat olanda edilir: kabinet
bölmələri aktiv təşkilat üzərində işləyir; başqa təşkilatın ``slug``-ı üçün
köhnə davranış (müstəqil səhifə) qalır.
"""

from __future__ import annotations

import logging
from urllib.parse import urlencode

from django.urls import reverse

logger = logging.getLogger(__name__)

_resolver = None


def register_cabinet_section_resolver(resolver) -> None:
    """``resolver(request, section) -> bool`` — kabinet bölməsi açıla bilərmi."""
    if not callable(resolver):
        raise TypeError("Cabinet section resolver must be callable")
    global _resolver
    _resolver = resolver


def cabinet_section_allowed(request, section: str) -> bool:
    if _resolver is None:
        return False
    try:
        return bool(_resolver(request, section))
    except Exception:  # noqa: BLE001 — körpü heç vaxt köhnə səhifəni sındırmır
        logger.exception("cabinet section resolver failed for %s", section)
        return False


def is_active_organization(request, organization) -> bool:
    active = getattr(request, "organization", None)
    return active is not None and getattr(active, "pk", None) == getattr(organization, "pk", None)


def cabinet_section_url(section: str, params=None) -> str:
    query = {"section": section}
    for key, value in (params or {}).items():
        if value not in (None, ""):
            query[key] = value
    return f"{reverse('accounts:profile')}?{urlencode(query)}"


def cabinet_redirect_url(request, organization, section: str, params=None) -> str:
    """Kabinet bölməsinin URL-i — yalnız aktiv təşkilat + bölmə icazəlidirsə; əks halda ``""``."""
    if not is_active_organization(request, organization):
        return ""
    if not cabinet_section_allowed(request, section):
        return ""
    return cabinet_section_url(section, params)


__all__ = [
    "cabinet_redirect_url",
    "cabinet_section_allowed",
    "cabinet_section_url",
    "is_active_organization",
    "register_cabinet_section_resolver",
]
