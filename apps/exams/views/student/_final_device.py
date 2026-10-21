"""Final cəhdinin cihaz bağlantısı — view qatı (təhlükəsizlik dizaynı 2026-10-08).

``final_device_guarded`` tələbənin cəhd endpoint-lərini (take səhifəsi + autosave/finish,
``question-seen``, kodlaşdırma) sarır:

* ``FinalDeviceMismatch`` (servis qatı, ``ensure_active_attempt_access`` / kilidli POST)
  → aydın mesajlı 403: səhifə üçün ``final_device_blocked.html``, AJAX üçün JSON
  (``device_blocked: true``). Audit sətri burada — tranzaksiyadan KƏNARDA — yazılır.
* bu sorğuda cəhd cihaza bağlandısa / cookie yox idisə imzalı cihaz cookie-si cavaba yazılır.
* 2026-10-13 (gecə): ``ExamNetworkDenied`` (final/midterm kənar şəbəkədən) → eyni formada
  aydın 403 (``exam_network_blocked.html`` / JSON ``network_blocked: true``) + audit.
* 2026-10-21 (sahib, sərt zal rejimi): ``HallComputerDenied`` (qeydsiz kompüter, açar
  ``exam.hall_computer_check`` açıq) → 403 xəbərdarlıq səhifəsi ``hall_computer_blocked.html``
  (giriş forması YOX, bu kompüterin öz IP/MAC-ı) / JSON ``hall_computer_blocked: true``.
"""

import functools

from django.http import JsonResponse
from django.template.response import TemplateResponse
from django.utils.translation import pgettext

from apps.exams.services.exam_center_gate import HallComputerDenied, client_address_diagnostic
from apps.exams.services.exam_network import ExamNetworkDenied, exam_network_denied_message, record_network_denial
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
    message = device_blocked_message(attempt)
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


def exam_network_blocked_response(request, exam, *, where="attempt", has_attempt=True):
    """Final/midterm kənar şəbəkədən — sual məzmunu olmayan 403 (audit tranzaksiyadan KƏNARDA)."""
    record_network_denial(request, exam, where=where)
    message = exam_network_denied_message()
    if _wants_json(request):
        return JsonResponse(
            {"success": False, "network_blocked": True, "error": message, "message": message}, status=403
        )
    response = TemplateResponse(
        request,
        "exams/student/exam_network_blocked.html",
        {
            "exam": exam,
            "message": message,
            "has_attempt": has_attempt,
            "retry_url": request.get_full_path() if request.method == "GET" else "",
        },
        status=403,
    )
    response.render()
    return response


def hall_computer_message() -> str:
    return pgettext(
        "exams.final_center.hall_computer",
        "Bu kompüter imtahan zalı kompüteri kimi qeydiyyatdan keçməyib. Final və midterm imtahanlarına yalnız "
        "imtahan zalındakı qeydiyyatlı kompüterlərdən daxil olmaq olar.",
    )


def hall_computer_blocked_response(request):
    """Qeydsiz kompüter — giriş forması OLMAYAN 403 xəbərdarlıq səhifəsi (yeni zal dizaynı) və ya JSON."""
    message = hall_computer_message()
    address = client_address_diagnostic(request)
    # Adi forma POST-u (giriş səhifəsi) HTML xəbərdarlığı görür; fetch/XHR (state, begin) JSON alır.
    accept = (request.headers.get("Accept") or "").lower()
    if request.headers.get("x-requested-with") == "XMLHttpRequest" or "application/json" in accept:
        return JsonResponse(
            {"success": False, "hall_computer_blocked": True, "error": message, "message": message}, status=403
        )
    response = TemplateResponse(
        request,
        "exams/student/hall_computer_blocked.html",
        {
            "message": message,
            "client_ip": address["ip"],
            "client_mac": address["mac"],
            "retry_url": request.get_full_path() if request.method == "GET" else "",
        },
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
        except ExamNetworkDenied as exc:
            return exam_network_blocked_response(request, exc.exam)
        except HallComputerDenied:
            return hall_computer_blocked_response(request)
        issue_device_cookie(request, response)
        return response

    return wrapper


def final_entry_network_guarded(view):
    """``/exams/final/`` view-ları: ``ExamNetworkDenied`` → aydın 403 (attempt hələ yoxdur)."""

    @functools.wraps(view)
    def wrapper(request, *args, **kwargs):
        try:
            return view(request, *args, **kwargs)
        except ExamNetworkDenied:
            return exam_network_blocked_response(request, None, where="final_entry", has_attempt=False)
        except HallComputerDenied:
            return hall_computer_blocked_response(request)

    return wrapper


__all__ = [
    "exam_network_blocked_response",
    "final_entry_network_guarded",
    "final_device_blocked_response",
    "final_device_guarded",
    "hall_computer_blocked_response",
    "hall_computer_message",
]
