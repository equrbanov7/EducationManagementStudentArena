"""Kabinet bölməsinin aktor üçün açıq olub-olmadığı — təşkilat körpüsünün həlledicisi.

``apps.organizations.cabinet_links`` köhnə ``/organizations/<slug>/…`` səhifələrini
kabinet bölmələrinə yönləndirməzdən əvvəl bunu soruşur (bax ``AccountsConfig.ready``).
Cavab profil qabığının ÖZ qapısıdır (``_role_capabilities(...)["allowed_sections"]``) —
yəni yönləndirmə heç vaxt «icazəniz yoxdur» xəbərdarlığına aparmır.
"""

from __future__ import annotations


def cabinet_section_allowed(request, section: str) -> bool:
    user = getattr(request, "user", None)
    if user is None or not getattr(user, "is_authenticated", False):
        return False
    from .profile_load import _load_user_profile
    from .rbac import _role_capabilities

    profile, _created = _load_user_profile(user)
    return section in _role_capabilities(user, profile)["allowed_sections"]


__all__ = ["cabinet_section_allowed"]
