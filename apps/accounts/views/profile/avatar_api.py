"""Profil şəkli üçün JSON endpoint (2026-10-01): yerində yüklə / dəyiş / sil.

Nazik HTTP qatı — yoxlama və fayl təmizliyi ``services.profile_avatar``-dadır.
Cavab: ``{"success", "error"?, "message"?, "has_avatar", "avatar_url", "initials",
"initial"}`` — JS (profile_avatar.js) səhifədəki bütün avatar yerlərini
(kimlik başlığı, redaktə bloku, navbar) bu vəziyyətlə yeniləyir.

View-as altında bu marşrut BÜTÜN rejimlərdə bloklanır (``update-avatar`` forması
kimi) — bax ``ViewAsMiddleware.BLOCKED_URL_NAMES``.
"""

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.utils.translation import pgettext
from django.views.decorators.http import require_POST

from apps.audit.public import log_action
from core.constants import AuditAction

from ...models import UserProfile
from ...services import profile_avatar

_CTX = "profile.avatar"


def _log(request, event):
    log_action(
        action=AuditAction.DELETE if event == "removed" else AuditAction.UPDATE,
        user=request.user,
        reason=f"Profile avatar {event}",
        changes={"avatar": event},
        request=request,
        resource_type="UserProfileAvatar",
        resource_id=str(request.user.pk),
        resource_repr=request.user.username,
    )


@login_required
@require_POST
def profile_avatar_api(request):
    """``action=upload`` (fayl: ``avatar``) və ya ``action=remove``."""
    profile, _created = UserProfile.objects.get_or_create(user=request.user)
    action = (request.POST.get("action") or "").strip()

    if action == "upload":
        ok, event, error = profile_avatar.replace_avatar(profile, request.FILES.get("avatar"))
        if not ok:
            return JsonResponse({"success": False, "error": error}, status=400)
        _log(request, event)
        message = pgettext(_CTX, "Profil şəkli yeniləndi.")
    elif action == "remove":
        if profile_avatar.remove_avatar(profile):
            _log(request, "removed")
        message = pgettext(_CTX, "Profil şəkli silindi.")
    else:
        return JsonResponse({"success": False, "error": pgettext(_CTX, "Naməlum əməliyyat.")}, status=400)

    return JsonResponse({"success": True, "message": message, **profile_avatar.avatar_state(request.user, profile)})
