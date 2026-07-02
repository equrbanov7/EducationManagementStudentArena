"""
Custom middleware for session management and auto-logout.
"""

import logging
from datetime import datetime

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import logout
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
        if request.user.is_authenticated:
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
    - ``request.view_as_mode``  — "full" | "readonly" | None

    Təhlükəsizlik:
    - READONLY: bütün unsafe metodlar bloklanır (yalnız çıxış endpoint-i istisna).
    - FULL: unsafe əməliyyatlar audit jurnalına yazılır; şifrə dəyişmə və
      hesab silmə kimi həssas əməliyyatlar HƏR İKİ rejimdə bloklanır.
    - Logout view-as sessiyasını bitirir (əsl istifadəçi sistemdən çıxmır).
    """

    SAFE_METHODS = {"GET", "HEAD", "OPTIONS", "TRACE"}
    #: Hər iki rejimdə bloklanan həssas `profile_form` POST dəyərləri.
    BLOCKED_PROFILE_FORMS = {"change-password", "update-avatar", "edit-profile"}

    def __init__(self, get_response):
        self.get_response = get_response
        self._exit_path = None
        self._logout_path = None
        self._delete_account_path = None

    def _resolve_paths(self):
        # URLConf yüklənəndən sonra bir dəfə cache-lənir.
        if self._exit_path is None:
            from django.urls import reverse

            self._exit_path = reverse("accounts:view_as_stop")
            self._logout_path = reverse("accounts:logout")
            self._delete_account_path = reverse("accounts:delete_account")

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
            MODE_READONLY,
            VIEW_AS_SESSION_KEY,
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

        if request.method not in self.SAFE_METHODS:
            if mode == MODE_READONLY:
                return self._reject(
                    request,
                    pgettext("accounts.view_as", "action_blocked_readonly"),
                )

            # FULL rejim: həssas əməliyyatlar yenə də bloklanır.
            profile_form = (request.POST.get("profile_form") or "").strip()
            if request.path == self._delete_account_path or profile_form in self.BLOCKED_PROFILE_FORMS:
                return self._reject(
                    request,
                    pgettext("accounts.view_as", "action_blocked_sensitive"),
                )

            # FULL rejimdə hər unsafe əməliyyat audit-ə yazılır (əsl istifadəçi adından).
            try:
                from apps.audit.public import log_action
                from core.constants import AuditAction

                log_action(
                    action=AuditAction.UPDATE,
                    user=request.real_user,
                    organization=None,
                    obj=target,
                    reason="view_as_action",
                    changes={
                        "path": request.path[:255],
                        "method": request.method,
                        "profile_form": profile_form[:64],
                    },
                    request=request,
                )
            except Exception:  # noqa: BLE001 — audit xətası əməliyyatı bloklamamalıdır
                logger.exception("view_as action audit log failed")

        request.is_view_as = True
        request.view_as_mode = mode
        request.view_as_target = target
        request.user = target

        return self.get_response(request)
