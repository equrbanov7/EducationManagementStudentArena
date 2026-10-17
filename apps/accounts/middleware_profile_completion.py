"""Məcburi profil məlumatları qapısı (sahib 2026-10-17).

``FirstLoginPasswordMiddleware``-dən SONRA, ``SurveyGateMiddleware``-dən ƏVVƏL durur: ilk-giriş axını (e-poçt OTP +
öz parolu) üstündür, sorğu isə məlumatlar tamamlandıqdan sonra gəlir. Siyasət (kimə, hansı sahə, kim azaddır)
YALNIZ ``apps/accounts/profile_completion.py``-dadır.

Davranış: HTML → 302 «Məlumatlarınızı tamamlayın» (GET-də ``?next=``); XHR/JSON → 403
``{"profile_completion_required": true, "redirect": …}``.

Açıq qalan yollar: səhifənin özü, çıxış, ilk-giriş / parol bərpası, view-as-dan çıxış, şəbəkə zonası izahı,
statik / media, dil seçimi, JS kataloqu, sağlamlıq ucları, admin (öz 2FA qapısı var) və canlı imtahan oyunçu
axını (QR / PIN ilə qoşulma HƏR vəziyyətdə işləməlidir — ilk-giriş qapısı ilə eyni istisna).

Sorğu büdcəsi: qapı söndürülüdürsə və ya sahələr doludursa SIFIR əlavə sorğu — profil və üzvlüklər əvvəlki
middleware-lərdə artıq yüklənib.
"""

from __future__ import annotations

from urllib.parse import urlencode

from django.http import JsonResponse
from django.shortcuts import redirect
from django.urls import NoReverseMatch, reverse

from . import profile_completion as policy

_STATIC_EXEMPT_PREFIXES = (
    "/static/",
    "/media/",
    "/i18n/",
    "/jsi18n/",
    "/health",
    "/ping/",
    "/metrics/",
    "/__debug__/",
    "/favicon",
    "/robots.txt",
    "/site.webmanifest",
)

#: Ad ilə açıq qalan marşrutlar (dəqiq yol).
_EXEMPT_URL_NAMES = (
    "accounts:complete_profile",
    "accounts:logout",
    "accounts:set_initial_password",
    "accounts:login",
    "accounts:staff_login",
    "accounts:student_login",
    "accounts:view_as_stop",
)

#: Bu marşrutun yolu və ALTINDAKI hər şey (``…/password-reset/done/``).
_EXEMPT_PREFIX_URL_NAMES = (("accounts:password_reset", {}),)
#: Bu marşrutun VALİDEYN qovluğu və altındakı hər şey (``/accounts/reset/<uid>/<token>/``, ``/accounts/sebeke/<x>/``).
_EXEMPT_PARENT_URL_NAMES = (
    ("accounts:password_reset_complete", {}),
    ("accounts:network_zone_denied", {"area": "x"}),
)


def _parent(path: str) -> str:
    return path.rstrip("/").rsplit("/", 1)[0] + "/"


class ProfileCompletionMiddleware:
    LIVE_PLAYER_PREFIXES = ("/live/join/", "/live/wait/", "/live/play/", "/live/state/")
    LIVE_PIN_ENTRY_PATH = "/live/"
    EXAM_PREFIXES = ("/exams/",)

    def __init__(self, get_response):
        self.get_response = get_response
        self._exempt_paths = None
        self._exempt_prefixes = None

    def __call__(self, request):
        user = getattr(request, "user", None)
        if user is None or not getattr(user, "is_authenticated", False):
            return self.get_response(request)
        if getattr(request, "is_view_as", False) or not policy.gate_enabled():
            return self.get_response(request)
        if self._is_exempt_path(request.path_info or request.path):
            return self.get_response(request)
        if not policy.missing_for_request(request):
            return self.get_response(request)
        return self._gate_response(request)

    def _resolve(self):
        if self._exempt_paths is not None:
            return
        paths, prefixes = set(), list(_STATIC_EXEMPT_PREFIXES)
        for name in _EXEMPT_URL_NAMES:
            try:
                paths.add(reverse(name))
            except NoReverseMatch:  # pragma: no cover — marşrut silinərsə sükutla keç
                continue
        for names, transform in ((_EXEMPT_PREFIX_URL_NAMES, str), (_EXEMPT_PARENT_URL_NAMES, _parent)):
            for name, kwargs in names:
                try:
                    prefixes.append(transform(reverse(name, kwargs=kwargs)))
                except NoReverseMatch:  # pragma: no cover
                    continue
        try:
            prefixes.append(reverse("admin:index"))
        except NoReverseMatch:  # pragma: no cover — admin bağlıdırsa
            pass
        self._exempt_paths = frozenset(paths)
        self._exempt_prefixes = tuple(prefixes)

    def _is_exempt_path(self, path: str) -> bool:
        if path.startswith(_STATIC_EXEMPT_PREFIXES):
            return True
        if path == self.LIVE_PIN_ENTRY_PATH or path.startswith(self.LIVE_PLAYER_PREFIXES):
            return True
        if path.startswith(self.EXAM_PREFIXES):
            # 2026-10-17 tövsiyə: imtahan (başla / cəhd / final gözləmə otağı) heç vaxt bu qapıda dayanmır —
            # məlumat sonra kabinetdə tamamlanır.
            return True
        try:
            self._resolve()
        except Exception:  # noqa: BLE001 — URLconf hazır deyil (başlanğıc) → bloklama
            return True
        return path in self._exempt_paths or path.startswith(self._exempt_prefixes)

    @staticmethod
    def _wants_json(request) -> bool:
        accept = (request.headers.get("Accept") or "").lower()
        return (
            request.headers.get("x-requested-with") == "XMLHttpRequest"
            or "application/json" in accept
            or request.headers.get("HX-Request") == "true"
        )

    def _gate_response(self, request):
        target = reverse("accounts:complete_profile")
        if self._wants_json(request):
            return JsonResponse(
                {
                    "ok": False,
                    "detail": "profile_completion_required",
                    "profile_completion_required": True,
                    "redirect": target,
                },
                status=403,
            )
        if request.method == "GET":
            next_path = request.get_full_path()
            if next_path and next_path not in ("/", reverse("accounts:profile")):
                return redirect(f"{target}?{urlencode({'next': next_path})}")
        return redirect(target)
