"""Nəzarət API-ləri (heartbeat / siqnal / hadisə / status) üçün ortaq cəhd qapısı (2026-10-13, gecə).

Əvvəl bu endpoint-lər yalnız cəhdin SAHİBİNİ yoxlayırdı: final/midterm cəhdinin heartbeat-i
kənar şəbəkədən də qəbul olunurdu, nəzarətçi yeni PIN verəndən sonra KÖHNƏ kompüterdəki tab
isə heartbeat/hadisə göndərməyə davam edib monitorda «canlı» görünürdü (və hadisə sayğacı ilə
yeni kompüterdəki cəhdi kilidləyə bilərdi). İndi:

* final/midterm kənar zonadan → 403 ``network_blocked`` (audit, dəqiqədə bir);
* final giriş sessiyası köhnəlib (yeni PIN verilib) → 403 ``entry_session_valid: false`` +
  ``redirect_url`` — klient giriş səhifəsinə qayıdır.

Bitmiş cəhdə toxunmur (endpoint-lərin öz «finished» cavabı qalır).
"""

from django.http import JsonResponse

from apps.exams.services.exam_network import attempt_network_allowed, exam_network_denied_message, record_network_denial


def attempt_api_gate(request, attempt, *, where: str, check_entry_session: bool = True):
    """Rədd üçün ``JsonResponse``, keçidə ``None``."""
    if attempt.is_finished:
        return None
    if not attempt_network_allowed(request, attempt):
        record_network_denial(request, attempt.exam, where=where)
        return JsonResponse({"network_blocked": True, "error": exam_network_denied_message()}, status=403)
    if check_entry_session:
        from apps.exams.services.final_center import final_attempt_entry_session_valid

        if not final_attempt_entry_session_valid(request, attempt):
            from apps.exams.services.center_exams import entry_url_for_exam

            return JsonResponse(
                {"entry_session_valid": False, "redirect_url": entry_url_for_exam(attempt.exam)}, status=403
            )
    return None


__all__ = ["attempt_api_gate"]
