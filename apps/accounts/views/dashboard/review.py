"""
Teacher review views: pending review and review results.
"""

from decimal import Decimal, InvalidOperation
from pathlib import PurePosixPath

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import pgettext_lazy

from apps.assignments.models import Submission
from apps.courses.models import Course
from apps.labs.models import LabAnswer, LabSubmission
from apps.projects.models import ProjectSubmission
from apps.task_submission_core.review import resolve_identity_window as resolve_submission_identity_window

from .._helpers import (
    REVIEW_EDIT_WINDOW,
    REVIEW_EDIT_WINDOW_MINUTES,
    _extract_assignment_attachments,
    _is_review_window_closed,
    _normalize_review_result_item_type,
    _parse_decimal_score,
    _pending_review_type_label,
    _render_profile_section,
    _review_window_seconds_left,
    _role_capabilities,
    _safe_same_origin_redirect_path,
    _tenant_scoped_courses,
)

User = get_user_model()


def _resolve_pending_review_identity(*, reviewable, student, now=None):
    is_hidden, seconds_left = resolve_submission_identity_window(
        reviewable,
        current_time=now,
    )
    student_display = "Anonim tələbə" if is_hidden else (student.get_full_name() or student.username)
    return student_display, is_hidden, seconds_left


def _format_decimal_input(value):
    if value is None or value == "":
        return ""
    formatted = format(Decimal(str(value)), "f")
    if "." in formatted:
        formatted = formatted.rstrip("0").rstrip(".")
    return formatted or "0"


@login_required
def pending_review(request):
    """Teacher review queue across exams, assignments, labs, and projects."""
    profile = getattr(request.user, "profile", None)
    capabilities = _role_capabilities(request.user, profile)
    if not capabilities["can_review_submissions"]:
        messages.error(request, pgettext_lazy("accounts.pending_review.message", "teacher_only"))
        return redirect("accounts:profile")

    return _render_profile_section(request, "pending-review")


@login_required
def pending_review_detail(request, item_type, item_id):
    """Teacher-facing grading page for pending assignment/project/lab submissions."""
    profile = getattr(request.user, "profile", None)
    capabilities = _role_capabilities(request.user, profile)
    if not capabilities["can_review_submissions"]:
        messages.error(request, pgettext_lazy("accounts.pending_review.message", "teacher_only"))
        return redirect("accounts:profile")

    normalized_type = _normalize_review_result_item_type(item_type)
    if not normalized_type:
        return redirect(f"{reverse('accounts:profile')}?section=pending-review")

    default_back_url = f"{reverse('accounts:profile')}?section=pending-review"
    back_url = _safe_same_origin_redirect_path(
        request,
        request.GET.get("return_to") or request.GET.get("next"),
    )
    if not back_url:
        back_url = default_back_url

    teacher_courses = _tenant_scoped_courses(request, Course.objects.filter(owner=request.user))
    redirect_url = request.get_full_path()

    base_context = {
        "item_type": normalized_type,
        "item_type_label": _pending_review_type_label(normalized_type),
        "back_url": back_url,
        "review_window_minutes": REVIEW_EDIT_WINDOW_MINUTES,
    }

    if normalized_type == "assignment":
        submission = get_object_or_404(
            Submission.objects.select_related(
                "assignment",
                "assignment__course",
                "assignment__course__organization",
                "user",
                "graded_by",
            ),
            id=item_id,
            assignment__course__in=teacher_courses,
        )
        max_score = Decimal(str(submission.assignment.max_score or 100))
        is_locked = _is_review_window_closed(submission.graded_at)
        is_recheck_window = bool(submission.status == "graded" and submission.graded_at and not is_locked)
        student_display, is_identity_hidden, identity_window_seconds_left = _resolve_pending_review_identity(
            reviewable=submission,
            student=submission.user,
        )

        if request.method == "POST":
            if is_locked:
                messages.error(request, "Bu cavab üçün yoxlama müddəti bitib. Artıq bal dəyişdirilə bilməz.")
                return redirect(redirect_url)

            feedback = (request.POST.get("feedback") or "").strip()
            try:
                score = _parse_decimal_score(request.POST.get("score"))
            except InvalidOperation:
                messages.error(request, "Bal düzgün rəqəm formatında olmalıdır.")
                return redirect(redirect_url)

            if score < 0 or score > max_score:
                messages.error(request, f"Bal 0 və {max_score} aralığında olmalıdır.")
                return redirect(redirect_url)

            submission.grade = score
            submission.feedback = feedback
            submission.status = "graded"
            submission.graded_by = request.user
            if not submission.graded_at:
                submission.graded_at = timezone.now()
            submission.save(update_fields=["grade", "feedback", "status", "graded_by", "graded_at"])
            messages.success(
                request,
                f"Qiymət saxlanıldı. {REVIEW_EDIT_WINDOW_MINUTES} dəqiqə ərzində yenidən yoxlaya bilərsiniz.",
            )
            return redirect(redirect_url)

        context = {
            **base_context,
            "item_title": submission.assignment.title,
            "course_title": submission.assignment.course.title,
            "student_display": student_display,
            "status_display": submission.get_status_display(),
            "submitted_at": submission.submitted_at,
            "graded_at": submission.graded_at,
            "feedback": submission.feedback,
            "content_text": submission.content,
            "attachments": _extract_assignment_attachments(submission),
            "current_score": submission.grade,
            "current_score_input_value": _format_decimal_input(submission.grade),
            "max_score": max_score,
            "is_locked": is_locked,
            "is_recheck_window": is_recheck_window,
            "is_identity_hidden": is_identity_hidden,
            "is_pregrade_anonymous_window": is_identity_hidden and not is_recheck_window,
            "review_window_seconds_left": _review_window_seconds_left(submission.graded_at),
            "identity_window_seconds_left": identity_window_seconds_left,
            "review_deadline": submission.graded_at + REVIEW_EDIT_WINDOW if submission.graded_at else None,
        }
        return render(request, "accounts/pending_review_detail.html", context)

    if normalized_type == "project":
        submission = get_object_or_404(
            ProjectSubmission.objects.select_related(
                "project",
                "project__course",
                "project__course__organization",
                "student",
                "graded_by",
            ),
            id=item_id,
            project__course__in=teacher_courses,
        )
        max_score = Decimal(str(submission.project.max_score or 100))
        is_locked = _is_review_window_closed(submission.graded_at)
        is_recheck_window = bool(submission.status == "graded" and submission.graded_at and not is_locked)
        student_display, is_identity_hidden, identity_window_seconds_left = _resolve_pending_review_identity(
            reviewable=submission,
            student=submission.student,
        )

        if request.method == "POST":
            if is_locked:
                messages.error(request, "Bu cavab üçün yoxlama müddəti bitib. Artıq bal dəyişdirilə bilməz.")
                return redirect(redirect_url)

            feedback = (request.POST.get("feedback") or "").strip()
            try:
                score = _parse_decimal_score(request.POST.get("score"))
            except InvalidOperation:
                messages.error(request, "Bal düzgün rəqəm formatında olmalıdır.")
                return redirect(redirect_url)

            if score < 0 or score > max_score:
                messages.error(request, f"Bal 0 və {max_score} aralığında olmalıdır.")
                return redirect(redirect_url)

            submission.grade = score
            submission.feedback = feedback
            submission.status = "graded"
            submission.graded_by = request.user
            if not submission.graded_at:
                submission.graded_at = timezone.now()
            submission.save(update_fields=["grade", "feedback", "status", "graded_by", "graded_at"])
            messages.success(
                request,
                f"Qiymət saxlanıldı. {REVIEW_EDIT_WINDOW_MINUTES} dəqiqə ərzində yenidən yoxlaya bilərsiniz.",
            )
            return redirect(redirect_url)

        attachments = []
        if submission.file:
            attachments.append({"name": PurePosixPath(submission.file.name).name, "url": submission.file.url})

        context = {
            **base_context,
            "item_title": submission.project.title,
            "course_title": submission.project.course.title,
            "student_display": student_display,
            "status_display": submission.get_status_display(),
            "submitted_at": submission.submitted_at,
            "graded_at": submission.graded_at,
            "feedback": submission.feedback,
            "content_text": submission.content,
            "attachments": attachments,
            "current_score": submission.grade,
            "current_score_input_value": _format_decimal_input(submission.grade),
            "max_score": max_score,
            "is_locked": is_locked,
            "is_recheck_window": is_recheck_window,
            "is_identity_hidden": is_identity_hidden,
            "is_pregrade_anonymous_window": is_identity_hidden and not is_recheck_window,
            "review_window_seconds_left": _review_window_seconds_left(submission.graded_at),
            "identity_window_seconds_left": identity_window_seconds_left,
            "review_deadline": submission.graded_at + REVIEW_EDIT_WINDOW if submission.graded_at else None,
        }
        return render(request, "accounts/pending_review_detail.html", context)

    submission = get_object_or_404(
        LabSubmission.objects.select_related(
            "assignment",
            "assignment__lab",
            "assignment__lab__course",
            "assignment__lab__course__organization",
            "assignment__student",
        ),
        id=item_id,
        assignment__lab__course__in=teacher_courses,
    )
    max_score = Decimal(str(submission.assignment.lab.max_score or 100))
    is_locked = _is_review_window_closed(submission.graded_at)
    is_recheck_window = bool(submission.status == "graded" and submission.graded_at and not is_locked)
    student_display, is_identity_hidden, identity_window_seconds_left = _resolve_pending_review_identity(
        reviewable=submission,
        student=submission.assignment.student,
    )

    lab_answers = list(
        submission.answers.select_related("question", "question__block").order_by(
            "question__block__order",
            "question__question_number",
        )
    )
    if not lab_answers:
        lab_answers = list(
            LabAnswer.objects.filter(
                lab=submission.assignment.lab,
                student=submission.assignment.student,
                attempt_number=submission.attempt_number,
                is_draft=False,
            )
            .select_related("question", "question__block")
            .order_by("question__block__order", "question__question_number")
        )

    if request.method == "POST":
        if is_locked:
            messages.error(request, "Bu cavab üçün yoxlama müddəti bitib. Artıq bal dəyişdirilə bilməz.")
            return redirect(redirect_url)

        feedback = (request.POST.get("feedback") or "").strip()
        try:
            auto_total = Decimal("0")
            has_posted_answer_scores = False
            for answer in lab_answers:
                raw_answer_score = (request.POST.get(f"answer_score_{answer.id}") or "").strip()
                if not raw_answer_score:
                    answer.score = None
                else:
                    has_posted_answer_scores = True
                    answer_score = _parse_decimal_score(raw_answer_score)
                    if answer_score < 0:
                        answer_score = Decimal("0")
                    question_max = Decimal(str(answer.question.points or 0))
                    if question_max > 0 and answer_score > question_max:
                        answer_score = question_max
                    answer.score = answer_score
                    auto_total += answer_score
                answer.save(update_fields=["score", "submitted_at"])

            entered_total = _parse_decimal_score(request.POST.get("score"))
        except InvalidOperation:
            messages.error(request, "Bal düzgün rəqəm formatında olmalıdır.")
            return redirect(redirect_url)

        score = entered_total if (not has_posted_answer_scores or entered_total != auto_total) else auto_total

        if score < 0 or score > max_score:
            messages.error(request, f"Bal 0 və {max_score} aralığında olmalıdır.")
            return redirect(redirect_url)

        submission.score = score
        submission.feedback = feedback
        submission.status = "graded"
        submission.graded_by = request.user
        if not submission.graded_at:
            submission.graded_at = timezone.now()
        submission.save(update_fields=["score", "feedback", "status", "graded_by", "graded_at"])
        messages.success(
            request,
            f"Qiymət saxlanıldı. {REVIEW_EDIT_WINDOW_MINUTES} dəqiqə ərzində yenidən yoxlaya bilərsiniz.",
        )
        return redirect(redirect_url)

    attachments = []
    if submission.submission_file:
        attachments.append(
            {
                "name": PurePosixPath(submission.submission_file.name).name,
                "url": submission.submission_file.url,
            }
        )
    if submission.submission_link:
        attachments.append({"name": submission.submission_link, "url": submission.submission_link})

    has_answer_scores = any(answer.score is not None for answer in lab_answers)
    auto_total_decimal = sum(
        (answer.score if answer.score is not None else Decimal("0") for answer in lab_answers),
        Decimal("0"),
    )
    use_manual_total_initial = False
    if submission.score is not None:
        submission_score_decimal = Decimal(str(submission.score))
        use_manual_total_initial = (not has_answer_scores) or submission_score_decimal != auto_total_decimal

    for answer in lab_answers:
        answer.score_input_value = _format_decimal_input(answer.score)

    context = {
        **base_context,
        "item_title": submission.assignment.lab.title,
        "course_title": submission.assignment.lab.course.title,
        "student_display": student_display,
        "status_display": submission.get_status_display(),
        "submitted_at": submission.submitted_at,
        "graded_at": submission.graded_at,
        "feedback": submission.feedback,
        "content_text": submission.submission_text,
        "attachments": attachments,
        "lab_answers": lab_answers,
        "current_score": submission.score,
        "current_score_input_value": _format_decimal_input(submission.score),
        "auto_total_score": auto_total_decimal,
        "auto_total_score_input_value": _format_decimal_input(auto_total_decimal),
        "max_score": max_score,
        "is_locked": is_locked,
        "is_recheck_window": is_recheck_window,
        "is_identity_hidden": is_identity_hidden,
        "is_pregrade_anonymous_window": is_identity_hidden and not is_recheck_window,
        "review_window_seconds_left": _review_window_seconds_left(submission.graded_at),
        "identity_window_seconds_left": identity_window_seconds_left,
        "review_deadline": submission.graded_at + REVIEW_EDIT_WINDOW if submission.graded_at else None,
        "use_manual_total_initial": use_manual_total_initial,
    }
    return render(request, "accounts/pending_review_detail.html", context)


@login_required
def review_results(request):
    """Teacher evaluated results across exams, assignments, labs, and projects."""
    profile = getattr(request.user, "profile", None)
    capabilities = _role_capabilities(request.user, profile)
    if not capabilities["can_review_submissions"]:
        messages.error(request, pgettext_lazy("accounts.pending_review.message", "teacher_only"))
        return redirect("accounts:profile")

    return _render_profile_section(request, "review-results")


@login_required
def review_result_detail(request, item_type, item_id):
    """Teacher-facing detail page for graded assignment/project/lab results."""
    profile = getattr(request.user, "profile", None)
    capabilities = _role_capabilities(request.user, profile)
    if not capabilities["can_review_submissions"]:
        messages.error(request, pgettext_lazy("accounts.pending_review.message", "teacher_only"))
        return redirect("accounts:profile")

    normalized_type = _normalize_review_result_item_type(item_type)
    if not normalized_type:
        return redirect(f"{reverse('accounts:profile')}?section=review-results")

    default_back_url = f"{reverse('accounts:profile')}?section=review-results"
    back_url = _safe_same_origin_redirect_path(
        request,
        request.GET.get("return_to") or request.GET.get("next"),
    )
    if not back_url:
        back_url = default_back_url

    teacher_courses = _tenant_scoped_courses(request, Course.objects.filter(owner=request.user))

    if normalized_type == "assignment":
        submission = get_object_or_404(
            Submission.objects.select_related("assignment", "assignment__course", "user", "graded_by"),
            id=item_id,
            assignment__course__in=teacher_courses,
        )
        context = {
            "item_type": normalized_type,
            "item_type_label": "Sərbəst iş",
            "item_title": submission.assignment.title,
            "course_title": submission.assignment.course.title,
            "student": submission.user,
            "status_display": submission.get_status_display(),
            "score_display": submission.grade if submission.grade is not None else "-",
            "submitted_at": submission.submitted_at,
            "graded_at": submission.graded_at,
            "feedback": submission.feedback,
            "content_text": submission.content,
            "attachments": _extract_assignment_attachments(submission),
            "back_url": back_url,
        }
        return render(request, "accounts/review_result_detail.html", context)

    if normalized_type == "project":
        submission = get_object_or_404(
            ProjectSubmission.objects.select_related("project", "project__course", "student", "graded_by"),
            id=item_id,
            project__course__in=teacher_courses,
        )
        attachments = []
        if submission.file:
            attachments.append({"name": PurePosixPath(submission.file.name).name, "url": submission.file.url})

        context = {
            "item_type": normalized_type,
            "item_type_label": "Kurs işi",
            "item_title": submission.project.title,
            "course_title": submission.project.course.title,
            "student": submission.student,
            "status_display": submission.get_status_display(),
            "score_display": submission.grade if submission.grade is not None else "-",
            "submitted_at": submission.submitted_at,
            "graded_at": submission.graded_at,
            "feedback": submission.feedback,
            "content_text": submission.content,
            "attachments": attachments,
            "back_url": back_url,
        }
        return render(request, "accounts/review_result_detail.html", context)

    submission = get_object_or_404(
        LabSubmission.objects.select_related(
            "assignment", "assignment__lab", "assignment__lab__course", "assignment__student"
        ),
        id=item_id,
        assignment__lab__course__in=teacher_courses,
    )
    lab_answers = list(
        submission.answers.select_related("question", "question__block").order_by(
            "question__block__order",
            "question__question_number",
        )
    )
    if not lab_answers:
        lab_answers = list(
            LabAnswer.objects.filter(
                lab=submission.assignment.lab,
                student=submission.assignment.student,
                attempt_number=submission.attempt_number,
                is_draft=False,
            )
            .select_related("question", "question__block")
            .order_by("question__block__order", "question__question_number")
        )

    attachments = []
    if submission.submission_file:
        attachments.append(
            {
                "name": PurePosixPath(submission.submission_file.name).name,
                "url": submission.submission_file.url,
            }
        )
    if submission.submission_link:
        attachments.append({"name": submission.submission_link, "url": submission.submission_link})

    context = {
        "item_type": normalized_type,
        "item_type_label": "Lab işi",
        "item_title": submission.assignment.lab.title,
        "course_title": submission.assignment.lab.course.title,
        "student": submission.assignment.student,
        "status_display": submission.get_status_display(),
        "score_display": submission.score if submission.score is not None else "-",
        "submitted_at": submission.submitted_at,
        "graded_at": submission.graded_at,
        "feedback": submission.feedback,
        "content_text": submission.submission_text,
        "attachments": attachments,
        "lab_answers": lab_answers,
        "back_url": back_url,
    }
    return render(request, "accounts/review_result_detail.html", context)
