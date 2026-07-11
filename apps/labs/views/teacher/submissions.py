"""Labs — müəllim submission idarəetməsi və qiymətləndirmə (F2, 2026-07-02)."""

import logging
import os
from datetime import datetime
from decimal import Decimal
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import pgettext
from django.views.decorators.http import require_POST

from apps.courses.models import CourseMembership
from core.helpers import REVIEW_EDIT_LOCK_WINDOW, _safe_same_origin_redirect_path
from core.permissions import request_has_permission

from ...lab_access import can_teacher_access_lab, resolve_identity_window, resolve_recheck_window
from ...lab_grading_service import format_decimal_input, grade_lab_answer, grade_lab_submission, parse_decimal_input
from ...models import LabAnswer, LabSubmission
from ..shared._helpers import _get_tenant_lab_or_404, _get_tenant_submission_or_404, _lab_back_url

logger = logging.getLogger(__name__)


def _parse_filter_date(raw_value):
    raw_date = (raw_value or "").strip()
    if not raw_date:
        return "", None
    try:
        return raw_date, datetime.strptime(raw_date, "%Y-%m-%d").date()
    except ValueError:
        return "", None


def _can_delete_submissions(request):
    return request_has_permission(request, "lab.delete") or request_has_permission(request, "course.delete")


def _raise_lab_teacher_access_denied():
    raise PermissionDenied(pgettext("labs.view.permission", "permission_denied"))


@login_required
def lab_submissions(request, pk):
    """Lab cavablarını göstər - müəllim üçün"""
    lab = _get_tenant_lab_or_404(request, pk)

    if not can_teacher_access_lab(lab, request.user):
        _raise_lab_teacher_access_denied()

    # Bütün submission-lar
    submissions = LabSubmission.objects.filter(assignment__lab=lab).select_related(
        "assignment__student",
        "assignment__lab__course__organization",
    )

    # Qrupları al - CourseMembership-dən

    memberships = (
        CourseMembership.objects.filter(course=lab.course, role="student")
        .exclude(group_name__isnull=True)
        .exclude(group_name="")
    )

    groups = sorted(memberships.values_list("group_name", flat=True).distinct())

    # Filters
    search_query = (request.GET.get("q") or "").strip()
    if search_query:
        submissions = submissions.filter(
            Q(assignment__student__username__icontains=search_query)
            | Q(assignment__student__first_name__icontains=search_query)
            | Q(assignment__student__last_name__icontains=search_query)
            | Q(assignment__student__email__icontains=search_query)
            | Q(submission_text__icontains=search_query)
            | Q(submission_link__icontains=search_query)
        )

    status_filter = (request.GET.get("status") or "all").strip().lower()
    allowed_status_filters = {"all", "submitted", "late", "graded", "returned"}
    if status_filter not in allowed_status_filters:
        status_filter = "all"

    group_filter = (request.GET.get("group") or "all").strip()
    if group_filter != "all" and group_filter not in groups:
        group_filter = "all"
    date_from_raw, date_from = _parse_filter_date(request.GET.get("date_from"))
    date_to_raw, date_to = _parse_filter_date(request.GET.get("date_to"))

    if status_filter != "all":
        submissions = submissions.filter(status=status_filter)

    if group_filter != "all":
        # Qrup filter - membership üzərindən
        student_ids = memberships.filter(group_name=group_filter).values_list("user_id", flat=True)
        submissions = submissions.filter(assignment__student_id__in=student_ids)
    if date_from:
        submissions = submissions.filter(submitted_at__date__gte=date_from)
    if date_to:
        submissions = submissions.filter(submitted_at__date__lte=date_to)

    submissions = submissions.order_by("-submitted_at")
    page_obj = Paginator(submissions, 12).get_page(request.GET.get("page"))
    submissions_page = list(page_obj.object_list)

    current_time = timezone.now()
    for submission in submissions_page:
        in_recheck_window, seconds_left = resolve_recheck_window(submission, current_time=current_time)
        is_identity_hidden, identity_window_seconds_left = resolve_identity_window(
            submission, current_time=current_time
        )
        submission.in_recheck_window = in_recheck_window
        submission.review_window_seconds_left = seconds_left
        submission.identity_window_seconds_left = identity_window_seconds_left
        submission.can_view_student_identity = not is_identity_hidden
        submission.student_display_name = (
            submission.assignment.student.get_full_name() or submission.assignment.student.username
            if submission.can_view_student_identity
            else pgettext("labs.view.label", "anonymous_student")
        )
        submission.student_display_email = (
            submission.assignment.student.email
            if submission.can_view_student_identity
            else pgettext("labs.view.label", "anonymous_view")
        )

    # Statistika
    all_submissions = LabSubmission.objects.filter(assignment__lab=lab)
    stats = {
        "total": all_submissions.count(),
        "pending": all_submissions.filter(status="submitted").count(),
        "graded": all_submissions.filter(status="graded").count(),
        "late": all_submissions.filter(status="late").count(),
    }

    # Hər submission üçün student-in qrup adını əlavə et
    student_groups = {}
    for m in memberships:
        student_groups[m.user_id] = m.group_name

    pagination_query = urlencode(
        {
            key: value
            for key, value in {
                "q": search_query,
                "status": status_filter,
                "group": group_filter,
                "date_from": date_from_raw,
                "date_to": date_to_raw,
                "from_section": (request.GET.get("from_section") or "").strip(),
                "return_to": (request.GET.get("return_to") or "").strip(),
            }.items()
            if value not in ("", None, "all")
        }
    )

    context = {
        "lab": lab,
        "submissions": submissions_page,
        "page_obj": page_obj,
        "groups": groups,
        "search_query": search_query,
        "status_filter": status_filter,
        "group_filter": group_filter,
        "date_from": date_from_raw,
        "date_to": date_to_raw,
        "stats": stats,
        "student_groups": student_groups,
        "back_url": _lab_back_url(request, lab),
        "pagination_query": pagination_query,
        "can_delete_submissions": _can_delete_submissions(request),
    }

    return render(request, "labs/lab_submissions.html", context)


@login_required
@require_POST
def delete_submissions(request, pk):
    lab = _get_tenant_lab_or_404(request, pk)

    if not can_teacher_access_lab(lab, request.user):
        _raise_lab_teacher_access_denied()

    if not _can_delete_submissions(request):
        messages.error(request, pgettext("labs.view.permission", "permission_denied"))
        return redirect(reverse("labs:lab_submissions", kwargs={"pk": lab.id}))

    redirect_url = _safe_same_origin_redirect_path(request, request.POST.get("next"))
    if not redirect_url:
        params = {}
        from_section = (request.POST.get("from_section") or "").strip()
        return_to = _safe_same_origin_redirect_path(request, request.POST.get("return_to"))
        if from_section:
            params["from_section"] = from_section
        if return_to:
            params["return_to"] = return_to
        redirect_url = reverse("labs:lab_submissions", kwargs={"pk": lab.id})
        if params:
            redirect_url = f"{redirect_url}?{urlencode(params)}"

    raw_ids = request.POST.getlist("submission_ids")
    single_submission_id = (request.POST.get("submission_id") or "").strip()
    if single_submission_id:
        raw_ids.append(single_submission_id)

    submission_ids = sorted({int(raw_id) for raw_id in raw_ids if str(raw_id).isdigit()})
    if not submission_ids:
        messages.warning(request, pgettext("labs.view.message", "bulk_delete_select_at_least_one"))
        return redirect(redirect_url)

    submissions_qs = LabSubmission.objects.filter(assignment__lab=lab, id__in=submission_ids)
    deleted_count = submissions_qs.count()
    if deleted_count == 0:
        messages.warning(request, pgettext("labs.view.message", "bulk_delete_none_found"))
        return redirect(redirect_url)

    submissions_qs.delete()
    messages.success(request, pgettext("labs.view.message", "bulk_delete_success").format(count=deleted_count))
    return redirect(redirect_url)


@login_required
def grade_submission_page(request, pk):
    """Qiymətləndirmə səhifəsi"""
    submission = _get_tenant_submission_or_404(request, pk)
    lab = submission.assignment.lab

    if not can_teacher_access_lab(lab, request.user):
        _raise_lab_teacher_access_denied()

    if not request_has_permission(request, "grade.input"):
        messages.error(request, pgettext("labs.view.permission", "permission_denied"))
        return redirect("labs:lab_submissions", pk=lab.id)

    is_recheck_window, review_window_seconds_left = resolve_recheck_window(submission)
    is_identity_hidden, identity_window_seconds_left = resolve_identity_window(submission)
    is_pregrade_anonymous_window = is_identity_hidden and not is_recheck_window
    is_locked = submission.status == "graded" and submission.graded_at and not is_recheck_window

    # Bu cəhdin cavablarını al
    try:
        answers = (
            LabAnswer.objects.filter(
                lab=lab,
                student=submission.assignment.student,
                attempt_number=submission.attempt_number,
                is_draft=False,
            )
            .select_related("question")
            .order_by("question__block__order", "question__question_number")
        )
        if not answers.exists():
            answers = (
                LabAnswer.objects.filter(
                    lab=lab,
                    student=submission.assignment.student,
                    submission=submission,
                    is_draft=False,
                )
                .select_related("question")
                .order_by("question__block__order", "question__question_number")
            )
    except Exception:
        answers = (
            LabAnswer.objects.filter(lab=lab, student=submission.assignment.student, is_draft=False)
            .select_related("question")
            .order_by("question__block__order", "question__question_number")
        )

    if request.method == "POST":
        if is_locked:
            messages.error(request, pgettext("labs.view.message", "grading_window_expired"))
            return redirect(request.path)

        try:
            # All per-question scores and the final score commit together. The
            # grading services re-read each row with SELECT ... FOR UPDATE so a
            # concurrent reviewer cannot silently overwrite a partial result.
            with transaction.atomic():
                auto_total = Decimal("0")
                has_posted_answer_scores = False
                for answer in answers:
                    raw_score = (request.POST.get(f"answer_score_{answer.id}", "") or "").strip()
                    if raw_score == "":
                        val = None
                    else:
                        has_posted_answer_scores = True
                        val = parse_decimal_input(raw_score)
                        if val is None:
                            val = Decimal("0")
                    graded_answer = grade_lab_answer(answer, val)
                    if graded_answer.score is not None:
                        auto_total += graded_answer.score

                score_raw = (request.POST.get("score", "") or "").strip()
                entered_total = parse_decimal_input(score_raw)
                use_manual_total = request.POST.get("use_manual_total") == "1"
                should_use_manual_total = entered_total is not None and (
                    use_manual_total or not has_posted_answer_scores or entered_total != auto_total
                )
                final_score = entered_total if should_use_manual_total else auto_total

                submission = grade_lab_submission(
                    submission,
                    final_score,
                    request.POST.get("feedback", ""),
                    request.user,
                    refresh_graded_at=False,
                )

            messages.success(request, pgettext("labs.view.message", "grade_saved_successfully"))
            return redirect("labs:lab_submissions", pk=lab.id)
        except Exception:
            logger.exception("Unexpected error while saving grades")
            messages.error(request, pgettext("labs.view.message", "unexpected_error_try_again"))

    has_answer_scores = any(answer.score is not None for answer in answers)
    auto_total_decimal = sum(
        (answer.score if answer.score is not None else Decimal("0") for answer in answers),
        Decimal("0"),
    )
    auto_total_score = float(auto_total_decimal) if answers else 0
    use_manual_total_initial = False
    if submission.score is not None:
        submission_score_decimal = Decimal(str(submission.score))
        use_manual_total_initial = (not has_answer_scores) or submission_score_decimal != auto_total_decimal

    for answer in answers:
        answer.score_input_value = format_decimal_input(answer.score)

    submission_score_input_value = format_decimal_input(submission.score)
    auto_total_score_input_value = format_decimal_input(auto_total_decimal)

    student_display = (
        pgettext("labs.view.label", "anonymous_student")
        if is_identity_hidden
        else (submission.assignment.student.get_full_name() or submission.assignment.student.username)
    )

    context = {
        "submission": submission,
        "lab": lab,
        "answers": answers,
        "auto_total_score": auto_total_score,
        "student_display": student_display,
        "is_recheck_window": is_recheck_window,
        "is_pregrade_anonymous_window": is_pregrade_anonymous_window,
        "is_locked": is_locked,
        "use_manual_total_initial": use_manual_total_initial,
        "submission_score_input_value": submission_score_input_value,
        "auto_total_score_input_value": auto_total_score_input_value,
        "review_window_seconds_left": review_window_seconds_left,
        "identity_window_seconds_left": identity_window_seconds_left,
        "review_window_minutes": int(REVIEW_EDIT_LOCK_WINDOW.total_seconds() // 60),
    }

    return render(request, "labs/grade_submission.html", context)


@login_required
def submission_answers(request, pk):
    """Submission-un cavablarını JSON olaraq qaytar"""
    submission = _get_tenant_submission_or_404(request, pk)

    if not can_teacher_access_lab(submission.assignment.lab, request.user):
        return JsonResponse(
            {"success": False, "error": pgettext("labs.view.permission", "permission_denied")}, status=403
        )

    # Bu submission-a aid cavabları al
    answers = (
        LabAnswer.objects.filter(
            lab=submission.assignment.lab,
            student=submission.assignment.student,
            is_draft=False,
        )
        .select_related("question")
        .order_by("question__block__order", "question__question_number")
    )

    answers_data = []
    for ans in answers:
        answers_data.append(
            {
                "question": ans.question.question_text,
                "answer": ans.answer or "",
                "file_url": ans.answer_file.url if ans.answer_file else None,
                "file_name": (os.path.basename(ans.answer_file.name) if ans.answer_file else None),
                "score": float(ans.score) if ans.score else None,
            }
        )

    return JsonResponse({"success": True, "answers": answers_data})
