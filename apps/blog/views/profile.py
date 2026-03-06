# blog/views/profile.py

from django.contrib.auth import get_user_model
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse

User = get_user_model()


def user_profile(request, username):
    """
    Legacy route redirect:
    - Own profile -> accounts profile
    - Other users -> accounts public profile
    """
    if request.user.is_authenticated and request.user.username == username:
        target_url = reverse("accounts:profile")
    else:
        # Keep existing 404 behavior when username does not exist.
        profile_user = get_object_or_404(User, username=username)
        target_url = reverse("accounts:public_profile", kwargs={"username": profile_user.username})

    query_string = request.GET.urlencode()
    if query_string:
        target_url = f"{target_url}?{query_string}"

    return redirect(target_url)
