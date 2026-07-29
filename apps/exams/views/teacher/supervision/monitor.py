"""teacher supervision view paketi — tələbə tərəfli proctoring endpoint-ləri.

Köhnə müəllim nəzarət UI-ı 2026-07-29-da silindi (bax paket __init__).
Burada yalnız imtahan səhifəsinin çağırdığı iki endpoint qalır.
"""

import json

from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.core.exceptions import RequestDataTooBig
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from apps.exams.features import disabled_supervision_status, exam_supervision_enabled
from apps.exams.models import ExamAttempt, SupervisionIncident
from apps.exams.services.supervision import (
    get_attempt_supervision_status,
    log_supervision_incident,
)
from core.rate_limit import record_rate_limit_hit

# EXAM-P1-10: tələbə brauzerindən gələn supervision incident POST-u
# etibarsızdır — payload sərt validasiya olunur və per-attempt throttle
# tətbiq edilir ki, saxta/spam hadisələr audit sayını şişirdə bilməsin.
_SUPERVISION_INCIDENT_RATE = "60/1m"
_SUPERVISION_METADATA_MAX_KEYS = 20
_SUPERVISION_METADATA_MAX_VALUE_LEN = 500
_SUPERVISION_BODY_MAX_BYTES = 16 * 1024
_SUPERVISION_BODY_KEYS = {"event_type", "metadata"}


def _sanitize_incident_metadata(metadata):
    """Client metadata-nı təhlükəsiz, yastı primitivlərə endirir."""
    if not isinstance(metadata, dict):
        return {}
    clean = {}
    for key, value in list(metadata.items())[:_SUPERVISION_METADATA_MAX_KEYS]:
        key = str(key)[:100]
        if isinstance(value, bool) or value is None or isinstance(value, (int, float)):
            clean[key] = value
        else:
            clean[key] = str(value)[:_SUPERVISION_METADATA_MAX_VALUE_LEN]
    return clean


def _parse_incident_body(request):
    """Kiçik və sərt schema-lı incident JSON body qaytarır."""
    raw_length = request.META.get("CONTENT_LENGTH")
    try:
        if raw_length and int(raw_length) > _SUPERVISION_BODY_MAX_BYTES:
            return None, JsonResponse({"error": "Incident payload is too large."}, status=413)
    except (TypeError, ValueError):
        return None, JsonResponse({"error": "Invalid Content-Length."}, status=400)

    try:
        raw_body = request.body
    except RequestDataTooBig:
        return None, JsonResponse({"error": "Incident payload is too large."}, status=413)
    if len(raw_body) > _SUPERVISION_BODY_MAX_BYTES:
        return None, JsonResponse({"error": "Incident payload is too large."}, status=413)

    try:
        body = json.loads(raw_body)
    except (json.JSONDecodeError, TypeError, ValueError):
        return None, JsonResponse({"error": "Invalid JSON body."}, status=400)
    if not isinstance(body, dict):
        return None, JsonResponse({"error": "JSON body must be an object."}, status=400)
    if set(body) - _SUPERVISION_BODY_KEYS:
        return None, JsonResponse({"error": "Unknown incident payload field."}, status=400)
    if not isinstance(body.get("event_type"), str):
        return None, JsonResponse({"error": "Invalid event type."}, status=400)
    if "metadata" in body and not isinstance(body["metadata"], dict):
        return None, JsonResponse({"error": "Metadata must be an object."}, status=400)
    return body, None


@login_required
@require_POST
def log_incident_api(request, attempt_id):
    """
    Student-side endpoint to log a supervision incident.
    Called by the client-side supervision JavaScript.
    """
    attempt = get_object_or_404(
        ExamAttempt,
        id=attempt_id,
        user=request.user,
    )
    if not exam_supervision_enabled():
        return JsonResponse({"supervised": False})

    is_manual_lock = bool(attempt.supervision_manual_lock and attempt.supervision_status == "locked")
    if not is_manual_lock:
        attempt.expire_if_time_limit_reached()
    if attempt.is_finished:
        return JsonResponse({"error": "Attempt is already finished."}, status=400)

    body, error_response = _parse_incident_body(request)
    if error_response is not None:
        return error_response

    event_type = body.get("event_type", "")
    metadata = body.get("metadata", {})

    # Validate event type
    valid_types = {c[0] for c in SupervisionIncident.EVENT_TYPE_CHOICES}
    if event_type not in valid_types:
        return JsonResponse({"error": "Invalid event type."}, status=400)

    # EXAM-P1-10: per-attempt throttle — bir cəhd üçün incident selini kəs.
    exceeded, retry_after = record_rate_limit_hit("supervision_incident", _SUPERVISION_INCIDENT_RATE, attempt.id)
    if exceeded:
        response = JsonResponse({"error": "Too many incidents."}, status=429)
        if retry_after:
            response["Retry-After"] = str(retry_after)
        return response

    # EXAM-P1-10: metadata sərt sanitizasiya olunur (açar/dəyər sayı və uzunluq
    # limiti, yalnız yastı primitivlər) — arbitrary/nested dict saxlanmır.
    metadata = _sanitize_incident_metadata(metadata)

    result = log_supervision_incident(attempt, event_type, metadata)

    if result is None:
        return JsonResponse({"supervised": False})

    return JsonResponse(
        {
            "supervised": True,
            "violation_count": result["violation_count"],
            "max_violations": result["max_violations"],
            "limit_exceeded": result["limit_exceeded"],
            "action_taken": result["action_taken"],
            "supervision_status": result["supervision_status"],
            "manual_lock": bool(attempt.supervision_manual_lock and attempt.supervision_status == "locked"),
            # Sınaq cəhdində limit aşılsa da kilid yoxdur — klient bunu görüb
            # dayandırma overlay-i əvəzinə xəbərdarlıq banneri göstərir.
            "is_trial": result.get("is_trial", False),
        }
    )


@login_required
@require_GET
@never_cache
def supervision_status_api(request, attempt_id):
    """
    Get current supervision status for an attempt.
    Used by student to check if they can continue.
    """
    attempt = get_object_or_404(
        ExamAttempt,
        id=attempt_id,
        user=request.user,
    )
    from apps.exams.services.final_center import clear_entry_session, final_attempt_entry_session_valid

    if not final_attempt_entry_session_valid(request, attempt):
        clear_entry_session(request)
        logout(request)
        return JsonResponse(
            {
                "entry_session_valid": False,
                "redirect_url": reverse("exams:final_exam_entry"),
            },
            status=403,
        )
    if not exam_supervision_enabled():
        return JsonResponse(disabled_supervision_status(attempt))

    is_manual_lock = bool(attempt.supervision_manual_lock and attempt.supervision_status == "locked")
    if not is_manual_lock:
        attempt.expire_if_time_limit_reached()
    attempt.expire_if_resume_window_expired()
    status = get_attempt_supervision_status(attempt)
    status["is_finished"] = attempt.is_finished
    status["attempt_status"] = attempt.status
    return JsonResponse(status)
