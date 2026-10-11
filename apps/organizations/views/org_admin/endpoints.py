"""Organizations — köhnə owner/admin səhifələrinin URL-ləri (F5 rol-skeleti, 2026-07-02).

Sahib 2026-10-11: müstəqil səhifələr («İdarə Paneli · Struktur · Üzvlər · Rollar ·
Ayarlar» naviqasiyalı köhnə şablonlar) SİLİNDİ. GET artıq yalnız kabinet bölməsinə
yönləndirir (bax ``legacy_redirect.py``); giriş qapıları dəyişməyib (fail-closed).
Kabinetin istifadə etdiyi POST yolu (struktur bölməsi yaratma) qalır.
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect
from django.utils.translation import pgettext

from ...models import Organization
from ..shared._helpers import (
    _can_access_organization,
    _can_manage_organization,
    _can_view_role_matrix,
    _can_view_structure,
    _get_structure_scope,
    _is_ajax_request,
)
from .context import (
    _create_structure_unit,
    _structure_ajax_response,
    build_organization_structure_context,
)
from .legacy_redirect import legacy_page_redirect


@login_required
def organization_dashboard(request, slug):
    """Köhnə panel → kabinetin «Təşkilat paneli» (`org-overview`). Qapı: `_can_access_organization`."""
    organization = get_object_or_404(Organization, slug=slug, is_active=True)

    if not _can_access_organization(request.user, organization):
        messages.error(request, pgettext("organizations.views.message", "no_org_access"))
        return redirect("organizations:select")

    return legacy_page_redirect(request, organization, ("org-overview",))


@login_required
def organization_structure(request, slug):
    """Köhnə struktur səhifəsi → kabinetin «Universitet strukturu» (`org-structure-tree`).

    POST (kabinetin `org-structure` bölməsindəki «bölmə yarat» forması) işləməyə davam
    edir: AJAX → bölmə fraqmenti (JSON), adi POST → nəticə mesajı + kabinetə yönləndirmə.
    """
    organization = get_object_or_404(Organization, slug=slug, is_active=True)
    scope = _get_structure_scope(request, organization)

    # Struktur idarəetmədir: yalnız org-wide idarəetmə scope-u və ya `unit.view`
    # icazəsi olanlar (rektor/admin, dekan, kafedra müdürü, HR, imtahan mərkəzi).
    if not _can_view_structure(request, organization, scope):
        messages.error(request, pgettext("organizations.views.message", "no_org_access"))
        return redirect("organizations:dashboard", slug=organization.slug)

    if request.method != "POST":
        return legacy_page_redirect(request, organization, ("org-structure-tree", "org-structure"))

    form_values = {
        "unit_kind": (request.POST.get("unit_kind") or "").strip(),
        "name": (request.POST.get("name") or "").strip(),
        "code": (request.POST.get("code") or "").strip(),
        "parent": (request.POST.get("parent") or "").strip(),
    }
    created, form_errors = _create_structure_unit(request, organization)
    notice = "Struktur bölməsi yaradıldı." if created else ""
    if _is_ajax_request(request):
        if created:
            context = build_organization_structure_context(request, organization, notice=notice)
            return _structure_ajax_response(request, context)
        context = build_organization_structure_context(
            request, organization, form_errors=form_errors, form_values=form_values
        )
        return _structure_ajax_response(request, context, status=400)
    if created:
        messages.success(request, notice)
    else:
        messages.error(
            request,
            form_errors.get("general") or pgettext("organizations.views.message", "Struktur bölməsi yaradıla bilmədi."),
        )
    return redirect("organizations:structure", slug=organization.slug)


#: Köhnə üzv səhifəsinin parametrləri → kabinet reyestrinin (`om_*`) parametrləri.
_MEMBERS_PARAM_MAP = (("search", "om_q"), ("role", "om_role"), ("members_page", "om_page"))
_MEMBERS_PARAMS = ("om_q", "om_role", "om_unit", "om_kind", "om_status", "om_sort", "om_page")


def _members_cabinet_params(request) -> dict:
    params = {new: request.GET.get(old, "") for old, new in _MEMBERS_PARAM_MAP}
    params.update({name: request.GET.get(name, "") for name in _MEMBERS_PARAMS if request.GET.get(name)})
    return params


@login_required
def organization_members(request, slug):
    """Köhnə üzv səhifəsi → kabinetin «Struktur üzvləri» (`org-members`).

    Köhnə `search`/`role`/`members_page` → `om_q`/`om_role`/`om_page`. Qapı və əhatə
    DƏYİŞMƏYİB — `resolve_members_access` köhnə `build_organization_members_context`
    qaydasının eynisidir.
    """
    from ...structure_views import resolve_members_access

    organization = get_object_or_404(Organization, slug=slug, is_active=True)

    # Giriş qaydası:
    # - idarəetmə levli (≥80, rektor/prorektor/org admin/dekan və s.) → icazəlidir
    # - `member.view` icazəli org-scope rollar (HR, imtahan mərkəzi) → icazəlidir
    # - `member.view` icazəli unit-scoped istifadəçilər → yalnız öz alt-ağacı
    if not resolve_members_access(request, organization).has_access:
        messages.error(request, pgettext("organizations.views.message", "no_org_access"))
        return redirect("organizations:select")

    return legacy_page_redirect(request, organization, ("org-members",), _members_cabinet_params(request))


@login_required
def organization_roles(request, slug):
    """Köhnə rol matrisi səhifəsi → kabinetin «Təşkilat rolları» (`org-roles`)."""
    organization = get_object_or_404(Organization, slug=slug, is_active=True)

    # Tenant girişi + KONKRET `role.view` açarı (2026-09-02 audit, P2-2):
    # `_can_manage_activity`-nin implicit `org_admin` alias-ı fakültəyə
    # scope-lanmış dekana org-genişliyində rol matrisini açırdı.
    if not _can_manage_organization(request.user, organization) or not _can_view_role_matrix(
        request.user, organization
    ):
        messages.error(request, pgettext("organizations.views.message", "no_org_access"))
        return redirect("organizations:select")

    # Qapıdan keçən aktor kabinetin «Təşkilat rolları» (`org-roles`) bölməsinə
    # yönləndirilir; süzgəc (`orl_*`) parametrləri daşınır.
    params = {key: value for key, value in request.GET.items() if key.startswith("orl_")}
    return legacy_page_redirect(request, organization, ("org-roles",), params)


@login_required
def organization_settings(request, slug):
    """Köhnə «Təşkilat Ayarları» səhifəsi — sahib 2026-10-11: «köhnə hissələr olmasın».

    Səhifə kabinetin «Təşkilat paneli»nə (`org-overview`) yönləndirir; bölmə aktor üçün yoxdursa kabinetin
    özünə. POST da heç nə YAZMIR (eyni yönləndirmə). Əlaqə sahələrinin datası bazada qalır (yazı yolu yoxdur).
    """
    organization = get_object_or_404(Organization, slug=slug, is_active=True)

    if not _can_access_organization(request.user, organization):
        messages.error(request, pgettext("organizations.views.message", "no_org_access"))
        return redirect("organizations:select")

    return legacy_page_redirect(request, organization, ("org-overview",))
