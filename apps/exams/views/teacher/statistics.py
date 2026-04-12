"""
exams/views/teacher/statistics.py
─────────────────────────────────
Teacher-facing advanced statistics page for non-live exam results.
Provides charts, summary cards, group comparisons, filtering, and
AI-powered analytics — matching the visual quality of the Live Exam
session detail page.
"""

from __future__ import annotations

from collections import Counter
from urllib.parse import urlencode

from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import render
from django.urls import reverse

from apps.exams.models import ExamAnswer, ExamAttempt, ExamQuestion, StudentGroup
from apps.exams.services.access_policy import _ensure_teacher
from apps.exams.services.ai_summary import generate_exam_statistics_summary
from apps.exams.views.shared.tenant import get_teacher_exam_or_404
from core.helpers import _safe_same_origin_redirect_path


def _parse_int(raw, default=None):
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


def _build_score_distribution(scores, bucket_limit=6):
    """Build score-distribution labels/counts for chart-friendly rendering."""
    normalized = sorted(max(0, int(s or 0)) for s in scores)
    if not normalized:
        return [], []

    counts = Counter(normalized)
    if len(counts) <= bucket_limit:
        items = sorted(counts.items())
        return [str(s) for s, _ in items], [c for _, c in items]

    mx = normalized[-1]
    bucket_size = max(1, -(-(mx + 1) // bucket_limit))
    labels, vals = [], []
    start = 0
    while start <= mx:
        end = min(mx, start + bucket_size - 1)
        labels.append(f"{start}" if start == end else f"{start}-{end}")
        vals.append(sum(start <= s <= end for s in normalized))
        start = end + 1
    return labels, vals


def _resolve_navigation(request, exam, *, default_section="my-exams"):
    valid = {
        "my-exams",
        "assigned-exams",
        "profile-info",
        "my-courses",
        "assigned-courses",
        "courses",
        "pending-review",
        "review-results",
    }
    section = (request.GET.get("from_section") or "").strip()
    if section not in valid:
        section = default_section

    fallback = f"{reverse('accounts:profile')}?section={section}"
    return_to = _safe_same_origin_redirect_path(request, request.GET.get("return_to")) or fallback
    nav_query = urlencode({"from_section": section, "return_to": return_to})

    exam_detail_url = f"{reverse('exams:teacher_exam_detail', kwargs={'slug': exam.slug})}?{nav_query}"
    results_url = f"{reverse('exams:teacher_exam_results', kwargs={'slug': exam.slug})}?{nav_query}"
    return exam_detail_url, results_url, nav_query


@login_required
def teacher_exam_statistics(request, slug):
    """Advanced statistics page for a standard (non-live) exam."""
    _ensure_teacher(request.user)
    exam = get_teacher_exam_or_404(request, slug=slug)
    exam_detail_url, results_url, nav_query = _resolve_navigation(request, exam)

    # ── Gather base queryset ──────────────────────────────────────────
    attempts = ExamAttempt.objects.filter(exam=exam).select_related("user")

    # ── Filters ───────────────────────────────────────────────────────
    group_id = _parse_int(request.GET.get("group"))
    student_q = (request.GET.get("student") or "").strip()
    date_from = (request.GET.get("date_from") or "").strip()
    date_to = (request.GET.get("date_to") or "").strip()
    status_filter = (request.GET.get("status") or "").strip()
    score_min = _parse_int(request.GET.get("score_min"))
    score_max = _parse_int(request.GET.get("score_max"))
    pass_fail = (request.GET.get("pass_fail") or "").strip()
    block_id = _parse_int(request.GET.get("block"))

    # Groups accessible by this teacher in the tenant
    org = getattr(request, "organization", None)
    teacher_groups = StudentGroup.objects.none()
    if org:
        teacher_groups = StudentGroup.objects.filter(organization=org)

    selected_group = None
    if group_id:
        selected_group = teacher_groups.filter(id=group_id).first()
        if selected_group:
            attempts = attempts.filter(user__in=selected_group.students.all())

    if student_q:
        attempts = attempts.filter(
            Q(user__username__icontains=student_q)
            | Q(user__first_name__icontains=student_q)
            | Q(user__last_name__icontains=student_q)
        )

    if date_from:
        attempts = attempts.filter(started_at__date__gte=date_from)
    if date_to:
        attempts = attempts.filter(started_at__date__lte=date_to)

    allowed_statuses = {"draft", "in_progress", "submitted", "expired"}
    if status_filter in allowed_statuses:
        attempts = attempts.filter(status=status_filter)

    pass_threshold = 50  # percent
    if exam.exam_type == "test":
        if score_min is not None:
            attempts = attempts.filter(correct_count__gte=score_min)
        if score_max is not None:
            attempts = attempts.filter(correct_count__lte=score_max)
    else:
        if score_min is not None:
            attempts = attempts.filter(teacher_score__gte=score_min)
        if score_max is not None:
            attempts = attempts.filter(teacher_score__lte=score_max)

    # ── Compute statistics ────────────────────────────────────────────
    attempts_list = list(attempts.order_by("-started_at"))
    total_attempts = len(attempts_list)

    if exam.exam_type == "test":
        scores = []
        for a in attempts_list:
            total_q = a.correct_count + a.wrong_count
            pct = round(a.correct_count * 100 / total_q, 1) if total_q else 0
            scores.append(pct)
    else:
        scores = [a.teacher_score or 0 for a in attempts_list]

    avg_score = round(sum(scores) / len(scores), 1) if scores else 0
    max_score_val = max(scores) if scores else 0
    min_score_val = min(scores) if scores else 0
    pass_count = sum(1 for s in scores if s >= pass_threshold)
    fail_count = total_attempts - pass_count
    pass_rate = round(pass_count * 100 / total_attempts, 1) if total_attempts else 0

    # Pass/fail filter (applied after computing for chart data)
    if pass_fail == "pass":
        if exam.exam_type == "test":
            filtered = []
            for a in attempts_list:
                total_q = a.correct_count + a.wrong_count
                pct = round(a.correct_count * 100 / total_q, 1) if total_q else 0
                if pct >= pass_threshold:
                    filtered.append(a)
            attempts_list = filtered
        else:
            attempts_list = [a for a in attempts_list if (a.teacher_score or 0) >= pass_threshold]
    elif pass_fail == "fail":
        if exam.exam_type == "test":
            filtered = []
            for a in attempts_list:
                total_q = a.correct_count + a.wrong_count
                pct = round(a.correct_count * 100 / total_q, 1) if total_q else 0
                if pct < pass_threshold:
                    filtered.append(a)
            attempts_list = filtered
        else:
            attempts_list = [a for a in attempts_list if (a.teacher_score or 0) < pass_threshold]

    # Duration stats
    durations = [a.duration_seconds for a in attempts_list if a.duration_seconds]
    avg_duration = round(sum(durations) / len(durations)) if durations else 0

    submitted_count = sum(1 for a in attempts_list if a.status == "submitted")
    expired_count = sum(1 for a in attempts_list if a.status == "expired")
    in_progress_count = sum(1 for a in attempts_list if a.status == "in_progress")

    # Score distribution
    dist_labels, dist_counts = _build_score_distribution(scores)

    # ── Question statistics ───────────────────────────────────────────
    questions = ExamQuestion.objects.filter(exam=exam).order_by("order")
    if block_id:
        questions = questions.filter(block_id=block_id)

    question_stats = []
    for q in questions:
        ans_qs = ExamAnswer.objects.filter(question=q, attempt__exam=exam)
        if attempts_list:
            attempt_ids = [a.id for a in attempts_list]
            ans_qs = ans_qs.filter(attempt_id__in=attempt_ids)
        total_a = ans_qs.count()
        correct_a = ans_qs.filter(is_correct=True).count()
        incorrect_a = total_a - correct_a
        accuracy = round(correct_a * 100 / total_a, 1) if total_a else 0
        question_stats.append(
            {
                "question": q,
                "total_answers": total_a,
                "correct_answers": correct_a,
                "incorrect_answers": incorrect_a,
                "accuracy_percent": accuracy,
            }
        )

    # ── Group comparison ──────────────────────────────────────────────
    compare_group_ids = request.GET.getlist("compare_groups")
    compare_groups_data = []
    if compare_group_ids:
        for gid in compare_group_ids:
            gid_int = _parse_int(gid)
            if not gid_int:
                continue
            grp = teacher_groups.filter(id=gid_int).first()
            if not grp:
                continue
            grp_attempts = ExamAttempt.objects.filter(
                exam=exam,
                user__in=grp.students.all(),
                status__in=["submitted", "expired"],
            )
            if date_from:
                grp_attempts = grp_attempts.filter(started_at__date__gte=date_from)
            if date_to:
                grp_attempts = grp_attempts.filter(started_at__date__lte=date_to)

            grp_list = list(grp_attempts)
            if exam.exam_type == "test":
                grp_scores = []
                for a in grp_list:
                    t = a.correct_count + a.wrong_count
                    grp_scores.append(round(a.correct_count * 100 / t, 1) if t else 0)
            else:
                grp_scores = [a.teacher_score or 0 for a in grp_list]

            grp_avg = round(sum(grp_scores) / len(grp_scores), 1) if grp_scores else 0
            grp_pass = sum(1 for s in grp_scores if s >= pass_threshold)
            grp_pass_rate = round(grp_pass * 100 / len(grp_scores), 1) if grp_scores else 0

            compare_groups_data.append(
                {
                    "id": grp.id,
                    "name": grp.name,
                    "count": len(grp_list),
                    "avg_score": grp_avg,
                    "pass_rate": grp_pass_rate,
                    "max_score": max(grp_scores) if grp_scores else 0,
                    "min_score": min(grp_scores) if grp_scores else 0,
                }
            )

    # ── Question blocks for filter ────────────────────────────────────
    blocks = list(exam.question_blocks.order_by("order"))

    # ── Chart data ────────────────────────────────────────────────────
    # Student scores chart
    student_labels = []
    student_scores_chart = []
    for a in attempts_list[:30]:
        name = a.user.get_full_name() or a.user.username
        student_labels.append(name[:25])
        if exam.exam_type == "test":
            t = a.correct_count + a.wrong_count
            student_scores_chart.append(round(a.correct_count * 100 / t, 1) if t else 0)
        else:
            student_scores_chart.append(a.teacher_score or 0)

    q_labels = [
        (q["question"].text[:40] + "..." if len(q["question"].text) > 40 else q["question"].text)
        for q in question_stats
    ]
    q_accuracy = [q["accuracy_percent"] for q in question_stats]
    q_correct = [q["correct_answers"] for q in question_stats]
    q_incorrect = [q["incorrect_answers"] for q in question_stats]

    chart_data = {
        "student_labels": student_labels,
        "student_scores": student_scores_chart,
        "question_labels": q_labels,
        "question_accuracy": q_accuracy,
        "question_correct": q_correct,
        "question_incorrect": q_incorrect,
        "score_distribution_labels": dist_labels,
        "score_distribution_counts": dist_counts,
        "group_labels": [g["name"] for g in compare_groups_data],
        "group_avg_scores": [g["avg_score"] for g in compare_groups_data],
        "group_pass_rates": [g["pass_rate"] for g in compare_groups_data],
        "group_counts": [g["count"] for g in compare_groups_data],
    }

    # ── AI Summary (AJAX) ─────────────────────────────────────────────
    if request.GET.get("ai_summary") == "1":
        ai_stats = {
            "total_attempts": total_attempts,
            "avg_score": avg_score,
            "max_score": max_score_val,
            "min_score": min_score_val,
            "pass_rate": pass_rate,
            "pass_count": pass_count,
            "fail_count": fail_count,
            "avg_duration_seconds": avg_duration,
            "submitted_count": submitted_count,
            "expired_count": expired_count,
            "question_stats": [
                {
                    "text": qs["question"].text[:80],
                    "accuracy": qs["accuracy_percent"],
                    "total": qs["total_answers"],
                    "correct": qs["correct_answers"],
                }
                for qs in question_stats[:20]
            ],
            "group_comparison": compare_groups_data,
        }
        result = generate_exam_statistics_summary(
            exam_title=exam.title,
            exam_type=exam.get_exam_type_display(),
            stats=ai_stats,
        )
        return JsonResponse(result)

    # ── Context ───────────────────────────────────────────────────────
    filter_query = urlencode(
        {
            k: v
            for k, v in {
                "group": group_id or "",
                "student": student_q,
                "date_from": date_from,
                "date_to": date_to,
                "status": status_filter,
                "score_min": score_min if score_min is not None else "",
                "score_max": score_max if score_max is not None else "",
                "pass_fail": pass_fail,
                "block": block_id or "",
            }.items()
            if v not in ("", None)
        },
        doseq=True,
    )
    if compare_group_ids:
        for gid in compare_group_ids:
            filter_query += f"&compare_groups={gid}"

    return render(
        request,
        "exams/teacher/teacher_exam_statistics.html",
        {
            "exam": exam,
            "exam_detail_url": exam_detail_url,
            "results_url": results_url,
            "nav_query": nav_query,
            # Summary cards
            "total_attempts": total_attempts,
            "avg_score": avg_score,
            "max_score": max_score_val,
            "min_score": min_score_val,
            "pass_rate": pass_rate,
            "pass_count": pass_count,
            "fail_count": fail_count,
            "avg_duration": avg_duration,
            "submitted_count": submitted_count,
            "expired_count": expired_count,
            "in_progress_count": in_progress_count,
            # Charts
            "chart_data": chart_data,
            # Question stats
            "question_stats": question_stats,
            # Groups
            "teacher_groups": teacher_groups,
            "compare_groups_data": compare_groups_data,
            # Blocks
            "blocks": blocks,
            # Current filters
            "f_group": group_id or "",
            "f_student": student_q,
            "f_date_from": date_from,
            "f_date_to": date_to,
            "f_status": status_filter,
            "f_score_min": score_min if score_min is not None else "",
            "f_score_max": score_max if score_max is not None else "",
            "f_pass_fail": pass_fail,
            "f_block": block_id or "",
            "f_compare_groups": compare_group_ids,
            "filter_query": filter_query,
        },
    )
