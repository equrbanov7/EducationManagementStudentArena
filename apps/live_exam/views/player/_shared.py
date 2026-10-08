"""live_exam player paketi — _shared."""

import secrets
from itertools import product

from django.conf import settings

from apps.live_exam.auth import (
    LIVE_CLIENT_ID_COOKIE_MAX_AGE,
    LIVE_CLIENT_ID_COOKIE_NAME,
    clean_nickname,
    get_client_id,
    get_request_client_id,
    nickname_match_key,
)
from apps.live_exam.constants import ACCESSORY_KEYS, AVATAR_KEYS, DEFAULT_ACCESSORY_KEY, DEFAULT_AVATAR_KEY
from apps.live_exam.models import LiveSession
from apps.live_exam.session_settings import THEME_KEYS, get_session_settings
from apps.live_exam.transport import broadcast, build_lobby_state_payload
from core.rate_limit import is_rate_limited, record_rate_limit_hit
from core.rls import bypass_rls
from core.utils import get_client_ip

from .constants import (
    _AMBIGUOUS_PIN_GLYPHS,
    _MAX_AMBIGUOUS_PIN_CANDIDATES,
    LIVE_PIN_IP_LIMIT_SCOPE,
    LIVE_PIN_IP_RATE_LIMIT_DEFAULT,
    LIVE_PIN_LIMIT_SCOPE,
)
from .texts import join_resume_copy, nickname_conflict_message, pin_entry_copy


def _pin_entry_copy() -> dict[str, str]:
    return pin_entry_copy()


def _pin_entry_theme_key(session: LiveSession | None = None, raw_theme: str | None = None) -> str:
    # Audit 2026-09-28 LXS-06: mövzu ARTIQ həll olunmuş sessiyadan götürülür —
    # əvvəl PIN burada ikinci dəfə (limitsiz) həll olunurdu və limit dolanda da
    # 429 səhifəsinin ``data-live-theme``-i PIN-in mövcudluğunu açırdı.
    if session is not None:
        return str(get_session_settings(session).get("theme_key") or "aurora")

    theme_key = str(raw_theme or "").strip().lower()
    return theme_key if theme_key in THEME_KEYS else "aurora"


def _join_resume_copy(nickname: str) -> dict[str, str]:
    return join_resume_copy(clean_nickname(nickname) or "Player")


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
    from apps.live_exam.models import MIN_PIN_LENGTH

    normalized = _normalize_pin(raw_pin)
    if len(normalized) < MIN_PIN_LENGTH:
        return normalized, None

    with bypass_rls():
        exact_match = LiveSession.objects.select_related("exam").filter(pin=normalized).first()
        if exact_match:
            return exact_match.pin, exact_match

        # Audit 2026-09-28 EX28-10: yalnız TAM PIN uyğunluğu (qarışdırılan
        # simvol variantları da tam uzunluqdadır). Əvvəlki ``pin__startswith``
        # prefiks axtarışı 6 simvolla aktiv oyunu tapmağa imkan verirdi —
        # 10 simvollu PIN-in entropiyası praktiki olaraq 6 simvola enirdi.
        candidates = _candidate_pin_variants(normalized)
        matches = list(LiveSession.objects.select_related("exam").filter(pin__in=candidates).order_by("id")[:2])
        if len(matches) == 1:
            return matches[0].pin, matches[0]

    return normalized, None


def _nickname_conflict_message() -> str:
    return nickname_conflict_message()


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
    """Ad «eyni görünür»mü — Audit 2026-09-28 LXS-03.

    Əvvəl ``nickname__iexact`` idi: «Ali\\u200b», «Аli» (kiril А), «Ａｌｉ», «ALİ»
    mövcud «Ali» ilə toqquşmurdu (liderlik cədvəlində saxta dublikat). İndi
    təmizlənmiş, casefold + homoglif açarı Python-da müqayisə olunur (sessiyada
    ≤ 500 oyunçu; çağıran adətən sessiya sətrini kilidləyib).
    """
    wanted = nickname_match_key(nickname)
    if not wanted:
        return False
    with bypass_rls():
        rows = session.players.values_list("id", "client_id", "nickname")
        for player_id, client_id, other in rows:
            if exclude_player_id and player_id == exclude_player_id:
                continue
            if exclude_client_id and client_id == exclude_client_id:
                continue
            if nickname_match_key(other) == wanted:
                return True
    return False


def _live_client_bucket_key(request) -> str:
    """Per-klient sərt vedrə açarı — YALNIZ etibarlı ``live_client_id`` üçün.

    Audit 2026-09-28 LXS-05: əvvəl cookie-siz klientin açarı İP idi — bütün sinfin
    NAT-ı bir «klient» vedrəsini (20/5dəq) bölüşürdü. Cookie-siz klienti yalnız
    İP vedrələri məhdudlaşdırır.
    """
    client_id = get_request_client_id(request)
    return f"client:{client_id}" if client_id else ""


def _live_ip_key(request) -> str:
    """Cookie-dən asılı olmayan İP açarı (EX28-10)."""
    return f"ip:{get_client_ip(request) or 'unknown'}"


def _pin_ip_rate() -> str:
    return getattr(settings, "LIVE_PIN_IP_RATE_LIMIT", LIVE_PIN_IP_RATE_LIMIT_DEFAULT)


def _pin_miss_buckets(request):
    buckets = [(LIVE_PIN_IP_LIMIT_SCOPE, _pin_ip_rate(), _live_ip_key(request))]
    client_key = _live_client_bucket_key(request)
    if client_key:
        buckets.append((LIVE_PIN_LIMIT_SCOPE, settings.LIVE_EXAM_JOIN_RATE_LIMIT, client_key))
    return buckets


def pin_lookup_limited(request) -> tuple[bool, int | None]:
    """UĞURSUZ PIN axtarışı büdcəsi (İP + etibarlı klient) bitibmi — ``(limited, retry_after)``.

    Audit 2026-09-28 LXS-06: büdcə BÜTÜN PIN həll edən giriş nöqtələri üçün
    ortaqdır (pin_entry, join səhifəsi, join/enter). Limit dolanda PIN ümumiyyətlə
    HƏLL OLUNMUR — əks halda «tapıldı / tapılmadı» fərqi brute force-u davam etdirərdi.
    """
    for scope, rate, key in _pin_miss_buckets(request):
        limited, retry_after = is_rate_limited(scope, rate, key)
        if limited:
            return True, retry_after
    return False, None


def record_pin_miss(request) -> None:
    """Uğursuz PIN axtarışını say (uğurlu axtarış heç vaxt sayılmır — sinif NAT-ı)."""
    for scope, rate, key in _pin_miss_buckets(request):
        record_rate_limit_hit(scope, rate, key)


def _ensure_live_client_cookie(request, response):
    if get_request_client_id(request):
        return response

    # Audit 2026-09-28 LXS-10: HttpOnly — JS bu cookie-ni oxumur, o isə
    # join/enter-də oyunçunu geri almaq açarıdır (XSS ilə oğurlanmasın).
    response.set_cookie(
        LIVE_CLIENT_ID_COOKIE_NAME,
        get_client_id(request),
        max_age=LIVE_CLIENT_ID_COOKIE_MAX_AGE,
        samesite="Lax",
        httponly=True,
        secure=request.is_secure(),
    )
    return response


def _broadcast_lobby_state(session: LiveSession) -> None:
    with bypass_rls():
        broadcast(session.pin, build_lobby_state_payload(session), "lobby")
