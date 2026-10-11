"""Köhnə müstəqil təşkilat səhifələri → kabinet bölmələri (sahib 2026-10-11).

«Köhnə olan hissələri, səhifələri sil — ordan olmasın»: ``/organizations/<slug>/``,
``…/structure/``, ``…/structure/faculties/``, ``…/structure/kafedras/``,
``…/members/``, ``…/roles/`` və ``…/settings/`` artıq HEÇ BİR səhifə render
etmir — yalnız kabinetin (``/accounts/profile/?section=…``) uyğun bölməsinə
yönləndirir. Köhnə əlfəcinlər işləməyə davam edir.

Qayda (giriş qapısı çağıranda, fail-closed, artıq keçilib):

1. URL-dəki təşkilat aktiv deyilsə — ``organizations:switch`` kimi aktiv edilir
   (eyni ``activate_organization``) və sorğu bir dəfə ``?switched=1`` ilə özünə
   qayıdır: middleware yeni təşkilatı NÖVBƏTİ sorğuda yükləyir, bölmə qapısı
   (``allowed_sections``) isə yeni təşkilat üçün hesablanmalıdır. Qayıdışda da
   aktiv deyilsə (middleware rədd edib) — kabinetin özünə; dövrə yoxdur.
2. Namizəd bölmələrdən aktor üçün AÇIQ olan ilkinə yönləndirilir.
3. Heç biri açıq deyilsə — ``accounts:profile`` (köhnə səhifəyə geri düşmə YOXDUR).
"""

from __future__ import annotations

from django.shortcuts import redirect

from ...cabinet_links import cabinet_redirect_url, is_active_organization
from ..member.selection import activate_organization

#: Sessiyada təşkilat YENİ dəyişəndə özünə bir dəfə qayıdış markeri (dövrəni kəsir).
SWITCHED_PARAM = "switched"


def legacy_page_redirect(request, organization, sections, params=None):
    """Köhnə səhifə GET-i üçün kabinet yönləndirməsi (bax modul şərhi)."""
    if not is_active_organization(request, organization):
        if request.GET.get(SWITCHED_PARAM) == "1":
            return redirect("accounts:profile")
        activate_organization(request, organization)
        query = request.GET.copy()
        query[SWITCHED_PARAM] = "1"
        return redirect(f"{request.path}?{query.urlencode()}")

    for section in sections:
        target = cabinet_redirect_url(request, organization, section, params)
        if target:
            return redirect(target)
    return redirect("accounts:profile")


__all__ = ["SWITCHED_PARAM", "legacy_page_redirect"]
