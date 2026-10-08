"""
Business logic layer for live_exam app — vəziyyət maşını (state machine) keçidləri.

Vəziyyətlər: ``lobby → question ⇄ reveal → … → finished`` (tam diaqram:
docs/live_exam/ENGINE.md).

Audit 2026-09-28 LXBE-04/05: HƏR keçid sessiya sətrini ``SELECT … FOR UPDATE OF
livesession`` ilə kilidləyir və vəziyyəti KİLİD ALTINDA yenidən yoxlayır. Cavablar
həmin sətri ``FOR SHARE`` tutduğu üçün (``scoring``) keçid yolda olan cavabları
gözləyir, keçiddən sonrakı cavab isə yeni vəziyyəti görür. Nəticədə ikiqat klik,
iki host tabı, auto-next taymeri + əl ilə klik, host reveal + «hamı cavab verdi»
yarışları eyni keçidi iki dəfə etmir və ``host_settings`` JSON-u itmir.
Yayımlar commit-dən SONRA göndərilir.

Public API
----------
lock_session              – sessiya sətrini FOR UPDATE ilə yenidən oxuyur
create_live_session       – create a new lobby-state session for an exam
start_game                – initialise question order and publish the first question
publish_question          – (kilid altında) sualı nəşr edir, qaydasını dondurur
advance_to_next           – reveal → növbəti sual (və ya finiş)
reveal_current            – aktiv sualı reveal edir (host)
reveal_if_all_answered    – hamı cavab verəndə (commit-dən sonra) reveal
auto_reveal_if_due        – autoplay + vaxt bitib + host reveal etməyib → server reveal edir
finish_session            – mark a session as finished
skip_question_intro       – intro-nu keçib cavab pəncərəsini dərhal açır
toggle_session_lock       – toggle (or explicitly set) the session lock flag
remove_player             – oyunçunu çıxarır: lobbidə silir, oyun gedərkən «çıxarıldı» (L6, 2026-10-08)
update_host_settings      – ayarları yazır (typed/multi yoxlaması ilə) və yayımlayır
"""

from __future__ import annotations

import random
from datetime import timedelta
from typing import Any

from django.db import transaction
from django.utils import timezone

from apps.live_exam.auth import remember_kicked_client
from apps.live_exam.constants import SERVER_AUTO_REVEAL_GRACE_SECONDS
from apps.live_exam.domain.question_config import freeze_question_config, resolve_question_config
from apps.live_exam.domain.session import (
    build_question_phase_times,
    clear_question_phase_override,
    get_active_question,
    get_exam_question_ids,
    get_question_by_index,
    get_total_questions,
    question_time_limit,
    set_question_phase_override,
)
from apps.live_exam.models import LiveAnswer, LivePlayer, LiveSession
from apps.live_exam.reveal import build_final_bundle, build_reveal_bundle
from apps.live_exam.roster import eligible_players
from apps.live_exam.session_settings import (
    get_host_session_settings,
    public_session_settings,
    update_session_settings,
)
from apps.live_exam.transport import (
    broadcast,
    broadcast_bundle,
    broadcast_host,
    broadcast_play,
    broadcast_player_kicked,
    broadcast_players,
    build_answer_progress_payload,
    build_lobby_state_payload,
    build_question_payload,
    build_question_phase_payload,
)

#: Oyun başlayanda wait room → player screen yönləndirməsinin səpələnmə aralığı (ms).
#: 1-ci sualın cavab pəncərəsi nəşrdən ~10 s sonra açılır — 1.5 s təhlükəsizdir.
GAME_START_REDIRECT_JITTER_MS = 1500

# ──────────────────────────────────────────────────────────────────────────────
# Kilid və köməkçilər
# ──────────────────────────────────────────────────────────────────────────────


def lock_session(session_or_pk) -> LiveSession:
    """Sessiya sətrini ``FOR UPDATE OF self`` ilə oxuyur (imtahan sətri kilidlənmir)."""
    pk = getattr(session_or_pk, "pk", session_or_pk)
    return LiveSession.objects.select_for_update(of=("self",)).select_related("exam").get(pk=pk)


def _lock_session_by_pin(pin: str) -> LiveSession | None:
    return LiveSession.objects.select_for_update(of=("self",)).select_related("exam").filter(pin=pin).first()


def _sync_instance(target: LiveSession, source: LiveSession, fields: tuple[str, ...]) -> None:
    """Çağıranın əlindəki köhnə instansı kilid altında yazılan dəyərlərlə yeniləyir."""
    if target is source:
        return
    for name in fields:
        setattr(target, name, getattr(source, name))


_GAME_FIELDS = (
    "state",
    "current_index",
    "current_question_id",
    "question_started_at",
    "question_ends_at",
    "selected_question_ids",
    "question_limit",
    "host_settings",
    "is_locked",
)


def select_question_ids(session: LiveSession, question_count: int | None) -> list[int]:
    """Oyun sualları (ayar: ``randomize_questions``) — ``ValueError`` kodları ilə."""
    all_ids = get_exam_question_ids(session)
    if not all_ids:
        raise ValueError("no_questions_in_exam")
    if question_count is not None:
        if question_count <= 0:
            raise ValueError("question_count_minimum")
        if question_count > len(all_ids):
            raise ValueError("question_count_exceeds_total")
    selected_ids = list(all_ids)
    if get_host_session_settings(session).get("randomize_questions", True):
        random.shuffle(selected_ids)
    return selected_ids[:question_count] if question_count is not None else selected_ids


def publish_question(locked: LiveSession, exam_question, *, idx: int, total: int) -> dict[str, Any]:
    """(Kilid altında) sualı nəşr edir: qaydanı dondurur, vaxtları yazır, paketi qaytarır."""
    clear_question_phase_override(locked)
    freeze_question_config(locked, exam_question)
    locked.state = LiveSession.STATE_QUESTION
    locked.current_index = idx
    locked.current_question_id = exam_question.id
    payload, started_at, ends_at = build_question_payload(locked, exam_question, idx=idx, total=total)
    locked.question_started_at = started_at
    locked.question_ends_at = ends_at
    locked.save(
        update_fields=[
            "state",
            "current_index",
            "current_question_id",
            "question_started_at",
            "question_ends_at",
            "host_settings",
        ]
    )
    return payload


def _apply_reveal(locked: LiveSession, exam_question, *, revealed_at) -> None:
    """(Kilid altında) QUESTION → REVEAL; cavabsız qalanların seriyası sıfırlanır."""
    config = resolve_question_config(locked, exam_question)
    locked.state = LiveSession.STATE_REVEAL
    locked.question_ends_at = revealed_at
    clear_question_phase_override(locked)
    locked.save(update_fields=["state", "question_ends_at", "host_settings"])
    if not config.is_neutral:
        answered = LiveAnswer.objects.filter(session_id=locked.id, question_id=exam_question.id).values("player_id")
        LivePlayer.objects.filter(session_id=locked.id, streak__gt=0).exclude(id__in=answered).update(streak=0)


def _after_commit(callback) -> None:
    """Yayım commit-dən SONRA (autocommit-də dərhal; ATOMIC_REQUESTS altında sorğu sonunda)."""
    transaction.on_commit(callback)


def game_started_payload(redirect: str) -> dict[str, Any]:
    """``game_started`` — ``redirect_jitter_ms``: FE yönləndirməni bu aralıqda səpələyə bilər
    (150 telefonun eyni anda səhifə yükləməsi HTTP limitini doldurmasın)."""
    return {"type": "game_started", "redirect": redirect, "redirect_jitter_ms": GAME_START_REDIRECT_JITTER_MS}


def _finish_locked(locked: LiveSession) -> None:
    locked.state = LiveSession.STATE_FINISHED
    locked.current_question_id = None
    clear_question_phase_override(locked)
    locked.save(update_fields=["state", "current_index", "current_question_id", "host_settings"])


# ──────────────────────────────────────────────────────────────────────────────
# Session lifecycle
# ──────────────────────────────────────────────────────────────────────────────


def create_live_session(exam, host_user) -> LiveSession:
    """Create a new LiveSession in STATE_LOBBY for *exam* hosted by *host_user*."""
    return LiveSession.objects.create(exam=exam, host_user=host_user)


def start_game(session: LiveSession, *, question_count: int | None = None) -> dict:
    """LOBBY → QUESTION (1-ci sual). ``ValueError`` kodları: sual yoxdur / say / vəziyyət."""
    from django.urls import reverse

    with transaction.atomic():
        locked = lock_session(session)
        if locked.state != LiveSession.STATE_LOBBY:
            raise ValueError("game_already_started")
        selected_ids = select_question_ids(locked, question_count)
        locked.selected_question_ids = selected_ids
        locked.question_limit = len(selected_ids)
        locked.save(update_fields=["selected_question_ids", "question_limit"])
        exam_question = get_question_by_index(locked, 0)
        if exam_question is None:
            raise ValueError("question_not_found")
        payload = publish_question(locked, exam_question, idx=0, total=len(selected_ids))
        total_in_exam = len(get_exam_question_ids(locked))
    _sync_instance(session, locked, _GAME_FIELDS)

    game_started = game_started_payload(reverse("liveExam:player_screen", kwargs={"pin": locked.pin}))
    _after_commit(lambda: broadcast(locked.pin, game_started, "lobby"))
    _after_commit(lambda: broadcast_play(locked.pin, payload))
    return {"ok": True, "question_count": len(selected_ids), "total_in_exam": total_in_exam}


def advance_to_next(session: LiveSession, *, expected_question_id: int | None = None) -> dict:
    """REVEAL → növbəti sual və ya FINISHED.

    Yalnız REVEAL-dən (LXBE-05): əvvəl QUESTION vəziyyətində «next» EYNİ sualı yeni
    taymerlə yenidən nəşr edirdi (ikiqat klikdə hamının taymeri sıfırlanırdı).
    """
    with transaction.atomic():
        locked = lock_session(session)
        if locked.state != LiveSession.STATE_REVEAL:
            return {"ok": False, "code": "invalid_state_for_next"}
        if expected_question_id and int(locked.current_question_id or 0) != int(expected_question_id):
            return {"ok": False, "code": "invalid_state_for_next"}
        next_idx = int(locked.current_index or 0) + 1
        total = get_total_questions(locked)
        exam_question = get_question_by_index(locked, next_idx)
        locked.current_index = next_idx
        if exam_question is None:
            _finish_locked(locked)
            finished_at = timezone.now()
            payload = None
        else:
            payload = publish_question(locked, exam_question, idx=next_idx, total=total)
    _sync_instance(session, locked, _GAME_FIELDS)

    if payload is None:
        bundle = build_final_bundle(locked, finished_at=finished_at, limit=50)
        _after_commit(lambda: broadcast_bundle(locked.pin, bundle))
        return {"ok": True, "finished": True}
    _after_commit(lambda: broadcast_play(locked.pin, payload))
    return {"ok": True, "finished": False, "index": next_idx + 1, "total": total}


def reveal_current(session: LiveSession, *, expected_question_id: int | None = None) -> dict:
    """QUESTION → REVEAL (host). ``ok=False`` + ``code`` vəziyyət uyğun deyilsə."""
    with transaction.atomic():
        locked = lock_session(session)
        if locked.state != LiveSession.STATE_QUESTION:
            return {"ok": False, "code": "not_in_question_state"}
        exam_question = get_active_question(locked)
        if exam_question is None:
            return {"ok": False, "code": "active_question_not_found"}
        if expected_question_id and int(exam_question.id) != int(expected_question_id):
            return {"ok": False, "code": "not_in_question_state"}
        revealed_at = timezone.now()
        _apply_reveal(locked, exam_question, revealed_at=revealed_at)
    _sync_instance(session, locked, _GAME_FIELDS)

    bundle = build_reveal_bundle(locked, exam_question.id, revealed_at=revealed_at, exam_question=exam_question)
    _after_commit(lambda: broadcast_bundle(locked.pin, bundle))
    return {"ok": True, "question_id": exam_question.id}


def reveal_if_all_answered(session_id: int, question_id: int, *, skip_locked: bool = False) -> bool:
    """Hamı cavab veribsə (kilid altında yenidən sayılır) reveal edir; yayımı çağıran edir.

    ``skip_locked=True`` — çağıran xarici tranzaksiyada sətri artıq ``FOR SHARE`` tutur:
    başqası da tutursa gözləmirik (kilid yüksəltmə deadlock-u olmasın), ``False`` qaytarırıq.
    """
    with transaction.atomic():
        locked = (
            LiveSession.objects.select_for_update(of=("self",), skip_locked=skip_locked)
            .select_related("exam")
            .filter(pk=session_id)
            .first()
        )
        if locked is None or locked.state != LiveSession.STATE_QUESTION:
            return False
        exam_question = get_active_question(locked)
        if exam_question is None or int(exam_question.id) != int(question_id):
            return False
        total_players = eligible_players(locked.id, int(locked.current_index or 0)).count()
        answered = LiveAnswer.objects.filter(session_id=locked.id, question_id=question_id).in_game().count()
        if total_players <= 0 or answered < total_players:
            return False
        _apply_reveal(locked, exam_question, revealed_at=timezone.now())
    return True


def auto_reveal_if_due(pin: str, question_id: int | None = None, *, now=None):
    """Server təhlükəsizlik toru (LXBE-08): ``autoplay`` açıq, vaxt + güzəşt bitib,
    host hələ reveal etməyib → reveal edir və ``Bundle`` qaytarır (yayım çağırandadır).
    Şərt ödənmirsə ``None``. Çox consumer eyni anda çağırsa da kilid bir keçid verir."""
    now = now or timezone.now()
    with transaction.atomic():
        locked = _lock_session_by_pin(pin)
        if locked is None or locked.state != LiveSession.STATE_QUESTION or locked.question_ends_at is None:
            return None
        if not get_host_session_settings(locked).get("autoplay", True):
            return None
        exam_question = get_active_question(locked)
        if exam_question is None or (question_id and int(exam_question.id) != int(question_id)):
            return None
        if now < locked.question_ends_at + timedelta(seconds=SERVER_AUTO_REVEAL_GRACE_SECONDS):
            return None
        _apply_reveal(locked, exam_question, revealed_at=now)
    return build_reveal_bundle(locked, exam_question.id, revealed_at=now, exam_question=exam_question)


def finish_session(session: LiveSession) -> None:
    """Mark the session as finished and broadcast the final leaderboard (idempotent)."""
    with transaction.atomic():
        locked = lock_session(session)
        if locked.state == LiveSession.STATE_FINISHED:
            _sync_instance(session, locked, _GAME_FIELDS)
            return
        _finish_locked(locked)
    _sync_instance(session, locked, _GAME_FIELDS)
    bundle = build_final_bundle(locked, finished_at=timezone.now(), limit=50)
    _after_commit(lambda: broadcast_bundle(locked.pin, bundle))


def skip_question_intro(session: LiveSession) -> dict:
    with transaction.atomic():
        locked = lock_session(session)
        if locked.state != LiveSession.STATE_QUESTION or locked.question_started_at is None:
            return {"ok": False, "code": "active_question_not_found", "status": 409}
        exam_question = get_active_question(locked)
        if exam_question is None:
            return {"ok": False, "code": "active_question_not_found", "status": 404}
        idx = int(locked.current_index or 0)
        _ready, answer_starts_at, _ends = build_question_phase_times(
            locked, exam_question, started_at=locked.question_started_at, idx=idx
        )
        now = timezone.now()
        if now >= answer_starts_at:
            return {"ok": True, "skipped": False, "already_open": True}
        ends_at = now + timedelta(seconds=question_time_limit(locked, exam_question))
        set_question_phase_override(
            locked, question_id=exam_question.id, ready_ends_at=now, answer_starts_at=now, ends_at=ends_at
        )
        locked.question_ends_at = ends_at
        locked.save(update_fields=["host_settings", "question_ends_at"])
        payload = build_question_phase_payload(
            locked,
            exam_question,
            idx=idx,
            total=get_total_questions(locked),
            started_at=locked.question_started_at,
            ready_ends_at=now,
            answer_starts_at=now,
            ends_at=ends_at,
        )
    _sync_instance(session, locked, _GAME_FIELDS)
    _after_commit(lambda: broadcast_play(locked.pin, payload))
    return {"ok": True, "skipped": True, "ends_at": ends_at.isoformat()}


def toggle_session_lock(session: LiveSession, *, locked: bool | None = None) -> bool:
    """
    Toggle (or explicitly set) the session lock.

    Parameters
    ----------
    locked:
        ``True`` / ``False`` to set explicitly; ``None`` to toggle.

    Returns
    -------
    The new lock state (bool).
    """
    with transaction.atomic():
        row = lock_session(session)
        row.is_locked = (not row.is_locked) if locked is None else bool(locked)
        row.save(update_fields=["is_locked"])
    _sync_instance(session, row, ("is_locked",))
    lobby_state = build_lobby_state_payload(row)
    _after_commit(lambda: broadcast(row.pin, lobby_state, "lobby"))
    return row.is_locked


def remove_player(session: LiveSession, player_id: int) -> dict[str, Any] | None:
    """Aparıcı oyunçunu çıxarır — lobbidə VƏ oyun gedərkən (2026-10-08, L6).

    * Lobbidə: sətir silinir (əvvəlki kimi — hələ cavab yoxdur).
    * Oyun gedərkən: ``removed_at`` yazılır (soft) — müəllimin nəticəsində «çıxarıldı» kimi qalır,
      liderlik / saylar / paylanma onu görmür (``LivePlayer.objects`` çıxarılmamışlardır).
    * Hər iki halda klient yadda saxlanılır (LXS-09: eyni cookie ilə qayıtmır), açıq socket-ləri
      ``kicked`` + 4403 ilə bağlanır; cari sualda qalanların hamısı cavab veribsə raund açılır.

    ``None`` — oyunçu tapılmadı. ``ValueError("session_finished")`` — bitmiş oyunda dəyişiklik yoxdur.
    Qaytarır: ``{"player_id", "nickname", "score", "mode": "deleted"|"removed", "state"}`` (audit üçün).
    """
    bundle = None
    with transaction.atomic():
        locked = lock_session(session)
        if locked.state == LiveSession.STATE_FINISHED:
            raise ValueError("session_finished")
        player = LivePlayer.objects.select_for_update().filter(session_id=locked.id, id=player_id).first()
        if player is None:
            return None
        # LX-SEC LXS-09: çıxarılan klient eyni cookie ilə yenidən qoşula bilməsin.
        remember_kicked_client(locked, player.client_id)  # ``locked.host_settings``-i də yeniləyir
        summary = {
            "player_id": player.id,
            "nickname": player.nickname,
            "score": int(player.score or 0),
            "state": locked.state,
            "mode": "deleted" if locked.state == LiveSession.STATE_LOBBY else "removed",
        }
        if locked.state == LiveSession.STATE_LOBBY:
            player.delete()
        else:
            player.removed_at = timezone.now()
            player.is_connected = False
            player.save(update_fields=["removed_at", "is_connected"])
            bundle = _reveal_if_rest_answered(locked)
    _sync_instance(session, locked, _GAME_FIELDS)
    lobby_state = build_lobby_state_payload(locked)
    _after_commit(lambda: broadcast(locked.pin, lobby_state, "lobby"))
    _after_commit(lambda: broadcast_player_kicked(locked.pin, player_id))
    if summary["mode"] == "removed" and locked.state == LiveSession.STATE_QUESTION and bundle is None:
        progress = _progress_payload(locked)
        if progress is not None:
            _after_commit(lambda: broadcast_host(locked.pin, progress))
    if bundle is not None:
        _after_commit(lambda: broadcast_bundle(locked.pin, bundle))
    return summary


def _reveal_if_rest_answered(locked: LiveSession):
    """(Kilid altında) çıxarılandan sonra qalanların hamısı cavab veribsə reveal — ``Bundle`` və ya ``None``."""
    if locked.state != LiveSession.STATE_QUESTION:
        return None
    exam_question = get_active_question(locked)
    if exam_question is None:
        return None
    eligible = eligible_players(locked.id, int(locked.current_index or 0)).count()
    answered = LiveAnswer.objects.filter(session_id=locked.id, question_id=exam_question.id).in_game().count()
    if eligible <= 0 or answered < eligible:
        return None
    revealed_at = timezone.now()
    _apply_reveal(locked, exam_question, revealed_at=revealed_at)
    return build_reveal_bundle(locked, exam_question.id, revealed_at=revealed_at, exam_question=exam_question)


def _progress_payload(locked: LiveSession) -> dict[str, Any] | None:
    question_id = int(locked.current_question_id or 0)
    if not question_id:
        return None
    return build_answer_progress_payload(
        question_id=question_id,
        answered_count=LiveAnswer.objects.filter(session_id=locked.id, question_id=question_id).in_game().count(),
        total_players=eligible_players(locked.id, int(locked.current_index or 0)).count(),
    )


def update_host_settings(session: LiveSession, raw_updates: dict | None, *, max_participants_cap: int) -> dict:
    """Ayarları kilid altında yazır; TAM ayarları qaytarır. ``SessionSettingsError`` → 400."""
    with transaction.atomic():
        locked = lock_session(session)
        settings = update_session_settings(locked, raw_updates, max_participants_cap=max_participants_cap)
    _sync_instance(session, locked, ("host_settings",))

    public = public_session_settings(settings)
    lobby_state = build_lobby_state_payload(locked)
    event = {"type": "session_settings", "is_locked": bool(locked.is_locked)}
    _after_commit(lambda: broadcast(locked.pin, lobby_state, "lobby"))
    _after_commit(lambda: broadcast_host(locked.pin, {**event, "settings": settings}))
    _after_commit(lambda: broadcast_players(locked.pin, {**event, "settings": public}))
    return settings
