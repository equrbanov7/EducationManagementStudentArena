"""
Protected media download view.

Private media files (submissions, exam uploads, lab files) must only be
accessible to authenticated users. This view enforces authentication before
serving files from MEDIA_ROOT.

In production with a properly configured nginx/caddy, set the X-Accel-Redirect
header and serve files from an internal location (e.g. ``/internal_media/``).
Set ``MEDIA_ACCEL_REDIRECT_URL`` to that internal prefix (e.g. ``/internal_media``).
"""

from __future__ import annotations

import mimetypes
import posixpath

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.exceptions import SuspiciousFileOperation
from django.http import FileResponse, Http404, HttpResponse
from django.utils._os import safe_join
from django.views.decorators.http import require_GET

# Paths that are considered public and do not require authentication.
# These are served openly (blog images, course covers, etc.).
_PUBLIC_PREFIXES: tuple[str, ...] = (
    "post_images/",
    "course_covers/",
    "question_media/",
)

# Paths that always require authentication.
_PRIVATE_PREFIXES: tuple[str, ...] = (
    "avatars/",
    "course_resources/",
    "projects/submissions/",
    "exam_uploads/",
    "exam_paints/",
    "labs/",
)


def _is_private(path: str) -> bool:
    """Return True if the path prefix belongs to sensitive private storage."""
    clean = path.lstrip("/")
    return clean.startswith(_PRIVATE_PREFIXES)


@require_GET
def protected_media(request, path: str):
    """
    Serve a media file, requiring authentication for private paths.

    Supports X-Accel-Redirect for nginx: set ``MEDIA_ACCEL_REDIRECT_URL``
    in settings to the internal location prefix (e.g. ``/internal_media``).
    """
    # Sanitize to prevent path traversal
    try:
        abs_path = safe_join(str(settings.MEDIA_ROOT), path)
    except SuspiciousFileOperation:
        raise Http404("Invalid media path.")

    if _is_private(path) and not request.user.is_authenticated:
        from django.contrib.auth.views import redirect_to_login
        return redirect_to_login(request.get_full_path())

    # Support X-Accel-Redirect for production nginx setups
    accel_url = (getattr(settings, "MEDIA_ACCEL_REDIRECT_URL", None) or "").rstrip("/")
    if accel_url:
        # Delegate file serving to nginx via internal redirect.
        clean_path = posixpath.normpath(path).lstrip("/")
        response = HttpResponse()
        response["X-Accel-Redirect"] = f"{accel_url}/{clean_path}"
        response["Content-Type"] = (
            mimetypes.guess_type(path)[0] or "application/octet-stream"
        )
        response["X-Content-Type-Options"] = "nosniff"
        if _is_private(path):
            response["Cache-Control"] = "private, no-store"
        return response

    # Fall back to Django-based file serving (development / simple deployments)
    import os

    if not os.path.isfile(abs_path):
        raise Http404("Media file not found.")

    content_type = mimetypes.guess_type(abs_path)[0] or "application/octet-stream"
    response = FileResponse(open(abs_path, "rb"), content_type=content_type)
    response["X-Content-Type-Options"] = "nosniff"
    if _is_private(path):
        response["Cache-Control"] = "private, no-store"
    else:
        response["Cache-Control"] = "public, max-age=3600"
    return response
