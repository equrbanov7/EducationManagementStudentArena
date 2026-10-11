"""«Jurnal təmizliyi» — YAZMA endpoint-i: TƏK JSON POST + ``action`` allow-list-i.

``preview`` (heç nə yazmır) → ``apply`` (önizləmə izi ilə, kilid altında yenidən yoxlanılır) → ``revert``.
Hər əməl eyni zəncirdən keçir: aktor (RİM rəhbəri / superadmin, view-as yox) → registrar servisində
``journal.correct`` → tenant → sətirlər → qərar jurnalı + audit. Domen məntiqi
``apps.registrar.journal_hygiene_actions``-dadır.
"""

from __future__ import annotations

import json
import logging

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.utils.translation import pgettext
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from apps.registrar.public import journal_hygiene_actions as hygiene_write
from core.logging_utils import safe_log_value

from .api import TABS
from .policy import resolve_actor

logger = logging.getLogger(__name__)

#: Allow-list — naməlum ``action`` 400 verir (səssiz keçid yoxdur).
ALLOWED_ACTIONS = frozenset({"preview", "apply", "revert"})


def _error(code, message, status=400, details=None):
    return JsonResponse({"ok": False, "error": code, "message": str(message), "details": details or []}, status=status)


def _payload(request) -> dict:
    if "application/json" in (request.content_type or "").lower():
        try:
            data = json.loads(request.body.decode("utf-8") or "{}")
        except ValueError:
            data = {}
    else:
        data = {key: request.POST.get(key) for key in request.POST}
        data["ids"] = request.POST.getlist("ids")
    return data if isinstance(data, dict) else {}


@never_cache
@login_required
@require_POST
def journal_hygiene_action(request):
    actor = resolve_actor(request)
    if not actor.can_apply:
        return _error(
            "permission_denied",
            pgettext("accounts.journal_hygiene", "Jurnal təmizliyi əməlləri yalnız RİM rəhbəri üçündür."),
            status=403,
        )
    data = _payload(request)
    action = str(data.get("action") or "").strip()
    if action not in ALLOWED_ACTIONS:
        return _error("unknown_action", pgettext("accounts.journal_hygiene", "Naməlum əməliyyat."))
    ids = data.get("ids") if isinstance(data.get("ids"), list) else []
    category = TABS.get(str(data.get("tab") or "").strip(), "")
    common = {"organization": actor.organization, "actor": actor.user}
    try:
        if action == "preview":
            payload = hygiene_write.preview(
                **common, category=category, enrollment_ids=ids, target=str(data.get("target") or "")
            )
        elif action == "apply":
            payload = hygiene_write.apply(
                **common,
                category=category,
                enrollment_ids=ids,
                target=str(data.get("target") or ""),
                reason=data.get("reason") or "",
                expected_digest=str(data.get("digest") or ""),
                request=request,
            )
            payload["message"] = pgettext(
                "accounts.journal_hygiene", "Yazıldı: %(n)d sətir. Geri qaytarmaq üçün «Tarixçə»yə keçin."
            ) % {"n": payload["changed"]}
        else:
            payload = hygiene_write.revert(**common, decision_ids=ids, reason=data.get("reason") or "", request=request)
            payload["message"] = pgettext("accounts.journal_hygiene", "Geri qaytarıldı: %(n)d qərar.") % {
                "n": payload["reverted"]
            }
    except hygiene_write.HygieneError as exc:
        # Servis mesajları istifadəçi-üzlüdür (səbəb, sürüşmə, blok) — olduğu kimi göstərilir.
        logger.info("journal hygiene %s rejected: %s", safe_log_value(action), safe_log_value(exc.code))
        return _error(exc.code, exc.message, status=exc.status, details=exc.details)
    return JsonResponse({"ok": True, **payload})


__all__ = ["ALLOWED_ACTIONS", "journal_hygiene_action"]
