"""
Session settings helpers for live exam hosting.
"""

from __future__ import annotations

import secrets
from copy import deepcopy
from typing import Any

from apps.accounts.public import ProfileRole

THEME_KEYS = {"standard", "winter", "aurora", "sweet"}
LANGUAGE_KEYS = {"system", "az", "en", "ru", "tr"}
LOBBY_MUSIC_KEYS = {"original", "focus", "silent"}
DEFAULT_MAX_PARTICIPANTS = 100
PRIVILEGED_MAX_PARTICIPANTS = 500

DEFAULT_SESSION_SETTINGS: dict[str, Any] = {
    "show_questions_on_devices": True,
    "characters_enabled": True,
    "theme_key": "aurora",
    "language": "system",
    "lobby_music": "original",
    "increase_contrast": False,
    "reactions_enabled": True,
    "randomize_questions": True,
    "randomize_answers": True,
    "autoplay": True,
    "qna_enabled": False,
    "team_selection_enabled": False,
    "team_talk_enabled": False,
    "nickname_generator": False,
    "two_step_join": True,
    "max_participants": DEFAULT_MAX_PARTICIPANTS,
    "sfx_volume": 70,
}

BOOLEAN_SETTING_KEYS = {
    "show_questions_on_devices",
    "characters_enabled",
    "increase_contrast",
    "reactions_enabled",
    "randomize_questions",
    "randomize_answers",
    "autoplay",
    "qna_enabled",
    "team_selection_enabled",
    "team_talk_enabled",
    "nickname_generator",
    "two_step_join",
}

NICKNAME_ADJECTIVES = (
    "Swift",
    "Nova",
    "Bold",
    "Bright",
    "Clever",
    "Echo",
    "Pixel",
    "Rocket",
    "Storm",
    "Lucky",
)

NICKNAME_NOUNS = (
    "Falcon",
    "Comet",
    "Panda",
    "Otter",
    "Ranger",
    "Spark",
    "Turtle",
    "Tiger",
    "Wizard",
    "Voyager",
)


def default_session_settings() -> dict[str, Any]:
    return deepcopy(DEFAULT_SESSION_SETTINGS)


def _coerce_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return default


def allowed_max_participants_for_user(user) -> int:
    if user is None:
        return DEFAULT_MAX_PARTICIPANTS

    level = 0
    if getattr(user, "is_superuser", False):
        return PRIVILEGED_MAX_PARTICIPANTS
    if hasattr(user, "_highest_role_level"):
        try:
            level = int(user._highest_role_level())
        except Exception:
            level = 0
    elif hasattr(user, "profile") and getattr(user.profile, "role_level", None) is not None:
        level = int(user.profile.role_level or 0)

    return (
        PRIVILEGED_MAX_PARTICIPANTS
        if level > ProfileRole.LEVELS.get(ProfileRole.TEACHER, 60)
        else DEFAULT_MAX_PARTICIPANTS
    )


def normalize_session_setting_updates(
    raw: dict[str, Any] | None,
    *,
    max_participants_cap: int = PRIVILEGED_MAX_PARTICIPANTS,
) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {}

    updates: dict[str, Any] = {}
    for key in BOOLEAN_SETTING_KEYS:
        if key in raw:
            updates[key] = _coerce_bool(raw.get(key), DEFAULT_SESSION_SETTINGS[key])

    if "theme_key" in raw:
        value = str(raw.get("theme_key") or "").strip().lower()
        updates["theme_key"] = value if value in THEME_KEYS else DEFAULT_SESSION_SETTINGS["theme_key"]

    if "language" in raw:
        value = str(raw.get("language") or "").strip().lower()
        updates["language"] = value if value in LANGUAGE_KEYS else DEFAULT_SESSION_SETTINGS["language"]

    if "lobby_music" in raw:
        value = str(raw.get("lobby_music") or "").strip().lower()
        updates["lobby_music"] = value if value in LOBBY_MUSIC_KEYS else DEFAULT_SESSION_SETTINGS["lobby_music"]

    if "max_participants" in raw:
        try:
            value = int(raw.get("max_participants"))
        except (TypeError, ValueError):
            value = DEFAULT_SESSION_SETTINGS["max_participants"]
        updates["max_participants"] = max(1, min(value, max(1, int(max_participants_cap or DEFAULT_MAX_PARTICIPANTS))))

    if "sfx_volume" in raw:
        try:
            value = int(raw.get("sfx_volume"))
        except (TypeError, ValueError):
            value = DEFAULT_SESSION_SETTINGS["sfx_volume"]
        updates["sfx_volume"] = max(0, min(100, value))

    return updates


def normalize_session_settings(raw: dict[str, Any] | None) -> dict[str, Any]:
    settings = default_session_settings()
    settings.update(normalize_session_setting_updates(raw, max_participants_cap=PRIVILEGED_MAX_PARTICIPANTS))
    return settings


def get_session_settings(session) -> dict[str, Any]:
    return normalize_session_settings(getattr(session, "host_settings", None) or {})


def update_session_settings(
    session,
    updates: dict[str, Any] | None,
    *,
    max_participants_cap: int = PRIVILEGED_MAX_PARTICIPANTS,
) -> dict[str, Any]:
    raw = getattr(session, "host_settings", None) or {}
    merged = get_session_settings(session)
    merged.update(normalize_session_setting_updates(updates, max_participants_cap=max_participants_cap))
    if isinstance(raw, dict):
        for key, value in raw.items():
            if key not in DEFAULT_SESSION_SETTINGS:
                merged[key] = value
    session.host_settings = merged
    session.save(update_fields=["host_settings"])

    # Invalidate the cache so the next read picks up the fresh settings.
    try:
        from core.cache import invalidate_session_settings_cache

        invalidate_session_settings_cache(session)
    except Exception:
        pass

    return merged


def session_join_path(session) -> str:
    settings = get_session_settings(session)
    return "/live/" if settings.get("two_step_join", True) else session.join_url_path()


def generate_guest_nickname() -> str:
    return (
        f"{secrets.choice(NICKNAME_ADJECTIVES)} " f"{secrets.choice(NICKNAME_NOUNS)} " f"{secrets.randbelow(90) + 10}"
    )
