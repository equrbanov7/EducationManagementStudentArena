"""
Prompt injection and abuse detection for the AI assistant.

Blocks requests that attempt to:
- Extract system prompts, API keys, or internal configuration
- Bypass permission checks or role restrictions
- Access other users' data or cross-tenant information
- Inject instructions to override the AI's behavior
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
    """
    if not message or not message.strip():
        return False, "empty_message"

    if len(message) > MAX_MESSAGE_LENGTH:
        return False, "message_too_long"

    for pattern, reason in _INJECTION_PATTERNS:
        if pattern.search(message):
            return False, reason

    return True, ""
