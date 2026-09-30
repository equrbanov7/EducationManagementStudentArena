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

Sorğu qurucusu (2026-09-30): eyni qapı dərc olunmuş MƏCBURİ ümumi sorğular üçün də işləyir
(``services/survey_gate.py`` — tələbə, müəllim, heyət; siyasət ``block`` / ``skip_once`` /
``defer_days``). Qapı YALNIZ kabinetdir (``/accounts/profile/…``): imtahan axını (``/exams/``,
``/live/``), çıxış, ``/sorgu/`` səhifələri, statik fayllar, sağlamlıq ucu, parol bərpası heç vaxt
bağlanmır; kabinet içində parol dəyişmə bölməsi və «Mənə təyin edilmiş imtahanlar» bölməsi də
istisnadır — imtahana gedən tələbə sorğu ilə dayandırılmır.
"""

from __future__ import annotations

from django.http import JsonResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone

from .services import survey_gate
from .services.gate import compute_state, deferral_active, student_entries


class SurveyGateMiddleware:
    CABINET_PREFIX = "/accounts/profile/"
    EXEMPT_PREFIXES = ("/accounts/profile/api/badges/", "/accounts/profile/api/password-otp/")
    #: «Mənə təyin edilmiş imtahanlar» (2026-09-30): imtahan girişi sorğu ilə bağlanmır.
    #: Təhlükəsizlik baxışı 2026-09-30 (M5): qapı indi müəllim/heyətə də aiddir — imtahanı
    #: İDARƏ edən bölmələr (PIN, zal, bal girişi, imtahanlarım, şans, apellyasiya statistikası)
    #: və parol sıfırlama da məcburi sorğu ilə bağlanmır.
    EXEMPT_SECTIONS = frozenset(
        {
            "change-password",
            "assigned-exams",
            "account-password-reset",
            "appeal-stats",
            "exam-center-pins",
            "exam-center-stats",
            "exam-chance",
            "exam-score-entry",
            "my-exams",
            "superadmin-exam-rooms",
            "unit-exams",
        }
    )
    SECTION_API_PREFIX = "/accounts/profile/api/sections/"

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path_info or ""
        if not path.startswith(self.CABINET_PREFIX):
            return self.get_response(request)
        today = timezone.localdate()
        blocked = self._campaign_blocks(request, today)
        blocked = self._surveys_block(request, today) or blocked
        if not blocked or self._is_exempt(request, path):
            return self.get_response(request)
        return self._gate_response(request)

    @staticmethod
    def _campaign_blocks(request, today) -> bool:
        entries = student_entries(request, today)
        if not entries:
            return False
        state = compute_state(request, request.organization, entries)
        request.survey_gate = state
        # Kabinet RBAC-ı (bölmə görünürlüyü, sayğac) request-siz işləyir — vəziyyət
        # istifadəçi obyektinə də bağlanır (request-ömürlü; bax public.cabinet_state).
        try:
            request.user._survey_gate_state = state
        except Exception:  # noqa: BLE001 — dəyişməz istifadəçi obyekti (nadir)
            pass
        blocking = state.blocking_campaign()
        if blocking is None:
            return False
        grace_until = blocking["grace_until"]
        return not (grace_until and today <= grace_until and deferral_active(request, blocking["id"], today))

    @staticmethod
    def _surveys_block(request, today) -> bool:
        """Sorğu qurucusu (2026-09-30): məcburi ümumi sorğu (sıfır sorğu — aid sorğu yoxdursa)."""
        entries = survey_gate.generic_entries(request, today)
        if not entries:
            return False
        rows = survey_gate.compute_state(request, request.organization, entries)
        request.survey_gate_generic = rows
        try:
            request.user._survey_generic_state = rows
        except Exception:  # noqa: BLE001 — dəyişməz istifadəçi obyekti (nadir)
            pass
        return survey_gate.blocking_row(request, rows, today) is not None

    def _is_exempt(self, request, path) -> bool:
        """Parol dəyişmə HƏMİŞƏ açıqdır — amma YALNIZ həqiqətən o bölmədirsə.

        Təhlükəsizlik (L-1, 2026-09-25): əvvəl istənilən kabinet yoluna ``?section=change-password``
        (və ya POST ``profile_form=change-password``) əlavə etmək qapını keçirdi — fraqment API-si
        bölməni YOLDAN oxuyur, ona görə ``/api/sections/dashboard/?section=change-password``
        ana səhifəni qaytarırdı. İndi istisna yalnız: kabinet səhifəsinin özü (``/accounts/profile/``)
        həmin parametrlə, və ya fraqment API-sinin yolu məhz ``…/api/sections/change-password/``."""
        if path.startswith(self.EXEMPT_PREFIXES):
            return True
        if path.startswith(self.SECTION_API_PREFIX):
            section = path[len(self.SECTION_API_PREFIX) :].strip("/")
            return section in self.EXEMPT_SECTIONS
        if path != self.CABINET_PREFIX:
            return False
        if request.method == "POST":
            return request.POST.get("profile_form") in self.EXEMPT_SECTIONS
        return request.GET.get("section") in self.EXEMPT_SECTIONS

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
