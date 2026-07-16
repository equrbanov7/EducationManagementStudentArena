"""
Public user profile view.

Renders a user's public profile: only published posts and non-confidential
profile information are exposed. Safe for anonymous visitors.

M2 (2026-07-02): post siyahısı/filtr məntiqi blog-a köçüb —
profile_hooks.public_posts_context (apps/blog/profile_sections.py).
"""

from django.contrib.auth import get_user_model
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_safe

from core.permissions import is_superadmin_user
from core.tenancy import get_request_organization

from ... import profile_hooks
from ...models import UserProfile

User = get_user_model()


def _admin_membership_for_viewer(request, profile_user):
    """
    Rol/email/qoşulma tarixi kartını yalnız haçansa göstər: baxan istifadəçi
    öz aktiv təşkilatında bu şəxsin üzvlərini görmək icazəsinə malikdirsə
    (Struktur üzvləri / Audit jurnalı üzərindən gələn admin baxışı üçün).
    """
    if not request.user.is_authenticated:
        return None

    viewer_org = get_request_organization(request)
    if viewer_org is None:
        return None

    from apps.organizations.views.shared._helpers import _can_manage_organization, _has_org_permission

    can_view_members = (
        is_superadmin_user(request.user)
        or _can_manage_organization(request.user, viewer_org)
        or _has_org_permission(request, "member.view")
    )
    if not can_view_members:
        return None

    return (
        profile_user.memberships.filter(organization=viewer_org, is_active=True)
        .select_related("role", "scope_unit")
        .order_by("-role__level")
        .first()
    )


@require_safe
def public_user_profile(request, username):
    """
    Public user profile showing only published posts and non-confidential
    profile information.
    """
    profile_user = get_object_or_404(User, username=username)

    if request.user.is_authenticated and request.user == profile_user:
        return redirect("accounts:profile")

    profile, _created = UserProfile.objects.get_or_create(user=profile_user)

    posts_result = profile_hooks.public_posts_context(request, profile_user)
    if posts_result["response"] is not None:
        return posts_result["response"]

    display_name = (f"{profile_user.first_name} {profile_user.last_name}").strip() or profile_user.username

    context = {
        "profile_user": profile_user,
        "profile": profile,
        "display_name": display_name,
        "profile_bio": (profile.bio or "").strip(),
        "profile_location": (profile.location or "").strip(),
        "admin_membership": _admin_membership_for_viewer(request, profile_user),
        **posts_result["context"],
    }
    return render(request, "accounts/public_profile.html", context)
