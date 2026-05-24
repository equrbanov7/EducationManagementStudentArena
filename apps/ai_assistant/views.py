"""
AI Assistant API views.

POST /api/ai-assistant/chat/ — authenticated users only.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from datetime import timezone as datetime_timezone

from django.conf import settings
from django.http import JsonResponse
from django.utils import timezone
from django.utils.translation import pgettext
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_GET, require_POST

from core.rate_limit import is_rate_limited, parse_rate, record_rate_limit_hit

from .context_builder import build_user_context
from .gemini_client import ask_gemini
from .models import AIAssistantLog
from .security import check_message_safety, sanitize_ai_response

logger = logging.getLogger(__name__)

_RATE_SCOPE = "ai_assistant"


def _get_rate_limit() -> str:
    return getattr(settings, "AI_ASSISTANT_RATE_LIMIT", "25/1h")


def _get_quota_info(user_id: int) -> dict:
    """Return remaining request count and reset time."""
    rate = _get_rate_limit()
    parsed = parse_rate(rate)
    if parsed is None:
        return {"remaining_requests": 0, "limit": 0, "reset_at": None}

    from core.rate_limit import _cache_keys, _rate_limit_cache

    rl_cache = _rate_limit_cache()
    count_key, expires_key = _cache_keys(_RATE_SCOPE, (user_id,))
    current = int(rl_cache.get(count_key) or 0)
    remaining = max(0, parsed.limit - current)

    expires_at_ts = rl_cache.get(expires_key)
    if expires_at_ts is not None:
        reset_at = datetime.fromtimestamp(float(expires_at_ts), tz=datetime_timezone.utc).isoformat()
    else:
        reset_at = (timezone.now() + timedelta(seconds=parsed.window_seconds)).isoformat()

    return {
        "remaining_requests": remaining,
        "limit": parsed.limit,
        "reset_at": reset_at,
    }


@require_GET
def quota_view(request):
    """Return the authenticated user's current AI assistant quota."""
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Authentication required."}, status=401)

    return JsonResponse(_get_quota_info(request.user.id))


@require_POST
@csrf_protect
def chat_view(request):
    """Handle an AI assistant chat request."""
    # ── Authentication check ──────────────────────────────────────────
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Authentication required."}, status=401)

    user = request.user
    organization = getattr(request, "organization", None)
    memberships = list(getattr(request, "org_memberships", []) or [])

    # ── Parse request body ────────────────────────────────────────────
    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"error": "Invalid JSON body."}, status=400)

    message = (body.get("message") or "").strip()
    if not message:
        return JsonResponse({"error": "Message is required."}, status=400)

    # ── Security: prompt injection check ──────────────────────────────
    is_safe, block_reason = check_message_safety(message)
    if not is_safe:
        _log_request(
            user=user,
            organization=organization,
            memberships=memberships,
            prompt=message[:500],
            status=AIAssistantLog.Status.BLOCKED,
            block_reason=block_reason,
        )
        return JsonResponse(
            {
                "answer": _blocked_response(block_reason),
                **_get_quota_info(user.id),
            }
        )

    # ── Rate limiting ─────────────────────────────────────────────────
    rate = _get_rate_limit()
    limited, retry_after = is_rate_limited(_RATE_SCOPE, rate, user.id)
    if limited:
        _log_request(
            user=user,
            organization=organization,
            memberships=memberships,
            prompt=message[:500],
            status=AIAssistantLog.Status.RATE_LIMITED,
        )
        return JsonResponse(
            {
                "error": "rate_limit_exceeded",
                "answer": pgettext(
                    "ai_assistant.limit_exceeded",
                    "Saatlıq AI sorğu limitinə çatdınız. Zəhmət olmasa bir az sonra yenidən cəhd edin.",
                ),
                **_get_quota_info(user.id),
            },
            status=429,
        )

    # ── Build permission-filtered context ─────────────────────────────
    current_page = (body.get("current_page") or "").strip()[:500]
    try:
        context = build_user_context(request, current_page=current_page)
    except Exception:
        logger.exception("Failed to build AI assistant context")
        context = f"[User: {user.username}]\nContext unavailable."

    # ── Call Gemini ───────────────────────────────────────────────────
    result = ask_gemini(user_message=message, context=context)

    if not result["ok"]:
        _log_request(
            user=user,
            organization=organization,
            memberships=memberships,
            prompt=message[:500],
            status=AIAssistantLog.Status.ERROR,
            response_summary=result.get("error", "")[:500],
        )
        return JsonResponse(
            {
                "error": "ai_service_error",
                "answer": pgettext("ai_assistant.error", "Xəta baş verdi. Zəhmət olmasa yenidən cəhd edin."),
                **_get_quota_info(user.id),
            },
            status=502,
        )

    # ── Output sanitisation ───────────────────────────────────────────
    # Final guard: redact any leaked secret / system-prompt echo from the
    # model response before it reaches the user. The context fed to Gemini is
    # already permission-filtered, so a redaction here means either a prompt
    # injection slipped past the input screen or the model misbehaved — either
    # way it is recorded in the audit log for review.
    answer, was_redacted = sanitize_ai_response(result["answer"])

    # ── Record rate limit hit and log ─────────────────────────────────
    record_rate_limit_hit(_RATE_SCOPE, rate, user.id)

    _log_request(
        user=user,
        organization=organization,
        memberships=memberships,
        prompt=message[:500],
        status=AIAssistantLog.Status.SUCCESS,
        response_summary=answer[:500],
        block_reason="response_redacted" if was_redacted else "",
        prompt_tokens=result.get("prompt_tokens", 0),
        response_tokens=result.get("response_tokens", 0),
    )

    if was_redacted:
        logger.warning(
            "AI assistant response was redacted for user %s (possible leak/injection)",
            user.id,
        )

    return JsonResponse(
        {
            "answer": answer,
            **_get_quota_info(user.id),
        }
    )


def _log_request(
    *,
    user,
    organization,
    memberships,
    prompt: str,
    status: str,
    block_reason: str = "",
    response_summary: str = "",
    prompt_tokens: int = 0,
    response_tokens: int = 0,
):
    """Write an audit log entry for this AI assistant interaction."""
    role_names = []
    for m in memberships or []:
        role = getattr(m, "role", None)
        if role:
            role_names.append(getattr(role, "display_name", "") or getattr(role, "name", ""))

    try:
        AIAssistantLog.objects.create(
            user=user,
            organization=organization,
            role_name=", ".join(role_names)[:100],
            prompt=prompt,
            response_summary=response_summary,
            status=status,
            block_reason=block_reason[:255],
            prompt_tokens=prompt_tokens,
            response_tokens=response_tokens,
        )
    except Exception:
        logger.exception("Failed to log AI assistant request")


def _blocked_response(reason: str) -> str:
    """Return a user-friendly message for blocked requests."""
    messages = {
        "empty_message": pgettext("ai_assistant.blocked", "Zəhmət olmasa mesajınızı daxil edin."),
        "message_too_long": pgettext("ai_assistant.blocked", "Mesajınız çox uzundur. Zəhmət olmasa qısaldın."),
        "prompt_injection_override": pgettext("ai_assistant.blocked", "Bu növ sorğu icazəli deyil."),
        "prompt_injection_role_change": pgettext("ai_assistant.blocked", "Bu növ sorğu icazəli deyil."),
        "system_prompt_extraction": pgettext("ai_assistant.blocked", "Sistem təlimatlarına baxmaq mümkün deyil."),
        "sensitive_info_extraction": pgettext("ai_assistant.blocked", "Bu məlumata giriş icazəli deyil."),
        "admin_url_probe": pgettext("ai_assistant.blocked", "Bu sahəyə giriş hüququnuz yoxdur."),
        "cross_user_data_probe": pgettext(
            "ai_assistant.blocked", "Başqa istifadəçilərin məlumatlarına giriş icazəli deyil."
        ),
        "data_dump_or_injection": pgettext("ai_assistant.blocked", "Bu növ sorğu icazəli deyil."),
        "permission_bypass_request": pgettext("ai_assistant.blocked", "İcazə qaydalarını keçmək mümkün deyil."),
    }
    return messages.get(reason, pgettext("ai_assistant.blocked", "Bu sorğu blok olundu."))
