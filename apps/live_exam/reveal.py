"""
Reveal və final paketləri — BİR batched sorğu dəsti ilə (Audit 2026-09-28 LXBE-03).

Əvvəl reveal-də hər qoşulu oyunçunun consumer-i öz nəticəsi üçün ayrıca DB
sorğuları edirdi (150 oyunçu → ~900 sorğu, hamısı Channels-in tək thread-ində
növbə ilə). İndi reveal anında:

* sualın bütün cavabları (1 sorğu) + sessiyanın bütün oyunçuları (1 sorğu) oxunur;
* host paketi, oyunçu paketi və HƏR oyunçunun şəxsi əlavələri (öz nəticəsi,
  ``rank``, ``gap_to_next``, ``next_nickname``) Python-da hesablanır;
* şəxsi əlavələr kanal-qatı hadisəsinə ``personal`` xəritəsi kimi (oyunçu id →
  JSON sətri) qoyulur; hər consumer yalnız ÖZ sətrini götürür və klientə yalnız
  onu göndərir — heç bir oyunçu başqasının şəxsi məlumatını almır.

Liderlik sırası: ``serializers.LEADERBOARD_ORDER`` (bal ↓, qoşulma ↑, id ↑).

SON sual (sahib 2026-09-30): reveal paketində liderlik cədvəli (``top``/``previous_top`` boş
siyahıdır) və şəxsi sıra (``rank``/``gap_to_next``/``next_nickname``) YOXDUR — nə host-a, nə oyunçulara
(WS, state JSON, HTTP cavabı eyni paketdən qurulur). Yerlər yalnız ``finished`` hadisəsi ilə,
final səhnəsində açılır. Nəticə fazasından sonra liderlər lövhəsi əvəzinə qısa gərginlik fazası
(``final_question``, ``final_suspense_ms``) gəlir.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from django.utils import timezone
from django.utils.translation import pgettext

from apps.live_exam.constants import PLAYER_FINAL_SUSPENSE_SECONDS, PLAYER_LEADERBOARD_SECONDS, PLAYER_RESULT_SECONDS
from apps.live_exam.domain.question_config import resolve_question_config
from apps.live_exam.domain.session import (
    build_reveal_phase_times,
    get_exam_question_ids,
    get_selected_question_ids,
    safe_int,
)
from apps.live_exam.models import LiveAnswer
from apps.live_exam.serializers import answer_choice_ids, question_mode_fields, speed_order_key
from apps.live_exam.typed_answers import build_typed_summary

_ANSWER_FIELDS = (
    "id",
    "player_id",
    "choice_id",
    "choice_ids",
    "text_answer",
    "is_correct",
    "answer_ms",
    "awarded_points",
)
_PLAYER_FIELDS = ("id", "nickname", "avatar_key", "accessory_key", "score", "streak", "best_streak", "created_at")


@dataclass
class Bundle:
    host: dict[str, Any]
    players: dict[str, Any]
    #: oyunçu id (str) → JSON sətri (şəxsi əlavələr). Kanal-qatında ötürülür, klientə yox.
    personal: dict[str, str] = field(default_factory=dict)

    def personal_for(self, player_id) -> dict[str, Any]:
        raw = self.personal.get(str(player_id))
        return json.loads(raw) if raw else {}


def _dumps(value: dict[str, Any]) -> str:
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False)


def leaderboard_key(row: dict[str, Any]) -> tuple:
    return (-safe_int(row.get("score"), 0), row.get("created_at"), safe_int(row.get("id"), 0))


def _leader_row(player: dict[str, Any], *, score: int | None = None) -> dict[str, Any]:
    return {
        "player_id": player["id"],
        "nickname": player["nickname"],
        "avatar_key": player["avatar_key"],
        "accessory_key": player["accessory_key"],
        "score": max(0, safe_int(player["score"] if score is None else score, 0)),
    }


def _players(session) -> list[dict[str, Any]]:
    return list(session.players.values(*_PLAYER_FIELDS))


def _rank_fields(ordered: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    """Hər oyunçu üçün ``rank`` (1-dən, liderlik sırası), yuxarıdakına fərq və ad."""
    fields: dict[int, dict[str, Any]] = {}
    for index, player in enumerate(ordered):
        above = ordered[index - 1] if index > 0 else None
        fields[player["id"]] = {
            "rank": index + 1,
            "gap_to_next": max(0, safe_int(above["score"], 0) - safe_int(player["score"], 0)) if above else 0,
            "next_nickname": above["nickname"] if above else None,
        }
    return fields


def is_final_question(session, question_id) -> bool:
    """Sual oyunun SONUNCU sualıdırmı (seçilmiş sıra; köhnə sessiyada imtahan sırası)."""
    ids = get_selected_question_ids(session) or get_exam_question_ids(session)
    return bool(ids) and safe_int(ids[-1], 0) == safe_int(question_id, 0)


def _timing_fields(session, revealed_at, *, final: bool = False) -> dict[str, Any]:
    leaderboard_starts_at, next_question_at = build_reveal_phase_times(session, revealed_at=revealed_at)
    result_ms = int(PLAYER_RESULT_SECONDS * 1000)
    phase_ms = int(PLAYER_LEADERBOARD_SECONDS * 1000)
    if final:
        # Liderlər lövhəsi yoxdur: nəticədən sonra qısa gərginlik, sonra (auto) final səhnəsi.
        phase_ms = int(PLAYER_FINAL_SUSPENSE_SECONDS * 1000)
        next_question_at = leaderboard_starts_at + timedelta(milliseconds=phase_ms)
    fields = {
        "revealed_at": revealed_at.isoformat(),
        "result_duration_ms": result_ms,
        "leaderboard_duration_ms": phase_ms,
        "transition_duration_ms": result_ms + phase_ms,
        "leaderboard_starts_at": leaderboard_starts_at.isoformat(),
        "next_question_at": next_question_at.isoformat(),
    }
    if final:
        fields["final_question"] = True
        fields["final_suspense_ms"] = phase_ms
    return fields


def _distribution(answers: list[dict[str, Any]]) -> dict[str, Any]:
    counts: dict[int, int] = {}
    for answer in answers:
        seen: set[int] = set()
        for raw_option_id in answer_choice_ids(answer):
            option_id = safe_int(raw_option_id, 0)
            if option_id <= 0 or option_id in seen:
                continue
            counts[option_id] = counts.get(option_id, 0) + 1
            seen.add(option_id)
    return {
        "total_answers": len(answers),
        "counts": [{"option_id": option_id, "count": count} for option_id, count in sorted(counts.items())],
    }


def _error_bundle() -> Bundle:
    payload = {"type": "error", "message": pgettext("live_exam.view.message", "question_not_found")}
    return Bundle(host=dict(payload), players=dict(payload))


def build_reveal_bundle(session, question_id: int, *, revealed_at=None, exam_question=None) -> Bundle:
    from apps.exams.models import ExamQuestion

    if exam_question is None:
        exam_question = (
            ExamQuestion.objects.filter(exam_id=session.exam_id, id=question_id).prefetch_related("options").first()
        )
    if exam_question is None:
        return _error_bundle()

    config = resolve_question_config(session, exam_question)
    revealed_at = revealed_at or session.question_ends_at or timezone.now()
    final = is_final_question(session, question_id)
    answers = list(LiveAnswer.objects.filter(session_id=session.id, question_id=question_id).values(*_ANSWER_FIELDS))
    players = _players(session)
    by_id = {player["id"]: player for player in players}

    answers_by_speed = sorted(answers, key=speed_order_key)
    speed_rank = {answer["id"]: index + 1 for index, answer in enumerate(answers_by_speed)}
    awarded_by_player = {answer["player_id"]: safe_int(answer["awarded_points"], 0) for answer in answers}

    ordered = sorted(players, key=leaderboard_key)
    before = sorted(
        players,
        key=lambda p: (
            -(safe_int(p["score"], 0) - awarded_by_player.get(p["id"], 0)),
            p["created_at"],
            safe_int(p["id"], 0),
        ),
    )

    fastest = next((answer for answer in answers_by_speed if answer["is_correct"]), None)
    fastest_correct = None
    if fastest is not None and fastest["player_id"] in by_id:
        fastest_correct = {
            **{key: value for key, value in _leader_row(by_id[fastest["player_id"]]).items() if key != "score"},
            "answer_ms": safe_int(fastest["answer_ms"], 0),
        }

    results = []
    for answer in sorted(answers, key=lambda a: (-safe_int(a["awarded_points"], 0), *speed_order_key(a)))[:50]:
        player = by_id.get(answer["player_id"])
        if player is None:
            continue
        row = {
            "player_id": player["id"],
            "nickname": player["nickname"],
            "avatar_key": player["avatar_key"],
            "accessory_key": player["accessory_key"],
            "is_correct": bool(answer["is_correct"]),
            "awarded_points": safe_int(answer["awarded_points"], 0),
            "total_score": safe_int(player["score"], 0),
            "answer_ms": safe_int(answer["answer_ms"], 0),
            "answer_rank": speed_rank[answer["id"]],
        }
        if config.is_text:
            row["text_answer"] = answer["text_answer"] or ""
        results.append(row)

    common = {
        "type": "reveal",
        "server_time": timezone.now().isoformat(),
        "question_id": int(question_id),
        "answer_input": config.answer_input,
        "correct_option_ids": list(config.correct_ids),
        "distribution": _distribution(answers),
        **_timing_fields(session, revealed_at, final=final),
    }
    if final:
        # Son sualda liderlik cədvəli GÖNDƏRİLMİR (sürpriz final səhnəsində açılır). Açarlar boş
        # siyahı kimi qalır — keşdəki köhnə JS də çökmədən işləyir.
        common["top"] = []
        common["previous_top"] = []
    else:
        common["top"] = [_leader_row(player) for player in ordered[:10]]
        common["previous_top"] = [
            _leader_row(player, score=safe_int(player["score"], 0) - awarded_by_player.get(player["id"], 0))
            for player in before[:10]
        ]
    if config.is_text:
        common["accepted_answers"] = list(config.accepted)
    if config.is_multi:
        common["multi_scoring"] = config.multi_scoring
        common["total_correct"] = len(config.correct_ids)

    host = {**common, "results": results, "fastest_correct": fastest_correct, "total_players": len(players)}
    if config.is_text:
        host["typed_summary"] = build_typed_summary(
            answers, accepted=config.accepted, typo_tolerance=config.typo_tolerance
        )
        host["typed_total"] = len(answers)
        host["typed_correct"] = sum(1 for answer in answers if answer["is_correct"])

    # Son sualda şəxsi sıra da yoxdur — telefon yerini final səhnəsi ilə birlikdə öyrənir.
    ranks = {} if final else _rank_fields(ordered)
    personal: dict[str, str] = {}
    answers_by_player = {answer["player_id"]: answer for answer in answers}
    for player in players:
        entry = dict(ranks.get(player["id"], {}))
        answer = answers_by_player.get(player["id"])
        if answer is not None:
            mode_fields = question_mode_fields(config, answer_choice_ids(answer), answer["text_answer"])
            entry["player_answer"] = {
                "player_id": player["id"],
                "choice_ids": answer_choice_ids(answer),
                "is_correct": bool(answer["is_correct"]),
                "awarded_points": safe_int(answer["awarded_points"], 0),
                "total_score": safe_int(player["score"], 0),
                "answer_ms": safe_int(answer["answer_ms"], 0),
                "answer_rank": speed_rank[answer["id"]],
                "streak": safe_int(player["streak"], 0),
                **mode_fields,
            }
            entry.update(mode_fields)
        personal[str(player["id"])] = _dumps(entry)

    return Bundle(host=host, players=dict(common), personal=personal)


def pre_question_rank(session, player_id: int, question_id: int | None) -> dict[str, Any]:
    """Açıq sual zamanı oyunçunun sırası — SUALDAN ƏVVƏLKİ ballarla (``previous_top`` kimi).

    Cari ballar cavab anında artdığı üçün canlı sıra reveal-dən əvvəl düzgünlüyü açardı.
    """
    players = _players(session)
    awarded: dict[int, int] = {}
    if question_id:
        for row in LiveAnswer.objects.filter(session_id=session.id, question_id=question_id).values(
            "player_id", "awarded_points"
        ):
            awarded[row["player_id"]] = safe_int(row["awarded_points"], 0)
    before = [{**player, "score": safe_int(player["score"], 0) - awarded.get(player["id"], 0)} for player in players]
    return _rank_fields(sorted(before, key=leaderboard_key)).get(int(player_id), {})


def questions_played(session) -> int:
    """Nəşr olunmuş sual sayı (finişdən sonra da düzgün: ``current_index`` son indeksdir
    və ya «next» ilə bitəndə siyahının uzunluğuna bərabərdir)."""
    selected = get_selected_question_ids(session)
    if not selected:
        return 0
    return min(len(selected), safe_int(session.current_index, 0) + 1)


def build_final_bundle(session, *, finished_at=None, limit: int = 50) -> Bundle:
    """``finished`` paketi: yekun liderlik (eyni sıra qaydası) + statistika (2 sorğu)."""
    resolved_finished_at = finished_at or session.question_ends_at or timezone.now()
    players = _players(session)
    ordered = sorted(players, key=leaderboard_key)
    per_player: dict[int, dict[str, int]] = {}
    answer_count = correct_total = ms_total = 0
    for answer in LiveAnswer.objects.filter(session_id=session.id).values("player_id", "is_correct", "answer_ms"):
        stats = per_player.setdefault(answer["player_id"], {"correct": 0, "answered": 0, "ms": 0})
        stats["answered"] += 1
        stats["correct"] += 1 if answer["is_correct"] else 0
        stats["ms"] += safe_int(answer["answer_ms"], 0)
        answer_count += 1
        correct_total += 1 if answer["is_correct"] else 0
        ms_total += safe_int(answer["answer_ms"], 0)

    def _avg(stats: dict[str, int]) -> int | None:
        return round(stats["ms"] / stats["answered"]) if stats.get("answered") else None

    total_questions = questions_played(session)
    top = []
    for player in ordered[:limit]:
        stats = per_player.get(player["id"], {})
        top.append(
            {
                **_leader_row(player),
                "correct_count": stats.get("correct", 0),
                "answered_count": stats.get("answered", 0),
                "best_streak": safe_int(player["best_streak"], 0),
                "avg_answer_ms": _avg(stats),
            }
        )
    payload = {
        "type": "finished",
        "server_time": timezone.now().isoformat(),
        "top": top,
        "finished_at": resolved_finished_at.isoformat(),
        "total_players": len(players),
        "stats": {
            "total_players": len(players),
            "total_questions": total_questions,
            "answer_count": answer_count,
            "correct_rate": round(correct_total / answer_count, 4) if answer_count else 0.0,
            "avg_answer_ms": round(ms_total / answer_count) if answer_count else None,
        },
    }
    ranks = _rank_fields(ordered)
    personal = {}
    for player in players:
        stats = per_player.get(player["id"], {})
        my_stats = {
            "correct": stats.get("correct", 0),
            "total": total_questions,
            "answered": stats.get("answered", 0),
            "best_streak": safe_int(player["best_streak"], 0),
            "avg_answer_ms": _avg(stats),
        }
        personal[str(player["id"])] = _dumps({"my_stats": my_stats, **ranks[player["id"]]})
    return Bundle(host=payload, players=dict(payload), personal=personal)
