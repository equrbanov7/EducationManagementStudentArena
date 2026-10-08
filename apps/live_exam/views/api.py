"""
live_exam/views/api.py
───────────────────────
API endpoints for live exam sessions.
"""

from __future__ import annotations

import json

from django.conf import settings
from django.db import transaction
from django.http import JsonResponse
from django.utils import timezone
from django.utils.translation import pgettext
from django.views.decorators.http import require_POST

from apps.live_exam.auth import PLAYER_COOKIE_NAME, get_request_player, is_client_kicked, load_player_token_payload
from apps.live_exam.delivery import build_delivery_progress_payload, received_count, record_question_seen
from apps.live_exam.domain.question_config import resolve_question_config
from apps.live_exam.domain.session import build_question_phase_times, get_question_by_index, get_total_questions
from apps.live_exam.i18n import player_language
from apps.live_exam.models import LiveAnswer, LiveSession
from apps.live_exam.reveal import build_final_bundle, build_reveal_bundle, pre_question_rank
from apps.live_exam.roster import eligible_players, is_pending
from apps.live_exam.scoring import save_answer_and_score
from apps.live_exam.serializers import (
    serialize_player_question_result,
    serialize_players,
    serialize_question,
    serialize_top_before_question,
)
from apps.live_exam.services import auto_reveal_if_due
from apps.live_exam.session_settings import get_host_session_settings, public_session_settings
from apps.live_exam.transport import (
    broadcast_bundle,
    broadcast_host,
    broadcast_players,
    build_answer_progress_payload,
    build_answer_saved_payload,
    parse_answer_submission,
    public_player_answer,
)
from apps.live_exam.views.host._shared import _ensure_host_org_permission
from apps.live_exam.views.player.texts import state_rate_limit_message
from core.rate_limit import record_rate_limit_hit
from core.rls import bypass_rls
from core.utils import get_client_ip

LIVE_STATE_LIMIT_SCOPE = "live_exam.state"
LIVE_ANSWER_HTTP_LIMIT_SCOPE = "live_exam.answer.http"

_REVEAL_TIMING_KEYS = (
    "top",
    "previous_top",
    "distribution",
    "revealed_at",
    "result_duration_ms",
    "leaderboard_duration_ms",
    "transition_duration_ms",
    "leaderboard_starts_at",
    "next_question_at",
)
_REVEAL_OPTIONAL_KEYS = (
    "answer_input",
    "accepted_answers",
    "multi_scoring",
    "total_correct",
    "results",
    "fastest_correct",
    "typed_summary",
    "typed_total",
    "typed_correct",
    "total_players",
    # Sahib 2026-09-30: son sual — liderlik/sıra yoxdur, gərginlik fazası (reveal.py).
    "final_question",
    "final_suspense_ms",
)


def _auth_error():
    return JsonResponse({"ok": False, "message": pgettext("live_exam.view.message", "auth_required")}, status=403)


def _player_auth_error(request, session):
    """403; aparıcının çıxardığı klientə ``kicked: true`` (telefon «müəllim səni çıxardı» göstərir)."""
    response = _auth_error()
    payload = load_player_token_payload(request.COOKIES.get(PLAYER_COOKIE_NAME), pin=session.pin)
    if payload is not None and is_client_kicked(session, payload.get("client_id")):
        response = JsonResponse(
            {"ok": False, "kicked": True, "message": pgettext("live_exam.view.message", "removed_by_host")}, status=403
        )
    return response


def _rate_limited(request, pin):
    if getattr(request.user, "is_authenticated", False):
        rate_key = ("host", request.user.id, pin)
    else:
        rate_key = ("player", request.COOKIES.get("live_client_id") or get_client_ip(request) or "unknown", pin)
    is_limited, retry_after = record_rate_limit_hit(LIVE_STATE_LIMIT_SCOPE, settings.LIVE_STATE_RATE_LIMIT, *rate_key)
    if not is_limited:
        return None
    response = JsonResponse({"ok": False, "message": state_rate_limit_message()}, status=429)
    if retry_after:
        response.headers["Retry-After"] = str(retry_after)
    return response


def _maybe_auto_reveal(session: LiveSession, now) -> LiveSession:
    """LXBE-08: vaxt + güzəşt bitib, autoplay açıq, host reveal etməyib → server reveal edir."""
    if session.state != LiveSession.STATE_QUESTION or session.question_ends_at is None:
        return session
    if now <= session.question_ends_at:
        return session
    bundle = auto_reveal_if_due(session.pin, session.current_question_id or None, now=now)
    if bundle is None:
        return session
    transaction.on_commit(lambda: broadcast_bundle(session.pin, bundle))
    return LiveSession.objects.select_related("exam").get(pk=session.pk)


def _finished_fields(session, *, player, data: dict) -> None:
    bundle = build_final_bundle(session, limit=50)
    data["top"] = bundle.host["top"]
    data["stats"] = bundle.host["stats"]
    if player is not None:
        data.update(bundle.personal_for(player.id))


def _reveal_fields(session, eq, *, ends, is_host: bool, player, data: dict) -> None:
    bundle = build_reveal_bundle(session, eq.id, revealed_at=ends, exam_question=eq)
    source = bundle.host if is_host else bundle.players
    for key in _REVEAL_TIMING_KEYS + _REVEAL_OPTIONAL_KEYS:
        if key in source:
            data[key] = source[key]
    data["correct_option_ids"] = source.get("correct_option_ids", [])
    if player is not None:
        personal = bundle.personal_for(player.id)
        data.update({key: value for key, value in personal.items() if key != "player_answer"})
        data["player_answer"] = personal.get("player_answer")


def _record_delivery(pin: str, question_id: int, player_id: int, *, at) -> None:
    received = record_question_seen(pin, question_id, player_id, at=at)
    if received is not None:
        payload = build_delivery_progress_payload(question_id=question_id, received=received)
        transaction.on_commit(lambda: broadcast_host(pin, payload))


def live_state_json(request, pin):
    """
    ✅ NEW: cari state-i HTTP ilə almaq (late join / miss olunan WS üçün)
    """
    limited = _rate_limited(request, pin)
    if limited is not None:
        return limited

    with bypass_rls():
        session = LiveSession.objects.select_related("exam__organization").filter(pin=pin).first()
        if session is None:
            return _auth_error()
        is_host = bool(getattr(request.user, "is_authenticated", False) and session.host_user_id == request.user.id)
        if is_host:
            # LX-SEC: host görünüşü (nəticələr + qəbul cavabları) digər host endpoint-ləri
            # ilə EYNİ RBAC-dan keçir (təşkilat konteksti + exam.host/exam.manage).
            _ensure_host_org_permission(request, session.exam.organization)
        player = None if is_host else get_request_player(request, pin=pin)
        if not is_host and player is None:
            return _player_auth_error(request, session)

        server_time = timezone.now()
        session = _maybe_auto_reveal(session, server_time)
        host_settings = get_host_session_settings(session)
        total = get_total_questions(session)

        data: dict = {
            "ok": True,
            "server_time": server_time.isoformat(),
            "pin": session.pin,
            "state": session.state,
            "is_locked": bool(session.is_locked),
            # Oyunçuya yazılı cavabların qəbul siyahısı GETMİR (yalnız host-a).
            "settings": host_settings if is_host else public_session_settings(host_settings),
            "current_index": int(session.current_index or 0),
            "total_questions": total,
            "created_at": session.created_at.isoformat() if session.created_at else None,
            "question_started_at": (session.question_started_at.isoformat() if session.question_started_at else None),
            "question_ends_at": (session.question_ends_at.isoformat() if session.question_ends_at else None),
            "finished_at": (
                (session.question_ends_at or server_time).isoformat()
                if session.state == LiveSession.STATE_FINISHED
                else None
            ),
        }
        if session.state == LiveSession.STATE_LOBBY and not (player is not None and request.GET.get("light") == "1"):
            players = serialize_players(session)
            data["players"] = players
            # Host-un «Yenilə» düyməsi / avtomatik sinxronu bu sayı HƏQİQƏT kimi götürür (sahib 2026-09-30).
            data["total_players"] = len(players) if len(players) < 200 else session.players.count()
            data["roster_count"] = data["total_players"]
        elif session.state in (LiveSession.STATE_QUESTION, LiveSession.STATE_REVEAL):
            # 2026-10-08 (L3): cari suala cavab verməli olanlar (gec qoşulan növbəti sualdan sayılır).
            data["total_players"] = eligible_players(session.id, int(session.current_index or 0)).count()
        else:
            # ``?light=1`` (oyunçu, lobby): 200 nəfərlik siyahı əvəzinə yalnız say — gözləmə
            # otağının ehtiyat sorğusu üçün (LX-FE-PLAYER). Host cavabı dəyişmir.
            data["total_players"] = session.players.count()
        if is_host and session.state != LiveSession.STATE_LOBBY:
            # 2026-10-08 (L6): oyun gedərkən aparıcının «İştirakçılar» çekməcəsi (çıxarılanlar yoxdur).
            roster = serialize_players(session)
            data["players"] = roster
            data["roster_count"] = len(roster) if len(roster) < 200 else session.players.count()
        if player is not None and is_pending(player, session):
            # Gec qoşulan: növbəti sual gözlənilir — cari/keçən sualın məzmunu və cavabı GÖNDƏRİLMİR.
            data["late_join_pending"] = True
            data["active_from_index"] = int(player.active_from_index or 0)
            return JsonResponse(data)
        if session.state == LiveSession.STATE_FINISHED:
            _finished_fields(session, player=player, data=data)
            return JsonResponse(data)

        idx = int(session.current_index or 0)
        eq = get_question_by_index(session, idx)
        if (
            not eq
            or session.state not in {LiveSession.STATE_QUESTION, LiveSession.STATE_REVEAL}
            or not session.question_started_at
        ):
            return JsonResponse(data)

        started = session.question_started_at
        ready_ends_at, answer_starts_at, computed_ends_at = build_question_phase_times(
            session,
            eq,
            started_at=started,
            idx=idx,
        )
        ends = session.question_ends_at or computed_ends_at
        data["question"] = serialize_question(
            session,
            eq,
            idx=idx,
            total=total,
            started_at=started,
            ready_ends_at=ready_ends_at,
            answer_starts_at=answer_starts_at,
            ends_at=ends,
        )
        data["answered_count"] = LiveAnswer.objects.filter(session_id=session.id, question_id=eq.id).in_game().count()

        if session.state == LiveSession.STATE_REVEAL:
            _reveal_fields(session, eq, ends=ends, is_host=is_host, player=player, data=data)
            return JsonResponse(data)

        data["correct_option_ids"] = []
        if is_host:
            data["previous_top"] = serialize_top_before_question(session, eq.id, limit=10)
            # LXNET: sualı neçə telefon aldı (host-un «N/M aldı» sayğacı, refresh-dən sonra).
            data["received_count"] = received_count(session.pin, eq.id)
        if player is not None:
            # LXNET: HTTP snapshot sualı bu oyunçuya verdi — çatmanın server-vaxtlı sübutu
            # (WS qopuq olanda yeganə yol). ``previous_top`` oyunçuya lazım deyil (ağır sorğu).
            _record_delivery(session.pin, eq.id, player.id, at=server_time)
            # Refresh-dən sonra telefonun sıra göstəricisi — sualdan ƏVVƏLKİ sıra (sızma yoxdur).
            data.update(pre_question_rank(session, player.id, eq.id))
            # EX28-10: açıq sual ərzində yalnız «cavab saxlanıb» (düzlük reveal-də).
            data["player_answer"] = public_player_answer(
                serialize_player_question_result(
                    session, eq.id, player.id, config=resolve_question_config(session, eq)
                ),
                revealed=False,
            )
        return JsonResponse(data)


@require_POST
def live_answer_submit(request, pin):
    # LXBE-01: vaxt serverə ÇATMA anından ölçülür (bal üçün müştəri vaxtı yalnız azalda bilər).
    received_at = timezone.now()
    player = get_request_player(request, pin=pin)
    if player is None:
        return _auth_error()

    is_limited, retry_after = record_rate_limit_hit(
        LIVE_ANSWER_HTTP_LIMIT_SCOPE,
        settings.LIVE_ANSWER_RATE_LIMIT,
        pin,
        player.id,
    )
    if is_limited:
        response = JsonResponse(
            {"ok": False, "message": pgettext("live_exam.consumer.error", "rate_limited")},
            status=429,
        )
        if retry_after:
            response.headers["Retry-After"] = str(retry_after)
        return response

    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except (TypeError, ValueError, json.JSONDecodeError):
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    if not payload and request.POST:
        payload = request.POST.dict()
        if "option_ids" in request.POST:
            payload["option_ids"] = request.POST.getlist("option_ids")

    ok, parsed = parse_answer_submission(payload)
    if not ok:
        return JsonResponse({"ok": False, "message": parsed}, status=400)

    question_id, option_ids, answer_ms, text = parsed
    with player_language(player.session):  # xəta mətnləri aparıcının seçdiyi dildə (2026-10-08)
        ok, result = save_answer_and_score(
            pin=pin,
            player_id=player.id,
            client_id=str(player.client_id or ""),
            question_id=question_id,
            option_ids=option_ids,
            answer_ms=answer_ms,
            received_at=received_at,
            text=text,
        )
    if not ok:
        return JsonResponse({"ok": False, "message": result}, status=400)

    # EX28-10: düzlük/bal reveal-ə qədər oyunçuya qaytarılmır.
    response_payload = {"ok": True, "answer": build_answer_saved_payload(result)}
    progress = result.get("progress")
    progress_payload = None
    if progress:
        progress_payload = build_answer_progress_payload(
            question_id=question_id,
            answered_count=progress["answered_count"],
            total_players=progress["total_players"],
        )
        response_payload["progress"] = progress_payload

    bundle = None
    reveal_question_id = result.get("reveal_question_id")
    if reveal_question_id:
        with bypass_rls():
            session = LiveSession.objects.select_related("exam").get(pin=pin)
            bundle = build_reveal_bundle(session, reveal_question_id)
        response_payload["reveal"] = {**bundle.players, **bundle.personal_for(player.id)}

    # `answer_saved` is a per-player UI state; broadcasting it to all players
    # makes other devices look like they already answered.
    if progress_payload is not None:
        broadcast_host(pin, progress_payload)
    if bundle is not None:
        broadcast_host(pin, bundle.host)
        broadcast_players(pin, bundle.players, personal=bundle.personal)

    return JsonResponse(response_payload)
