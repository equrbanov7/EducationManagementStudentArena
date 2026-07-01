"""live_exam player paketi — _shared."""

import secrets
from itertools import product

from django.db.models import Q
from django.utils.translation import get_language

from apps.live_exam.auth import LIVE_CLIENT_ID_COOKIE_MAX_AGE, LIVE_CLIENT_ID_COOKIE_NAME, clean_nickname, get_client_id
from apps.live_exam.constants import ACCESSORY_KEYS, AVATAR_KEYS, DEFAULT_ACCESSORY_KEY, DEFAULT_AVATAR_KEY
from apps.live_exam.models import LiveSession
from apps.live_exam.session_settings import THEME_KEYS, get_session_settings
from apps.live_exam.transport import broadcast, build_lobby_state_payload
from core.rls import bypass_rls
from core.utils import get_client_ip

from .constants import (
    _AMBIGUOUS_PIN_GLYPHS,
    _JOINABLE_SESSION_STATES,
    _MAX_AMBIGUOUS_PIN_CANDIDATES,
    JOIN_RESUME_COPY,
    NICKNAME_CONFLICT_COPY,
    PIN_ENTRY_COPY,
)


def _pin_entry_copy() -> dict[str, str]:
    lang = (get_language() or "az")[:2].lower()
    return PIN_ENTRY_COPY.get(lang, PIN_ENTRY_COPY["az"])


def _pin_entry_theme_key(pin_value: str, raw_theme: str | None = None) -> str:
    _, session = _resolve_live_session(pin_value)
    if session:
        return str(get_session_settings(session).get("theme_key") or "aurora")

    theme_key = str(raw_theme or "").strip().lower()
    return theme_key if theme_key in THEME_KEYS else "aurora"


def _join_resume_copy(nickname: str) -> dict[str, str]:
    lang = (get_language() or "az")[:2].lower()
    copy = JOIN_RESUME_COPY.get(lang, JOIN_RESUME_COPY["az"]).copy()
    safe_nickname = clean_nickname(nickname) or "Player"
    for key, value in copy.items():
        copy[key] = value.format(nickname=safe_nickname)
    return copy


def _normalize_pin(raw_pin: str | None) -> str:
    """
    Normalize a raw PIN input to the canonical format used by ``LiveSession``.

    Strips whitespace, converts to uppercase (the PIN alphabet is digits +
    A–Z) and truncates to ``PIN_LENGTH`` characters.  Non-alphanumeric
    characters are removed.
    """
    from apps.live_exam.models import PIN_LENGTH

    return "".join(ch for ch in str(raw_pin or "").upper() if ch.isalnum())[:PIN_LENGTH]


def _candidate_pin_variants(pin_value: str) -> tuple[str, ...]:
    normalized = _normalize_pin(pin_value)
    if not normalized:
        return ()

    variants: list[tuple[str, ...]] = []
    variant_count = 1
    for ch in normalized:
        choices = _AMBIGUOUS_PIN_GLYPHS.get(ch, (ch,))
        variants.append(choices)
        variant_count *= len(choices)
        if variant_count > _MAX_AMBIGUOUS_PIN_CANDIDATES:
            return (normalized,)

    if variant_count == 1:
        return (normalized,)

    return tuple(dict.fromkeys("".join(chars) for chars in product(*variants)))


def _resolve_live_session(raw_pin: str | None) -> tuple[str, LiveSession | None]:
    from apps.live_exam.models import MIN_PIN_LENGTH, PIN_LENGTH

    normalized = _normalize_pin(raw_pin)
    if len(normalized) < MIN_PIN_LENGTH:
        return normalized, None

    with bypass_rls():
        exact_match = LiveSession.objects.select_related("exam").filter(pin=normalized).first()
        if exact_match:
            return exact_match.pin, exact_match

        candidates = _candidate_pin_variants(normalized)
        matches = list(LiveSession.objects.select_related("exam").filter(pin__in=candidates).order_by("id")[:2])
        if len(matches) == 1:
            return matches[0].pin, matches[0]

        if len(normalized) < PIN_LENGTH:
            prefix_candidates = tuple(
                dict.fromkeys(candidate for candidate in candidates if len(candidate) >= MIN_PIN_LENGTH)
            )
            prefix_query = None
            for prefix in prefix_candidates:
                clause = Q(pin__startswith=prefix)
                prefix_query = clause if prefix_query is None else prefix_query | clause

            if prefix_query is not None:
                prefix_matches = list(
                    LiveSession.objects.select_related("exam")
                    .filter(prefix_query, state__in=_JOINABLE_SESSION_STATES)
                    .order_by("id")[:2]
                )
                if len(prefix_matches) == 1:
                    return prefix_matches[0].pin, prefix_matches[0]

    return normalized, None


def _nickname_conflict_message() -> str:
    lang = (get_language() or "az")[:2].lower()
    return NICKNAME_CONFLICT_COPY.get(lang, NICKNAME_CONFLICT_COPY["az"])


def _random_join_avatar_key() -> str:
    return secrets.choice(AVATAR_KEYS) if AVATAR_KEYS else DEFAULT_AVATAR_KEY


def _random_join_accessory_key() -> str:
    candidates = [key for key in ACCESSORY_KEYS if key and key != DEFAULT_ACCESSORY_KEY]
    return secrets.choice(candidates) if candidates else DEFAULT_ACCESSORY_KEY


def _nickname_is_taken(
    session: LiveSession,
    nickname: str,
    *,
    exclude_player_id: int | None = None,
    exclude_client_id: str | None = None,
) -> bool:
    with bypass_rls():
        queryset = session.players.filter(nickname__iexact=nickname)
        if exclude_player_id:
            queryset = queryset.exclude(id=exclude_player_id)
        if exclude_client_id:
            queryset = queryset.exclude(client_id=exclude_client_id)
        return queryset.exists()


def _live_client_id_key(request) -> str:
    return request.COOKIES.get(LIVE_CLIENT_ID_COOKIE_NAME) or get_client_ip(request) or "unknown"


def _ensure_live_client_cookie(request, response):
    if request.COOKIES.get(LIVE_CLIENT_ID_COOKIE_NAME):
        return response

    response.set_cookie(
        LIVE_CLIENT_ID_COOKIE_NAME,
        get_client_id(request),
        max_age=LIVE_CLIENT_ID_COOKIE_MAX_AGE,
        samesite="Lax",
        secure=request.is_secure(),
    )
    return response


def _broadcast_lobby_state(session: LiveSession) -> None:
    with bypass_rls():
        broadcast(session.pin, build_lobby_state_payload(session), "lobby")
