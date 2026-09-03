"""Kataloq YAZMA endpoint-i — hesabı dayandır/bərpa et, müəllim statusu.

RİM ilə eyni naxış: TƏK POST marşrutu + ``action`` allow-list-i. Səbəb eynidir —
hər əməliyyat eyni ön-şərt zəncirindən keçir (aktor → hədəf → icazə → scope →
iyerarxiya → audit); marşrutları parçalasaq zəncir dörd yerdə təkrarlanardı.

⚠️ TƏSDİQ TƏLƏBİ: dağıdıcı əməllər (``block``, ``revoke_teacher``,
``transfer_group``, ``set_academic_status`` → xaric/məzuniyyət) üçün ``reason``
MƏCBURİDİR (ən azı 3 simvol) — servis qatı onu yoxlayır və UI təsdiq modalını
bu tələb üzərində qurur.

⚠️ AKADEMİK əməllərin hədəfi ``user_id`` DEYİL, ``record_id``-dir: bir tələbənin
bir neçə proqram qeydi ola bilər (``uniq_student_program``) və hansının
köçürüldüyü birmənalı olmalıdır. Ona görə ``load_target`` yolu YALNIZ hesab
əməllərinə aiddir; akademik əməllər ``academic.load_record`` qapısından keçir.
"""

from __future__ import annotations

import json
import logging

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from apps.accounts.services import people
from apps.accounts.services.rim.policy import RimAccessError
from core.logging_utils import safe_log_value

logger = logging.getLogger(__name__)

#: Allow-list — naməlum `action` 400 verir (səssiz keçid yoxdur).
ALLOWED_ACTIONS = frozenset(
    {
        "block",
        "unblock",
        "grant_teacher",
        "revoke_teacher",
        # Tələbə idarəetməsi (`people.manage_academic`) — hədəf `record_id`.
        "transfer_group",
        "set_academic_status",
    }
)

#: Hədəfi akademik QEYD olan əməllər (hesab deyil).
RECORD_ACTIONS = frozenset({"transfer_group", "set_academic_status"})


def _read_payload(request) -> dict:
    content_type = (request.content_type or "").lower()
    if "application/json" in content_type:
        try:
            data = json.loads(request.body.decode("utf-8") or "{}")
        except ValueError:
            return {}
        return data if isinstance(data, dict) else {}
    return {key: value for key, value in request.POST.items()}


def _error(exc: RimAccessError) -> JsonResponse:
    return JsonResponse({"ok": False, "error": exc.reason_code, "message": exc.message}, status=exc.status)


@never_cache
@login_required
@require_POST
def people_action(request):
    """Kataloq əməllərinin vahid giriş nöqtəsi."""
    actor = people.resolve_actor(request)
    payload = _read_payload(request)

    action = str(payload.get("action") or "").strip()
    if action not in ALLOWED_ACTIONS:
        return JsonResponse({"ok": False, "error": "unknown_action", "message": "Naməlum əməliyyat."}, status=400)

    reason = payload.get("reason") or ""

    try:
        if action in RECORD_ACTIONS:
            result = _run_record_action(actor, action, payload, request)
            return JsonResponse({"ok": True, "action": action, "result": result})

        target = people.load_target(actor, payload.get("user_id"))
        if action in ("block", "unblock"):
            result = people.set_account_status(
                actor,
                target,
                active=(action == "unblock"),
                reason=reason,
                request=request,
            )
        else:
            result = people.set_teacher_role(
                actor,
                target,
                grant=(action == "grant_teacher"),
                reason=reason,
                unit_id=payload.get("unit_id") or None,
                request=request,
            )
    except RimAccessError as exc:
        return _error(exc)
    except Exception:  # noqa: BLE001 — daxili xəta istifadəçiyə sızmamalıdır
        logger.exception("people action failed: %s", safe_log_value(action))
        return JsonResponse(
            {"ok": False, "error": "action_failed", "message": "Əməliyyat tamamlana bilmədi."},
            status=500,
        )

    return JsonResponse({"ok": True, "action": action, "result": result})


def _run_record_action(actor, action, payload, request):
    """Akademik qeyd üzərindəki əməllər — scope qapısı servis qatındadır."""
    record_id = payload.get("record_id") or ""
    reason = payload.get("reason") or ""
    if action == "transfer_group":
        return people.transfer_group(
            actor,
            record_id=record_id,
            new_group_id=payload.get("group_id") or "",
            reason=reason,
            request=request,
        )
    return people.set_academic_status(
        actor,
        record_id=record_id,
        status=payload.get("status") or "",
        reason=reason,
        request=request,
    )


__all__ = ["ALLOWED_ACTIONS", "RECORD_ACTIONS", "people_action"]
