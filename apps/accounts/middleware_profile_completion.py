"""Məcburi profil məlumatları qapısı (sahib 2026-10-17).

``FirstLoginPasswordMiddleware``-dən SONRA, ``SurveyGateMiddleware``-dən ƏVVƏL durur: ilk-giriş axını (e-poçt OTP +
öz parolu) üstündür, sorğu isə məlumatlar tamamlandıqdan sonra gəlir. Siyasət (kimə, hansı sahə, kim azaddır)
YALNIZ ``apps/accounts/profile_completion.py``-dadır.

Davranış: HTML → 302 «Məlumatlarınızı tamamlayın» (GET-də ``?next=``); XHR/JSON → 403
``{"profile_completion_required": true, "redirect": …}``.

Açıq qalan yollar: səhifənin özü, çıxış, ilk-giriş / parol bərpası, view-as-dan çıxış, şəbəkə zonası izahı,
statik / media, dil seçimi, JS kataloqu, sağlamlıq ucları, admin (öz 2FA qapısı var) və canlı imtahan oyunçu
axını (QR / PIN ilə qoşulma HƏR vəziyyətdə işləməlidir — ilk-giriş qapısı ilə eyni istisna), ``/exams/``
altında isə yalnız imtahan verənin yolları (``EXAM_TAKER_URL_NAMES``).

View-as: aktor qapını view-as-a GİRƏNDƏ keçir (``view_as_start`` qapılıdır), ona görə view-as içində yoxlanmır —
hədəfin adından səhifə hədəfin məlumatını yazmamalıdır.

Sorğu büdcəsi: qapı söndürülüdürsə və ya sahələr doludursa SIFIR əlavə sorğu — profil və üzvlüklər əvvəlki
middleware-lərdə artıq yüklənib.
"""

from __future__ import annotations

from urllib.parse import urlencode

from django.http import JsonResponse
from django.shortcuts import redirect
from django.urls import NoReverseMatch, Resolver404, resolve, reverse

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
    #: ``/exmas/`` — imtahan zalında tez-tez yazılan səhv (``config/urls.legacy_exmas_redirect`` → ``/exams/…``).
    EXAM_PREFIXES = ("/exams/",)
    EXAM_TYPO_PREFIXES = ("/exmas",)
    #: SEC-1 F6 / QA-2 F-12 (2026-10-17): ``/exams/`` altında YALNIZ imtahan VERƏNİN yolları açıqdır — siyahı,
    #: başla, cəhd (+ kod / proktorinq API-ləri), nəticə, final PIN girişi və gözləmə otağı. İmtahan günü cəhd heç
    #: vaxt kəsilmir (rol yoxlanmır — cəhd edən müəllim də keçir). İmtahan mərkəzi, sual bankı, müəllim idarəsi və
    #: axtarış ucları kabinetin qalanı kimi qapılıdır. ``teacher_exam_list`` (``/exams/``) yalnız yönləndirmədir.
    EXAM_TAKER_URL_NAMES = frozenset(
        {
            "teacher_exam_list",
            "student_exam_list",
            "assigned_exam_list",
            "student_exam_history",
            "exam_code_check",
            "final_exam_entry",
            "midterm_exam_entry",
            "final_exam_waiting",
            "final_exam_cancel",
            "final_exam_begin",
            "final_ticket_state",
            "start_exam",
            "take_exam",
            "question_seen",
            "exam_result",
            "coding_autosave",
            "coding_run",
            "coding_submit",
            "coding_submission_download",
            "supervision_log_incident",
            "supervision_status_api",
            "supervision_log_signal",
            "supervision_heartbeat",
            # Cəhd səhifəsi tələbənin ÖZ şəklini buradan yükləyir (nəzarətçi üçün); view öz / heyət əhatəsini yoxlayır.
            "proctor_student_photo",
        }
    )
    #: QA-1 P2 (2026-10-17): tələbənin imtahan SİYAHISI kabinet bölməsidir — ``/exams/`` və ``/exams/available/``
    #: ``?section=assigned-exams``-ə yönləndirir. Yalnız bu bölmə (səhifə + AJAX fraqmenti) qapıda dayanmır;
    #: kabinetin qalan bölmələri qapılı qalır (``my-exams`` — müəllimin idarə səhifəsidir, qapılıdır).
    EXAM_CABINET_SECTIONS = ("assigned-exams",)

    def __init__(self, get_response):
        self.get_response = get_response
        self._exempt_paths = None
        self._exempt_prefixes = None
        self._profile_path = None
        self._exam_section_paths = frozenset()

    def __call__(self, request):
        user = getattr(request, "user", None)
        if user is None or not getattr(user, "is_authenticated", False):
            return self.get_response(request)
        if getattr(request, "is_view_as", False) or not policy.gate_enabled():
            return self.get_response(request)
        path = request.path_info or request.path
        if self._is_exempt_path(path) or self._is_exam_cabinet_section(request, path):
            return self.get_response(request)
        if policy.skipped_in_session(request):
            # «Hələlik keç» — yalnız bu sessiya; növbəti girişdə səhifə yenə gəlir.
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
        try:
            self._profile_path = reverse("accounts:profile")
            self._exam_section_paths = frozenset(
                reverse("accounts:profile_section_fragment", kwargs={"section": section})
                for section in self.EXAM_CABINET_SECTIONS
            )
        except NoReverseMatch:  # pragma: no cover — kabinet marşrutu yoxdursa istisna da yoxdur
            self._profile_path, self._exam_section_paths = None, frozenset()
        self._exempt_paths = frozenset(paths)
        self._exempt_prefixes = tuple(prefixes)

    def _is_exam_cabinet_section(self, request, path: str) -> bool:
        """Kabinetin imtahan siyahısı bölməsi (``?section=assigned-exams`` və ya onun AJAX fraqmenti)."""
        if request.method not in ("GET", "HEAD"):
            return False
        self._resolve()
        if path in self._exam_section_paths:
            return True
        return path == self._profile_path and (request.GET.get("section") or "") in self.EXAM_CABINET_SECTIONS

    def _is_exempt_path(self, path: str) -> bool:
        if path.startswith(_STATIC_EXEMPT_PREFIXES):
            return True
        if path == self.LIVE_PIN_ENTRY_PATH or path.startswith(self.LIVE_PLAYER_PREFIXES):
            return True
        if path.startswith(self.EXAM_TYPO_PREFIXES) or path == "/exams":
            return True  # yalnız yönləndirmədir — hədəf yol ``/exams/…`` kimi ayrıca yoxlanılır
        if path.startswith(self.EXAM_PREFIXES):
            # 2026-10-17 tövsiyə: imtahan (başla / cəhd / final gözləmə otağı) heç vaxt bu qapıda dayanmır —
            # məlumat sonra kabinetdə tamamlanır. Heyətin imtahan idarə yolları isə qapılıdır (SEC-1 F6).
            return self._is_exam_taker_path(path)
        try:
            self._resolve()
        except Exception:  # noqa: BLE001 — URLconf hazır deyil (başlanğıc) → bloklama
            return True
        return path in self._exempt_paths or path.startswith(self._exempt_prefixes)

    def _is_exam_taker_path(self, path: str) -> bool:
        try:
            match = resolve(path)
        except Resolver404:
            # Review 2026-10-17 (P1): ``/exams/final`` (sonda «/» yoxdur) həll olunmur — tələbə zalda əl ilə yazır.
            # Naməlum yol onsuz da 404-dür, APPEND_SLASH yönləndirməsinin hədəfi isə ayrıca düzgün yoxlanılır.
            return True
        except Exception:  # noqa: BLE001 — URLconf hazır deyil → imtahanı bloklama
            return True
        return match.namespace == "exams" and match.url_name in self.EXAM_TAKER_URL_NAMES

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
