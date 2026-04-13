"""
live_exam/views/results.py
──────────────────────────
Teacher-facing views for reviewing live exam session results and statistics.
"""

from __future__ import annotations

from collections import Counter
from urllib.parse import urlencode

from django.contrib.auth.decorators import login_required
from django.db.models import Avg, Count, Max, Q, Sum
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse

from apps.exams.models import Exam, ExamQuestion
from apps.exams.domain.question_bank import ExamQuestionOption
from apps.exams.services.access_policy import is_teacher_user
from apps.exams.services.ai_summary import generate_exam_statistics_summary
from apps.live_exam.models import LiveAnswer, LivePlayer, LiveSession
from core.helpers import _safe_same_origin_redirect_path
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


def _build_score_distribution(scores, bucket_limit=6):
    """Build score-distribution labels/counts for chart-friendly rendering."""
    normalized_scores = sorted(max(0, int(score or 0)) for score in scores)
    if not normalized_scores:
        return [], []

    score_counts = Counter(normalized_scores)
    if len(score_counts) <= bucket_limit:
        items = sorted(score_counts.items())
        return [str(score) for score, _ in items], [count for _, count in items]

    max_score = normalized_scores[-1]
    bucket_size = max(1, -(-(max_score + 1) // bucket_limit))
    labels = []
    counts = []
    start = 0
    while start <= max_score:
        end = min(max_score, start + bucket_size - 1)
        labels.append(f"{start}" if start == end else f"{start}-{end}")
        counts.append(sum(start <= score <= end for score in normalized_scores))
        start = end + 1

    return labels, counts


def _resolve_exam_navigation(request, exam, *, default_section="my-exams"):
    valid_profile_sections = {
        "my-exams",
        "assigned-exams",
        "profile-info",
        "my-courses",
        "assigned-courses",
        "courses",
        "pending-review",
        "review-results",
    }
    requested_profile_section = (request.GET.get("from_section") or "").strip()
    if requested_profile_section not in valid_profile_sections:
        requested_profile_section = default_section

    fallback_return_url = f"{reverse('accounts:profile')}?section={requested_profile_section}"
    return_to = _safe_same_origin_redirect_path(request, request.GET.get("return_to")) or fallback_return_url
    navigation_query = urlencode(
        {
            "from_section": requested_profile_section,
            "return_to": return_to,
        }
    )
    exam_detail_url = f"{reverse('exams:teacher_exam_detail', kwargs={'slug': exam.slug})}?{navigation_query}"
    results_url = f"{reverse('liveExam:teacher_live_results', kwargs={'slug': exam.slug})}?{navigation_query}"
    return exam_detail_url, results_url, navigation_query


@login_required
def teacher_live_exam_results(request, slug):
    """
    Show all finished live sessions for an exam, with aggregate statistics.
    """
    exam = get_object_or_404(Exam.objects.select_related("organization"), slug=slug)
    _ensure_teacher_access(request, exam)
    exam_detail_url, _results_url, navigation_query = _resolve_exam_navigation(request, exam)

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
            "exam_detail_url": exam_detail_url,
            "live_results_navigation_query": navigation_query,
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
    _exam_detail_url, live_results_url, navigation_query = _resolve_exam_navigation(request, exam)

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
    per_question_option_stats = []
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

        # Per-question option distribution for chart
        options = ExamQuestionOption.objects.filter(question=q).order_by("label", "id")
        option_labels = []
        option_counts = []
        option_colors = []
        for opt in options:
            label_text = opt.label or opt.text[:20]
            option_labels.append(label_text)
            # Count answers that chose this option (via choice_id or choice_ids)
            chosen_count = answers.filter(
                Q(choice_id=opt.id) | Q(choice_ids__contains=[opt.id])
            ).count()
            option_counts.append(chosen_count)
            option_colors.append("#059669" if opt.is_correct else "#6b7280")
        per_question_option_stats.append(
            {
                "question_text": (q.text[:40] + "...") if len(q.text) > 40 else q.text,
                "labels": option_labels,
                "counts": option_counts,
                "colors": option_colors,
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

    player_scores = [int(p.score or 0) for p in players]
    score_distribution_labels, score_distribution_counts = _build_score_distribution(player_scores)

    # JSON-safe data for charts
    chart_data = {
        "player_labels": [p.nickname for p in players],
        "player_scores": player_scores,
        "question_labels": [
            (qs["question"].text[:40] + "...") if len(qs["question"].text) > 40 else qs["question"].text
            for qs in question_stats
        ],
        "question_accuracy": [qs["accuracy_percent"] for qs in question_stats],
        "question_correct": [qs["correct_answers"] for qs in question_stats],
        "question_incorrect": [qs["incorrect_answers"] for qs in question_stats],
        "question_avg_ms": [qs["avg_answer_ms"] for qs in question_stats],
        "score_distribution_labels": score_distribution_labels,
        "score_distribution_counts": score_distribution_counts,
        "per_question_option_stats": per_question_option_stats,
    }

    # ── AI Summary (AJAX) ─────────────────────────────────────────────
    if request.GET.get("ai_summary") == "1":
        ai_stats = {
            "player_count": player_count,
            "total_answers": total_answers_count,
            "total_correct": total_correct_count,
            "overall_accuracy": overall_accuracy,
            "avg_score": round(avg_score_val),
            "max_score": max_score_val,
            "avg_response_ms": round(avg_response_ms),
            "question_stats": [
                {
                    "text": qs["question"].text[:80],
                    "accuracy": qs["accuracy_percent"],
                    "total": qs["total_answers"],
                    "correct": qs["correct_answers"],
                    "avg_ms": qs["avg_answer_ms"],
                }
                for qs in question_stats[:20]
            ],
            "players": [{"nickname": p.nickname, "score": p.score, "correct": p.correct_count} for p in players],
        }
        result = generate_exam_statistics_summary(
            exam_title=exam.title,
            exam_type="Live Exam",
            stats=ai_stats,
            user_id=request.user.pk,
        )
        return JsonResponse(result)

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
            "chart_data": chart_data,
            "live_results_url": live_results_url,
            "live_results_navigation_query": navigation_query,
        },
    )
