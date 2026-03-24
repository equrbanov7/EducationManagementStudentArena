"""
Custom middleware for session management and auto-logout.
"""

from datetime import datetime

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import logout
from django.shortcuts import redirect
from django.utils import timezone


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
                    # You can add a message here if needed
                    # messages.info(request, "Siz uzun müddət aktiv olmadığınız üçün sistemdən çıxarıldınız.")

            # Update last activity time
            request.session["last_activity"] = timezone.now().isoformat()

        response = self.get_response(request)
        return response


class SuspendedOrganizationMiddleware:
    """
    Blocks regular users from accessing the app when their organization is suspended.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated and not request.user.is_superuser:
            # Use request.organization set by OrganizationMiddleware (new membership model).
            organization = getattr(request, "organization", None)

            # Block when the organization is not in "active" status (covers both
            # "suspended" and "inactive" status values).  OrganizationMiddleware
            # already handles is_active=False by clearing the session org, so we
            # only need to check the status field here.
            if organization and organization.status != "active":
                if not getattr(request.user, "is_superadmin", False):
                    logout(request)
                    messages.error(
                        request,
                        "Təşkilatınız dayandırılıb. Hesaba giriş müvəqqəti bloklanıb.",
                    )
                    return redirect("accounts:login")

        return self.get_response(request)
