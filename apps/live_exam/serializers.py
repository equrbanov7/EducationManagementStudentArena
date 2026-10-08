"""
Serialization helpers for live exam transport payloads.
"""

from __future__ import annotations

import hashlib
import random
from datetime import datetime
from typing import Any

from django.db.models import F, IntegerField, OuterRef, Q, Subquery, Sum, Value
from django.db.models.expressions import ExpressionWrapper
from django.db.models.functions import Coalesce
from django.utils.translation import pgettext

from apps.live_exam.constants import ANSWER_LATENCY_GRACE_SECONDS
from apps.live_exam.domain.question_config import resolve_question_config
from apps.live_exam.domain.session import (
    get_option_text,
    get_question_text,
    question_points,
    question_time_limit,
    safe_int,
)
from apps.live_exam.models import LiveAnswer, LivePlayer, LiveSession
from apps.live_exam.session_settings import get_session_settings

#: Liderlik cədvəlinin YEGANƏ sıralama qaydası (bərabər balda qoşulma sırası):
#: bal ↓, qoşulma vaxtı ↑, id ↑. Canlı top, previous_top, final, nəticə səhifəsi
#: eyni qaydanı istifadə edir (docs/live_exam/ENGINE.md «Leaderboard»).
LEADERBOARD_ORDER = ("-score", "created_at", "id")


def serialize_player_identity(player: LivePlayer) -> dict[str, Any]:
    return {
        "id": player.id,
        "nickname": player.nickname,
        "avatar_key": player.avatar_key,
        "accessory_key": player.accessory_key,
    }


def serialize_players(session: LiveSession, limit: int = 200) -> list[dict[str, Any]]:
    # ``active_from_index`` — aparıcının siyahısında «növbəti sualdan» nişanı (gec qoşulan, 2026-10-08).
    rows = session.players.order_by("-created_at").values(
        "id", "nickname", "avatar_key", "accessory_key", "active_from_index"
    )[:limit]
    return list(rows)


def serialize_top(session: LiveSession, limit: int = 10) -> list[dict[str, Any]]:
    players = session.players.order_by(*LEADERBOARD_ORDER).values(
        "id",
        "nickname",
        "avatar_key",
        "accessory_key",
        "score",
    )[:limit]
    return [
        {
            "player_id": row["id"],
            "nickname": row["nickname"],
            "avatar_key": row["avatar_key"],
            "accessory_key": row["accessory_key"],
            "score": safe_int(row["score"], 0),
        }
        for row in players
    ]


def serialize_top_before_question(session: LiveSession, question_id: int, limit: int = 10) -> list[dict[str, Any]]:
    # Subquery: total awarded_points for this player on this question.
    awarded_subquery = (
        LiveAnswer.objects.filter(
            session=session,
            question_id=question_id,
            player_id=OuterRef("id"),
        )
        .values("player_id")
        .annotate(total=Sum("awarded_points"))
        .values("total")[:1]
    )

    # Annotate each player with score_before = score - awarded_for_question,
    # then sort and limit entirely in the DB — no full-list Python sort required.
    players = (
        session.players.annotate(
            awarded_for_question=Coalesce(
                Subquery(awarded_subquery, output_field=IntegerField()),
                Value(0),
            ),
            score_before=ExpressionWrapper(
                F("score") - F("awarded_for_question"),
                output_field=IntegerField(),
            ),
        )
        # Tiebreaker: ascending `id` is the player's primary key, equivalent
        # to the original `player_id` tiebreaker in the Python sort.
        .order_by("-score_before", "created_at", "id").values(
            "id", "nickname", "avatar_key", "accessory_key", "score_before"
        )[:limit]
    )

    return [
        {
            "player_id": row["id"],
            "nickname": row["nickname"],
            "avatar_key": row["avatar_key"],
            "accessory_key": row["accessory_key"],
            "score": max(0, safe_int(row["score_before"], 0)),
        }
        for row in players
    ]


def serialize_answer_distribution(session: LiveSession, question_id: int) -> dict[str, Any]:
    counts: dict[int, int] = {}
    total_answers = 0

    answers = (
        LiveAnswer.objects.filter(session=session, question_id=question_id).in_game().values("choice_id", "choice_ids")
    )
    for answer in answers:
        option_ids = list(answer.get("choice_ids") or [])
        if not option_ids and answer.get("choice_id") is not None:
            option_ids = [answer.get("choice_id")]

        seen: set[int] = set()
        for raw_option_id in option_ids:
            option_id = safe_int(raw_option_id, 0)
            if option_id <= 0 or option_id in seen:
                continue
            counts[option_id] = counts.get(option_id, 0) + 1
            seen.add(option_id)

        total_answers += 1

    return {
        "total_answers": total_answers,
        "counts": [
            {
                "option_id": option_id,
                "count": safe_int(count, 0),
            }
            for option_id, count in sorted(counts.items())
        ],
    }


def speed_order_key(answer) -> tuple[int, int]:
    """Cavab sürəti sırası (``answer_rank``): ``answer_ms`` ↑, sonra ``id`` ↑."""
    if isinstance(answer, dict):
        return safe_int(answer.get("answer_ms"), 0), safe_int(answer.get("id"), 0)
    return safe_int(answer.answer_ms, 0), safe_int(answer.id, 0)


def serialize_question_results(session: LiveSession, question_id: int, limit: int = 50) -> list[dict[str, Any]]:
    # Single query: fetch all answers with related player, ordered by speed for rank calculation.
    all_answers = list(
        LiveAnswer.objects.filter(session=session, question_id=question_id)
        .in_game()
        .select_related("player")
        .order_by("answer_ms", "id")
    )
    # Compute speed rank in Python — avoids a second DB round-trip.
    speed_rank_lookup = {answer.id: index + 1 for index, answer in enumerate(all_answers)}

    # Sort for display: highest points first, then fastest answer.
    sorted_answers = sorted(
        all_answers,
        key=lambda a: (-safe_int(a.awarded_points, 0), *speed_order_key(a)),
    )[:limit]

    results: list[dict[str, Any]] = []
    for answer in sorted_answers:
        results.append(
            {
                "player_id": answer.player_id,
                "nickname": answer.player.nickname,
                "avatar_key": answer.player.avatar_key,
                "accessory_key": answer.player.accessory_key,
                "is_correct": bool(answer.is_correct),
                "awarded_points": safe_int(answer.awarded_points, 0),
                "total_score": safe_int(answer.player.score, 0),
                "answer_ms": safe_int(answer.answer_ms, 0),
                "answer_rank": safe_int(speed_rank_lookup.get(answer.id), 0),
            }
        )
    return results


def answer_choice_ids(answer) -> list[int]:
    raw = answer.get("choice_ids") if isinstance(answer, dict) else answer.choice_ids
    choice_ids = list(raw or [])
    fallback = answer.get("choice_id") if isinstance(answer, dict) else answer.choice_id
    if not choice_ids and fallback is not None:
        choice_ids = [fallback]
    return choice_ids


def question_mode_fields(config, choice_ids: list[int] | None = None, text: str | None = None) -> dict[str, Any]:
    """Cavab növünə görə əlavə şəxsi sahələr (yazılı: ``your_text``; multi: seçim sayları)."""
    if config is None:
        return {}
    if config.is_text:
        return {"your_text": text or ""}
    if config.is_multi:
        chosen = {safe_int(value, 0) for value in (choice_ids or [])}
        correct = set(config.correct_ids)
        return {
            "correct_selected": len(chosen & correct),
            "wrong_selected": len(chosen - correct),
            "total_correct": len(correct),
        }
    return {}


def speed_rank(session_id: int, question_id: int, answer) -> int:
    answer_ms, answer_id = speed_order_key(answer)
    faster = (
        LiveAnswer.objects.filter(session_id=session_id, question_id=question_id)
        .in_game()
        .filter(Q(answer_ms__lt=answer_ms) | Q(answer_ms=answer_ms, id__lt=answer_id))
        .count()
    )
    return faster + 1


def personal_result_from_answer(session, answer, *, player=None, config=None, rank: bool = True) -> dict[str, Any]:
    """Oyunçunun öz nəticəsi (reveal-də / sonuncu cavabda göndərilir)."""
    owner = player if player is not None else answer.player
    choice_ids = answer_choice_ids(answer)
    result = {
        "player_id": answer.player_id,
        "choice_ids": choice_ids,
        "is_correct": bool(answer.is_correct),
        "awarded_points": safe_int(answer.awarded_points, 0),
        "total_score": safe_int(owner.score, 0),
        "answer_ms": safe_int(answer.answer_ms, 0),
        "streak": safe_int(getattr(owner, "streak", 0), 0),
    }
    if rank:
        result["answer_rank"] = speed_rank(session.id, answer.question_id, answer)
    result.update(question_mode_fields(config, choice_ids, getattr(answer, "text_answer", "")))
    return result


def serialize_player_question_result(
    session: LiveSession, question_id: int, player_id: int | None, *, config=None
) -> dict[str, Any] | None:
    if not player_id:
        return None

    answer = (
        LiveAnswer.objects.filter(session=session, question_id=question_id, player_id=player_id)
        .select_related("player")
        .first()
    )
    if answer is None:
        return None
    if config is None:
        from apps.exams.models import ExamQuestion

        question = (
            ExamQuestion.objects.filter(exam_id=session.exam_id, id=question_id).prefetch_related("options").first()
        )
        config = resolve_question_config(session, question) if question is not None else None
    return personal_result_from_answer(session, answer, config=config)


def options_seed(pin: str, question_id: int, started_at: datetime) -> int:
    seed_str = f"{pin}:{int(question_id)}:{started_at.isoformat()}"
    return int(hashlib.sha256(seed_str.encode("utf-8")).hexdigest()[:8], 16)


def build_options(exam_question, *, seed: int | None = None, randomize: bool = True) -> list[dict[str, Any]]:
    letters = ["A", "B", "C", "D", "E", "F"]
    shapes = [
        {"key": "triangle", "label": "Triangle"},
        {"key": "diamond", "label": "Diamond"},
        {"key": "circle", "label": "Circle"},
        {"key": "square", "label": "Square"},
        {"key": "pentagon", "label": "Pentagon"},
        {"key": "hexagon", "label": "Hexagon"},
    ]
    # Materialize with list() first so we always iterate the queryset / prefetch cache exactly once.
    options = sorted(list(exam_question.options.all()), key=lambda o: o.id)
    if randomize:
        rnd = random.Random(seed) if seed is not None else random  # nosec B311
        rnd.shuffle(options)

    payload: list[dict[str, Any]] = []
    for index, option in enumerate(options):
        label = letters[index] if index < len(letters) else str(index + 1)
        shape = shapes[index % len(shapes)]
        text = get_option_text(option) or pgettext("live_exam.view.option", "option_fallback_text").format(label=label)
        payload.append(
            {
                "id": option.id,
                "label": label,
                "shape": shape["key"],
                "shape_label": shape["label"],
                "text": text,
            }
        )

    return payload


def serialize_question(
    session: LiveSession,
    exam_question,
    *,
    idx: int,
    total: int,
    started_at,
    ready_ends_at,
    answer_starts_at,
    ends_at,
) -> dict[str, Any]:
    config = resolve_question_config(session, exam_question)
    settings = get_session_settings(session)
    randomize_answers = bool(settings.get("randomize_answers", True))
    seed = options_seed(session.pin, exam_question.id, started_at) if started_at and randomize_answers else None
    # Yazılı cavab sualında variant/düzgünlük məlumatı HEÇ göndərilmir.
    options = [] if config.is_text else build_options(exam_question, seed=seed, randomize=randomize_answers)

    return {
        "id": exam_question.id,
        "text": get_question_text(exam_question),
        "time_limit": question_time_limit(session, exam_question),
        "points": question_points(session, exam_question),
        "multi": config.is_multi,
        "max_select": config.max_select,
        "options": options,
        **config.to_payload_fields(),
        "answer_grace_ms": int(ANSWER_LATENCY_GRACE_SECONDS * 1000),
        "started_at": started_at.isoformat() if started_at else None,
        "ready_ends_at": ready_ends_at.isoformat() if ready_ends_at else None,
        "answer_starts_at": answer_starts_at.isoformat() if answer_starts_at else None,
        "ends_at": ends_at.isoformat() if ends_at else None,
        "get_ready_duration_ms": (
            int(max(0, (ready_ends_at - started_at).total_seconds() * 1000)) if ready_ends_at and started_at else 0
        ),
        "intro_duration_ms": (
            int(max(0, (answer_starts_at - ready_ends_at).total_seconds() * 1000))
            if answer_starts_at and ready_ends_at
            else 0
        ),
        "index": safe_int(idx, 0) + 1,
        "total": safe_int(total, 0),
    }
