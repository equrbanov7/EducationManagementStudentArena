"""Kabinet qapısı — məcburi sorğu doldurulmayınca tələbə kabineti ``/sorgu/``-ya yönlənir.

``FirstLoginPasswordMiddleware``-dən SONRA durur (auth → org → view-as → ilk-giriş
axını artıq həll olunub): ilk-giriş parolu sorğudan ÜSTÜNDÜR.

Kimə tətbiq olunur: YALNIZ tələbə hesabı (``student``/``lead_student`` üzvlüyü,
heyət rolu yoxdur); view-as sessiyasında, superuser/heyət üçün HEÇ VAXT.
Harada: yalnız kabinet yolları (``/accounts/profile/…`` — səhifə, bölmə fraqmenti,
form POST-ları). İstisnalar: sayğac API-si (zərərsiz sayı), parol dəyişmə bölməsi
və OTP API-si (təhlükəsizlik heç vaxt sorğu ilə bloklanmır).

Davranış: HTML → 302 ``surveys:home``; XHR/JSON → 409
``{"survey_required": true, "redirect": "/sorgu/"}``. ``grace_until``-a qədər
tələbə «Sonra doldur» ilə 24 saatlıq möhlət ala bilər; sonra qapı sərtdir.

Sorğu büdcəsi: kabinet yolu olmayan hər sorğu və açıq kampaniyası olmayan hər
təşkilat üçün SIFIR əlavə sorğu (bax ``services.gate``).
"""

from __future__ import annotations

from django.http import JsonResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone

from .services.gate import compute_state, deferral_active, student_entries


class SurveyGateMiddleware:
    CABINET_PREFIX = "/accounts/profile/"
    EXEMPT_PREFIXES = ("/accounts/profile/api/badges/", "/accounts/profile/api/password-otp/")
    EXEMPT_SECTIONS = frozenset({"change-password"})

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path_info or ""
        if not path.startswith(self.CABINET_PREFIX):
            return self.get_response(request)
        today = timezone.localdate()
        entries = student_entries(request, today)
        if not entries:
            return self.get_response(request)
        state = compute_state(request, request.organization, entries)
        request.survey_gate = state
        # Kabinet RBAC-ı (bölmə görünürlüyü, sayğac) request-siz işləyir — vəziyyət
        # istifadəçi obyektinə də bağlanır (request-ömürlü; bax public.cabinet_state).
        try:
            request.user._survey_gate_state = state
        except Exception:  # noqa: BLE001 — dəyişməz istifadəçi obyekti (nadir)
            pass
        blocking = state.blocking_campaign()
        if blocking is None or self._is_exempt(request, path):
            return self.get_response(request)
        grace_until = blocking["grace_until"]
        if grace_until and today <= grace_until and deferral_active(request, blocking["id"], today):
            return self.get_response(request)
        return self._gate_response(request)

    def _is_exempt(self, request, path) -> bool:
        if path.startswith(self.EXEMPT_PREFIXES):
            return True
        if request.GET.get("section") in self.EXEMPT_SECTIONS:
            return True
        if request.method == "POST" and request.POST.get("profile_form") in self.EXEMPT_SECTIONS:
            return True
        return False

    @staticmethod
    def _wants_json(request) -> bool:
        accept = (request.headers.get("Accept") or "").lower()
        return request.headers.get("x-requested-with") == "XMLHttpRequest" or "application/json" in accept

    def _gate_response(self, request):
        target = reverse("surveys:home")
        if self._wants_json(request):
            return JsonResponse(
                {"ok": False, "detail": "survey_required", "survey_required": True, "redirect": target},
                status=409,
            )
        return redirect(target)
