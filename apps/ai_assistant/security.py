"""
Prompt injection and abuse detection for the AI assistant.

This module provides TWO layers of defence:

1. Input check (:func:`check_message_safety`) — a best-effort regex screen of
   the *incoming* user message. This is deliberately a SECONDARY control: it is
   easy to bypass with rephrasing, encoding, or other languages, so it must
   never be relied on alone.

2. Output sanitisation (:func:`sanitize_ai_response`) — a final guard over the
   *outgoing* model response. Even though the context fed to the model is
   already permission-filtered (see ``context_builder.build_user_context``),
   this layer redacts anything that looks like a leaked secret, credential, or
   internal system detail before the answer reaches the user.

The REAL tenant/permission guarantee is the permission-scoped context builder
plus the database Row-Level Security policies — not these regexes.
"""

from __future__ import annotations

import re

# Patterns that indicate prompt injection or privilege escalation attempts.
# Each tuple: (compiled regex, human-readable reason for blocking).
_INJECTION_PATTERNS: list[tuple[re.Pattern, str]] = [
    (
        re.compile(
            r"(?:ignore|forget|disregard|override|bypass|skip)\s+"
            r"(?:all\s+)?(?:previous|prior|above|system|your|safety|security)\s+"
            r"(?:instructions?|rules?|prompts?|guidelines?|restrictions?|permissions?)",
            re.IGNORECASE,
        ),
        "prompt_injection_override",
    ),
    (
        re.compile(
            r"(?:you\s+are\s+now|act\s+as|pretend\s+(?:to\s+be|you\s+are)|"
            r"new\s+instructions?|from\s+now\s+on\s+you|"
            r"your\s+new\s+(?:role|task|instructions?))",
            re.IGNORECASE,
        ),
        "prompt_injection_role_change",
    ),
    (
        re.compile(
            r"(?:system\s+prompt|hidden\s+prompt|initial\s+(?:prompt|instructions?)|"
            r"(?:show|reveal|print|output|repeat|display)\s+(?:your|the|system)\s+"
            r"(?:prompt|instructions?|rules?))",
            re.IGNORECASE,
        ),
        "system_prompt_extraction",
    ),
    (
        re.compile(
            r"(?:api[_\s]?key|secret[_\s]?key|gemini[_\s]?key|"
            r"database\s+(?:password|credentials?|connection|schema|structure)|"
            r"env(?:ironment)?\s+var(?:iable)?s?|\.env\b|settings\.py)",
            re.IGNORECASE,
        ),
        "sensitive_info_extraction",
    ),
    (
        re.compile(
            r"(?:superadmin|super\s+admin)\s+(?:panel|url|link|page|dashboard|access|login)",
            re.IGNORECASE,
        ),
        "admin_url_probe",
    ),
    (
        re.compile(
            r"(?:other\s+(?:user|student|teacher|person)(?:'?s)?|"
            r"another\s+(?:user|student|teacher|person)(?:'?s)?|"
            r"başqa\s+(?:tələbə|müəllim|istifadəçi))\s*"
            r"(?:data|grades?|results?|info|password|email|məlumat|bal|nəticə)",
            re.IGNORECASE,
        ),
        "cross_user_data_probe",
    ),
    (
        re.compile(
            r"(?:(?:list|show|dump|export)\s+all\s+(?:users?|students?|teachers?|emails?|passwords?)|"
            r"sql\s+inject|union\s+select|drop\s+table|;\s*delete\s|;\s*update\s)",
            re.IGNORECASE,
        ),
        "data_dump_or_injection",
    ),
    (
        re.compile(
            r"(?:do\s+not|don'?t)\s+(?:check|verify|enforce|apply)\s+"
            r"(?:permissions?|authorization|access|roles?|auth)",
            re.IGNORECASE,
        ),
        "permission_bypass_request",
    ),
]

# Hard length cap on user messages to prevent context flooding.
MAX_MESSAGE_LENGTH = 2000


def check_message_safety(message: str) -> tuple[bool, str]:
    """Check a user message for injection or abuse patterns.

    Returns (is_safe, block_reason). If is_safe is True, block_reason is empty.

    NOTE: This is a SECONDARY control. The primary guarantee that the AI cannot
    leak data is the permission-scoped context builder + database RLS. Do not
    weaken those layers because this regex screen exists.
    """
    if not message or not message.strip():
        return False, "empty_message"

    if len(message) > MAX_MESSAGE_LENGTH:
        return False, "message_too_long"

    for pattern, reason in _INJECTION_PATTERNS:
        if pattern.search(message):
            return False, reason

    return True, ""


# ── Output sanitisation ────────────────────────────────────────────────────
# Marker placed where a leaked secret/internal detail is removed.
REDACTION_MARKER = "[redacted]"

# Patterns that must never appear in a response that reaches the user. Each is
# redacted (not blocked) so a single false positive does not destroy an
# otherwise-helpful answer.
_LEAK_PATTERNS: list[re.Pattern] = [
    # Google / Gemini API key format (AIza + 35 chars).
    re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b"),
    # Brevo SMTP key format.
    re.compile(r"\bxsmtpsib-[0-9a-f]{64}-[0-9A-Za-z]{16}\b"),
    # GitHub fine-grained / classic personal access tokens.
    re.compile(r"\bgithub_pat_[0-9A-Za-z_]{22,}\b"),
    re.compile(r"\bghp_[0-9A-Za-z]{36}\b"),
    # Generic "KEY = value" / "SECRET: value" leaks of long opaque strings.
    re.compile(r"(?i)\b(?:secret[_\s-]?key|api[_\s-]?key|access[_\s-]?token|" r"password|passwd)\b\s*[:=]\s*\S{8,}"),
    # Database connection URIs with embedded credentials.
    re.compile(r"\b(?:postgres(?:ql)?|mysql|redis|mongodb)://[^\s/@]+:[^\s/@]+@\S+"),
    # Private key blocks.
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"),
]

# Phrases indicating the model echoed its own system prompt / internal rules.
_SYSTEM_PROMPT_ECHO = re.compile(
    r"(?im)^\s*(?:RULES?:|SYSTEM[_\s]?PROMPT|FORMATTING:|CONTEXT AWARENESS:|"
    r"\[User Context\b|\[Response Language\]|You are EMSArena AI Assistant)"
)


def sanitize_ai_response(answer: str) -> tuple[str, bool]:
    """Redact leaked secrets / internal details from a model response.

    Returns (clean_answer, was_modified). This is the OUTPUT-side counterpart to
    :func:`check_message_safety`. It runs after every successful model call so a
    prompt-injection that slipped past the input screen still cannot exfiltrate
    a credential or the system prompt.
    """
    if not answer:
        return answer, False

    cleaned = answer
    modified = False

    for pattern in _LEAK_PATTERNS:
        cleaned, count = pattern.subn(REDACTION_MARKER, cleaned)
        if count:
            modified = True

    # If the model echoed its own system prompt, drop those lines entirely.
    if _SYSTEM_PROMPT_ECHO.search(cleaned):
        kept = [ln for ln in cleaned.splitlines() if not _SYSTEM_PROMPT_ECHO.match(ln)]
        new_cleaned = "\n".join(kept).strip()
        if new_cleaned != cleaned:
            cleaned = new_cleaned
            modified = True

    return cleaned, modified
