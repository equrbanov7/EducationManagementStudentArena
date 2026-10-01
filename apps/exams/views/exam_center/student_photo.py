"""İM nəzarətçisi üçün tələbə şəkli — yalnız icazəli aktora (2026-10-01).

Ümumi ``accounts:profile_avatar`` istənilən daxil olmuş istifadəçiyə açıqdır;
imtahan monitoru isə ondan istifadə ETMİR — şəkil bu marşrutdan keçir və
``can_view_student_photo`` qaydası tətbiq olunur (tələbə yalnız öz şəklini,
nəzarətçi yalnız nəzarət etdiyi zaldakı tələbəni görür). İcazəsiz aktora
faylın mövcudluğu da bildirilmir (404, ``core.media_views`` ilə eyni prinsip).
"""

import mimetypes

from django.apps import apps as django_apps
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, Http404, HttpResponseBadRequest
from django.utils.http import http_date
from django.views.decorators.http import require_GET

from apps.exams.services.supervision.identity import can_view_student_photo
from apps.exams.views.shared.tenant import get_active_organization


@login_required
@require_GET
def proctor_student_photo(request, user_id):
    version = request.GET.get("v", "")
    if version and (not version.isdigit() or len(version) > 12):
        return HttpResponseBadRequest("Invalid version parameter.")

    organization = get_active_organization(request)
    if not can_view_student_photo(request.user, organization, user_id):
        raise Http404("Photo not found.")

    profile_model = django_apps.get_model("accounts", "UserProfile")
    profile = profile_model.objects.filter(user_id=user_id, user__is_active=True).only("avatar", "updated_at").first()
    if profile is None or not profile.avatar:
        raise Http404("Photo not found.")

    avatar = profile.avatar
    try:
        stream = avatar.storage.open(avatar.name, "rb")
    except Exception as exc:  # noqa: BLE001
        raise Http404("Photo not found.") from exc

    content_type = mimetypes.guess_type(avatar.name or "")[0] or "application/octet-stream"
    if not content_type.startswith("image/"):
        stream.close()
        raise Http404("Photo not found.")
    response = FileResponse(stream, content_type=content_type)
    response["Cache-Control"] = "private, max-age=300"
    response["Last-Modified"] = http_date(profile.updated_at.timestamp())
    response["X-Content-Type-Options"] = "nosniff"
    response["Content-Disposition"] = "inline"
    return response


__all__ = ["proctor_student_photo"]
