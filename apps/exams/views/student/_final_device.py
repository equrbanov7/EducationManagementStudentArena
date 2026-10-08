"""Final cəhdinin cihaz bağlantısı — view qatı (təhlükəsizlik dizaynı 2026-10-08).

``final_device_guarded`` tələbənin cəhd endpoint-lərini (take səhifəsi + autosave/finish,
``question-seen``, kodlaşdırma) sarır:

* ``FinalDeviceMismatch`` (servis qatı, ``ensure_active_attempt_access`` / kilidli POST)
  → aydın mesajlı 403: səhifə üçün ``final_device_blocked.html``, AJAX üçün JSON
  (``device_blocked: true``). Audit sətri burada — tranzaksiyadan KƏNARDA — yazılır.
* bu sorğuda cəhd cihaza bağlandısa / cookie yox idisə imzalı cihaz cookie-si cavaba yazılır.
"""

import functools

from django.http import JsonResponse
from django.template.response import TemplateResponse

from apps.exams.services.final_center.device_binding import (
    FinalDeviceMismatch,
    device_blocked_message,
    issue_device_cookie,
    record_device_mismatch,
)


def _wants_json(request) -> bool:
    accept = (request.headers.get("Accept") or "").lower()
    return (
        request.method != "GET"
        or request.headers.get("x-requested-with") == "XMLHttpRequest"
        or "application/json" in accept
    )


def final_device_blocked_response(request, attempt):
    record_device_mismatch(request, attempt)
    message = device_blocked_message()
    if _wants_json(request):
        return JsonResponse(
            {"success": False, "device_blocked": True, "error": message, "message": message}, status=403
        )
    response = TemplateResponse(
        request,
        "exams/student/final_device_blocked.html",
        {"exam": attempt.exam, "message": message, "retry_url": request.get_full_path()},
        status=403,
    )
    response.render()
    return response


def final_device_guarded(view):
    @functools.wraps(view)
    def wrapper(request, *args, **kwargs):
        try:
            response = view(request, *args, **kwargs)
        except FinalDeviceMismatch as exc:
            response = final_device_blocked_response(request, exc.attempt)
        issue_device_cookie(request, response)
        return response

    return wrapper


__all__ = ["final_device_blocked_response", "final_device_guarded"]
