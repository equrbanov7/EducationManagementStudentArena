"""
Labs Views - Student Views
Tələbə görünüşü və cavablar
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.translation import pgettext

from apps.courses.models import CourseMembership
from core.helpers import REVIEW_EDIT_LOCK_WINDOW

from ..models import LabAnswer, LabAssignment, LabQuestion, LabSubmission
from ._helpers import _append_return_to, _get_tenant_lab_or_404, _lab_back_url, _lab_return_to


def _user_can_access_course_roster(user, course):
    """
    Check if user can access course roster (groups/students).
    User must be course owner OR have teacher/assistant role in the course.
    """
    if course.owner == user:
        return True

    # Check if user has teacher or assistant role in the course
    return CourseMembership.objects.filter(
        course=course,
        user=user,
        role__in=["teacher", "assistant"]
    ).exists()


def _raise_lab_access_denied():
    raise PermissionDenied("You do not have permission to access this lab.")


def _format_lab_submission_duration(start_time, submitted_at):
    if not start_time or not submitted_at:
        return None

    delta = submitted_at - start_time
    total_seconds = int(delta.total_seconds())
    if total_seconds <= 0:
        return None

    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    if hours > 0:
        duration_tpl = pgettext("labs.view.message", "duration_hours_minutes")
        try:
            return duration_tpl % {"hours": hours, "minutes": minutes}
        except Exception:
            return duration_tpl.format(hours=hours, minutes=minutes)

    duration_tpl = pgettext("labs.view.message", "duration_minutes")
    try:
        return duration_tpl % {"minutes": minutes}
    except Exception:
        return duration_tpl.format(minutes=minutes)


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
        if lab.can_teacher_access(request.user):
            questions = (
                LabQuestion.objects.filter(block__lab=lab)
                .select_related("block")
                .order_by("block__order", "question_number")
            )

            print(f"[TEACHER] {request.user.username} - {questions.count()} sual göstərilir")

        # Tələbə üçün assignment yarat və sualları təyin et
        else:
            if not lab.can_student_access(request.user):
                _raise_lab_access_denied()

            assignment = LabAssignment.get_or_create_for_student(lab, request.user)

            # ƏSAS FİX: select_related və prefetch_related istifadə et
            questions = assignment.assigned_questions.select_related("block").order_by(
                "block__order", "question_number"
            )

            print(f"[STUDENT] {request.user.username} - Assignment ID: {assignment.id}")
            print(f"[STUDENT] Assigned questions count: {questions.count()}")

            # Əgər hələ də sual yoxdursa, yenidən təyin et
            if questions.count() == 0:
                print("[WARNING] Sual tapılmadı, yenidən assign edilir...")
                assignment.assign_questions()
                questions = assignment.assigned_questions.select_related("block").order_by(
                    "block__order", "question_number"
                )
                print(f"[STUDENT] Yenidən assign: {questions.count()} sual")

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
        current_attempt = 1
        if assignment:
            submitted_count = LabSubmission.objects.filter(assignment=assignment).count()
            current_attempt = submitted_count + 1

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

    if not lab.can_student_access(request.user):
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
        submission.duration = _format_lab_submission_duration(start_time, submission.submitted_at)
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


@login_required
def api_get_groups(request, course_id):
    """Kurs qruplarını qaytarır"""
    from ._helpers import _get_tenant_course_or_404

    course = _get_tenant_course_or_404(request, course_id)

    # Authorization check: user must be course owner or have teacher/assistant role
    if not _user_can_access_course_roster(request.user, course):
        raise PermissionDenied("You do not have permission to access this course roster.")

    groups = (
        CourseMembership.objects.filter(course=course, role="student")
        .exclude(group_name="")
        .exclude(group_name__isnull=True)
        .values_list("group_name", flat=True)
        .distinct()
    )

    return JsonResponse({"groups": [{"id": i, "name": name} for i, name in enumerate(groups, 1)]})


@login_required
def api_get_students(request, course_id):
    """Kurs tələbələrini qaytarır"""
    from ._helpers import _get_tenant_course_or_404

    course = _get_tenant_course_or_404(request, course_id)

    # Authorization check: user must be course owner or have teacher/assistant role
    if not _user_can_access_course_roster(request.user, course):
        raise PermissionDenied("You do not have permission to access this course roster.")

    groups = request.GET.get("groups", "").split(",")
    groups = [g.strip() for g in groups if g.strip()]

    memberships = CourseMembership.objects.filter(course=course, role="student").select_related("user")

    if groups:
        memberships = memberships.filter(group_name__in=groups)

    students = []
    for m in memberships:
        students.append(
            {
                "id": m.user.id,
                "name": m.user.get_full_name() or m.user.username,
                "group_name": m.group_name or "",
            }
        )

    return JsonResponse({"students": students})
