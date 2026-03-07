"""
Labs Views - Student Views
Tələbə görünüşü və cavablar
"""

from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.translation import pgettext

from apps.courses.models import CourseMembership

from ..models import LabAnswer, LabAssignment, LabQuestion, LabSubmission
from ._helpers import _get_tenant_lab_or_404, _lab_back_url

REVIEW_EDIT_LOCK_WINDOW = timedelta(minutes=5)


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

    if request.user.is_authenticated:
        # Müəllim üçün bütün sualları göstər
        if getattr(request.user, "is_teacher", False):
            questions = (
                LabQuestion.objects.filter(block__lab=lab)
                .select_related("block")
                .order_by("block__order", "question_number")
            )

            print(f"[TEACHER] {request.user.username} - {questions.count()} sual göstərilir")

        # Tələbə üçün assignment yarat və sualları təyin et
        else:
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
        "back_url": _lab_back_url(request, lab),
    }

    return render(request, "labs/lab_detail.html", context)


@login_required
def my_lab_answers(request, pk):
    """Tələbənin öz cavablarını görmək"""
    lab = _get_tenant_lab_or_404(request, pk)

    assignment = LabAssignment.objects.filter(lab=lab, student=request.user).first()
    if not assignment:
        messages.error(request, pgettext("labs.view.error", "assignment_not_found"))
        return redirect("courses:course_dashboard", pk=lab.course.id)

    all_submissions = LabSubmission.objects.filter(assignment=assignment).order_by("attempt_number")

    if not all_submissions.exists():
        messages.error(request, pgettext("labs.view.error", "submission_not_found"))
        return redirect("courses:course_dashboard", pk=lab.course.id)

    total_attempts = all_submissions.count()

    # Hansı cəhdə baxılır?
    attempt = request.GET.get("attempt")
    if attempt and attempt.isdigit():
        attempt_number = int(attempt)
        submission = all_submissions.filter(attempt_number=attempt_number).first()
        if not submission:
            submission = all_submissions.last()
            attempt_number = submission.attempt_number
    else:
        submission = all_submissions.last()
        attempt_number = submission.attempt_number if submission else 1

    # Müddət
    duration = None
    if submission and submission.submitted_at:
        start_time = assignment.assigned_at if assignment.assigned_at else lab.start_datetime
        if start_time:
            delta = submission.submitted_at - start_time
            total_seconds = int(delta.total_seconds())
            if total_seconds > 0:
                hours = total_seconds // 3600
                minutes = (total_seconds % 3600) // 60
                if hours > 0:
                    duration_tpl = pgettext("labs.view.message", "duration_hours_minutes")
                    try:
                        duration = duration_tpl % {"hours": hours, "minutes": minutes}
                    except Exception:
                        duration = duration_tpl.format(hours=hours, minutes=minutes)
                else:
                    duration_tpl = pgettext("labs.view.message", "duration_minutes")
                    try:
                        duration = duration_tpl % {"minutes": minutes}
                    except Exception:
                        duration = duration_tpl.format(minutes=minutes)

    # Bu cəhdin cavablarını al - attempt_number ilə
    # Əgər attempt_number field yoxdursa, bütün cavabları göstər
    try:
        answers = (
            LabAnswer.objects.filter(
                lab=lab,
                student=request.user,
                attempt_number=attempt_number,
                is_draft=False,
            )
            .select_related("question")
            .order_by("question__block__order", "question__question_number")
        )
    except Exception:
        # Əgər attempt_number field yoxdursa
        answers = (
            LabAnswer.objects.filter(lab=lab, student=request.user, is_draft=False)
            .select_related("question")
            .order_by("question__block__order", "question__question_number")
        )

    show_review_data = False
    review_available_in_seconds = 0
    review_reveal_at = None
    if (
        submission
        and submission.status == "graded"
        and submission.graded_at
        and timezone.now() >= submission.graded_at + REVIEW_EDIT_LOCK_WINDOW
    ):
        show_review_data = True
    elif submission and submission.status == "graded" and submission.graded_at:
        reveal_at = submission.graded_at + REVIEW_EDIT_LOCK_WINDOW
        remain = int((reveal_at - timezone.now()).total_seconds())
        if remain > 0:
            review_available_in_seconds = remain
            review_reveal_at = reveal_at

    context = {
        "lab": lab,
        "submission": submission,
        "all_submissions": all_submissions,
        "answers": answers,
        "duration": duration,
        "attempt_number": attempt_number,
        "total_attempts": total_attempts,
        "show_review_data": show_review_data,
        "review_available_in_seconds": review_available_in_seconds,
        "review_reveal_at": review_reveal_at,
    }

    return render(request, "labs/my_lab_answers.html", context)


@login_required
def api_get_groups(request, course_id):
    """Kurs qruplarını qaytarır"""
    from ._helpers import _get_tenant_course_or_404

    course = _get_tenant_course_or_404(request, course_id)

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
