"""
Scoring and answer persistence helpers for live exams.

Qaydalar (tam təsvir: docs/live_exam/ENGINE.md):

* **Vaxt əmsalı** — Kahoot: düzgün cavab 100% → 50% (cavab pəncərəsinin
  sonunadək xətti). Vaxt SERVERİN gördüyü andan ölçülür: mesajın serverə ÇATDIĞI
  an (WS ``receive`` / HTTP view girişi — növbə gözləməsi daxil deyil). Müştərinin
  ``answer_ms``-i balı YALNIZ AZALDA bilər (Audit 2026-09-28 LXBE-01). Sual oyunçuya pəncərə
  açılandan SONRA çatıbsa (server sübutu, ``delivery.py``), vaxt tavanla həmin andan ölçülür (LXNET).
* **Çox seçimli** — ``multi_scoring``: ``partial`` (default) =
  baza × əmsal × max(0, (düz − səhv) / cəmi_düz); ``strict`` = yalnız dəqiq dəst.
* **Yazılı cavab** — düzgün → baza × əmsal; səhv/boş → 0.
* **Seriya (streak)** — dəqiq düzgün cavab +1, digər cavab → 0, cavabsız qalmaq
  reveal-də → 0; bonus bal YOXDUR. Düzgün variantı olmayan sual — neytral.
* **Paralellik** — cavab sessiya sətrini ``FOR SHARE`` (cavablar bir-birini
  gözləmir), oyunçu sətrini ``FOR UPDATE`` ilə kilidləyir; host keçidləri
  (reveal/next/finish) sessiyanı ``FOR UPDATE`` ilə kilidlədiyi üçün hər qəbul
  olunmuş cavab keçiddən ƏVVƏL commit olunur, keçiddən sonra gələn cavab isə yeni
  vəziyyəti görür (LXBE-04).
"""

from __future__ import annotations

from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from django.db import connection, transaction
from django.utils import timezone
from django.utils.translation import pgettext

from apps.exams.models import ExamQuestion
from apps.live_exam.constants import ANSWER_LATENCY_GRACE_SECONDS
from apps.live_exam.delivery import late_delivery_shift_ms, question_seen_at
from apps.live_exam.domain.question_config import resolve_question_config
from apps.live_exam.domain.session import build_question_phase_times, get_active_question, question_points
from apps.live_exam.models import LiveAnswer, LivePlayer, LiveSession
from apps.live_exam.roster import eligible_count_for_current, is_pending
from apps.live_exam.serializers import personal_result_from_answer, speed_rank
from apps.live_exam.session_settings import MULTI_SCORING_STRICT
from apps.live_exam.text_safety import sanitize_player_text
from apps.live_exam.typed_answers import TEXT_MAX_LENGTH, typed_answer_matches
from core.rls import bypass_rls

#: Köhnə ad (geri uyğunluq). Artıq istifadə olunmur: müştəri vaxtı serverin
#: ölçdüyü vaxtdan AZ ola bilməz (LXBE-01).
ANSWER_MS_LATENCY_ALLOWANCE_MS = 0


def _error(msgid: str) -> str:
    return pgettext("live_exam.consumer.error", msgid)


def score_multi_fraction(chosen_ids: list[int], correct_ids: list[int], *, mode: str = "strict") -> float:
    chosen = set(int(value) for value in (chosen_ids or []))
    correct = set(int(value) for value in (correct_ids or []))
    if not correct:
        return 0.0

    picked_correct = len(chosen & correct)
    picked_wrong = len(chosen - correct)
    correct_total = len(correct)

    if mode == "strict":
        if picked_wrong > 0:
            return 0.0
        return 1.0 if picked_correct == correct_total else 0.0

    return max(0.0, (picked_correct - picked_wrong) / float(correct_total))


def _round_awarded_points(value: float | Decimal) -> int:
    """
    Round points to the nearest integer using half-up semantics.

    `int(...)` truncates `0.5` down to `0`, which caused 1-point questions to
    award zero to correct answers answered later in the timer window.
    """
    return max(0, int(Decimal(str(value)).quantize(Decimal("1"), rounding=ROUND_HALF_UP)))


def _kahoot_time_factor(*, answer_ms: int, total_ms: int) -> float:
    """
    Kahoot-style speed multiplier.

    A correct answer can earn between 100% and 50% of its base score depending
    on how quickly it was submitted during the active answer window.
    """
    if total_ms <= 0:
        return 1.0

    bounded_answer_ms = max(0, min(int(answer_ms or 0), int(total_ms)))
    progress = bounded_answer_ms / float(total_ms)
    return max(0.5, 1.0 - (progress * 0.5))


def effective_answer_ms(*, client_ms: int | None, server_elapsed_ms: int, total_ms: int) -> int:
    """Balda istifadə olunan cavab vaxtı: ``max(server, müştəri)``, [0, total_ms] aralığında."""
    value = max(int(server_elapsed_ms or 0), int(client_ms or 0), 0)
    return min(value, int(total_ms)) if total_ms > 0 else value


def calculate_answer_score(
    *,
    option_ids: list[int],
    correct_ids: list[int],
    base_points: int,
    answer_ms: int,
    total_ms: int,
    multi_scoring: str = "partial",
) -> dict[str, Any]:
    selected_set = set(int(value) for value in option_ids)
    correct_set = set(int(value) for value in correct_ids)

    picked_correct = len(selected_set & correct_set)
    picked_wrong = len(selected_set - correct_set)
    correct_total = len(correct_set)
    mode = "strict" if multi_scoring == MULTI_SCORING_STRICT else "partial"
    fraction = min(1.0, max(0.0, score_multi_fraction(option_ids, correct_ids, mode=mode)))
    is_perfect = bool(correct_set) and selected_set == correct_set

    bounded_answer_ms = int(answer_ms or 0)
    if total_ms > 0:
        bounded_answer_ms = max(0, min(bounded_answer_ms, total_ms))
    else:
        bounded_answer_ms = max(0, bounded_answer_ms)

    time_factor = _kahoot_time_factor(answer_ms=bounded_answer_ms, total_ms=total_ms)
    if fraction <= 0:
        awarded_points = 0
    else:
        awarded_points = _round_awarded_points(int(base_points) * fraction * time_factor)

    return {
        "is_correct": is_perfect,
        "fraction": round(float(fraction), 4),
        "time_factor": round(float(time_factor), 4),
        "picked_correct": picked_correct,
        "picked_wrong": picked_wrong,
        "correct_total": correct_total,
        "awarded_points": awarded_points,
        "base": int(base_points),
        "bonus": 0,
        "answer_ms": bounded_answer_ms,
    }


def calculate_typed_score(
    *, text: str, accepted: list[str], typo_tolerance: bool, base_points: int, answer_ms: int, total_ms: int
) -> dict[str, Any]:
    is_correct = typed_answer_matches(text, accepted, typo_tolerance=typo_tolerance)
    bounded_answer_ms = max(0, min(int(answer_ms or 0), total_ms)) if total_ms > 0 else max(0, int(answer_ms or 0))
    time_factor = _kahoot_time_factor(answer_ms=bounded_answer_ms, total_ms=total_ms)
    awarded_points = _round_awarded_points(int(base_points) * time_factor) if is_correct else 0
    return {
        "is_correct": is_correct,
        "fraction": 1.0 if is_correct else 0.0,
        "time_factor": round(float(time_factor), 4),
        "picked_correct": 0,
        "picked_wrong": 0,
        "correct_total": 0,
        "awarded_points": awarded_points,
        "base": int(base_points),
        "bonus": 0,
        "answer_ms": bounded_answer_ms,
    }


def answer_progress_counts(session_id: int, question_id: int) -> dict[str, int]:
    """Commit olunmuş cavab/oyunçu sayları (unikal məhdudiyyət: 1 cavab = 1 oyunçu)."""
    return {
        "question_id": int(question_id),
        "answered_count": LiveAnswer.objects.filter(session_id=session_id, question_id=question_id).in_game().count(),
        # 2026-10-08 (L3): yalnız bu suala cavab verməli olanlar (gec qoşulan növbəti sualdan sayılır).
        "total_players": eligible_count_for_current(session_id),
    }


def get_answer_progress(*, pin: str, question_id: int) -> dict[str, int]:
    with bypass_rls():
        session_id = LiveSession.objects.filter(pin=pin).values_list("id", flat=True).first()
        if session_id is None:
            raise LiveSession.DoesNotExist
        return answer_progress_counts(session_id, question_id)


def _lock_session_for_answer(pin: str) -> LiveSession:
    """Sessiya sətri ``FOR SHARE`` (cavablar paralel, host keçidləri gözləyir)."""
    if connection.vendor == "postgresql":
        table = connection.ops.quote_name(LiveSession._meta.db_table)
        with connection.cursor() as cursor:
            cursor.execute(
                f"SELECT id FROM {table} WHERE pin = %s FOR SHARE", [pin]
            )  # nosec B608 — cədvəl adı modeldən
            row = cursor.fetchone()
        if row is None:
            raise LiveSession.DoesNotExist
        return LiveSession.objects.select_related("exam").get(pk=row[0])
    return LiveSession.objects.select_related("exam").get(pin=pin)


def _already_answered(session, player, answer, question) -> tuple[bool, dict[str, Any], LiveAnswer, bool]:
    """Təkrar göndəriş idempotentdir: mövcud cavab qaytarılır (reveal-ə qədər nəticəsiz)."""
    config = resolve_question_config(session, question)
    personal = personal_result_from_answer(session, answer, player=player, config=config, rank=False) or {}
    return (
        True,
        {
            "answer": {"message": _error("already_answered"), "score": player.score, **personal},
            "question_id": int(answer.question_id),
            "reveal_question_id": None,
        },
        answer,
        False,
    )


def _score_submission(session, question, config, *, option_ids, text, answer_ms, received_at, seen_at=None):
    """``(score_dict, None)`` və ya ``(None, error_message)`` — pəncərə + forma yoxlaması.

    ``seen_at`` — sualın bu oyunçuya çatdığının server sübutu (``delivery``): pəncərə açılandan
    SONRA çatıbsa, sürət vaxtı tavanla həmin andan ölçülür (LXNET 2026-10-02). Pəncərə dəyişmir.
    """
    question_idx = int(session.current_index or 0)
    _, answer_starts_at, _ = build_question_phase_times(
        session, question, started_at=session.question_started_at, idx=question_idx
    )
    deadline = session.question_ends_at + timedelta(seconds=ANSWER_LATENCY_GRACE_SECONDS)
    if not (answer_starts_at <= received_at <= deadline):
        return None, _error("submission_outside_active_window")

    total_ms = max(0, int((session.question_ends_at - answer_starts_at).total_seconds() * 1000))
    shift_ms = late_delivery_shift_ms(seen_at=seen_at, answer_starts_at=answer_starts_at, total_ms=total_ms)
    server_elapsed_ms = max(0, int((received_at - answer_starts_at).total_seconds() * 1000) - shift_ms)
    effective_ms = effective_answer_ms(client_ms=answer_ms, server_elapsed_ms=server_elapsed_ms, total_ms=total_ms)
    base_points = question_points(session, question)

    if config.is_text:
        if option_ids or text is None:
            return None, _error("bad_payload")
        return (
            calculate_typed_score(
                text=text,
                accepted=list(config.accepted),
                typo_tolerance=config.typo_tolerance,
                base_points=base_points,
                answer_ms=effective_ms,
                total_ms=total_ms,
            ),
            None,
        )

    if text is not None:
        return None, _error("bad_payload")
    # Tapılmayan/başqa suala aid id-lər saxta yükdür (paylanmanı da korlayardı).
    valid_option_ids = {option.id for option in question.options.all()}
    chosen = set(int(value) for value in option_ids or [])
    if not chosen or not chosen <= valid_option_ids:
        return None, _error("bad_payload")
    # Audit 2026-09-28 EX28-10: ``max_select`` server tərəfdə də tətbiq olunur.
    if len(chosen) > config.max_select:
        return None, _error("bad_payload")
    return (
        calculate_answer_score(
            option_ids=list(option_ids),
            correct_ids=list(config.correct_ids),
            base_points=base_points,
            answer_ms=effective_ms,
            total_ms=total_ms,
            multi_scoring=config.multi_scoring,
        ),
        None,
    )


def _persist_answer(*, pin, player_id, client_id, question_id, option_ids, text, answer_ms, received_at, seen_at=None):
    """Tranzaksiya 1: yoxla + saxla + bal/seriya. ``(ok, result|msg, answer, created, session)``."""
    with transaction.atomic():
        session = _lock_session_for_answer(pin)
        player = LivePlayer.objects.select_for_update().get(id=player_id, session=session, client_id=client_id)
        # 2026-10-08 (L3): gec qoşulan cari suala cavab vermir (növbəti sual sərhədindən oyundadır).
        if is_pending(player, session):
            return False, _error("Növbəti sual başlayanda oyuna qoşulacaqsan."), None, False, session

        question = get_active_question(session)
        if question is None or int(question_id) != int(question.id):
            exists = ExamQuestion.objects.filter(id=question_id, exam_id=session.exam_id).exists()
            if not exists:
                return False, _error("question_not_found"), None, False, session
            if question is None:
                return False, _error("active_question_not_found"), None, False, session
            return False, _error("question_not_active"), None, False, session

        existing = LiveAnswer.objects.filter(session=session, player=player, question_id=question_id).first()
        if existing is not None:
            return (*_already_answered(session, player, existing, question), session)

        if (
            session.state != LiveSession.STATE_QUESTION
            or session.question_started_at is None
            or session.question_ends_at is None
        ):
            return False, _error("question_not_accepting_answers"), None, False, session

        config = resolve_question_config(session, question)
        score, error = _score_submission(
            session,
            question,
            config,
            option_ids=option_ids,
            text=text,
            answer_ms=answer_ms,
            received_at=received_at,
            seen_at=seen_at,
        )
        if error:
            return False, error, None, False, session

        answer = LiveAnswer.objects.create(
            session=session,
            player=player,
            question_id=question_id,
            choice_id=(option_ids[0] if option_ids else None),
            choice_ids=list(option_ids or []),
            text_answer=text or "",
            is_correct=score["is_correct"],
            answer_ms=score["answer_ms"],
            awarded_points=score["awarded_points"],
        )

        # Audit 2026-09-28 LXBE-06: seriya oyunçu sətri kilidli olduğu üçün itmir.
        if not config.is_neutral:
            player.streak = int(player.streak or 0) + 1 if score["is_correct"] else 0
            player.best_streak = max(int(player.best_streak or 0), int(player.streak))
        player.score = int(player.score or 0) + int(score["awarded_points"])
        player.last_seen = received_at
        player.save(update_fields=["score", "streak", "best_streak", "last_seen"])

        personal = personal_result_from_answer(session, answer, player=player, config=config, rank=False) or {}
        result = {
            "answer": {
                "is_correct": score["is_correct"],
                "fraction": score["fraction"],
                "picked_correct": score["picked_correct"],
                "picked_wrong": score["picked_wrong"],
                "correct_total": score["correct_total"],
                "awarded_points": score["awarded_points"],
                "base": score["base"],
                "bonus": score["bonus"],
                "score": player.score,
                **personal,
            },
            "question_id": int(question_id),
            "reveal_question_id": None,
        }
    return True, result, answer, True, session


def _deferred_reveal(session_id: int, pin: str, question_id: int) -> None:
    """Xarici tranzaksiya commit olunandan SONRA (``on_commit``) — kilid yüksəltmə
    (FOR SHARE → FOR UPDATE) deadlock-u olmasın deyə; reveal olarsa özü yayımlayır."""
    from apps.live_exam.reveal import build_reveal_bundle
    from apps.live_exam.services import reveal_if_all_answered
    from apps.live_exam.transport import broadcast_bundle

    with bypass_rls():
        progress = answer_progress_counts(session_id, question_id)
        if progress["total_players"] <= 0 or progress["answered_count"] < progress["total_players"]:
            return
        if not reveal_if_all_answered(session_id, question_id):
            return
        session = LiveSession.objects.select_related("exam").get(pk=session_id)
        bundle = build_reveal_bundle(session, question_id)
    broadcast_bundle(pin, bundle)


def _save_answer_and_score_impl(
    *,
    pin: str,
    player_id: int,
    client_id: str,
    question_id: int,
    option_ids: list[int],
    answer_ms: int,
    received_at=None,
    text: str | None = None,
) -> tuple[bool, str | dict[str, Any], LiveAnswer | None, bool]:
    from apps.live_exam.services import reveal_if_all_answered

    received_at = received_at or timezone.now()
    if text is not None:
        # Birbaşa çağırışlar üçün də eyni gigiyena (nəzarət/görünməz simvollar, ≤ 60).
        text = sanitize_player_text(text, max_length=TEXT_MAX_LENGTH)
    # Xarici tranzaksiya (RLS_TRANSACTION_SCOPED / ATOMIC_REQUESTS) daxilindəyiksə
    # «hamı cavab verdi» yoxlaması commit-ə qədər təxirə salınır.
    nested = connection.in_atomic_block
    # Keş oxunuşu kilidlərdən ƏVVƏL (tranzaksiya içində şəbəkə gözləməsi olmasın).
    seen_at = question_seen_at(pin, question_id, player_id)
    try:
        with bypass_rls():
            ok, result, answer, created, session = _persist_answer(
                pin=pin,
                player_id=player_id,
                client_id=client_id,
                question_id=question_id,
                option_ids=list(option_ids or []),
                text=text,
                answer_ms=answer_ms,
                received_at=received_at,
                seen_at=seen_at,
            )
            if not ok or not created:
                return ok, result, answer, created

            # Commit-dən SONRA saylar bütün commit olunmuş cavabları görür: iki
            # «sonuncu» cavab eyni anda gəlsə, sonra commit olunan hamını görür —
            # reveal itmir; kilid altında yenidən sayıldığı üçün TƏK dəfə olur (LXBE-04).
            progress = answer_progress_counts(session.id, question_id)
            result["progress"] = progress
            revealed = False
            if progress["total_players"] > 0 and progress["answered_count"] >= progress["total_players"]:
                revealed = reveal_if_all_answered(session.id, int(question_id), skip_locked=nested)
            if revealed:
                result["reveal_question_id"] = int(question_id)
                result["answer"]["answer_rank"] = speed_rank(session.id, int(question_id), answer)
            elif nested:
                # Xarici tranzaksiyada saylar hələ commit olunmamış qonşu cavabları görmür —
                # commit-dən sonra yenidən yoxlanır (lazımdırsa reveal + yayım orada).
                transaction.on_commit(lambda: _deferred_reveal(session.id, session.pin, int(question_id)))
    except LiveSession.DoesNotExist:
        return False, _error("session_not_found"), None, False
    except LivePlayer.DoesNotExist:
        return False, _error("player_not_found"), None, False

    return True, result, answer, True


def _legacy_answer_ms(session: LiveSession, question: ExamQuestion, submitted_at) -> int:
    if session.question_started_at is None:
        return 0

    question_idx = int(session.current_index or 0)
    _, answer_starts_at, _ = build_question_phase_times(
        session,
        question,
        started_at=session.question_started_at,
        idx=question_idx,
    )
    return max(0, int((submitted_at - answer_starts_at).total_seconds() * 1000))


def save_answer_and_score(
    *,
    pin: str | None = None,
    player_id: int | None = None,
    client_id: str | None = None,
    question_id: int | None = None,
    option_ids: list[int] | None = None,
    answer_ms: int | None = None,
    session: LiveSession | None = None,
    player: LivePlayer | None = None,
    question: ExamQuestion | None = None,
    submitted_at=None,
    received_at=None,
    text: str | None = None,
):
    if session is not None or player is not None or question is not None:
        if session is None or player is None or question is None:
            raise TypeError("Legacy save_answer_and_score calls require session=, player=, and question=.")

        effective_submitted_at = submitted_at or timezone.now()
        ok, _result, answer, created = _save_answer_and_score_impl(
            pin=session.pin,
            player_id=player.id,
            client_id=str(player.client_id or ""),
            question_id=question.id,
            option_ids=list(option_ids or []),
            answer_ms=_legacy_answer_ms(session, question, effective_submitted_at),
            received_at=effective_submitted_at,
            text=text,
        )
        if not ok:
            return None
        return answer, created

    if pin is None or player_id is None or question_id is None:
        raise TypeError("pin=, player_id=, and question_id= are required.")

    ok, result, _answer, _created = _save_answer_and_score_impl(
        pin=pin,
        player_id=player_id,
        client_id=str(client_id or ""),
        question_id=question_id,
        option_ids=list(option_ids or []),
        answer_ms=int(answer_ms or 0),
        received_at=received_at,
        text=text,
    )
    return ok, result
