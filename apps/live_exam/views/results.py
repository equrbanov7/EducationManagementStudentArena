"""
live_exam/views/results.py
──────────────────────────
Teacher-facing views for reviewing live exam session results and statistics.
"""

from __future__ import annotations

import json

from django.contrib.auth.decorators import login_required
from django.db.models import Avg, Count, Max, Q, Sum
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, render

from apps.exams.models import Exam, ExamQuestion
from apps.exams.services.access_policy import is_teacher_user
from apps.live_exam.models import LiveAnswer, LivePlayer, LiveSession
from core.permissions import request_has_permission


def _ensure_teacher_access(request, exam):
    """Raise Http404 unless the user is a teacher with exam.manage permission."""
    if not is_teacher_user(request.user):
        raise Http404
    if not (request_has_permission(request, "exam.manage") or request_has_permission(request, "exam.host")):
        raise Http404
    org = getattr(request, "organization", None)
    if org is None or exam.organization_id != org.id:
        raise Http404


@login_required
def teacher_live_exam_results(request, slug):
    """
    Show all finished live sessions for an exam, with aggregate statistics.
    """
    exam = get_object_or_404(Exam.objects.select_related("organization"), slug=slug)
    _ensure_teacher_access(request, exam)

    sessions = (
        LiveSession.objects.filter(exam=exam, state=LiveSession.STATE_FINISHED)
        .order_by("-created_at")
        .annotate(
            player_count=Count("players", distinct=True),
            answer_count=Count("answers", distinct=True),
            avg_score=Avg("players__score"),
            total_correct=Count("answers", filter=Q(answers__is_correct=True)),
        )
    )

    return render(
        request,
        "liveExam/teacher_live_results.html",
        {
            "exam": exam,
            "sessions": sessions,
        },
    )


@login_required
def teacher_live_session_detail(request, slug, pin):
    """
    Show detailed statistics for a single live exam session.
    Returns JSON for AJAX requests, HTML for normal page loads.
    """
    exam = get_object_or_404(Exam.objects.select_related("organization"), slug=slug)
    _ensure_teacher_access(request, exam)

    session = get_object_or_404(LiveSession, exam=exam, pin=pin, state=LiveSession.STATE_FINISHED)

    players = (
        LivePlayer.objects.filter(session=session)
        .order_by("-score", "created_at")
        .annotate(
            correct_count=Count("answers", filter=Q(answers__is_correct=True)),
            total_answers=Count("answers"),
            total_points=Sum("answers__awarded_points"),
        )
    )

    questions = ExamQuestion.objects.filter(
        exam=exam,
        id__in=session.selected_question_ids or [],
    ).order_by("order")

    question_stats = []
    for q in questions:
        answers = LiveAnswer.objects.filter(session=session, question_id=q.id)
        total = answers.count()
        correct = answers.filter(is_correct=True).count()
        avg_ms = answers.aggregate(avg=Avg("answer_ms"))["avg"] or 0
        question_stats.append(
            {
                "question": q,
                "total_answers": total,
                "correct_answers": correct,
                "incorrect_answers": total - correct,
                "accuracy_percent": (round(correct * 100 / total, 1) if total > 0 else 0),
                "avg_answer_ms": round(avg_ms),
            }
        )

    # Aggregate stats for summary cards
    player_count = players.count()
    total_answers_count = LiveAnswer.objects.filter(session=session).count()
    total_correct_count = LiveAnswer.objects.filter(session=session, is_correct=True).count()
    overall_accuracy = round(total_correct_count * 100 / total_answers_count, 1) if total_answers_count > 0 else 0
    avg_score_val = players.aggregate(avg=Avg("score"))["avg"] or 0
    max_score_val = players.aggregate(mx=Max("score"))["mx"] or 0
    avg_response_ms = LiveAnswer.objects.filter(session=session).aggregate(avg=Avg("answer_ms"))["avg"] or 0

    # JSON data for charts
    chart_data = {
        "player_labels": [p.nickname for p in players],
        "player_scores": [p.score for p in players],
        "question_labels": [
            (qs["question"].text[:40] + "...") if len(qs["question"].text) > 40 else qs["question"].text
            for qs in question_stats
        ],
        "question_accuracy": [qs["accuracy_percent"] for qs in question_stats],
        "question_correct": [qs["correct_answers"] for qs in question_stats],
        "question_incorrect": [qs["incorrect_answers"] for qs in question_stats],
        "question_avg_ms": [qs["avg_answer_ms"] for qs in question_stats],
    }

    if request.headers.get("Accept") == "application/json":
        return JsonResponse(
            {
                "ok": True,
                "pin": session.pin,
                "created_at": session.created_at.isoformat(),
                "player_count": player_count,
                "players": [
                    {
                        "nickname": p.nickname,
                        "score": p.score,
                        "correct_count": p.correct_count,
                        "total_answers": p.total_answers,
                    }
                    for p in players
                ],
                "question_stats": [
                    {
                        "question_id": qs["question"].id,
                        "question_text": qs["question"].text[:120],
                        "total_answers": qs["total_answers"],
                        "correct_answers": qs["correct_answers"],
                        "accuracy_percent": qs["accuracy_percent"],
                        "avg_answer_ms": qs["avg_answer_ms"],
                    }
                    for qs in question_stats
                ],
            }
        )

    return render(
        request,
        "liveExam/teacher_live_session_detail.html",
        {
            "exam": exam,
            "session": session,
            "players": players,
            "question_stats": question_stats,
            "player_count": player_count,
            "total_answers_count": total_answers_count,
            "total_correct_count": total_correct_count,
            "overall_accuracy": overall_accuracy,
            "avg_score": round(avg_score_val),
            "max_score": max_score_val,
            "avg_response_ms": round(avg_response_ms),
            "chart_data_json": json.dumps(chart_data),
        },
    )
