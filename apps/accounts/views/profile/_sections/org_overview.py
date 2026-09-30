"""«Təşkilat paneli» (``org-overview``) kabinet bölməsi — sahib 2026-10-01.

Profil kartındakı «Panel» keçidi əvvəl köhnə müstəqil ``/organizations/<slug>/``
səhifəsinə aparırdı (base.html-siz, köhnə naviqasiya, 3 rəqəm). İndi panel kabinet
qabığının içindədir: kimlik (ad, növ, status, loqo, yaradılma tarixi, cari dövr),
üzv KPI-ləri (tələbə / müəllim / heyət), struktur sayları, rol paylanması, son
qoşulanlar, son üzvlük/rol dəyişiklikləri və icazəli bölmələrə sürətli keçidlər.

QAPILAR (hər vidcet ÖZ qapısı ilə — panel görünürlüyü data hüququ VERMİR):
  * bölmə: ``rbac_sections`` (təşkilat-idarəetmə bölməsi olan aktor);
  * üzv rəqəmləri / rol paylanması / son qoşulanlar: «Struktur üzvləri» reyestrinin
    giriş + əhatə qaydası (``build_overview_data`` → ``resolve_members_access``);
  * audit axını: ``audit-log`` bölməsi + audit modulunun öz ``can_view_audit`` qapısı;
  * keçidlər: yalnız ``allowed_sections``-da olan bölmələr; «Ayarlar» —
    ``can_manage_org_settings`` (səviyyə ≥ 90 + ``org.settings``).
"""

from __future__ import annotations

from django.urls import reverse
from django.utils import timezone
from django.utils.translation import pgettext, pgettext_lazy

_CTX = "organizations.overview"
SECTION = "org-overview"

#: (bölmə, ikon, başlıq, izah) — sürətli keçidlər; yalnız icazəli olanlar göstərilir.
_LINKS = (
    (
        "org-structure-tree",
        "fa-sitemap",
        pgettext_lazy(_CTX, "Universitet strukturu"),
        pgettext_lazy(_CTX, "Fakültə, kafedra və ixtisas ağacı"),
    ),
    (
        "org-faculties",
        "fa-building-columns",
        pgettext_lazy(_CTX, "Fakültələr"),
        pgettext_lazy(_CTX, "Dekanlar, kafedralar, tələbə sayı"),
    ),
    (
        "org-kafedras",
        "fa-landmark",
        pgettext_lazy(_CTX, "Kafedralar"),
        pgettext_lazy(_CTX, "Müdirlər və müəllim heyəti"),
    ),
    (
        "groups-registry",
        "fa-people-group",
        pgettext_lazy(_CTX, "Qruplar"),
        pgettext_lazy(_CTX, "Akademik qruplar və tələbələr"),
    ),
    (
        "org-members",
        "fa-users",
        pgettext_lazy(_CTX, "Üzvlər"),
        pgettext_lazy(_CTX, "Rol, vəzifə və bölmə ilə üzv reyestri"),
    ),
    ("org-roles", "fa-user-shield", pgettext_lazy(_CTX, "Rollar"), pgettext_lazy(_CTX, "Rol kataloqu və icazələr")),
    (
        "manage-roles",
        "fa-user-gear",
        pgettext_lazy(_CTX, "Rolları idarə et"),
        pgettext_lazy(_CTX, "Rol vermək və geri almaq"),
    ),
    (
        "permission-editor",
        "fa-key",
        pgettext_lazy(_CTX, "İcazələr"),
        pgettext_lazy(_CTX, "Rolların icazə açarlarını redaktə et"),
    ),
    (
        "audit-log",
        "fa-clipboard-list",
        pgettext_lazy(_CTX, "Audit jurnalı"),
        pgettext_lazy(_CTX, "Kim, nə vaxt, nəyi dəyişdi"),
    ),
)


def _section_url(section: str, **params) -> str:
    from urllib.parse import urlencode

    query = {"section": section, **{key: value for key, value in params.items() if value not in (None, "")}}
    return f"{reverse('accounts:profile')}?{urlencode(query)}"


def _status(organization) -> dict:
    if organization.is_active and organization.status == "active":
        return {"label": pgettext(_CTX, "Aktiv"), "tone": "success"}
    if organization.status == "pending":
        return {"label": pgettext(_CTX, "Gözləmədə"), "tone": "warning"}
    return {"label": pgettext(_CTX, "Dayandırılıb"), "tone": "danger"}


def _identity(organization) -> dict:
    logo_url = ""
    if getattr(organization, "logo", None):
        try:
            logo_url = organization.logo.url
        except ValueError:  # fayl yoxdur — sadəcə inisial göstərilir
            logo_url = ""
    name = organization.name or ""
    return {
        "name": name,
        "initials": "".join(part[0] for part in name.split()[:2]).upper() or "—",
        "type_label": organization.get_org_type_display(),
        "status": _status(organization),
        "logo_url": logo_url,
        "created": timezone.localtime(organization.created_at).date() if organization.created_at else None,
        "identifier": organization.organization_identifier or "",
        "website": organization.website or "",
        "email": organization.email or "",
        "phone": organization.phone or "",
        "description": organization.description or "",
    }


def _period(organization) -> dict | None:
    from apps.registrar.public import dashboard_data

    period = dashboard_data.current_period(organization)
    if period is None:
        return None
    today = timezone.localdate()
    return {
        "name": period.name,
        "year": period.academic_year,
        "start": period.start_date,
        "end": period.end_date,
        "running": dashboard_data.period_contains(period, today),
        "upcoming": period.start_date > today,
    }


def _member_tiles(members: dict, *, linkable: bool, is_org_wide: bool) -> list[dict]:
    def url(kind: str = "") -> str:
        return _section_url("org-members", om_kind=kind) if linkable else ""

    scope_note = pgettext(_CTX, "fərqli şəxs") if is_org_wide else pgettext(_CTX, "sizin əhatənizdə")
    return [
        {"key": "total", "label": pgettext(_CTX, "Üzv"), "value": members["total"], "note": scope_note, "url": url()},
        {"key": "students", "label": pgettext(_CTX, "Tələbə"), "value": members["students"], "url": url("students")},
        {"key": "teachers", "label": pgettext(_CTX, "Müəllim"), "value": members["teachers"], "url": url("teachers")},
        {
            "key": "staff",
            "label": pgettext(_CTX, "Heyət"),
            "value": members["staff"],
            "note": pgettext(_CTX, "tələbə olmayan rollar"),
            "url": url("staff"),
        },
    ]


def _structure_tiles(structure: dict, allowed_sections) -> list[dict]:
    def url(section: str) -> str:
        return _section_url(section) if section in allowed_sections else ""

    return [
        {
            "key": "faculties",
            "label": pgettext(_CTX, "Fakültə"),
            "value": structure["faculties"],
            "url": url("org-faculties"),
        },
        {
            "key": "kafedras",
            "label": pgettext(_CTX, "Kafedra"),
            "value": structure["kafedras"],
            "url": url("org-kafedras"),
        },
        {"key": "specialties", "label": pgettext(_CTX, "İxtisas"), "value": structure["specialties"], "url": ""},
        {"key": "groups", "label": pgettext(_CTX, "Qrup"), "value": structure["groups"], "url": url("groups-registry")},
    ]


def _links(request, organization, allowed_sections) -> list[dict]:
    links = [
        {
            "section": section,
            "icon": icon,
            "title": str(title),
            "body": str(body),
            "url": _section_url(section),
        }
        for section, icon, title, body in _LINKS
        if section in allowed_sections
    ]
    from apps.organizations.public import can_manage_org_settings

    if can_manage_org_settings(request.user, organization):
        links.append(
            {
                "section": "",
                "icon": "fa-sliders",
                "title": pgettext(_CTX, "Təşkilat ayarları"),
                "body": pgettext(_CTX, "Əlaqə məlumatı, ünvan və sayt"),
                "url": reverse("organizations:settings", kwargs={"slug": organization.slug}),
            }
        )
    return links


def build_org_overview_section(request, section, *, active_organization, allowed_sections, active_section):
    """``org_overview_section`` sözlüyünü yerində doldurur (yalnız aktiv bölmədə)."""
    if SECTION not in allowed_sections or active_section != SECTION:
        return section
    if active_organization is None:
        section.update({"has_access": False, "empty_title": pgettext(_CTX, "Aktiv təşkilat seçilməyib")})
        return section

    from apps.organizations.public import build_overview_data

    data = build_overview_data(request, active_organization)
    members = data["members"]
    can_open_members = "org-members" in allowed_sections and data["members_access"]
    activity = []
    if "audit-log" in allowed_sections:
        from apps.audit.public import recent_org_changes

        activity = recent_org_changes(request, limit=6)

    section.update(
        {
            "has_access": True,
            "organization": active_organization,
            "identity": _identity(active_organization),
            "period": _period(active_organization),
            "members_access": data["members_access"],
            "is_org_wide": data["is_org_wide"],
            "scope_unset": data["scope_unset"],
            "member_tiles": (
                _member_tiles(members, linkable=can_open_members, is_org_wide=data["is_org_wide"]) if members else []
            ),
            "inactive_count": members["inactive"] if members else 0,
            # Hamı son 30 gündə qoşulubsa (məs. ilk idxal) qeyd məlumat vermir — göstərilmir.
            "recent_count": members["recent"] if members and members["recent"] < members["total"] else 0,
            "inactive_url": _section_url("org-members", om_status="inactive") if can_open_members else "",
            "structure_tiles": _structure_tiles(data["structure"], allowed_sections),
            "roles": data["roles"],
            "roles_url": _section_url("org-roles") if "org-roles" in allowed_sections else "",
            "recent": data["recent"],
            "members_url": _section_url("org-members", om_sort="newest") if can_open_members else "",
            "activity": activity,
            "show_activity": "audit-log" in allowed_sections,
            "audit_url": (
                _section_url("audit-log", al_resource="rt:membership") if "audit-log" in allowed_sections else ""
            ),
            "links": _links(request, active_organization, allowed_sections),
        }
    )
    return section


__all__ = ["SECTION", "build_org_overview_section"]
