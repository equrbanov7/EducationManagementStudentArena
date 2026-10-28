"""Hesaba bağlı jurnal şəbəkə istisnası; rol və tenant icazələrini dəyişmir."""

from django.conf import settings
from django.http import HttpResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from core.admin_auth import ADMIN_2FA_VERIFIED_USER_SESSION_KEY, admin_2fa_required_for_user


def journal_remote_access_allowed(request):
    from .network_zone import gate_actor

    user = gate_actor(request)
    if not user or not user.is_authenticated or not user.is_active:
        return False
    allowed = getattr(settings, "JOURNAL_REMOTE_USER_IDS", ())
    if str(user.pk) not in {str(value) for value in allowed}:
        return False
    if admin_2fa_required_for_user(user):
        verified = request.session.get(ADMIN_2FA_VERIFIED_USER_SESSION_KEY, "")
        if str(verified) != str(user.pk):
            return False
    return True


@never_cache
@require_GET
def journal_remote_auth(request):
    """nginx auth_request: yalnız server sessiyası + hesab istisnası təsdiqlənir."""
    return HttpResponse(status=204 if journal_remote_access_allowed(request) else 403)
