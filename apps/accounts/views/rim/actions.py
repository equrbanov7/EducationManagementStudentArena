"""RİM yazma endpoint-i — parol / blok / silmə / bərpa / redaktə (tək POST marşrutu).

Niyə tək marşrut? Hər əməliyyat EYNİ ön-şərtlər dəstindən keçir (aktor həlli →
hədəf həlli → icazə → iyerarxiya → audit). Marşrutları parçalasaq bu zəncir
beş yerdə təkrarlanardı və birində unudulmuş yoxlama səssiz boşluq yaradardı.
Əməliyyat ``action`` sahəsi ilə seçilir və AÇIQ allow-list-dən keçir.

Cavab həmişə JSON-dur; UI onu modal + toast ilə göstərir.

DİQQƏT — parol cavabı: ``set_password`` əməliyyatının cavabında xam parol
**yalnız bir dəfə** qayıdır. O, nə DB-yə, nə audit-ə, nə log-a yazılır; brauzer
tərəfdə də saxlanılmır (yalnız modalda göstərilir).
"""

from __future__ import annotations

import json
import logging

from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from apps.accounts.services.rim import (
    RimAccessError,
    assert_can_manage,
    block_user,
    manageable_users_queryset,
    resolve_actor,
    restore_user,
    serialize_detail,
    set_temporary_password,
    soft_delete_user,
    unblock_user,
    update_user_fields,
)
from apps.accounts.services.rim.profile_edit import EDITABLE_FIELDS
from core.logging_utils import safe_log_value

logger = logging.getLogger(__name__)

#: İcazə verilən əməliyyatlar — allow-list (naməlum `action` → 400).
ALLOWED_ACTIONS = frozenset(
    {
        "set_password",
        "block",
        "unblock",
        "soft_delete",
        "restore",
        "edit",
    }
)


def _read_payload(request) -> dict:
    """JSON gövdəsini (və ya form-encoded POST-u) oxuyur."""
    content_type = (request.content_type or "").lower()
    if "application/json" in content_type:
        try:
            data = json.loads(request.body.decode("utf-8") or "{}")
        except ValueError:
            # `UnicodeDecodeError` də `ValueError`-un alt sinfidir — pozuq
            # gövdə səssizcə boş payload sayılır və aşağıda 400 qaytarılır.
            return {}
        return data if isinstance(data, dict) else {}
    return {key: value for key, value in request.POST.items()}


def _error_response(exc: RimAccessError) -> JsonResponse:
    return JsonResponse(
        {"ok": False, "error": exc.reason_code, "message": exc.message},
        status=exc.status,
    )


def _target_error(actor, user_id) -> JsonResponse:
    """Hədəf idarə sahəsində deyil — SƏBƏBİ dəqiqləşdirir (QA 2026-09-05 P3-8).

    Əvvəl bütün hallar `target_not_found` (404) idi: operator «bu hesab niyə
    idarə olunmur?» sualına cavab ala bilmirdi (öz hesabı? superadmin? rütbə
    yüksəkdir?). İndi hədəf AKTORUN ÖZ TƏŞKİLATINDA tapılırsa siyasət qatı
    dəqiq səbəb kodunu verir; təşkilatdan kənar hesab yenə 404-dür (mövcudluq
    sızmır).
    """
    from django.contrib.auth import get_user_model

    not_found = JsonResponse(
        {"ok": False, "error": "target_not_found", "message": "İstifadəçi tapılmadı."},
        status=404,
    )
    organization = getattr(actor, "organization", None)
    try:
        candidate = get_user_model().objects.select_related("profile").filter(pk=user_id).first()
    except (TypeError, ValueError, ValidationError):
        return not_found
    if candidate is None:
        return not_found

    is_self = getattr(actor.user, "pk", None) == candidate.pk
    in_org = organization is not None and candidate.memberships.filter(organization=organization).exists()
    if not (is_self or in_org or getattr(actor, "is_superadmin", False)):
        return not_found

    try:
        assert_can_manage(actor, candidate)
    except RimAccessError as exc:
        return _error_response(exc)
    return not_found


@never_cache
@login_required
@require_POST
def rim_action(request):
    """RİM əməliyyatlarının vahid giriş nöqtəsi."""
    actor = resolve_actor(request)
    payload = _read_payload(request)

    action = str(payload.get("action") or "").strip()
    if action not in ALLOWED_ACTIONS:
        return JsonResponse(
            {"ok": False, "error": "unknown_action", "message": "Naməlum əməliyyat."},
            status=400,
        )

    user_id = payload.get("user_id")
    if not user_id:
        return JsonResponse(
            {"ok": False, "error": "target_required", "message": "İstifadəçi seçilməyib."},
            status=400,
        )

    # Hədəf aktorun idarə sahəsindən seçilir; kənardırsa 404 (mövcudluq sızmır).
    try:
        target = manageable_users_queryset(actor).filter(pk=user_id).first()
    except (TypeError, ValueError):
        target = None
    if target is None:
        return _target_error(actor, user_id)

    reason = payload.get("reason", "")
    extra: dict = {}

    try:
        if action == "set_password":
            raw_password = set_temporary_password(actor, target, request=request, reason=reason)
            # Yeganə yer, parolun görünəcəyi — birdəfəlik cavab.
            extra["password"] = raw_password
            message = "Müvəqqəti parol təyin edildi. İstifadəçi ilk girişdə öz parolunu quracaq."
        elif action == "block":
            block_user(actor, target, reason=reason, request=request)
            message = "Hesab bloklandı."
        elif action == "unblock":
            unblock_user(actor, target, reason=reason, request=request)
            message = "Hesabın bloku açıldı."
        elif action == "soft_delete":
            soft_delete_user(actor, target, reason=reason, request=request)
            message = "Hesab silindi (tarixi qeydlər saxlanıldı)."
        elif action == "restore":
            result = restore_user(actor, target, reason=reason, request=request)
            # Bərpa natamam ola bilər (qrup üzvlüyü, izsiz üzvlük) — operator
            # «uğur» mesajı ilə aldadılmamalıdır (QA Y-1).
            extra["restore_notices"] = list(result.notices)
            message = " ".join(("Hesab bərpa edildi.", *result.notices))
        else:  # action == "edit"
            fields = {name: payload[name] for name in EDITABLE_FIELDS if name in payload}
            changes = update_user_fields(actor, target, data=fields, request=request, reason=reason)
            extra["changed_fields"] = sorted(changes)
            message = "Məlumatlar yeniləndi." if changes else "Dəyişiklik yoxdur."
    except RimAccessError as exc:
        logger.info(
            "RİM əməliyyatı rədd edildi: action=%s actor=%s target=%s reason_code=%s",
            safe_log_value(action),
            getattr(actor.user, "pk", None),
            target.pk,
            exc.reason_code,
        )
        return _error_response(exc)

    # Kartı YENİ oxunmuş obyektdən qururuq: əməliyyat həm `User`, həm `UserProfile`
    # sətrini dəyişir və köhnə obyektdə keşlənmiş `profile` köhnə statusu göstərərdi.
    from django.contrib.auth import get_user_model

    fresh_target = get_user_model().objects.select_related("profile").filter(pk=target.pk).first() or target

    return JsonResponse(
        {
            "ok": True,
            "action": action,
            "message": message,
            "user": serialize_detail(fresh_target, actor),
            **extra,
        }
    )


__all__ = ["ALLOWED_ACTIONS", "rim_action"]
