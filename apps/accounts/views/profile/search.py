"""
Input-sanitization helpers for the public profile view and avatar serving.

All functions here are pure: they validate/normalize untrusted query-string
values and never touch the database or the request beyond what is passed in.
"""

from django.core.exceptions import ValidationError

from .constants import (
    PROFILE_AVATAR_VERSION_MAX_LENGTH,
    PROFILE_AVATAR_VERSION_PATTERN,
    PUBLIC_PROFILE_ALLOWED_QUERY_PUNCTUATION,
    PUBLIC_PROFILE_CATEGORY_MAX_LENGTH,
    PUBLIC_PROFILE_CATEGORY_PATTERN,
    PUBLIC_PROFILE_FORMAT_SPECIFIER_PATTERN,
    PUBLIC_PROFILE_PAGE_NUMBER_PATTERN,
    PUBLIC_PROFILE_SEARCH_MAX_LENGTH,
)


def _normalize_public_profile_query_value(raw_value, *, max_length):
    normalized = " ".join(str(raw_value or "").split())
    return normalized[:max_length]


def _sanitize_public_profile_search_query(raw_value):
    normalized = _normalize_public_profile_query_value(raw_value, max_length=PUBLIC_PROFILE_SEARCH_MAX_LENGTH)
    if not normalized:
        return "", False

    if PUBLIC_PROFILE_FORMAT_SPECIFIER_PATTERN.search(normalized):
        return "", True

    sanitized = "".join(
        character
        for character in normalized
        if character.isalnum() or character in PUBLIC_PROFILE_ALLOWED_QUERY_PUNCTUATION
    ).strip()
    return sanitized[:PUBLIC_PROFILE_SEARCH_MAX_LENGTH], sanitized != normalized


def _validate_public_profile_category(raw_value, *, allowed_slugs):
    normalized = _normalize_public_profile_query_value(raw_value, max_length=PUBLIC_PROFILE_CATEGORY_MAX_LENGTH).lower()
    if not normalized:
        return "", False

    if not PUBLIC_PROFILE_CATEGORY_PATTERN.fullmatch(normalized):
        return "", True

    if normalized not in allowed_slugs:
        return "", True

    return normalized, False


def _parse_public_profile_page_number(raw_value):
    normalized = str(raw_value or "").strip()
    if not normalized:
        return None

    if not PUBLIC_PROFILE_PAGE_NUMBER_PATTERN.fullmatch(normalized):
        return None

    return int(normalized)


def _validate_profile_avatar_version(raw_value):
    normalized = _normalize_public_profile_query_value(raw_value, max_length=PROFILE_AVATAR_VERSION_MAX_LENGTH)
    if not normalized:
        return ""

    if not PROFILE_AVATAR_VERSION_PATTERN.fullmatch(normalized):
        raise ValidationError("Invalid avatar version parameter.")

    return normalized
