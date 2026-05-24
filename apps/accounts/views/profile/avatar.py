"""
Profile avatar serving view.

Serves a logged-in user's requested profile avatar through Django so that
avatar files are never exposed via a public media URL.
"""

import mimetypes

from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import FileResponse, Http404, HttpResponseBadRequest
from django.shortcuts import get_object_or_404
from django.utils.http import http_date

from ...models import UserProfile
from .search import _validate_profile_avatar_version

User = get_user_model()


@login_required
def profile_avatar(request, user_id):
    """Serve a logged-in user's requested profile avatar through Django."""
    try:
        _validate_profile_avatar_version(request.GET.get("v"))
    except ValidationError:
        return HttpResponseBadRequest("Invalid avatar version parameter.")

    target_user = get_object_or_404(User, id=user_id, is_active=True)
    target_profile = UserProfile.objects.filter(user=target_user).only("avatar", "updated_at").first()
    if not target_profile or not target_profile.avatar:
        raise Http404("Avatar tapılmadı.")

    avatar_field = target_profile.avatar
    try:
        avatar_stream = avatar_field.storage.open(avatar_field.name, "rb")
    except Exception as exc:
        raise Http404("Avatar faylı açılmadı.") from exc

    content_type = mimetypes.guess_type(avatar_field.name or "")[0] or "application/octet-stream"
    response = FileResponse(avatar_stream, content_type=content_type)
    response["Cache-Control"] = "private, max-age=300"
    response["Last-Modified"] = http_date(target_profile.updated_at.timestamp())
    response["X-Content-Type-Options"] = "nosniff"
    return response
