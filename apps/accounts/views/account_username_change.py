"""«İstifadəçi adını dəyiş» JSON endpoint-ləri — «Parol sıfırlama» bölməsində (sahib 2026-10-26).

Hər ikisi YALNIZ POST + CSRF və `never_cache`-dir (ad URL-ə / access log-a düşmür). Qapılar servis
qatındadır (`services/username_change_admin.py`); parol, sessiya və e-poçt təsdiqi TOXUNULMUR.
"""

from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.utils.translation import pgettext
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from ..services.password_reset_admin import PasswordResetError, enforce_lookup_rate
from ..services.password_reset_lookup import serialize_candidates
from ..services.username_change_admin import (
    UsernameAdminError,
    audit_denied,
    change_username,
    enforce_rename_rate,
    operator_for,
    suggest_username,
)
from .account_password_reset import _read_payload

_CTX = "accounts.username_change_admin"


def _error(exc: UsernameAdminError) -> JsonResponse:
    return JsonResponse({"ok": False, "error": exc.code, "message": exc.message}, status=exc.status)


@never_cache
@login_required
@require_POST
def account_username_change_suggest(request):
    """«Avtomatik təklif» — hədəfin ad və soyadından boş ``ad.soyad`` (YAZMIR)."""
    try:
        try:
            enforce_lookup_rate(request)
        except PasswordResetError as exc:
            raise UsernameAdminError(exc.code, exc.status) from exc
        actor = operator_for(request)
        result = suggest_username(actor, _read_payload(request).get("user_id"))
    except UsernameAdminError as exc:
        return _error(exc)
    return JsonResponse({"ok": True, **result})


@never_cache
@login_required
@require_POST
def account_username_change_perform(request):
    """Seçilmiş hədəfin istifadəçi adını dəyişir (səbəb məcburi; parol dəyişmir)."""
    payload = _read_payload(request)
    target_id = payload.get("user_id")
    actor = None
    try:
        enforce_rename_rate(request)
        actor = operator_for(request, for_write=True)
        target, old_username = change_username(
            actor, target_id, payload.get("new_username"), reason=payload.get("reason"), request=request
        )
    except UsernameAdminError as exc:
        audit_denied(actor, request, target_id, exc.code)
        return _error(exc)

    return JsonResponse(
        {
            "ok": True,
            "old_username": old_username,
            "user": serialize_candidates(actor, [target])[0],
            "message": pgettext(
                _CTX,
                "İstifadəçi adı «%(old)s» → «%(new)s» olaraq dəyişdirildi. Parol dəyişmədi; istifadəçi bundan sonra "
                "yeni adla daxil olur.",
            )
            % {"old": old_username, "new": target.username},
        }
    )


__all__ = ["account_username_change_perform", "account_username_change_suggest"]
