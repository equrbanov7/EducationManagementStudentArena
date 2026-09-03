"""Profil «applications» bölməsi — «Müraciətlərim».

Panel profil shell-inin İÇİNDƏ açılır (sol sidebar qalır, fraqment sağdadır).
Ekran SPA-dır: server yalnız ÇƏRÇİVƏNİ (bayraqlar + endpoint URL-ləri + kontekst
zolağının mətnləri) verir, sətirlər/detal/KPI-lar JSON API-dən gəlir.

Domen məntiqi ``apps.applications``-dadır və bura YALNIZ public fasaddan gəlir
(``build_applications_context`` / ``handled_unit_names``) — modul sərhədi
pozulmur.

──────────────────────────────────────────────────────────────────────────────
CONTEXT MÜQAVİLƏSİ (şablon buna söykənir — açar adları dəyişməz)
──────────────────────────────────────────────────────────────────────────────
``applications_section`` (dict):

    has_access   bool  — bölmə aktiv təşkilat kontekstində qurula bildi
    family       str   — "student" | "teacher" | "staff" | ""
    can_create   bool  — «Yeni müraciət» düyməsi + «Müraciətlərim» tabı
    is_handler   bool  — «Mənə gələnlər» / «İzlədiklərim» tabları
    can_manage   bool  — `application.manage` (yalnız oxu genişlənməsi)
    endpoints    dict  — list/catalog/kpis/create/detail/action
    rules        dict  — min_subject_length / min_body_length / min_note_length
    who          str   — kontekst zolağının sol adı (kabinet və ya şöbə adları)
    scope        str   — kontekst zolağının izahı
    role_label   str   — sağdakı rol pill-i (AZ-a çevrilmiş Role.display_name)
    i18n         dict  — JS mətn kataloqu (`json_script` ilə DOM-a düşür)
"""

from django.utils.translation import pgettext

_CTX = "accounts.applications"


def _cabinet_label(family: str) -> str:
    """Kontekst zolağının «kim baxır» mətni (dizayn §4.1)."""
    if family == "student":
        return pgettext(_CTX, "Tələbə kabineti")
    if family == "teacher":
        return pgettext(_CTX, "Müəllim kabineti")
    if family == "staff":
        return pgettext(_CTX, "Əməkdaş kabineti")
    return pgettext(_CTX, "Kabinet")


def _role_label(user, organization) -> str:
    """Aktiv üzvlüyün ən yüksək rolu — yalnız GÖRÜNTÜ üçün (qapı DEYİL)."""
    from apps.organizations.public import get_active_memberships

    membership = (
        get_active_memberships(user, organization)
        .filter(organization=organization)
        .select_related("role")
        .order_by("-role__level")
        .first()
    )
    if membership is None:
        return ""
    from core.roles import resolve_seeded_role_label

    return str(resolve_seeded_role_label(membership.role.name, membership.role.display_name) or "")


def build_applications_section(
    request,
    section: dict,
    *,
    active_organization=None,
    allowed_sections=None,
    active_section=None,
):
    """``applications_section`` sözlüyünü yerində doldurur."""
    if active_organization is None:
        section["has_access"] = False
        return section

    from apps.applications.public import build_applications_context, handled_unit_names

    from .applications_i18n import build_applications_i18n

    payload = build_applications_context(request, organization=active_organization)
    section.update(
        {
            "has_access": True,
            "family": payload.get("family") or "",
            "can_create": bool(payload.get("can_create")),
            "is_handler": bool(payload.get("is_handler")),
            "can_manage": bool(payload.get("can_manage")),
            "endpoints": payload.get("endpoints") or {},
            "rules": payload.get("rules") or {},
            "role_label": _role_label(request.user, active_organization),
            "i18n": build_applications_i18n(),
        }
    )

    if section["is_handler"]:
        names = handled_unit_names(request.user, active_organization)
        section["who"] = " · ".join(names) if names else pgettext(_CTX, "Şöbə")
        section["scope"] = pgettext(_CTX, "şöbəyə gələn müraciətlər")
    else:
        section["who"] = _cabinet_label(section["family"])
        section["scope"] = pgettext(_CTX, "öz müraciətlərim")
    return section


__all__ = ["build_applications_section"]
