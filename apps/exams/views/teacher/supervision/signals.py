"""Tələbə tərəfli proktorinq SİQNAL və HEARTBEAT endpoint-ləri (2026-10-01).

* ``POST supervision/api/signal/<attempt_id>/`` — evristik aşkarlama
  (genişlənmə, DevTools, əlavə monitor, mətn inyeksiyası …) → ``ProctoringLog``.
* ``POST supervision/api/heartbeat/<attempt_id>/`` — skriptin canlılığı →
  yalnız cache (DB yazısı yox); uzun fasilə sonrası bir ``heartbeat_gap`` siqnalı.

Hər ikisi: yalnız cəhdin sahibi, yalnız davam edən cəhd, yalnız nəzarətli
imtahan; sərt JSON sxemi + ölçü limiti + cəhd başına rate-limit. Server
klientin «ciddilik» və ya «xal» dəyərinə ETİBAR ETMİR.
"""

import json

from django.contrib.auth.decorators import login_required
from django.core.exceptions import RequestDataTooBig
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from apps.exams.features import exam_supervision_enabled
from apps.exams.models import ExamAttempt
from apps.exams.services.supervision import get_supervision_config
from apps.exams.services.supervision.heartbeat import HEARTBEAT_INTERVAL_SECONDS, record_heartbeat
from apps.exams.services.supervision.signals import CLIENT_SIGNAL_KINDS, log_proctoring_signal, signal_throttle
from core.rate_limit import record_rate_limit_hit

_BODY_MAX_BYTES = 4 * 1024
_HEARTBEAT_RATE = "12/1m"
# DB-dən əvvəlki istifadəçi səviyyəli qoruyucu (başqasının cəhd id-si ilə sel → 404 sorğuları).
_SIGNAL_USER_RATE = "60/1m"


def _json_error(message, status):
    return JsonResponse({"error": message}, status=status)


def _parse_body(request, allowed_keys):
    raw_length = request.META.get("CONTENT_LENGTH")
    try:
        if raw_length and int(raw_length) > _BODY_MAX_BYTES:
            return None, _json_error("Payload is too large.", 413)
    except (TypeError, ValueError):
        return None, _json_error("Invalid Content-Length.", 400)
    try:
        raw_body = request.body
    except RequestDataTooBig:
        return None, _json_error("Payload is too large.", 413)
    if len(raw_body) > _BODY_MAX_BYTES:
        return None, _json_error("Payload is too large.", 413)
    try:
        body = json.loads(raw_body or b"{}")
    except (json.JSONDecodeError, TypeError, ValueError):
        return None, _json_error("Invalid JSON body.", 400)
    if not isinstance(body, dict):
        return None, _json_error("JSON body must be an object.", 400)
    if set(body) - allowed_keys:
        return None, _json_error("Unknown payload field.", 400)
    return body, None


def _supervised_attempt_or_response(request, attempt_id):
    """(attempt, None) və ya (None, JsonResponse) — sahiblik + status + nəzarət."""
    attempt = get_object_or_404(
        ExamAttempt.objects.select_related("exam", "exam__supervision_config"),
        id=attempt_id,
        user=request.user,
    )
    if not exam_supervision_enabled() or get_supervision_config(attempt.exam) is None:
        return None, JsonResponse({"supervised": False})
    if attempt.is_finished:
        return None, JsonResponse({"supervised": True, "finished": True}, status=409)
    return attempt, None


@login_required
@require_POST
@never_cache
def log_signal_api(request, attempt_id):
    body, error = _parse_body(request, {"kind", "detail"})
    if error is not None:
        return error
    kind = body.get("kind")
    if not isinstance(kind, str) or kind not in CLIENT_SIGNAL_KINDS:
        return _json_error("Invalid signal kind.", 400)
    detail = body.get("detail", {})
    if not isinstance(detail, dict):
        return _json_error("Detail must be an object.", 400)

    exceeded, _retry = record_rate_limit_hit("proctor_signal_user", _SIGNAL_USER_RATE, request.user.id)
    if exceeded:
        response = _json_error("Too many signals.", 429)
        response["Retry-After"] = "60"
        return response

    attempt, response = _supervised_attempt_or_response(request, attempt_id)
    if response is not None:
        return response

    verdict = signal_throttle(attempt.pk, kind)
    if verdict == "rate":
        response = _json_error("Too many signals.", 429)
        response["Retry-After"] = "60"
        return response
    if verdict == "dedup":
        return JsonResponse({"supervised": True, "logged": False})
    log_proctoring_signal(attempt, kind, detail)
    return JsonResponse({"supervised": True, "logged": True})


@login_required
@require_POST
@never_cache
def heartbeat_api(request, attempt_id):
    body, error = _parse_body(request, {"state"})
    if error is not None:
        return error
    state = body.get("state", {})
    if not isinstance(state, dict):
        return _json_error("State must be an object.", 400)

    # Limit DB-dən ƏVVƏL: qaçaq dövrə bazaya toxunmasın (açar: istifadəçi + cəhd).
    exceeded, retry_after = record_rate_limit_hit("proctor_heartbeat", _HEARTBEAT_RATE, request.user.id, attempt_id)
    if exceeded:
        response = _json_error("Too many heartbeats.", 429)
        response["Retry-After"] = str(retry_after or HEARTBEAT_INTERVAL_SECONDS)
        return response

    attempt, response = _supervised_attempt_or_response(request, attempt_id)
    if response is not None:
        return response

    result = record_heartbeat(attempt.pk, state)
    if result.get("gap_seconds"):
        if signal_throttle(attempt.pk, "heartbeat_gap") == "ok":
            log_proctoring_signal(attempt, "heartbeat_gap", {"gap_seconds": result["gap_seconds"]})
    return JsonResponse({"supervised": True, "interval": HEARTBEAT_INTERVAL_SECONDS})


__all__ = ["heartbeat_api", "log_signal_api"]
