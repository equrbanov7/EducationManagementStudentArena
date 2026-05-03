"""
live_exam/views/results.py
──────────────────────────
Teacher-facing views for reviewing live exam session results and statistics.
"""

from __future__ import annotations

from collections import Counter
from urllib.parse import urlencode

from django.contrib.auth.decorators import login_required
from django.db.models import Avg, Case, Count, IntegerField, Q, Sum, When
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse

from apps.exams.models import Exam, ExamQuestion
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


def _session_question_ids(session: LiveSession) -> list[int]:
    question_ids: list[int] = []
    for raw_id in session.selected_question_ids or []:
        try:
            question_ids.append(int(raw_id))
        except (TypeError, ValueError):
            continue

    if question_ids:
        return question_ids

    fallback_ids: list[int] = []
    for question_id in LiveAnswer.objects.filter(session=session).values_list("question_id", flat=True):
        try:
            normalized_id = int(question_id)
        except (TypeError, ValueError):
            continue
        if normalized_id not in fallback_ids:
            fallback_ids.append(normalized_id)
    return fallback_ids


def _session_questions(exam: Exam, session: LiveSession) -> list[ExamQuestion]:
    question_ids = _session_question_ids(session)
    if not question_ids:
        return []

    ordering = Case(
        *[When(id=question_id, then=position) for position, question_id in enumerate(question_ids)],
        output_field=IntegerField(),
    )
    return list(
        ExamQuestion.objects.filter(exam=exam, id__in=question_ids)
        .prefetch_related("options")
        .annotate(_session_order=ordering)
        .order_by("_session_order", "order", "id")
    )


def _truncate_question_text(value: str | None, limit: int) -> str:
    text = (value or "").strip()
    if len(text) <= limit:
        return text
    return f"{text[:limit]}..."


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

    players = list(
        LivePlayer.objects.filter(session=session)
        .order_by("-score", "created_at")
        .annotate(
            correct_count=Count("answers", filter=Q(answers__is_correct=True)),
            total_answers=Count("answers"),
            total_points=Sum("answers__awarded_points"),
        )
    )

    questions = _session_questions(exam, session)
    question_ids = [question.id for question in questions]

    raw_answers = list(
        LiveAnswer.objects.filter(session=session, question_id__in=question_ids).values(
            "question_id",
            "choice_id",
            "choice_ids",
            "is_correct",
            "answer_ms",
        )
    )

    question_totals: dict[int, dict[str, int]] = {
        question.id: {"total": 0, "correct": 0, "answer_ms_sum": 0} for question in questions
    }
    option_totals: dict[int, Counter[int]] = {question.id: Counter() for question in questions}

    total_answers_count = 0
    total_correct_count = 0
    total_answer_ms = 0
    for answer in raw_answers:
        question_id = int(answer["question_id"])
        stats = question_totals.setdefault(question_id, {"total": 0, "correct": 0, "answer_ms_sum": 0})
        stats["total"] += 1
        total_answers_count += 1

        if answer["is_correct"]:
            stats["correct"] += 1
            total_correct_count += 1

        answer_ms = int(answer["answer_ms"] or 0)
        stats["answer_ms_sum"] += answer_ms
        total_answer_ms += answer_ms

        chosen_option_ids = list(answer["choice_ids"] or [])
        if not chosen_option_ids and answer["choice_id"] is not None:
            chosen_option_ids = [answer["choice_id"]]

        seen_option_ids: set[int] = set()
        for raw_option_id in chosen_option_ids:
            try:
                option_id = int(raw_option_id)
            except (TypeError, ValueError):
                continue
            if option_id <= 0 or option_id in seen_option_ids:
                continue
            option_totals.setdefault(question_id, Counter())[option_id] += 1
            seen_option_ids.add(option_id)

    question_stats = []
    per_question_option_stats = []
    for q in questions:
        stats = question_totals.get(q.id, {"total": 0, "correct": 0, "answer_ms_sum": 0})
        total = int(stats["total"] or 0)
        correct = int(stats["correct"] or 0)
        avg_ms = round(stats["answer_ms_sum"] / total) if total > 0 else 0
        question_stats.append(
            {
                "question": q,
                "total_answers": total,
                "correct_answers": correct,
                "incorrect_answers": total - correct,
                "accuracy_percent": (round(correct * 100 / total, 1) if total > 0 else 0),
                "avg_answer_ms": avg_ms,
            }
        )

        # Per-question option distribution for chart
        options = sorted(q.options.all(), key=lambda option: (option.label or "", option.id))
        option_labels = []
        option_counts = []
        option_colors = []
        for opt in options:
            label_text = opt.label or _truncate_question_text(opt.text, 20)
            option_labels.append(label_text)
            option_counts.append(int(option_totals.get(q.id, Counter()).get(opt.id, 0)))
            option_colors.append("#059669" if opt.is_correct else "#6b7280")
        per_question_option_stats.append(
            {
                "question_text": _truncate_question_text(q.text, 40),
                "labels": option_labels,
                "counts": option_counts,
                "colors": option_colors,
            }
        )

    # Aggregate stats for summary cards
    player_count = len(players)
    overall_accuracy = round(total_correct_count * 100 / total_answers_count, 1) if total_answers_count > 0 else 0
    player_scores = [int(player.score or 0) for player in players]
    avg_score_val = (sum(player_scores) / player_count) if player_count else 0
    max_score_val = max(player_scores, default=0)
    avg_response_ms = round(total_answer_ms / total_answers_count) if total_answers_count > 0 else 0

    score_distribution_labels, score_distribution_counts = _build_score_distribution(player_scores)

    # JSON-safe data for charts
    chart_data = {
        "player_labels": [player.nickname for player in players],
        "player_scores": player_scores,
        "question_labels": [_truncate_question_text(qs["question"].text, 40) for qs in question_stats],
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
            "avg_response_ms": avg_response_ms,
            "question_stats": [
                {
                    "text": _truncate_question_text(qs["question"].text, 80),
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
                        "question_text": _truncate_question_text(qs["question"].text, 120),
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
            "avg_response_ms": avg_response_ms,
            "chart_data": chart_data,
            "live_results_url": live_results_url,
            "live_results_navigation_query": navigation_query,
        },
    )
