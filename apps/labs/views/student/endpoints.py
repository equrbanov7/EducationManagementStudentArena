"""Labs — tələbə səthi (F2 rol-skeleti, 2026-07-02)."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.translation import pgettext

from core.helpers import REVIEW_EDIT_LOCK_WINDOW

from ...lab_access import can_student_access_lab, can_teacher_access_lab
from ...lab_assignment_service import get_lab_assignment_for_student
from ...lab_submission_service import format_lab_submission_duration, get_next_attempt_number
from ...models import LabAnswer, LabAssignment, LabQuestion, LabSubmission
from ..shared._helpers import _append_return_to, _get_tenant_lab_or_404, _lab_back_url, _lab_return_to


def _raise_lab_access_denied():
    raise PermissionDenied("You do not have permission to access this lab.")


@login_required
def lab_detail(request, pk):
    """Lab detalları - Tələbə görünüşü"""
    lab = _get_tenant_lab_or_404(request, pk)

    assignment = None
    questions = []
    has_submitted = False
    submission = None
    attempt_count = 0
    can_retry = True
    show_review_data = False
    review_available_in_seconds = 0

    if request.user.is_authenticated:
        if can_teacher_access_lab(lab, request.user):
            questions = (
                LabQuestion.objects.filter(block__lab=lab)
                .select_related("block")
                .order_by("block__order", "question_number")
            )

        # Tələbə üçün assignment yarat və sualları təyin et
        else:
            if not can_student_access_lab(lab, request.user):
                _raise_lab_access_denied()

            assignment = get_lab_assignment_for_student(lab, request.user)

            # ƏSAS FİX: select_related və prefetch_related istifadə et
            questions = assignment.assigned_questions.select_related("block").order_by(
                "block__order", "question_number"
            )

            # Əgər hələ də sual yoxdursa, yenidən təyin et (exists() — count-dan ucuz).
            if not questions.exists():
                assignment.assign_questions()
                questions = assignment.assigned_questions.select_related("block").order_by(
                    "block__order", "question_number"
                )

            # Submission yoxlaması
            submissions = LabSubmission.objects.filter(assignment=assignment).order_by("-submitted_at")

            attempt_count = submissions.count()
            has_submitted = attempt_count > 0
            submission = submissions.first() if has_submitted else None
            if submission and submission.status == "graded":
                show_review_data = not submission.graded_at or (
                    timezone.now() >= submission.graded_at + REVIEW_EDIT_LOCK_WINDOW
                )
                if submission.graded_at and not show_review_data:
                    reveal_at = submission.graded_at + REVIEW_EDIT_LOCK_WINDOW
                    review_available_in_seconds = max(0, int((reveal_at - timezone.now()).total_seconds()))

            max_attempts = lab.max_attempts or 1
            can_retry = attempt_count < max_attempts

    # Saved answers - yalnız cari cəhd üçün draft cavablar
    saved_answers = {}
    if request.user.is_authenticated:
        current_attempt = get_next_attempt_number(assignment)

        answers = LabAnswer.objects.filter(
            lab=lab,
            student=request.user,
            attempt_number=current_attempt,
            is_draft=True,
        )
        for ans in answers:
            saved_answers[ans.question_id] = ans.answer

    context = {
        "lab": lab,
        "questions": questions,
        "assignment": assignment,
        "saved_answers": saved_answers,
        "has_submitted": has_submitted,
        "submission": submission,
        "attempt_count": attempt_count,
        "can_retry": can_retry,
        "show_review_data": show_review_data,
        "review_available_in_seconds": review_available_in_seconds,
        "review_window_minutes": int(REVIEW_EDIT_LOCK_WINDOW.total_seconds() // 60),
        "answers_url": _append_return_to(f"/labs/{lab.id}/my-answers/", _lab_return_to(request)),
        "back_url": _lab_back_url(request, lab),
    }

    return render(request, "labs/lab_detail.html", context)


@login_required
def my_lab_answers(request, pk):
    """Tələbənin öz cavablarını görmək"""
    lab = _get_tenant_lab_or_404(request, pk)

    if not can_student_access_lab(lab, request.user):
        _raise_lab_access_denied()

    assignment = LabAssignment.objects.filter(lab=lab, student=request.user).first()
    if not assignment:
        messages.error(request, pgettext("labs.view.error", "assignment_not_found"))
        return redirect("courses:course_dashboard", course_id=lab.course.id)

    all_submissions = list(
        LabSubmission.objects.filter(assignment=assignment).order_by("-submitted_at", "-attempt_number")
    )

    if not all_submissions:
        messages.error(request, pgettext("labs.view.error", "submission_not_found"))
        return redirect("courses:course_dashboard", course_id=lab.course.id)

    total_attempts = len(all_submissions)
    attempts_left = max((lab.max_attempts or 1) - total_attempts, 0)
    requested_attempt = request.GET.get("attempt")
    preopen_submission_id = None

    try:
        answers = list(
            LabAnswer.objects.filter(
                lab=lab,
                student=request.user,
                is_draft=False,
            )
            .select_related("question")
            .order_by("question__block__order", "question__question_number")
        )
    except Exception:
        answers = list(
            LabAnswer.objects.filter(lab=lab, student=request.user, is_draft=False)
            .select_related("question")
            .order_by("question__block__order", "question__question_number")
        )

    answers_by_submission_id = {}
    answers_by_attempt = {}
    for answer in answers:
        if answer.submission_id:
            answers_by_submission_id.setdefault(answer.submission_id, []).append(answer)
        answers_by_attempt.setdefault(answer.attempt_number, []).append(answer)

    now = timezone.now()
    start_time = assignment.assigned_at if assignment.assigned_at else lab.start_datetime
    submissions = []
    for submission in all_submissions:
        submission_answers = answers_by_submission_id.get(submission.id) or answers_by_attempt.get(
            submission.attempt_number, []
        )
        submission.answer_items = submission_answers
        submission.answer_count = len(submission_answers)
        submission.duration = format_lab_submission_duration(start_time, submission.submitted_at)
        submission.show_review_data = False
        submission.review_available_in_seconds = 0
        submission.is_review_pending = False

        if submission.status == "graded" and submission.graded_at:
            reveal_at = submission.graded_at + REVIEW_EDIT_LOCK_WINDOW
            if now >= reveal_at:
                submission.show_review_data = True
            else:
                submission.is_review_pending = True
                submission.review_available_in_seconds = max(0, int((reveal_at - now).total_seconds()))

        submissions.append(submission)

        if requested_attempt and requested_attempt.isdigit() and submission.attempt_number == int(requested_attempt):
            preopen_submission_id = submission.id

    latest_submission = submissions[0]
    show_review_data = latest_submission.show_review_data
    review_available_in_seconds = latest_submission.review_available_in_seconds

    context = {
        "lab": lab,
        "submission": latest_submission,
        "submissions": submissions,
        "total_attempts": total_attempts,
        "attempts_left": attempts_left,
        "show_review_data": show_review_data,
        "review_available_in_seconds": review_available_in_seconds,
        "preopen_submission_id": preopen_submission_id,
        "back_url": _lab_back_url(request, lab),
    }

    return render(request, "labs/my_lab_answers.html", context)
