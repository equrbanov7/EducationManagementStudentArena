"""
Transport helpers for live exam HTTP and websocket payloads.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlencode

from django.conf import settings
from django.utils import timezone
from django.utils.translation import pgettext

from asgiref.sync import async_to_sync
from channels.exceptions import InvalidChannelLayerError
from channels.layers import get_channel_layer

from apps.live_exam.constants import PLAYER_QUESTION_PUBLISH_GRACE_SECONDS
from apps.live_exam.domain.session import build_question_phase_times
from apps.live_exam.reveal import Bundle, build_final_bundle, build_reveal_bundle
from apps.live_exam.serializers import (
    serialize_player_identity,
    serialize_players,
    serialize_question,
    serialize_top,
    serialize_top_before_question,
)
from apps.live_exam.session_settings import get_session_settings, session_join_path
from apps.live_exam.text_safety import sanitize_player_text
from apps.live_exam.typed_answers import TEXT_MAX_LENGTH

#: Audit 2026-09-28 EX28-10: reveal-dən ƏVVƏL oyunçuya gedən cavab sahələri.
#: ``is_correct`` / ``awarded_points`` / ``score`` / ``answer_rank`` və s.
#: burada YOXDUR — əks halda atılan (throw-away) oyunçularla variantları
#: yoxlayıb əsas oyunçu ilə düz cavab vermək olurdu.
PRE_REVEAL_ANSWER_KEYS = ("player_id", "choice_ids", "message")

#: Bir cavab mesajında maksimal variant sayı (saxta yükün ölçüsünü məhdudlaşdırır).
MAX_OPTION_IDS_PER_ANSWER = 50


def public_player_answer(answer: dict | None, *, revealed: bool) -> dict | None:
    """Oyunçunun öz cavabı — reveal olunmayıbsa yalnız «saxlandı» məlumatı."""
    if not answer:
        return answer
    if revealed:
        return dict(answer)
    safe = {key: answer[key] for key in PRE_REVEAL_ANSWER_KEYS if key in answer}
    safe["saved"] = True
    return safe


def build_answer_saved_payload(result: dict[str, Any]) -> dict[str, Any]:
    """``answer_saved`` (WS unicast / HTTP cavabı) — reveal-dən əvvəl nəticəsiz.

    Cavab raundu bitirdisə (``reveal_question_id``) reveal onsuz da başlayır —
    onda tam şəxsi nəticə qaytarılır.
    """
    revealed = bool(result.get("reveal_question_id"))
    answer = public_player_answer(result.get("answer") or {}, revealed=revealed) or {}
    return {"type": "answer_saved", "saved": True, "question_id": result.get("question_id"), **answer}


def get_public_base_url(request) -> str:
    configured = (getattr(settings, "LIVE_EXAM_PUBLIC_HOST", None) or getattr(settings, "LAN_HOST", None) or "").strip()

    if configured:
        configured = configured.rstrip("/")
        if configured.startswith(("http://", "https://")):
            return configured
        scheme = "https" if request.is_secure() else "http"
        return f"{scheme}://{configured}"

    return request.build_absolute_uri("/").rstrip("/")


def build_join_url(request, session) -> str:
    base_url = f"{get_public_base_url(request)}{session_join_path(session)}"
    if get_session_settings(session).get("two_step_join", True):
        return f"{base_url}?{urlencode({'pin': session.pin})}"
    return base_url


def _group_send(group: str, event: dict[str, Any]) -> None:
    try:
        layer = get_channel_layer()
    except (InvalidChannelLayerError, ModuleNotFoundError):
        return
    if layer is None:
        return
    try:
        async_to_sync(layer.group_send)(group, event)
    except (InvalidChannelLayerError, ModuleNotFoundError):
        return


def broadcast(pin: str, payload: dict[str, Any], group_suffix: str, *, personal: dict[str, str] | None = None) -> None:
    """Broadcast a payload to a specific channel-layer group.

    group_suffix can be:
      - "lobby"           → live_<pin>_lobby  (lobby_event)
      - "play_host"       → live_<pin>_play_host  (play_event, host only)
      - "play_players"    → live_<pin>_play_players  (play_event, players only)
    """
    event_type = "lobby_event" if group_suffix == "lobby" else "play_event"
    event = {"type": event_type, "data": payload}
    if personal is not None:
        # Şəxsi əlavələr (oyunçu id → JSON) — consumer yalnız öz sətrini klientə qoşur.
        event["personal"] = personal
    _group_send(f"live_{pin}_{group_suffix}", event)


def broadcast_host(pin: str, payload: dict[str, Any]) -> None:
    """Broadcast a payload to the host-only play group."""
    broadcast(pin, payload, "play_host")


def broadcast_players(pin: str, payload: dict[str, Any], *, personal: dict[str, str] | None = None) -> None:
    """Broadcast a payload to the players-only play group."""
    broadcast(pin, payload, "play_players", personal=personal)


#: LXNET 2026-10-02: sual nəşrində yalnız host-un istifadə etdiyi sahələr — oyunçu kopyasından
#: atılır (isti yolda daha kiçik kadr; telefon ``previous_top``-u reveal paketindən götürür).
HOST_ONLY_QUESTION_KEYS = ("previous_top",)


def player_question_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("type") != "question_published":
        return payload
    return {key: value for key, value in payload.items() if key not in HOST_ONLY_QUESTION_KEYS}


def broadcast_play(pin: str, payload: dict[str, Any]) -> None:
    """Broadcast a payload to both host and player play groups (sual nəşri oyunçuya yığcam)."""
    broadcast_host(pin, payload)
    broadcast_players(pin, player_question_payload(payload))


def bundle_events(pin: str, bundle: Bundle) -> list[tuple[str, dict[str, Any]]]:
    """Reveal/final paketinin kanal-qatı hadisələri: host tam paket, oyunçular ümumi
    paket + ``personal`` (hər consumer yalnız öz sətrini klientə əlavə edir)."""
    return [
        (f"live_{pin}_play_host", {"type": "play_event", "data": bundle.host}),
        (f"live_{pin}_play_players", {"type": "play_event", "data": bundle.players, "personal": bundle.personal}),
    ]


def broadcast_bundle(pin: str, bundle: Bundle) -> None:
    for group, event in bundle_events(pin, bundle):
        _group_send(group, event)


def kick_events(pin: str, player_id: int) -> list[tuple[str, dict[str, Any]]]:
    """Audit 2026-09-28 LXBE-07: silinmiş oyunçunun açıq socket-ləri bağlanır."""
    event = {"type": "player_kicked", "player_id": int(player_id)}
    return [(f"live_{pin}_lobby", dict(event)), (f"live_{pin}_play_players", dict(event))]


def broadcast_player_kicked(pin: str, player_id: int) -> None:
    for group, event in kick_events(pin, player_id):
        _group_send(group, event)


def parse_answer_submission(data: dict[str, Any]) -> tuple[bool, Any]:
    """``(True, (question_id, option_ids, answer_ms, text))`` və ya ``(False, mesaj)``.

    Yazılı cavab: ``text`` (sətir, ≤ 60 simvol) — ``option_id(s)`` ilə birgə gəlməz.
    """
    bad_payload = pgettext("live_exam.consumer.error", "bad_payload")
    try:
        question_id = int(data.get("question_id"))
        answer_ms = int(data.get("answer_ms") or 0)
        # DB «integer out of range» (500) olmasın — id-lər int4 aralığındadır.
        if not 0 < question_id < 2**31:
            return False, bad_payload

        if "text" in data and data.get("text") is not None:
            raw_text = data.get("text")
            has_options = bool(data.get("option_ids")) or data.get("option_id") is not None
            if not isinstance(raw_text, str) or has_options or len(raw_text) > TEXT_MAX_LENGTH * 8:
                return False, bad_payload
            # LX-SEC gigiyenası: nəzarət/görünməz/bidi simvollar atılır (NUL → 500 olmasın).
            text = sanitize_player_text(raw_text, max_length=TEXT_MAX_LENGTH * 4)
            if len(text) > TEXT_MAX_LENGTH:
                return False, bad_payload
            return True, (question_id, [], answer_ms, text)

        if isinstance(data.get("option_ids"), list):
            raw_option_ids = data.get("option_ids")
            # Bound attacker-controlled list size before any processing; no real
            # question has anywhere near this many options.
            if len(raw_option_ids) > MAX_OPTION_IDS_PER_ANSWER:
                return False, bad_payload
            option_ids = [int(value) for value in raw_option_ids if str(value).isdigit()]
        else:
            option_ids = [int(data.get("option_id"))]

        option_ids = list(dict.fromkeys(option_ids))
        if not option_ids:
            return False, pgettext("live_exam.consumer.error", "no_options_selected")

        return True, (question_id, option_ids, answer_ms, None)
    except Exception:
        return False, bad_payload


def build_lobby_state_payload(session, *, limit: int = 200) -> dict[str, Any]:
    players = serialize_players(session, limit=limit)
    return {
        "type": "lobby_state",
        "server_time": timezone.now().isoformat(),
        # Siyahı ``limit``-lə kəsilir; say isə həmişə həqiqi say olmalıdır (host sayğacı).
        "count": len(players) if len(players) < limit else session.players.count(),
        "players": players,
        "is_locked": bool(session.is_locked),
        # İctimai görünüş — yazılı cavabların qəbul siyahısı lobby-yə getmir.
        "settings": get_session_settings(session),
    }


def build_reaction_event_payload(*, player, reaction_key: str, emoji: str, created_at=None) -> dict[str, Any]:
    payload = {
        "type": "reaction_event",
        "reaction_key": reaction_key,
        "emoji": emoji,
        "player": serialize_player_identity(player),
    }
    if created_at is not None:
        payload["created_at"] = created_at.isoformat()
    return payload


def build_answer_progress_payload(*, question_id: int, answered_count: int, total_players: int) -> dict[str, Any]:
    return {
        "type": "answer_progress",
        "server_time": timezone.now().isoformat(),
        "question_id": question_id,
        "answered_count": answered_count,
        "total_players": total_players,
    }


def build_question_payload(session, exam_question, *, idx: int, total: int):
    started_at = timezone.now() + timezone.timedelta(seconds=PLAYER_QUESTION_PUBLISH_GRACE_SECONDS)
    ready_ends_at, answer_starts_at, ends_at = build_question_phase_times(
        session,
        exam_question,
        started_at=started_at,
        idx=idx,
    )
    payload = {
        "type": "question_published",
        "server_time": timezone.now().isoformat(),
        "question": serialize_question(
            session,
            exam_question,
            idx=idx,
            total=total,
            started_at=started_at,
            ready_ends_at=ready_ends_at,
            answer_starts_at=answer_starts_at,
            ends_at=ends_at,
        ),
        "previous_top": serialize_top(session, limit=10),
    }
    return payload, started_at, ends_at


def build_question_phase_payload(
    session,
    exam_question,
    *,
    idx: int,
    total: int,
    started_at,
    ready_ends_at,
    answer_starts_at,
    ends_at,
):
    return {
        "type": "question_published",
        "server_time": timezone.now().isoformat(),
        "question": serialize_question(
            session,
            exam_question,
            idx=idx,
            total=total,
            started_at=started_at,
            ready_ends_at=ready_ends_at,
            answer_starts_at=answer_starts_at,
            ends_at=ends_at,
        ),
        "previous_top": serialize_top_before_question(session, exam_question.id, limit=10),
    }


def build_reveal_payload(
    session,
    question_id: int,
    *,
    revealed_at=None,
    exam_question=None,
) -> dict[str, Any]:
    """Host reveal paketi (``results`` daxil). Hər ikisi lazımdırsa ``build_reveal_bundle``."""
    return build_reveal_bundle(session, question_id, revealed_at=revealed_at, exam_question=exam_question).host


def build_player_reveal_payload(
    session,
    question_id: int,
    *,
    revealed_at=None,
    exam_question=None,
) -> dict[str, Any]:
    """Reveal payload for players.

    Includes correct_option_ids (appropriate at reveal stage), distribution, and leaderboard
    data, but omits per-player answer details (``results``) which are host-only analytics.
    On the FINAL question the leaderboard (``top``/``previous_top``) is withheld as well —
    places are revealed only by the ``finished`` event / final stage (owner 2026-09-30).
    """
    return build_reveal_bundle(session, question_id, revealed_at=revealed_at, exam_question=exam_question).players


def build_finished_payload(session, *, finished_at=None, limit: int = 50) -> dict[str, Any]:
    return build_final_bundle(session, finished_at=finished_at, limit=limit).host
