"""Profil örtüyü (sidebar) template tag-ləri.

Standalone səhifələr (məs. sual göndərişi workbench-i) profil sidebar-ını sol
tərəfdə saxlaya bilsin deyə: sidebar-ı öz kontekstini HESABLAYARAQ render edir
(cross-app Python importu yoxdur — tag accounts app-ındadır). Badge sayğacları
verilmirsə şablonda sadəcə göstərilmir (Django yoxdur → boş).
"""

from django import template
from django.urls import reverse

from apps.accounts.models import UserProfile
from apps.accounts.views._helpers.rbac import _role_capabilities

register = template.Library()


@register.inclusion_tag("accounts/profile/_sidebar.html", takes_context=True)
def profile_sidebar(context, active_section=""):
    """Profil sidebar-ını verilmiş aktiv bölmə ilə render edir (standalone
    səhifələr üçün). Sidebar keçidləri tam URL-lərdir → profil səhifəsinə naviqasiya."""
    request = context.get("request")
    user = getattr(request, "user", None)
    profile = getattr(user, "profile", None)
    if profile is None and user is not None:
        profile = UserProfile.objects.filter(user=user).first()
    capabilities = _role_capabilities(user, profile)

    unread = 0
    try:
        from apps.notifications.public import get_unread_count

        unread = get_unread_count(user=user)
    except Exception:  # noqa: BLE001 — bildiriş sayğacı sidebar-ı bloklamamalıdır
        unread = 0

    return {
        "request": request,
        "role_capabilities": capabilities,
        "allowed_sections": capabilities.get("allowed_sections", []),
        "active_section": active_section,
        "profile_base_url": reverse("accounts:profile"),
        "notifications_unread_count": unread,
    }
