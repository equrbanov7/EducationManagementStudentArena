"""
Serialization helpers for live exam transport payloads.
"""

from __future__ import annotations

import hashlib
import random
from datetime import datetime
from typing import Any

from django.db.models import Sum
from django.utils.translation import pgettext

from apps.exams.models import ExamQuestionOption
from apps.live_exam.domain.session import (
    detect_multi,
    get_option_label,
    get_option_text,
    get_question_text,
    question_points,
    question_time_limit,
    safe_int,
)
from apps.live_exam.models import LiveAnswer, LivePlayer, LiveSession


def serialize_player_identity(player: LivePlayer) -> dict[str, Any]:
    return {
        "id": player.id,
        "nickname": player.nickname,
        "avatar_key": player.avatar_key,
        "accessory_key": player.accessory_key,
    }


def serialize_players(session: LiveSession, limit: int = 50) -> list[dict[str, Any]]:
    return list(session.players.order_by("-created_at").values("id", "nickname", "avatar_key", "accessory_key")[:limit])


def serialize_top(session: LiveSession, limit: int = 10) -> list[dict[str, Any]]:
    players = session.players.order_by("-score", "created_at").values(
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
    awarded_lookup = {
        int(row["player_id"]): safe_int(row["awarded_total"], 0)
        for row in (
            LiveAnswer.objects.filter(session=session, question_id=question_id)
            .values("player_id")
            .annotate(awarded_total=Sum("awarded_points"))
        )
    }

    players = list(
        session.players.values(
            "id",
            "nickname",
            "avatar_key",
            "accessory_key",
            "score",
            "created_at",
        )
    )

    rows: list[dict[str, Any]] = []
    for row in players:
        score_before = safe_int(row["score"], 0) - safe_int(awarded_lookup.get(int(row["id"]), 0), 0)
        rows.append(
            {
                "player_id": row["id"],
                "nickname": row["nickname"],
                "avatar_key": row["avatar_key"],
                "accessory_key": row["accessory_key"],
                "score": max(0, score_before),
                "_created_at": row["created_at"],
            }
        )

    rows.sort(key=lambda item: (-safe_int(item["score"], 0), item["_created_at"], safe_int(item["player_id"], 0)))
    return [{key: value for key, value in row.items() if key != "_created_at"} for row in rows[:limit]]


def serialize_answer_distribution(session: LiveSession, question_id: int) -> dict[str, Any]:
    counts: dict[int, int] = {}
    total_answers = 0

    answers = LiveAnswer.objects.filter(session=session, question_id=question_id).values("choice_id", "choice_ids")
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


def serialize_question_results(session: LiveSession, question_id: int, limit: int = 50) -> list[dict[str, Any]]:
    speed_rank_lookup = {
        answer.id: index + 1
        for index, answer in enumerate(
            LiveAnswer.objects.filter(session=session, question_id=question_id).order_by("answer_ms", "created_at", "id")
        )
    }
    answers = (
        LiveAnswer.objects.filter(session=session, question_id=question_id)
        .select_related("player")
        .order_by("-awarded_points", "answer_ms", "created_at", "id")
    )[:limit]

    results: list[dict[str, Any]] = []
    for answer in answers:
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


def serialize_player_question_result(session: LiveSession, question_id: int, player_id: int | None) -> dict[str, Any] | None:
    if not player_id:
        return None

    answers = list(
        LiveAnswer.objects.filter(session=session, question_id=question_id)
        .select_related("player")
        .order_by("answer_ms", "created_at", "id")
    )
    if not answers:
        return None

    answer = next((item for item in answers if int(item.player_id) == int(player_id)), None)
    if answer is None:
        return None

    answer_rank = 1
    for index, item in enumerate(answers, start=1):
        if item.id == answer.id:
            answer_rank = index
            break

    choice_ids = list(answer.choice_ids or [])
    if not choice_ids and answer.choice_id is not None:
        choice_ids = [answer.choice_id]

    return {
        "player_id": answer.player_id,
        "choice_ids": choice_ids,
        "is_correct": bool(answer.is_correct),
        "awarded_points": safe_int(answer.awarded_points, 0),
        "total_score": safe_int(answer.player.score, 0),
        "answer_ms": safe_int(answer.answer_ms, 0),
        "answer_rank": answer_rank,
    }


def options_seed(pin: str, question_id: int, started_at: datetime) -> int:
    seed_str = f"{pin}:{int(question_id)}:{started_at.isoformat()}"
    return int(hashlib.sha256(seed_str.encode("utf-8")).hexdigest()[:8], 16)


def build_options(exam_question, *, seed: int | None = None) -> list[dict[str, Any]]:
    letters = ["A", "B", "C", "D", "E", "F"]
    options = list(ExamQuestionOption.objects.filter(question=exam_question).order_by("id"))
    rnd = random.Random(seed) if seed is not None else random
    rnd.shuffle(options)

    payload: list[dict[str, Any]] = []
    for index, option in enumerate(options):
        label = get_option_label(option) or (letters[index] if index < len(letters) else str(index + 1))
        text = get_option_text(option) or pgettext("live_exam.view.option", "option_fallback_text").format(label=label)
        payload.append({"id": option.id, "label": label, "text": text})

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
    is_multi, max_select, _ = detect_multi(exam_question)
    seed = options_seed(session.pin, exam_question.id, started_at) if started_at else None

    return {
        "id": exam_question.id,
        "text": get_question_text(exam_question),
        "time_limit": question_time_limit(session, exam_question),
        "points": question_points(session, exam_question),
        "multi": is_multi,
        "max_select": max_select,
        "options": build_options(exam_question, seed=seed),
        "started_at": started_at.isoformat() if started_at else None,
        "ready_ends_at": ready_ends_at.isoformat() if ready_ends_at else None,
        "answer_starts_at": answer_starts_at.isoformat() if answer_starts_at else None,
        "ends_at": ends_at.isoformat() if ends_at else None,
        "get_ready_duration_ms": int(max(0, (ready_ends_at - started_at).total_seconds() * 1000)) if ready_ends_at and started_at else 0,
        "intro_duration_ms": int(max(0, (answer_starts_at - ready_ends_at).total_seconds() * 1000)) if answer_starts_at and ready_ends_at else 0,
        "index": safe_int(idx, 0) + 1,
        "total": safe_int(total, 0),
    }
