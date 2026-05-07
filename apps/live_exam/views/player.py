"""
live_exam/views/player.py
──────────────────────────
Player views for live exam sessions.
"""

from __future__ import annotations

import io
import secrets
from itertools import product

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import get_language, pgettext
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

import qrcode

from apps.live_exam.auth import (
    LIVE_CLIENT_ID_COOKIE_MAX_AGE,
    LIVE_CLIENT_ID_COOKIE_NAME,
    PLAYER_COOKIE_NAME,
    PLAYER_TOKEN_MAX_AGE,
    build_player_token,
    clean_nickname,
    get_client_id,
    get_request_player,
)
from apps.live_exam.constants import (
    ACCESSORY_KEYS,
    AVATAR_KEYS,
    DEFAULT_ACCESSORY_KEY,
    DEFAULT_AVATAR_KEY,
    REACTION_KEYS,
    REACTIONS,
    build_wait_room_catalog,
)
from apps.live_exam.models import LivePlayer, LiveSession
from apps.live_exam.serializers import serialize_player_identity, serialize_players
from apps.live_exam.session_settings import (
    DEFAULT_MAX_PARTICIPANTS,
    THEME_KEYS,
    generate_guest_nickname,
    get_session_settings,
)
from apps.live_exam.transport import (
    broadcast,
    build_join_url,
    build_lobby_state_payload,
    build_reaction_event_payload,
)
from core.rate_limit import is_rate_limited, record_rate_limit_hit
from core.rls import bypass_rls
from core.utils import get_client_ip

PIN_ENTRY_COPY = {
    "az": {
        "title": "Canlı imtahana qoşul",
        "eyebrow": "EMSArena Live",
        "subtitle": "Müəllimin göstərdiyi PIN-i yaz, sonra adını seçib oyuna daxil ol.",
        "pin_label": "Oyun PIN-i",
        "pin_placeholder": "Məsələn: 3A8K2B94F1",
        "button": "Davam et",
        "hint": "PIN-i ekranda gördüyün kimi daxil et. Növbəti addımda ad və avatar seçəcəksən.",
        "feature_fast": "Saniyələr içində qoşul",
        "feature_device": "Telefon, planşet və kompüterdən işləyir",
        "feature_live": "Canlı nəticə və liderlik cədvəli",
        "card_title": "Hazırsan?",
        "card_subtitle": "Bir URL, bir PIN, hamısı eyni oyunda.",
        "footer_left": "Müəllim ekranında PIN və QR kod görünür.",
        "footer_right": "Daxil olduqdan sonra avatar və ad seçimi gəlir.",
        "loading": "Yoxlanılır...",
        "invalid_pin": "Düzgün PIN daxil et.",
        "session_not_found": "Bu PIN tapılmadı və ya oyun bağlanıb.",
    },
    "en": {
        "title": "Join a live exam",
        "eyebrow": "EMSArena Live",
        "subtitle": "Enter the PIN shown by the teacher, then choose your name and join the game.",
        "pin_label": "Game PIN",
        "pin_placeholder": "Example: 3A8K2B94F1",
        "button": "Continue",
        "hint": "Type the PIN exactly as shown on screen. You will choose your nickname and avatar next.",
        "feature_fast": "Join in seconds",
        "feature_device": "Works on phone, tablet, and desktop",
        "feature_live": "Live results and leaderboard",
        "card_title": "Ready to play?",
        "card_subtitle": "One link, one PIN, everyone in the same session.",
        "footer_left": "The teacher screen shows the PIN and QR code.",
        "footer_right": "After this step, students choose nickname and avatar.",
        "loading": "Checking...",
        "invalid_pin": "Enter a valid PIN.",
        "session_not_found": "This PIN was not found or the session is closed.",
    },
    "ru": {
        "title": "Присоединитесь к живому экзамену",
        "eyebrow": "EMSArena Live",
        "subtitle": "Введите PIN, который показал преподаватель, затем выберите имя и войдите в игру.",
        "pin_label": "PIN игры",
        "pin_placeholder": "Например: 3A8K2B94F1",
        "button": "Продолжить",
        "hint": "Введите PIN точно как на экране. На следующем шаге вы выберете ник и аватар.",
        "feature_fast": "Подключение за несколько секунд",
        "feature_device": "Работает на телефоне, планшете и компьютере",
        "feature_live": "Живые результаты и таблица лидеров",
        "card_title": "Готовы?",
        "card_subtitle": "Одна ссылка, один PIN, одна общая сессия.",
        "footer_left": "На экране преподавателя видны PIN и QR-код.",
        "footer_right": "После этого шага ученик выбирает ник и аватар.",
        "loading": "Проверяем...",
        "invalid_pin": "Введите действительный PIN.",
        "session_not_found": "Такой PIN не найден или сессия уже закрыта.",
    },
    "tr": {
        "title": "Canlı sınava katıl",
        "eyebrow": "EMSArena Live",
        "subtitle": "Öğretmenin gösterdiği PIN kodunu gir, sonra adını seçip oyuna katıl.",
        "pin_label": "Oyun PIN'i",
        "pin_placeholder": "Örnek: 3A8K2B94F1",
        "button": "Devam et",
        "hint": "PIN kodunu ekrandaki gibi gir. Sonraki adımda rumuz ve avatar seçeceksin.",
        "feature_fast": "Saniyeler içinde katıl",
        "feature_device": "Telefon, tablet ve bilgisayarda çalışır",
        "feature_live": "Canlı sonuç ve lider tablosu",
        "card_title": "Hazır mısın?",
        "card_subtitle": "Tek link, tek PIN, herkes aynı oturumda.",
        "footer_left": "Öğretmen ekranında PIN ve QR kod görünür.",
        "footer_right": "Bu adımdan sonra öğrenci ad ve avatar seçer.",
        "loading": "Kontrol ediliyor...",
        "invalid_pin": "Geçerli bir PIN gir.",
        "session_not_found": "Bu PIN bulunamadı veya oturum kapanmış.",
    },
}

JOIN_RESUME_COPY = {
    "az": {
        "notice_title": "Əvvəlki qoşulma tapıldı",
        "notice_body": "{nickname} adı ilə bu oyuna artıq daxil olmusan.",
        "notice_hint": "İstəsən həmin oyunçu ilə davam et, istəsən yeni ad və avatarla yenidən qoşul.",
        "continue_button": "{nickname} kimi davam et",
        "modal_title": "Əvvəlki adla davam etmək istəyirsən?",
        "modal_body": "Bu PIN üçün aktiv oyunçu profilin var. Həmin profil ilə gözləmə otağına qayıda və ya yeni ad/avatar seçib yenidən daxil ola bilərsən.",
        "restart_button": "Yenidən daxil ol",
        "close_button": "Bağla",
    },
    "en": {
        "notice_title": "Previous join found",
        "notice_body": "You already joined this game as {nickname}.",
        "notice_hint": "Continue with that player or join again with a new nickname and avatar.",
        "continue_button": "Continue as {nickname}",
        "modal_title": "Continue with your previous name?",
        "modal_body": "You already have an active player profile for this PIN. You can jump back into the waiting room or join again with a new nickname and avatar.",
        "restart_button": "Join again",
        "close_button": "Close",
    },
    "ru": {
        "notice_title": "Найдено предыдущее подключение",
        "notice_body": "Вы уже вошли в эту игру как {nickname}.",
        "notice_hint": "Можно продолжить с этим игроком или войти заново с новым именем и аватаром.",
        "continue_button": "Продолжить как {nickname}",
        "modal_title": "Продолжить с прежним именем?",
        "modal_body": "Для этого PIN уже есть активный профиль игрока. Вы можете вернуться в комнату ожидания или войти заново с новым именем и аватаром.",
        "restart_button": "Войти заново",
        "close_button": "Закрыть",
    },
    "tr": {
        "notice_title": "Önceki katılım bulundu",
        "notice_body": "Bu oyuna zaten {nickname} adıyla katıldın.",
        "notice_hint": "İstersen aynı oyuncuyla devam et, istersen yeni rumuz ve avatarla tekrar katıl.",
        "continue_button": "{nickname} olarak devam et",
        "modal_title": "Önceki adınla devam etmek ister misin?",
        "modal_body": "Bu PIN için aktif bir oyuncu profilin var. Bekleme odasına geri dönebilir ya da yeni rumuz ve avatarla yeniden katılabilirsin.",
        "restart_button": "Yeniden katıl",
        "close_button": "Kapat",
    },
}

NICKNAME_CONFLICT_COPY = {
    "az": "Bu ad artıq istifadə olunur. Başqa ad seç.",
    "en": "This nickname is already in use. Choose another one.",
    "ru": "Этот ник уже используется. Выберите другой.",
    "tr": "Bu rumuz zaten kullanılıyor. Başka bir ad seç.",
}

LIVE_JOIN_LIMIT_SCOPE = "live_exam.join"
LIVE_PIN_LIMIT_SCOPE = "live_exam.pin"
LIVE_REACTION_LIMIT_SCOPE = "live_exam.reaction"
LIVE_RATE_LIMIT_MESSAGE = "Çox sayda cəhd edildi. Zəhmət olmasa bir az sonra yenidən cəhd edin."
REACTION_EMOJI = dict(REACTIONS)
_AMBIGUOUS_PIN_GLYPHS = {
    "0": ("0", "O"),
    "O": ("0", "O"),
    "1": ("1", "I", "L"),
    "I": ("1", "I", "L"),
    "L": ("1", "I", "L"),
}
_MAX_AMBIGUOUS_PIN_CANDIDATES = 64
_JOINABLE_SESSION_STATES = (
    LiveSession.STATE_LOBBY,
    LiveSession.STATE_QUESTION,
    LiveSession.STATE_REVEAL,
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


# ════════════════════════════════════════════════════════════════════════════
# Player Join / Wait / Screen
# ════════════════════════════════════════════════════════════════════════════


@never_cache
def live_pin_entry(request):
    from apps.live_exam.models import MIN_PIN_LENGTH, PIN_LENGTH

    copy = _pin_entry_copy()
    pin_value, matched_session = _resolve_live_session(
        request.POST.get("pin") if request.method == "POST" else request.GET.get("pin")
    )
    raw_theme = request.POST.get("theme") if request.method == "POST" else request.GET.get("theme")
    theme_key = _pin_entry_theme_key(pin_value, raw_theme)
    error_message = ""
    status_code = 200
    session_exists = matched_session is not None

    if request.method != "POST" and session_exists:
        return _ensure_live_client_cookie(request, redirect("liveExam:join_page", pin=matched_session.pin))

    if request.method == "POST":
        is_limited, retry_after = is_rate_limited(
            LIVE_PIN_LIMIT_SCOPE,
            settings.LIVE_EXAM_JOIN_RATE_LIMIT,
            _live_client_id_key(request),
        )
        if is_limited:
            response = render(
                request,
                "liveExam/pin_entry.html",
                {
                    "copy": copy,
                    "pin_value": pin_value,
                    "pin_length": PIN_LENGTH,
                    "pin_slots": range(1, PIN_LENGTH + 1),
                    "min_pin_length": MIN_PIN_LENGTH,
                    "error_message": LIVE_RATE_LIMIT_MESSAGE,
                    "theme_key": theme_key,
                },
                status=429,
            )
            if retry_after:
                response.headers["Retry-After"] = str(retry_after)
            return _ensure_live_client_cookie(request, response)

        if len(pin_value) < MIN_PIN_LENGTH:
            record_rate_limit_hit(
                LIVE_PIN_LIMIT_SCOPE,
                settings.LIVE_EXAM_JOIN_RATE_LIMIT,
                _live_client_id_key(request),
            )
            error_message = copy["invalid_pin"]
            status_code = 400
        elif not session_exists:
            record_rate_limit_hit(
                LIVE_PIN_LIMIT_SCOPE,
                settings.LIVE_EXAM_JOIN_RATE_LIMIT,
                _live_client_id_key(request),
            )
            error_message = copy["session_not_found"]
            status_code = 404
        else:
            return _ensure_live_client_cookie(request, redirect("liveExam:join_page", pin=matched_session.pin))

    response = render(
        request,
        "liveExam/pin_entry.html",
        {
            "copy": copy,
            "pin_value": pin_value,
            "pin_length": PIN_LENGTH,
            "pin_slots": range(1, PIN_LENGTH + 1),
            "min_pin_length": MIN_PIN_LENGTH,
            "error_message": error_message,
            "theme_key": theme_key,
        },
        status=status_code,
    )
    return _ensure_live_client_cookie(request, response)


@never_cache
def live_join_page(request, pin):
    resolved_pin, session = _resolve_live_session(pin)
    if session is None:
        raise Http404()
    if resolved_pin != pin:
        return _ensure_live_client_cookie(request, redirect("liveExam:join_page", pin=resolved_pin))
    remembered_player = get_request_player(request, pin=pin)
    session_settings = get_session_settings(session)
    context = {
        "session": session,
        "avatars": AVATAR_KEYS,
        "live_catalog": build_wait_room_catalog(),
        "remembered_player": serialize_player_identity(remembered_player) if remembered_player else None,
        "remembered_join_copy": _join_resume_copy(remembered_player.nickname) if remembered_player else None,
        "resume_url": reverse("liveExam:wait_room", kwargs={"pin": session.pin}),
        "session_settings": session_settings,
        "generated_nickname": generate_guest_nickname() if session_settings.get("nickname_generator") else "",
    }
    response = render(request, "liveExam/join.html", context)
    return _ensure_live_client_cookie(request, response)


@require_POST
def live_join_enter(request, pin):
    is_limited, retry_after = record_rate_limit_hit(
        LIVE_JOIN_LIMIT_SCOPE,
        settings.LIVE_EXAM_JOIN_RATE_LIMIT,
        pin,
        _live_client_id_key(request),
    )
    if is_limited:
        response = JsonResponse(
            {"ok": False, "message": LIVE_RATE_LIMIT_MESSAGE},
            status=429,
        )
        if retry_after:
            response.headers["Retry-After"] = str(retry_after)
        return response

    resolved_pin, session = _resolve_live_session(pin)
    if session is None:
        raise Http404()
    session_settings = get_session_settings(session)

    if session.is_locked:
        return JsonResponse(
            {"ok": False, "message": pgettext("live_exam.view.message", "lobby_locked")},
            status=403,
        )

    nickname = clean_nickname(request.POST.get("nickname"))
    if not nickname and session_settings.get("nickname_generator"):
        nickname = generate_guest_nickname()

    characters_enabled = bool(session_settings.get("characters_enabled", True))
    avatar_key = request.POST.get("avatar_key") or ""
    accessory_key = request.POST.get("accessory_key") or ""
    if not characters_enabled:
        avatar_key = DEFAULT_AVATAR_KEY
        accessory_key = DEFAULT_ACCESSORY_KEY
    else:
        if avatar_key not in AVATAR_KEYS:
            avatar_key = _random_join_avatar_key()
        if accessory_key not in ACCESSORY_KEYS:
            accessory_key = _random_join_accessory_key()

    if not nickname:
        return JsonResponse(
            {"ok": False, "message": pgettext("live_exam.view.message", "nickname_required")},
            status=400,
        )

    client_id = get_client_id(request)
    now = timezone.now()
    max_participants = max(1, int(session_settings.get("max_participants", DEFAULT_MAX_PARTICIPANTS) or 0))

    with bypass_rls():
        with transaction.atomic():
            locked_session = LiveSession.objects.select_for_update().get(pk=session.pk)
            player = LivePlayer.objects.select_for_update().filter(session=locked_session, client_id=client_id).first()

            if player is None and LivePlayer.objects.filter(session=locked_session).count() >= max_participants:
                return JsonResponse(
                    {
                        "ok": False,
                        "message": pgettext("live_exam.view.message", "participant_limit_reached").format(
                            limit=max_participants
                        ),
                    },
                    status=403,
                )

            nickname_conflict = (
                LivePlayer.objects.filter(session=locked_session, nickname__iexact=nickname)
                .exclude(client_id=client_id)
                .exists()
            )
            if nickname_conflict:
                return JsonResponse(
                    {"ok": False, "message": _nickname_conflict_message()},
                    status=409,
                )

            if player:
                player.nickname = nickname
                player.avatar_key = avatar_key
                player.accessory_key = accessory_key
                player.is_connected = True
                player.last_seen = now
                player.save(update_fields=["nickname", "avatar_key", "accessory_key", "is_connected", "last_seen"])
            else:
                try:
                    player = LivePlayer.objects.create(
                        session=locked_session,
                        client_id=client_id,
                        nickname=nickname,
                        avatar_key=avatar_key,
                        accessory_key=accessory_key,
                        is_connected=True,
                        last_seen=now,
                    )
                except IntegrityError:
                    player = (
                        LivePlayer.objects.select_for_update()
                        .filter(
                            session=locked_session,
                            client_id=client_id,
                        )
                        .first()
                    )
                    if player is None:
                        raise

                    player.nickname = nickname
                    player.avatar_key = avatar_key
                    player.accessory_key = accessory_key
                    player.is_connected = True
                    player.last_seen = now
                    player.save(update_fields=["nickname", "avatar_key", "accessory_key", "is_connected", "last_seen"])

    token = build_player_token(pin=session.pin, player_id=player.id, client_id=client_id)

    _broadcast_lobby_state(session)

    wait_url = reverse("liveExam:wait_room", kwargs={"pin": session.pin})
    resp = JsonResponse({"ok": True, "redirect": wait_url})

    # Set cookies with appropriate security flags
    resp.set_cookie(
        LIVE_CLIENT_ID_COOKIE_NAME,
        client_id,
        max_age=LIVE_CLIENT_ID_COOKIE_MAX_AGE,
        samesite="Lax",
        secure=request.is_secure(),
    )
    resp.set_cookie(
        PLAYER_COOKIE_NAME,
        token,
        max_age=PLAYER_TOKEN_MAX_AGE,
        samesite="Lax",
        httponly=True,
        secure=request.is_secure(),
    )

    return resp


def live_qr_png(request, pin):
    with bypass_rls():
        session = LiveSession.objects.filter(pin=pin).first()

    if (
        session is None
        or not getattr(request.user, "is_authenticated", False)
        or session.host_user_id != request.user.id
    ):
        raise Http404(pgettext("live_exam.view.permission", "not_allowed"))

    join_url = build_join_url(request, session)

    img = qrcode.make(join_url)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)

    from django.http import HttpResponse

    return HttpResponse(buf.getvalue(), content_type="image/png")


def live_wait_room(request, pin):
    with bypass_rls():
        session = get_object_or_404(LiveSession, pin=pin)
        player = get_request_player(request, pin=pin)
        if player is None:
            return redirect("liveExam:join_page", pin=pin)
        if session.state != LiveSession.STATE_LOBBY:
            return redirect("liveExam:player_screen", pin=pin)

        players = serialize_players(session)
    return render(
        request,
        "liveExam/wait_room.html",
        {
            "session": session,
            "players": players,
            "my_player": serialize_player_identity(player),
            "my_player_id": player.id,
            "player_screen_url": reverse("liveExam:player_screen", kwargs={"pin": session.pin}),
            "live_catalog": build_wait_room_catalog(),
            "session_settings": get_session_settings(session),
        },
    )


@require_POST
def live_wait_profile_update(request, pin):
    with bypass_rls():
        session = get_object_or_404(LiveSession, pin=pin)
        player = get_request_player(request, pin=pin)
        if player is None or player.session_id != session.id:
            return JsonResponse(
                {"ok": False, "message": pgettext("live_exam.view.message", "auth_required")},
                status=403,
            )

    session_settings = get_session_settings(session)
    nickname = clean_nickname(request.POST.get("nickname"))
    avatar_key = request.POST.get("avatar_key") or DEFAULT_AVATAR_KEY
    accessory_key = request.POST.get("accessory_key") or DEFAULT_ACCESSORY_KEY

    if not nickname:
        return JsonResponse(
            {"ok": False, "message": pgettext("live_exam.view.message", "nickname_required")},
            status=400,
        )
    if not session_settings.get("characters_enabled", True):
        avatar_key = DEFAULT_AVATAR_KEY
        accessory_key = DEFAULT_ACCESSORY_KEY
    elif avatar_key not in AVATAR_KEYS:
        return JsonResponse(
            {"ok": False, "message": pgettext("live_exam.view.message", "invalid_avatar")},
            status=400,
        )
    if accessory_key not in ACCESSORY_KEYS:
        return JsonResponse(
            {"ok": False, "message": pgettext("live_exam.view.message", "invalid_accessory")},
            status=400,
        )
    if _nickname_is_taken(session, nickname, exclude_player_id=player.id):
        return JsonResponse(
            {"ok": False, "message": _nickname_conflict_message()},
            status=409,
        )

    with bypass_rls():
        player.nickname = nickname
        player.avatar_key = avatar_key
        player.accessory_key = accessory_key
        player.is_connected = True
        player.last_seen = timezone.now()
        player.save(update_fields=["nickname", "avatar_key", "accessory_key", "is_connected", "last_seen"])

    _broadcast_lobby_state(session)

    return JsonResponse(
        {
            "ok": True,
            "player": serialize_player_identity(player),
        }
    )


@require_POST
def live_wait_reaction(request, pin):
    with bypass_rls():
        session = get_object_or_404(LiveSession, pin=pin)
        player = get_request_player(request, pin=pin)
        if player is None or player.session_id != session.id:
            return JsonResponse(
                {"ok": False, "message": pgettext("live_exam.view.message", "auth_required")},
                status=403,
            )

    if not get_session_settings(session).get("reactions_enabled", True):
        return JsonResponse(
            {"ok": False, "message": pgettext("live_exam.view.message", "Reactions are disabled for this live exam.")},
            status=403,
        )

    reaction_key = (request.POST.get("reaction_key") or "").strip().lower()
    if reaction_key not in REACTION_KEYS:
        return JsonResponse(
            {"ok": False, "message": pgettext("live_exam.view.message", "invalid_reaction")},
            status=400,
        )

    is_limited, retry_after = record_rate_limit_hit(
        LIVE_REACTION_LIMIT_SCOPE,
        settings.LIVE_REACTION_RATE_LIMIT,
        pin,
        player.id,
        player.client_id,
    )
    if is_limited:
        response = JsonResponse(
            {"ok": False, "message": pgettext("live_exam.view.message", "reaction_rate_limited")},
            status=429,
        )
        if retry_after:
            response.headers["Retry-After"] = str(retry_after)
        return response

    created_at = timezone.now()
    broadcast(
        session.pin,
        build_reaction_event_payload(
            player=player,
            reaction_key=reaction_key,
            emoji=REACTION_EMOJI[reaction_key],
            created_at=created_at,
        ),
        "lobby",
    )

    return JsonResponse(
        {
            "ok": True,
            "reaction_key": reaction_key,
        }
    )


def live_player_screen(request, pin):
    with bypass_rls():
        session = get_object_or_404(LiveSession, pin=pin)
        player = get_request_player(request, pin=pin)
        if player is None:
            return redirect("liveExam:join_page", pin=pin)

    return render(
        request,
        "liveExam/player_screen.html",
        {
            "session": session,
            "player": player,
            "session_settings": get_session_settings(session),
        },
    )
