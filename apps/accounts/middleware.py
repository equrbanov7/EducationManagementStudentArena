"""
Custom middleware for session management and auto-logout.
"""

import logging
from datetime import datetime

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import logout
from django.shortcuts import redirect
from django.utils import timezone

logger = logging.getLogger(__name__)


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
