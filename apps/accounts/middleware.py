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
    Middleware to automatically logout users after 3 days of inactivity.
    Tracks the last activity time in the session.
    """

    def __init__(self, get_response):
        self.get_response = get_response
        self.timeout_seconds = settings.SESSION_INACTIVITY_TIMEOUT

    def __call__(self, request):
        if request.user.is_authenticated:
            # Get the last activity time from session
            last_activity = request.session.get("last_activity")

            if last_activity:
                # Convert to datetime if it's a string
                if isinstance(last_activity, str):
                    last_activity = datetime.fromisoformat(last_activity)

                # Check if session has expired
                time_since_activity = timezone.now() - last_activity
                if time_since_activity.total_seconds() > self.timeout_seconds:
                    # Session expired, logout the user
                    logout(request)

            # Update last activity time
            request.session["last_activity"] = timezone.now().isoformat()

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
