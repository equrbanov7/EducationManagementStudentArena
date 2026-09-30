"""Organizations — owner/admin idarə səhifələri (F5 rol-skeleti, 2026-07-02)."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import pgettext

from ...cabinet_links import cabinet_redirect_url, is_active_organization
from ...models import Organization
from ..shared._helpers import (
    _can_access_organization,
    _can_manage_org_settings,
    _can_manage_organization,
    _can_view_role_matrix,
    _can_view_structure,
    _get_structure_scope,
    _is_ajax_request,
    _user_holds_org_permission,
)
from .context import (
    _create_structure_unit,
    _structure_ajax_response,
    build_organization_roles_context,
    build_organization_structure_context,
)

#: Sessiyada təşkilat YENİ dəyişəndə özünə bir dəfə qayıdış markeri (dövrəni kəsir).
_SWITCHED_PARAM = "switched"


def _can_view_org_audit(user, organization) -> bool:
    """Köhnə panelin «Son fəaliyyət» axını — audit bölməsinin qapısı ilə eyni (2026-10-01).

    Əvvəl axın təşkilatın HƏR aktiv üzvünə (tələbəyə də) göstərilirdi — başqalarının
    istifadəçi adı və əməlləri görünürdü. İndi superadmin · sahib · `audit.view`.
    """
    if getattr(user, "is_superuser", False) or getattr(user, "is_superadmin", False):
        return True
    if getattr(organization, "owner_id", None) == getattr(user, "id", None):
        return True
    return _user_holds_org_permission(user, organization, "audit.view")


@login_required
def organization_dashboard(request, slug):
    """
    Organization dashboard with stats and recent activity.

    2026-10-01 (sahib): panel kabinetin «Təşkilat paneli» (`org-overview`) bölməsinə
    köçdü. Qapı DƏYİŞMƏYİB (`_can_access_organization`) və təşkilat əvvəlki kimi
    aktiv edilir; bölmə aktor üçün açıqdırsa ora yönləndirilir, deyilsə köhnə
    səhifə render olunur (məs. menyusunda idarəetmə bölməsi olmayan üzv).
    """
    from apps.audit.models import AuditLog

    organization = get_object_or_404(Organization, slug=slug, is_active=True)

    if not _can_access_organization(request.user, organization):
        messages.error(request, pgettext("organizations.views.message", "no_org_access"))
        return redirect("organizations:select")

    # Set as active organization
    request.session["active_organization"] = organization.slug

    if is_active_organization(request, organization):
        target = cabinet_redirect_url(request, organization, "org-overview")
        if target:
            return redirect(target)
    elif request.GET.get(_SWITCHED_PARAM) != "1":
        # Təşkilat bu sorğuda dəyişdi — middleware onu NÖVBƏTİ sorğuda aktiv edir;
        # bölmə qapısı yeni təşkilat üçün hesablansın deyə bir dəfə özümüzə qayıdırıq.
        return redirect(f"{request.path}?{_SWITCHED_PARAM}=1")

    # Get stats
    stats = {
        "total_members": organization.memberships.filter(is_active=True).count(),
        "total_units": organization.units.filter(is_active=True).count(),
        "total_roles": organization.roles.filter(is_active=True).count(),
    }

    # Get recent activity from audit log (yalnız audit qapısından keçənə — bax yuxarı)
    recent_activity = []
    if _can_view_org_audit(request.user, organization):
        recent_activity = (
            AuditLog.objects.filter(organization=organization).select_related("user").order_by("-created_at")[:10]
        )

    # Get user's memberships in this org
    user_memberships = request.user.memberships.filter(organization=organization, is_active=True).select_related("role")

    context = {
        "organization": organization,
        "stats": stats,
        "recent_activity": recent_activity,
        "user_memberships": user_memberships,
    }

    return render(request, "organizations/dashboard.html", context)


@login_required
def organization_structure(request, slug):
    """
    Organization structure management with tree view of units.
    """
    organization = get_object_or_404(Organization, slug=slug, is_active=True)

    if not _can_access_organization(request.user, organization):
        messages.error(request, pgettext("organizations.views.message", "no_org_access"))
        return redirect("organizations:select")

    scope = _get_structure_scope(request, organization)

    # Struktur səhifəsi idarəetmə səhifəsidir: yalnız org-wide idarəetmə scope-u
    # və ya `unit.view` icazəsi olanlar (rektor/admin, dekan, kafedra müdürü,
    # HR, imtahan mərkəzi) görə bilər. Adi tələbənin scope_unit-i olsa belə
    # `unit.view` icazəsi olmadığı üçün bura düşmür.
    if not _can_view_structure(request, organization, scope):
        messages.error(request, pgettext("organizations.views.message", "no_org_access"))
        return redirect("organizations:dashboard", slug=organization.slug)

    form_errors = {}
    form_values = {}
    notice = ""
    if request.method == "POST":
        form_values = {
            "unit_kind": (request.POST.get("unit_kind") or "").strip(),
            "name": (request.POST.get("name") or "").strip(),
            "code": (request.POST.get("code") or "").strip(),
            "parent": (request.POST.get("parent") or "").strip(),
        }
        created, form_errors = _create_structure_unit(request, organization)
        if created:
            notice = "Struktur bölməsi yaradıldı."
            if _is_ajax_request(request):
                context = build_organization_structure_context(request, organization, notice=notice)
                return _structure_ajax_response(request, context)
            messages.success(request, notice)
            return redirect("organizations:structure", slug=organization.slug)
        if not _is_ajax_request(request):
            messages.error(
                request,
                form_errors.get("general")
                or pgettext("organizations.views.message", "Struktur bölməsi yaradıla bilmədi."),
            )

    context = build_organization_structure_context(
        request,
        organization,
        form_errors=form_errors,
        form_values=form_values,
        notice=notice,
    )
    context["org_structure_section"] = context

    if request.method == "POST" and _is_ajax_request(request):
        return _structure_ajax_response(request, context, status=400)

    return render(request, "organizations/structure.html", context)


#: Köhnə üzv səhifəsinin parametrləri → kabinet reyestrinin (`om_*`) parametrləri.
_MEMBERS_PARAM_MAP = (("search", "om_q"), ("role", "om_role"), ("members_page", "om_page"))
_MEMBERS_PARAMS = ("om_q", "om_role", "om_unit", "om_kind", "om_status", "om_sort", "om_page")


def _members_cabinet_params(request) -> dict:
    params = {new: request.GET.get(old, "") for old, new in _MEMBERS_PARAM_MAP}
    params.update({name: request.GET.get(name, "") for name in _MEMBERS_PARAMS if request.GET.get(name)})
    return params


@login_required
def organization_members(request, slug):
    """
    Member management with filters and search.

    2026-10-01 (sahib): səhifə kabinetin «Struktur üzvləri» (`org-members`) reyestrinə
    yönləndirir (köhnə `search`/`role`/`members_page` → `om_q`/`om_role`/`om_page`).
    Qapı və əhatə DƏYİŞMƏYİB — `resolve_members_access` köhnə
    `build_organization_members_context` qaydasının eynisidir. Başqa (aktiv olmayan)
    təşkilat üçün və ya bölmə menyuda yoxdursa, müstəqil səhifə EYNİ reyestri göstərir.
    """
    from ...structure_views import build_members_section, resolve_members_access

    organization = get_object_or_404(Organization, slug=slug, is_active=True)

    # Giriş qaydası:
    # - idarəetmə levli (≥80, rektor/prorektor/org admin/dekan və s.) → icazəlidir
    # - `member.view` icazəli org-scope rollar (HR, imtahan mərkəzi) → icazəlidir
    # - `member.view` icazəli unit-scoped istifadəçilər → yalnız öz alt-ağacı
    if not resolve_members_access(request, organization).has_access:
        messages.error(request, pgettext("organizations.views.message", "no_org_access"))
        return redirect("organizations:select")

    target = cabinet_redirect_url(request, organization, "org-members", _members_cabinet_params(request))
    if target:
        return redirect(target)

    section = build_members_section(request, organization)
    section["embedded_in_profile"] = False
    section["filter_base_url"] = request.path
    context = {"organization": organization, "org_members_section": section}
    return render(request, "organizations/members.html", context)


@login_required
def organization_roles(request, slug):
    """
    Role management with permission matrix.
    """
    organization = get_object_or_404(Organization, slug=slug, is_active=True)

    # Tenant girişi + KONKRET `role.view` açarı (2026-09-02 audit, P2-2):
    # `_can_manage_activity`-nin implicit `org_admin` alias-ı fakültəyə
    # scope-lanmış dekana org-genişliyində rol matrisini açırdı.
    if not _can_manage_organization(request.user, organization) or not _can_view_role_matrix(
        request.user, organization
    ):
        messages.error(request, pgettext("organizations.views.message", "no_org_access"))
        return redirect("organizations:select")

    # 2026-10-01 (sahib): qapıdan keçən aktor kabinetin «Təşkilat rolları»
    # (`org-roles`) bölməsinə yönləndirilir; süzgəc (`orl_*`) parametrləri daşınır.
    params = {key: value for key, value in request.GET.items() if key.startswith("orl_")}
    target = cabinet_redirect_url(request, organization, "org-roles", params)
    if target:
        return redirect(target)

    context = build_organization_roles_context(request, organization)
    context["filter_base_url"] = request.path  # süzgəc bu səhifədə qalsın (kabinetə atmasın)
    context["org_roles_section"] = context

    return render(request, "organizations/roles.html", context)


@login_required
def organization_settings(request, slug):
    """
    Organization settings page.
    """
    organization = get_object_or_404(Organization, slug=slug, is_active=True)

    if not _can_access_organization(request.user, organization):
        messages.error(request, pgettext("organizations.views.message", "no_org_access"))
        return redirect("organizations:select")

    is_superadmin = getattr(request.user, "is_superuser", False) or getattr(request.user, "is_superadmin", False)
    is_owner = organization.owner == request.user

    # Səviyyə (≥90) + `org.settings`; POST üçün əlavə `org.edit` — bax
    # `_can_manage_org_settings` (audit 2026-09-13 F-06, 2026-09-14).
    if not _can_manage_org_settings(request.user, organization, write=request.method == "POST"):
        messages.error(request, pgettext("organizations.views.message", "no_settings_access"))
        return redirect("organizations:dashboard", slug=slug)

    if request.method == "POST":
        # Update organization settings
        organization.description = request.POST.get("description", "")
        organization.email = request.POST.get("email", "")
        organization.phone = request.POST.get("phone", "")
        organization.address = request.POST.get("address", "")
        organization.website = request.POST.get("website", "")
        organization.save()

        messages.success(request, pgettext("organizations.views.message", "settings_updated"))
        return redirect("organizations:settings", slug=slug)

    context = {
        "organization": organization,
        "is_owner": is_owner or is_superadmin,
    }

    return render(request, "organizations/settings.html", context)
