"""
Custom middleware for session management and auto-logout.
"""

from datetime import datetime, timedelta

from django.conf import settings
from django.contrib.auth import logout
from django.utils import timezone


class SessionTimeoutMiddleware:
    """
    Middleware to automatically logout users after 3 days of inactivity.
    Tracks the last activity time in the session.
    """

    def __init__(self, get_response):
        self.get_response = get_response
        # Default to 3 days (in seconds)
        self.timeout_seconds = getattr(settings, "SESSION_INACTIVITY_TIMEOUT", 3 * 24 * 60 * 60)

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
