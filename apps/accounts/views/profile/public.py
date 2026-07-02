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

from ... import profile_hooks
from ...models import UserProfile

User = get_user_model()


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
        **posts_result["context"],
    }
    return render(request, "accounts/public_profile.html", context)
