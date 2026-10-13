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
from django.http import FileResponse, Http404, HttpResponseBadRequest, HttpResponseNotModified
from django.utils.cache import patch_vary_headers
from django.utils.http import http_date, parse_http_date_safe
from django.views.decorators.http import require_GET

from apps.exams.services.supervision.identity import can_view_student_photo
from apps.exams.views.shared.tenant import get_active_organization

# 2026-10-13 (gecə, examphoto): yalnız raster şəkil növləri. SVG (və ya ad uzantısı dəyişdirilmiş
# fayl) öz origin-imizdən `inline` verilsəydi skript daşıya bilərdi (saxlanan XSS) — ImageField
# Pillow ilə yoxlasa da, yükləmə yolundan asılı olmayan ikinci qat burada.
_ALLOWED_TYPES = frozenset({"image/jpeg", "image/png", "image/webp", "image/gif"})


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
    content_type = mimetypes.guess_type(avatar.name or "")[0] or ""
    if content_type not in _ALLOWED_TYPES:
        raise Http404("Photo not found.")

    # 2026-10-13 (gecə, perf): imtahan səhifəsi şəkli başlıq çipi + yan kartda göstərir, hər
    # reload-da 5 dəqiqəlik keş bitəndə fayl yenidən axıdılırdı. İcazə YOXLANANDAN SONRA
    # If-Modified-Since → 304 (fayl açılmır, bayt göndərilmir).
    last_modified = int(profile.updated_at.timestamp())
    since = parse_http_date_safe(request.headers.get("If-Modified-Since", ""))
    if since is not None and since >= last_modified:
        not_modified = HttpResponseNotModified()
        _private_cache_headers(not_modified, last_modified)
        return not_modified

    try:
        stream = avatar.storage.open(avatar.name, "rb")
    except Exception as exc:  # noqa: BLE001
        raise Http404("Photo not found.") from exc

    response = FileResponse(stream, content_type=content_type)
    _private_cache_headers(response, last_modified)
    response["X-Content-Type-Options"] = "nosniff"
    response["Content-Disposition"] = "inline"
    # Birbaşa açılsa belə sənəd kimi heç nə icra olunmasın.
    response["Content-Security-Policy"] = "default-src 'none'; img-src 'self'; sandbox"
    return response


def _private_cache_headers(response, last_modified):
    """Yalnız brauzer keşi (paylaşılan proxy/CDN YOX) — şəkil sessiyaya bağlıdır."""
    response["Cache-Control"] = "private, max-age=300"
    response["Last-Modified"] = http_date(last_modified)
    patch_vary_headers(response, ("Cookie",))


__all__ = ["proctor_student_photo"]
