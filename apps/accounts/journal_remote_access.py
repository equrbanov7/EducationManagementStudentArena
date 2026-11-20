"""Hesaba bağlı jurnal şəbəkə istisnası; rol və tenant icazələrini dəyişmir.

İki mənbə (sahib 2026-11-20): server tənzimləməsi ``JOURNAL_REMOTE_USER_IDS`` (mühit, sahibin öz hesabı) VƏ RİM
rəhbərinin kabinetdən verdiyi icazə («Sistem tənzimləmələri» → «Kənardan jurnal girişi»,
``services.remote_journal_access``). Hər iki halda admin 2FA qaydası eynidir.
"""

from django.conf import settings
from django.http import HttpResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from core.admin_auth import ADMIN_2FA_VERIFIED_USER_SESSION_KEY, admin_2fa_required_for_user


def _account_is_listed(user) -> bool:
    allowed = getattr(settings, "JOURNAL_REMOTE_USER_IDS", ())
    if str(user.pk) in {str(value) for value in allowed}:
        return True
    from .services.remote_journal_access import has_active_grant

    return has_active_grant(user.pk)


def journal_remote_access_allowed(request):
    from .network_zone import gate_actor

    user = gate_actor(request)
    if not user or not user.is_authenticated or not user.is_active:
        return False
    if not _account_is_listed(user):
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
