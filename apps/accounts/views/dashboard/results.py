"""
My-result detail view.
"""

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import pgettext, pgettext_lazy

from apps.assignments.models import Submission
from apps.exams.models import ExamAttempt
from apps.labs.models import LabAnswer, LabSubmission
from apps.projects.models import ProjectSubmission

from .._helpers import (
    REVIEW_EDIT_WINDOW_MINUTES,
    _append_query_params,
    _is_result_visible_to_student,
    _normalize_pending_answers_filter,
    _normalize_results_filter,
    _result_status_badge,
    _role_capabilities,
    _tenant_scoped_courses,
    _tenant_scoped_exams,
)

User = get_user_model()


@login_required
def my_result_detail(request, item_type, item_id):
    """Detail page for a single item from My Results."""
    profile = getattr(request.user, "profile", None)
    capabilities = _role_capabilities(request.user, profile)
    if not capabilities["can_view_student_assignments"]:
        messages.error(request, pgettext_lazy("accounts.student_assignments.message", "student_or_member_only"))
        return redirect("accounts:profile")

    requested_section = (request.GET.get("section") or "").strip().lower()
    results_filter = "all"
    if requested_section == "pending-answers":
        pending_filter = _normalize_pending_answers_filter(request.GET.get("pending_type") or request.GET.get("type"))
        back_url = _append_query_params(
            reverse("accounts:profile"),
            section="pending-answers",
            pending_type=pending_filter,
            pending_search=(request.GET.get("pending_search") or "").strip(),
        )
    else:
        results_filter = _normalize_results_filter(request.GET.get("results_type") or request.GET.get("type"))
        back_url = _append_query_params(
            reverse("accounts:profile"),
            section="my-results",
            results_type=results_filter,
        )

    normalized_type = (item_type or "").lower()
    tenant_course_ids = _tenant_scoped_courses(request).values_list("id", flat=True)

    if normalized_type == "exams":
        attempt = get_object_or_404(
            ExamAttempt.objects.select_related("exam"),
            id=item_id,
            user=request.user,
            exam__in=_tenant_scoped_exams(request),
        )
        if attempt.exam.results_hidden_from_students:
            messages.info(
                request,
                pgettext(
                    "accounts.my_results.message",
                    "Bu imtahanın nəticəsi müəllim tərəfindən tələbələrdən gizlədilib.",
                ),
            )
            return redirect(back_url)
        if (
            attempt.exam.exam_type != "test"
            and attempt.checked_by_teacher
            and attempt.teacher_checked_at
            and not _is_result_visible_to_student(attempt.teacher_checked_at)
        ):
            messages.info(
                request,
                pgettext(
                    "accounts.my_results.message",
                    "Nəticə hələ yekunlaşmayıb. {minutes} dəqiqə tamam olduqdan sonra görünəcək.",
                ).format(minutes=REVIEW_EDIT_WINDOW_MINUTES),
            )
            return redirect(back_url)
        result_url = reverse("exams:exam_result", kwargs={"slug": attempt.exam.slug, "attempt_id": attempt.id})
        if requested_section != "pending-answers":
            result_url = _append_query_params(
                result_url,
                from_section="my-results",
                return_to=back_url,
                results_type=results_filter,
            )
        return redirect(result_url)

    if normalized_type == "courses":
        submission = get_object_or_404(
            Submission.objects.select_related("assignment", "assignment__course"),
            id=item_id,
            user=request.user,
            assignment__course_id__in=tenant_course_ids,
        )
        if (
            submission.status == "graded"
            and submission.graded_at
            and not _is_result_visible_to_student(submission.graded_at)
        ):
            messages.info(
                request,
                pgettext(
                    "accounts.my_results.message",
                    "Nəticə hələ yekunlaşmayıb. {minutes} dəqiqə tamam olduqdan sonra görünəcək.",
                ).format(minutes=REVIEW_EDIT_WINDOW_MINUTES),
            )
            return redirect(back_url)

        is_graded_visible = submission.status == "graded" and (
            not submission.graded_at or _is_result_visible_to_student(submission.graded_at)
        )
        context = {
            "item_type": "courses",
            "item_type_label": pgettext_lazy("accounts.my_result_detail.type", "course"),
            "item_title": submission.assignment.title,
            "item_subtitle": submission.assignment.course.title,
            "submitted_at": submission.submitted_at,
            "status": _result_status_badge(submission.status, is_graded=is_graded_visible),
            "status_raw": submission.get_status_display(),
            "score": submission.grade if is_graded_visible else None,
            "feedback": submission.feedback if is_graded_visible else "",
            "content_text": submission.content,
            "files": submission.files or [],
            "back_url": back_url,
        }
        return render(request, "accounts/my_result_detail.html", context)

    if normalized_type == "labs":
        submission = get_object_or_404(
            LabSubmission.objects.select_related("assignment", "assignment__lab", "assignment__lab__course"),
            id=item_id,
            assignment__student=request.user,
            assignment__lab__course_id__in=tenant_course_ids,
        )
        if (
            submission.status == "graded"
            and submission.graded_at
            and not _is_result_visible_to_student(submission.graded_at)
        ):
            messages.info(
                request,
                pgettext(
                    "accounts.my_results.message",
                    "Nəticə hələ yekunlaşmayıb. {minutes} dəqiqə tamam olduqdan sonra görünəcək.",
                ).format(minutes=REVIEW_EDIT_WINDOW_MINUTES),
            )
            return redirect(back_url)

        is_graded_visible = submission.status == "graded" and (
            not submission.graded_at or _is_result_visible_to_student(submission.graded_at)
        )
        lab_answers = (
            LabAnswer.objects.filter(
                lab=submission.assignment.lab,
                student=request.user,
                attempt_number=submission.attempt_number,
                is_draft=False,
            )
            .select_related("question", "question__block")
            .order_by("question__block__order", "question__question_number")
        )
        if not lab_answers.exists():
            lab_answers = (
                submission.answers.filter(is_draft=False)
                .select_related("question", "question__block")
                .order_by("question__block__order", "question__question_number")
            )

        context = {
            "item_type": "labs",
            "item_type_label": pgettext_lazy("accounts.my_result_detail.type", "lab"),
            "item_title": submission.assignment.lab.title,
            "item_subtitle": submission.assignment.lab.course.title,
            "submitted_at": submission.submitted_at,
            "status": _result_status_badge(submission.status, is_graded=is_graded_visible),
            "status_raw": submission.get_status_display(),
            "score": submission.score if is_graded_visible else None,
            "feedback": submission.feedback if is_graded_visible else "",
            "content_text": submission.submission_text,
            "submission_link": submission.submission_link,
            "submission_file": submission.submission_file,
            "lab_answers": lab_answers,
            "lab_answer_count": lab_answers.count(),
            "back_url": back_url,
        }
        return render(request, "accounts/my_result_detail.html", context)

    if normalized_type == "independent":
        submission = get_object_or_404(
            ProjectSubmission.objects.select_related("project", "project__course"),
            id=item_id,
            student=request.user,
            project__course_id__in=tenant_course_ids,
        )
        if (
            submission.status == "graded"
            and submission.graded_at
            and not _is_result_visible_to_student(submission.graded_at)
        ):
            messages.info(
                request,
                pgettext(
                    "accounts.my_results.message",
                    "Nəticə hələ yekunlaşmayıb. {minutes} dəqiqə tamam olduqdan sonra görünəcək.",
                ).format(minutes=REVIEW_EDIT_WINDOW_MINUTES),
            )
            return redirect(back_url)

        is_graded_visible = submission.status == "graded" and (
            not submission.graded_at or _is_result_visible_to_student(submission.graded_at)
        )
        context = {
            "item_type": "independent",
            "item_type_label": pgettext_lazy("accounts.my_result_detail.type", "independent_work"),
            "item_title": submission.project.title,
            "item_subtitle": submission.project.course.title,
            "submitted_at": submission.submitted_at,
            "status": _result_status_badge(submission.status, is_graded=is_graded_visible),
            "status_raw": submission.get_status_display(),
            "score": submission.grade if is_graded_visible else None,
            "feedback": submission.feedback if is_graded_visible else "",
            "content_text": submission.content,
            "submission_file": submission.file,
            "back_url": back_url,
        }
        return render(request, "accounts/my_result_detail.html", context)

    messages.error(request, pgettext_lazy("accounts.my_results.message", "unknown_result_type"))
    return redirect(back_url)
