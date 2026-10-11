"""accounts auth view paketi — logout.

Sahib 2026-10-10 (URL auditi A5/B8): açıq qeydiyyat axını (``register``,
``verify-code``, ``verify-email``, ``resend-code``) silindi — hesabları universitet
administrasiyası yaradır. Həmin modulda yaşayan ``logout_view`` bura köçdü.
"""

from django.contrib import messages
from django.contrib.auth import logout
from django.http import HttpResponseNotAllowed
from django.shortcuts import redirect
from django.utils.translation import pgettext_lazy


def logout_view(request):
    """Logout user and redirect to the login page.

    Only POST requests are accepted to prevent cross-site forced-logout attacks
    (e.g. an attacker embedding ``<img src="/accounts/logout/">`` on another page).
    GET requests receive HTTP 405 Method Not Allowed.
    """
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    logout(request)
    messages.success(request, pgettext_lazy("accounts.auth.message", "logout_success"))
    return redirect("accounts:login")
