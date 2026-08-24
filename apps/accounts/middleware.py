"""
Custom middleware for session management and auto-logout.
"""

import logging
from datetime import datetime

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import SESSION_KEY, logout
from django.http import HttpResponseRedirect
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone

logger = logging.getLogger(__name__)

POST_LOGIN_REDIRECT_GUARD_SESSION_KEY = "post_login_redirect_guard"


class SessionTimeoutMiddleware:
    """
    Automatically log users out after a period of inactivity.

    Performance note: the ``last_activity`` timestamp is only written back to
    the session at most once every ``SESSION_ACTIVITY_WRITE_INTERVAL`` seconds.
    Writing it on every request marked the session dirty on every authenticated
    hit, forcing a session save (a DB write under db/cached_db backends) for
    each request and serialising authenticated traffic under load. Throttling
    the write keeps inactivity enforcement accurate (the stored value is at most
    one interval stale against a multi-hour timeout) while removing that
    per-request write.
    """

    def __init__(self, get_response):
        self.get_response = get_response
        self.timeout_seconds = settings.SESSION_INACTIVITY_TIMEOUT
        self.write_interval = getattr(settings, "SESSION_ACTIVITY_WRITE_INTERVAL", 300)

    def __call__(self, request):
        # Backend siyahısından çıxarılmış köhnə/bypass backend sessiyası Django
        # tərəfindən anonymous kimi yüklənir, amma auth açarları sessiyada qala
        # bilər. Onları request view-a çatmamış tam sil.
        if not request.user.is_authenticated and SESSION_KEY in request.session:
            logout(request)
            return self.get_response(request)
        if request.user.is_authenticated:
            from .identity import user_access_is_staged

            if user_access_is_staged(request.user):
                logout(request)
                return self.get_response(request)
            now = timezone.now()
            last_activity = request.session.get("last_activity")

            if last_activity:
                if isinstance(last_activity, str):
                    try:
                        last_activity = datetime.fromisoformat(last_activity)
                    except ValueError:
                        last_activity = None

            if last_activity:
                seconds_since_activity = (now - last_activity).total_seconds()
                if seconds_since_activity > self.timeout_seconds:
                    # Session expired through inactivity → log the user out.
                    logout(request)
                elif seconds_since_activity >= self.write_interval:
                    # Refresh the timestamp only once per interval to avoid a
                    # session write on every request.
                    request.session["last_activity"] = now.isoformat()
            else:
                # First authenticated request (or unparseable value): seed it.
                request.session["last_activity"] = now.isoformat()

        response = self.get_response(request)
        return response


class PostLoginRedirectGuardMiddleware:
    """
    Redirect the very first post-login 403/404 page back to a safe home URL.

    This protects users from stale ``next=`` URLs that belonged to another
    session/user and would otherwise land on a dead-end error page right after
    successful authentication.
    """

    _REDIRECTING_STATUSES = {301, 302, 303, 307, 308}
    _GUARDED_STATUSES = {403, 404}

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        if not self._should_guard(request, response):
            if self._should_clear_guard(response):
                request.session.pop(POST_LOGIN_REDIRECT_GUARD_SESSION_KEY, None)
            return response

        request.session.pop(POST_LOGIN_REDIRECT_GUARD_SESSION_KEY, None)
        return HttpResponseRedirect(reverse("home"))

    def _should_guard(self, request, response):
        if response.status_code not in self._GUARDED_STATUSES:
            return False

        if request.method != "GET":
            return False

        if not getattr(request.user, "is_authenticated", False):
            return False

        if not request.session.get(POST_LOGIN_REDIRECT_GUARD_SESSION_KEY):
            return False

        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return False

        accepted = (request.headers.get("Accept") or "").lower()
        if accepted and "text/html" not in accepted and "*/*" not in accepted:
            return False

        return True

    def _should_clear_guard(self, response):
        if response.status_code in self._REDIRECTING_STATUSES:
            return False
        return response.status_code < 500


class SuspendedOrganizationMiddleware:
    """
    Handles organization status enforcement for regular users:

    - ``suspended``: user is immediately logged out (hard block).
    - ``pending``: user may remain logged in but the request is flagged as
      read-only (``request.org_pending_approval = True``). Views and templates
      can inspect this flag to disable write actions without a full logout.
    - Any other non-``active`` status: treated as suspended (hard block).
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated and not request.user.is_superuser:
            organization = getattr(request, "blocked_organization", None) or getattr(request, "organization", None)

            if organization and organization.status != "active":
                is_superadmin = getattr(request.user, "is_superadmin", False)
                if not is_superadmin:
                    if organization.status == "pending":
                        # Allow read-only / viewer mode while awaiting superadmin approval.
                        # Views that perform write operations must check this flag.
                        request.org_pending_approval = True
                    else:
                        # Suspended or any other non-active, non-pending status → hard logout.
                        logout(request)
                        messages.error(
                            request,
                            "Təşkilatınız dayandırılıb. Hesaba giriş müvəqqəti bloklanıb.",
                        )
                        return redirect("accounts:login")

        # Ensure the flag is always defined on the request object.
        if not hasattr(request, "org_pending_approval"):
            request.org_pending_approval = False

        return self.get_response(request)


class FirstLoginPasswordMiddleware:
    """Force administration-provisioned users through the first-login flow.

    E-university accounts are created by the administration; on first login the
    user must verify their email (OTP) and set their own password. Until
    ``profile.password_change_required`` is cleared, every request from that user
    is redirected to ``accounts:set_initial_password`` — except a small exempt
    set (the set-password view itself, logout, static/media, admin, language
    switch, health) so the user is never trapped in a loop and can always leave.
    """

    #: Path prefixes that must remain reachable during the first-login lock.
    EXEMPT_PREFIXES = (
        "/static/",
        "/media/",
        "/admin/",
        "/i18n/",
        "/health",
        "/__debug__/",
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if (
            user is not None
            and user.is_authenticated
            and not user.is_superuser
            and self._requires_first_login(user)
            and not self._is_exempt(request)
        ):
            return redirect("accounts:set_initial_password")
        return self.get_response(request)

    @staticmethod
    def _requires_first_login(user):
        profile = getattr(user, "profile", None)
        return bool(profile is not None and getattr(profile, "password_change_required", False))

    def _is_exempt(self, request):
        path = request.path
        if any(path.startswith(prefix) for prefix in self.EXEMPT_PREFIXES):
            return True
        try:
            exempt_paths = {
                reverse("accounts:set_initial_password"),
                reverse("accounts:logout"),
            }
        except Exception:  # noqa: BLE001 — URLconf not ready (e.g. during startup)
            return True
        return path in exempt_paths


class ViewAsMiddleware:
    """
    "View as" (istifadəçi profilinə baxış) middleware-i.

    AuthenticationMiddleware-dən SONRA, OrganizationMiddleware-dən ƏVVƏL
    işləməlidir: aktiv view-as sessiyası varsa ``request.user``-i hədəf
    istifadəçi ilə əvəzləyir, beləcə org/RLS konteksti və bütün view-lar
    hədəfin icazələri daxilində işləyir.

    Request atributları (hər sorğuda mövcuddur):
    - ``request.real_user``     — autentifikasiya olunmuş ƏSL istifadəçi
    - ``request.is_view_as``    — aktiv view-as sessiyası varmı
    - ``request.view_as_mode``  — "full" | "limited" | "readonly" | None

    Təhlükəsizlik:
    - READONLY: bütün unsafe metodlar bloklanır (yalnız çıxış endpoint-i istisna).
    - LIMITED: unsafe metod YALNIZ aktorun rolu üçün açıq şəkildə icazəli olan
      marşrutlarda keçir (bax ``view_as.LIMITED_WRITE_ALLOWLIST``); qalanı
      bloklanır. Həm icazə verilən, həm bloklanan cəhd audit-ə yazılır.
    - FULL: unsafe əməliyyatlar audit jurnalına yazılır; şifrə dəyişmə və
      hesab silmə kimi həssas əməliyyatlar BÜTÜN rejimlərdə bloklanır.
    - Django admin səthi view-as altında rejimdən asılı olmayaraq TAM bağlıdır
      (GET daxil): admin 2FA təsdiqi, `password_change` və bütün model CRUD
      marşrutları oradadır və hədəf `is_staff` olduqda hamısı açılırdı.
    - Logout view-as sessiyasını bitirir (əsl istifadəçi sistemdən çıxmır).
    """

    SAFE_METHODS = {"GET", "HEAD", "OPTIONS", "TRACE"}
    #: Hər iki rejimdə bloklanan həssas `profile_form` POST dəyərləri.
    BLOCKED_PROFILE_FORMS = {"change-password", "update-avatar", "edit-profile"}
    #: Hesab ələ keçirmə yolları — view-as altında HƏR İKİ rejimdə bloklanır.
    #: İlk-giriş axını (parol təyini + e-poçt OTP) hədəfin kimlik sübutudur:
    #: aktor onu keçsə, hədəfin parolunu təyin edib hesabı tam ələ keçirə bilər.
    #: Bax: ViewAsMiddleware FirstLoginPasswordMiddleware-dən ƏVVƏL işləyir, ona
    #: görə `password_change_required=True` hədəfdə hər sorğu set-password-a
    #: yönləndirilir və POST orada açıq qalırdı.
    BLOCKED_URL_NAMES = frozenset(
        {
            "accounts:set_initial_password",
            "accounts:send_otp_api",
            "accounts:verify_otp_api",
            "accounts:resend_otp_api",
            "accounts:resend_code",
            "accounts:delete_account",
        }
    )

    def __init__(self, get_response):
        self.get_response = get_response
        self._exit_path = None
        self._logout_path = None
        self._delete_account_path = None
        self._blocked_paths = None
        self._admin_prefix = None

    def _resolve_paths(self):
        # URLConf yüklənəndən sonra bir dəfə cache-lənir.
        if self._exit_path is None:
            from django.urls import NoReverseMatch, reverse

            self._exit_path = reverse("accounts:view_as_stop")
            self._logout_path = reverse("accounts:logout")
            self._delete_account_path = reverse("accounts:delete_account")

            blocked = set()
            for name in self.BLOCKED_URL_NAMES:
                try:
                    blocked.add(reverse(name))
                except NoReverseMatch:  # pragma: no cover — route silinərsə sükutla keç
                    continue
            self._blocked_paths = frozenset(blocked)

            try:
                self._admin_prefix = reverse("admin:index")
            except NoReverseMatch:  # pragma: no cover — admin bağlıdırsa
                self._admin_prefix = None

    @staticmethod
    def _resolved_url_name(request):
        """``namespace:name`` — middleware URL həllindən ƏVVƏL işlədiyi üçün əl ilə."""
        from django.urls import Resolver404, resolve

        try:
            match = resolve(request.path_info)
        except Resolver404:
            return ""
        return match.view_name or ""

    @staticmethod
    def _view_as_organization(request):
        """View-as sessiyasının təşkilatı (LIMITED icazə siyahısını həll etmək üçün)."""
        from core.rls import bypass_rls

        from .services.view_as import get_view_as_state

        state = get_view_as_state(request) or {}
        org_id = state.get("org_id")
        if not org_id:
            return None
        from apps.organizations.models import Organization

        with bypass_rls():
            return Organization.objects.filter(pk=org_id).first()

    def _audit_view_as_write(self, request, target, mode, url_name, *, allowed, profile_form=""):
        """Rollararası hər yazma cəhdini (icazəli və bloklanmış) audit-ə yazır.

        ƏSL istifadəçinin adına yazılır — domen qatındakı qeydlər isə
        ``request.user``-i, yəni HƏDƏFİ görür (bax ``core.audit.log_action``
        impersonasiya damğasına).

        TƏŞKİLAT MÜTLƏQ ÖTÜRÜLMƏLİDİR. Əvvəllər ``organization=None`` yazılırdı
        və nəticə bu idi: qeyd bazada var, amma TENANT AUDİT JURNALINDA YOXDUR —
        ``apps/audit/views.py`` superadmin olmayan hər kəs üçün sorğunu
        ``organization``-a görə filtrləyir. Yəni təşkilatın öz idarəçisi
        «view-as başladı» sətrini görürdü (o, org damğalıdır), amma impersonasiya
        altında NƏ EDİLDİYİNİ və hansı cəhdin BLOKLANDIĞINI görə bilmirdi.
        Bloklanmış cəhd qeydləri xüsusilə vacibdir: onlar başqa heç bir yerdə
        yaranmır (sorğu view-a çatmır), yəni pozuntu siqnalı yalnız platforma
        superadmininə görünürdü.
        """
        try:
            from apps.audit.public import log_action
            from core.constants import AuditAction

            log_action(
                action=AuditAction.UPDATE,
                user=request.real_user,
                organization=self._view_as_organization(request),
                obj=target,
                reason="view_as_action" if allowed else "view_as_action_blocked",
                changes={
                    "path": request.path[:255],
                    "method": request.method,
                    "url_name": (url_name or "")[:120],
                    "mode": mode,
                    "allowed": bool(allowed),
                    "profile_form": (profile_form or "")[:64],
                },
                request=request,
            )
        except Exception:  # noqa: BLE001 — audit xətası əməliyyatı bloklamamalıdır
            logger.exception("view_as action audit log failed")

    @staticmethod
    def _wants_json(request):
        accept = (request.headers.get("Accept") or "").lower()
        return request.headers.get("x-requested-with") == "XMLHttpRequest" or "application/json" in accept

    def _reject(self, request, message_text):
        from django.contrib import messages
        from django.http import JsonResponse
        from django.shortcuts import redirect
        from django.urls import reverse

        if self._wants_json(request):
            return JsonResponse({"detail": message_text, "view_as_blocked": True}, status=403)
        messages.warning(request, message_text)
        referer = request.META.get("HTTP_REFERER") or ""
        # Open-redirect qorunması: yalnız öz host-umuza qayıdırıq.
        from django.utils.http import url_has_allowed_host_and_scheme

        if referer and url_has_allowed_host_and_scheme(referer, allowed_hosts={request.get_host()}):
            return redirect(referer)
        return redirect(reverse("accounts:profile"))

    def __call__(self, request):
        request.real_user = request.user
        request.is_view_as = False
        request.view_as_mode = None
        request.view_as_target = None

        if not getattr(request.user, "is_authenticated", False):
            return self.get_response(request)

        from django.utils.translation import pgettext

        from .services.view_as import (
            MODE_LIMITED,
            MODE_READONLY,
            MUTATING_GET_URL_NAMES,
            VIEW_AS_SESSION_KEY,
            actor_limited_write_url_names,
            resolve_view_as_request,
            stop_view_as,
        )

        if VIEW_AS_SESSION_KEY not in request.session:
            return self.get_response(request)

        self._resolve_paths()

        # Logout → əvvəlcə view-as-i bitir, sonra normal davam (əsl istifadəçi çıxır).
        if request.path == self._logout_path:
            stop_view_as(request, reason="view_as_stopped_on_logout")
            return self.get_response(request)

        # Çıxış endpoint-i view-as aktiv ikən ƏSL istifadəçi ilə işləyir.
        if request.path == self._exit_path:
            return self.get_response(request)

        target, mode = resolve_view_as_request(request)
        if target is None:
            from django.contrib import messages

            messages.info(
                request,
                pgettext("accounts.view_as", "session_ended"),
            )
            return self.get_response(request)

        # Django admin view-as altında TAM bağlıdır (GET daxil). Admin-də həm
        # `password_change`, həm admin 2FA təsdiqi, həm də bütün modellərin CRUD
        # marşrutları var; hədəf `is_staff` olduqda bu səth bütövlükdə açılırdı
        # (middleware yalnız `is_superuser` hədəfləri istisna edir).
        if self._admin_prefix and request.path.startswith(self._admin_prefix):
            return self._reject(
                request,
                pgettext("accounts.view_as", "action_blocked_sensitive"),
            )

        # Qapı YALNIZ metoda bağlı ola bilməz: bəzi marşrutlar GET ilə də
        # vəziyyət dəyişir (bax `MUTATING_GET_URL_NAMES`). Onlar da yazma kimi
        # işlənməlidir — həm rejim yoxlaması, həm audit üçün.
        url_name = self._resolved_url_name(request)
        is_write = request.method not in self.SAFE_METHODS or url_name in MUTATING_GET_URL_NAMES

        if is_write:

            # Kimlik-sübutu axınları (ilk-giriş parolu, e-poçt OTP, hesab silmə)
            # rejimdən ASILI OLMAYARAQ bloklanır — aktor hədəfin parolunu təyin
            # edib hesabı ələ keçirə bilməməlidir.
            if request.path in (self._blocked_paths or ()):
                self._audit_view_as_write(request, target, mode, url_name, allowed=False)
                return self._reject(
                    request,
                    pgettext("accounts.view_as", "action_blocked_sensitive"),
                )

            if mode == MODE_READONLY:
                self._audit_view_as_write(request, target, mode, url_name, allowed=False)
                return self._reject(
                    request,
                    pgettext("accounts.view_as", "action_blocked_readonly"),
                )

            if mode == MODE_LIMITED:
                # Yalnız aktorun rolu üçün açıq siyahıdakı marşrutlar. Siyahı
                # aktorun ROLUNDAN çıxarılır (hədəfin icazələrindən DEYİL) —
                # hədəf-tərəfli yoxlama aktorun kim olduğunu heç görmür.
                organization = self._view_as_organization(request)
                allowed_names = (
                    actor_limited_write_url_names(request.real_user, organization) if organization else frozenset()
                )
                if url_name not in allowed_names:
                    self._audit_view_as_write(request, target, mode, url_name, allowed=False)
                    return self._reject(
                        request,
                        pgettext("accounts.view_as", "action_blocked_out_of_scope"),
                    )

            # Həssas profil əməliyyatları FULL rejimdə də bloklanır.
            profile_form = (request.POST.get("profile_form") or "").strip()
            if request.path == self._delete_account_path or profile_form in self.BLOCKED_PROFILE_FORMS:
                self._audit_view_as_write(request, target, mode, url_name, allowed=False)
                return self._reject(
                    request,
                    pgettext("accounts.view_as", "action_blocked_sensitive"),
                )

            # İcazə verilən hər unsafe əməliyyat ƏSL istifadəçinin adına yazılır.
            self._audit_view_as_write(
                request,
                target,
                mode,
                url_name,
                allowed=True,
                profile_form=profile_form,
            )

        request.is_view_as = True
        request.view_as_mode = mode
        request.view_as_target = target
        request.user = target

        return self.get_response(request)
