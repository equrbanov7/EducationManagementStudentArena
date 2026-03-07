"""
Labs Views - Submissions & Grading
Submission idarəetməsi və qiymətləndirmə
"""

import json
import os
import traceback
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import pgettext
from django.views.decorators.http import require_POST

from apps.courses.models import CourseMembership
from core.helpers import REVIEW_EDIT_LOCK_WINDOW
from core.permissions import request_has_permission

from ..models import LabAnswer, LabAssignment, LabSubmission
from ._helpers import (
    _get_tenant_submission_or_404,
    _get_tenant_lab_or_404,
    _lab_back_url,
    _normalize_extensions,
    _tenant_scoped_questions,
    _validate_and_prepare_lab_upload,
)


@login_required
def lab_submissions(request, pk):
    """Lab cavablarını göstər - müəllim üçün"""
    lab = _get_tenant_lab_or_404(request, pk)

    if lab.created_by != request.user:
        messages.error(request, pgettext("labs.view.permission", "permission_denied"))
        return redirect("courses:course_dashboard", pk=lab.course.id)

    # Bütün submission-lar
    submissions = (
        LabSubmission.objects.filter(assignment__lab=lab)
        .select_related("assignment__student")
        .order_by("-submitted_at")
    )

    # Qrupları al - CourseMembership-dən

    memberships = (
        CourseMembership.objects.filter(course=lab.course, role="student")
        .exclude(group_name__isnull=True)
        .exclude(group_name="")
    )

    groups = list(memberships.values_list("group_name", flat=True).distinct())

    # Filters
    status_filter = request.GET.get("status", "")
    group_filter = request.GET.get("group", "")

    if status_filter:
        submissions = submissions.filter(status=status_filter)

    if group_filter:
        # Qrup filter - membership üzərindən
        student_ids = memberships.filter(group_name=group_filter).values_list("user_id", flat=True)
        submissions = submissions.filter(assignment__student_id__in=student_ids)

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

    context = {
        "lab": lab,
        "submissions": submissions,
        "groups": groups,
        "status_filter": status_filter,
        "group_filter": group_filter,
        "stats": stats,
        "student_groups": student_groups,
        "back_url": _lab_back_url(request, lab),
    }

    return render(request, "labs/lab_submissions.html", context)


@login_required
def grade_submission_page(request, pk):
    """Qiymətləndirmə səhifəsi"""
    submission = _get_tenant_submission_or_404(request, pk)
    lab = submission.assignment.lab

    if not request_has_permission(request, "grade.input"):
        messages.error(request, pgettext("labs.view.permission", "permission_denied"))
        return redirect("labs:lab_submissions", pk=lab.id)

    if lab.created_by != request.user:
        messages.error(request, pgettext("labs.view.permission", "permission_denied"))
        return redirect("labs:lab_submissions", pk=lab.id)

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
        if (
            submission.status == "graded"
            and submission.graded_at
            and timezone.now() >= submission.graded_at + REVIEW_EDIT_LOCK_WINDOW
        ):
            messages.error(request, "Yoxlama müddəti bitib. Artıq dəyişiklik etmək mümkün deyil.")
            return redirect(request.path)

        try:
            auto_total = Decimal("0")
            for answer in answers:
                raw_score = (request.POST.get(f"answer_score_{answer.id}", "") or "").strip()
                if raw_score == "":
                    answer.score = None
                else:
                    try:
                        val = Decimal(raw_score)
                    except (InvalidOperation, TypeError):
                        val = Decimal("0")
                    if val < 0:
                        val = Decimal("0")
                    q_max = Decimal(str(answer.question.points or 0))
                    if q_max > 0 and val > q_max:
                        val = q_max
                    answer.score = val
                    auto_total += val
                answer.save(update_fields=["score", "submitted_at"])

            score_raw = (request.POST.get("score", "") or "").strip()
            use_manual_total = request.POST.get("use_manual_total") == "1"
            if use_manual_total and score_raw != "":
                try:
                    final_score = Decimal(score_raw)
                except (InvalidOperation, TypeError):
                    final_score = auto_total
            else:
                final_score = auto_total

            if final_score < 0:
                final_score = Decimal("0")
            lab_max = Decimal(str(lab.max_score or 0))
            if lab_max > 0 and final_score > lab_max:
                final_score = lab_max

            submission.score = final_score
            submission.feedback = request.POST.get("feedback", "")
            submission.status = "graded"
            submission.graded_by = request.user
            if not submission.graded_at:
                submission.graded_at = timezone.now()
            submission.save()

            messages.success(request, pgettext("labs.view.message", "grade_saved_successfully"))
            return redirect("labs:lab_submissions", pk=lab.id)
        except Exception as e:
            messages.error(request, pgettext("labs.view.error", "error_with_details").format(error=str(e)))

    auto_total_score = sum([float(a.score) for a in answers if a.score is not None]) if answers else 0

    context = {
        "submission": submission,
        "lab": lab,
        "answers": answers,
        "auto_total_score": auto_total_score,
    }

    return render(request, "labs/grade_submission.html", context)


@login_required
@require_POST
def auto_save_answer(request, pk):
    """Cavabı avtomatik saxla - cari cəhd üçün"""
    lab = _get_tenant_lab_or_404(request, pk)

    now = timezone.now()
    if lab.start_datetime and lab.end_datetime:
        is_open = lab.status == "published" and lab.start_datetime <= now <= lab.end_datetime
    else:
        is_open = lab.status == "published"

    if not is_open:
        return JsonResponse({"success": False, "error": pgettext("labs.view.error", "lab_closed")})

    try:
        # Cari cəhd nömrəsini tap
        assignment = LabAssignment.objects.filter(lab=lab, student=request.user).first()
        current_attempt = 1
        if assignment:
            submitted_count = LabSubmission.objects.filter(assignment=assignment).count()
            current_attempt = submitted_count + 1

        update_answer_text = False
        if request.content_type == "application/json":
            data = json.loads(request.body)
            question_id = data.get("question_id")
            answer = data.get("answer", "")
            answer_file = None
            update_answer_text = True
        else:
            question_id = request.POST.get("question_id")
            answer = request.POST.get("answer", "")
            answer_file = request.FILES.get("answer_file")
            # File autosave zamanı boş text ilə mövcud cavabı silməmək üçün
            # yalnız real mətn gələndə answer sahəsini yenilə.
            update_answer_text = bool((answer or "").strip())

        from django.shortcuts import get_object_or_404
        question = get_object_or_404(_tenant_scoped_questions(request), id=question_id, block__lab=lab)

        # Bu cəhd üçün cavab yarat/yenilə
        lab_answer, created = LabAnswer.objects.get_or_create(
            lab=lab,
            question=question,
            student=request.user,
            attempt_number=current_attempt,
            defaults={"answer": answer, "is_draft": True},
        )

        if not created:
            if update_answer_text:
                lab_answer.answer = answer
            lab_answer.is_draft = True

        if answer_file:
            allowed_extensions = _normalize_extensions(lab.allowed_extensions)
            _validate_and_prepare_lab_upload(
                answer_file,
                allowed_extensions=allowed_extensions,
                max_size_mb=lab.max_file_size_mb or 25,
            )
            lab_answer.answer_file = answer_file

        lab_answer.save()

        return JsonResponse({"success": True})

    except ValidationError as exc:
        return JsonResponse({"success": False, "error": exc.messages[0]}, status=400)
    except Exception as e:

        traceback.print_exc()
        return JsonResponse({"success": False, "error": str(e)})


@login_required
@require_POST
def submit_lab(request, pk):
    """Labı göndər"""
    lab = _get_tenant_lab_or_404(request, pk)

    now = timezone.now()
    if lab.start_datetime and lab.end_datetime:
        is_open = lab.status == "published" and lab.start_datetime <= now <= lab.end_datetime
    else:
        is_open = lab.status == "published"

    if not is_open and not lab.allow_late_submission:
        return JsonResponse({"success": False, "error": pgettext("labs.view.error", "lab_closed")})

    try:
        assignment = LabAssignment.objects.filter(lab=lab, student=request.user).first()
        if not assignment:
            return JsonResponse({"success": False, "error": pgettext("labs.view.error", "assignment_not_found")})

        current_attempts = LabSubmission.objects.filter(assignment=assignment).count()
        max_attempts = lab.max_attempts or 1

        if current_attempts >= max_attempts:
            return JsonResponse({"success": False, "error": pgettext("labs.view.error", "attempts_exhausted")})

        new_attempt_number = current_attempts + 1

        # Yeni submission yarat
        submission = LabSubmission.objects.create(
            assignment=assignment, status="submitted", attempt_number=new_attempt_number
        )

        # Bu cəhdin cavablarını submission-a bağla və final et
        LabAnswer.objects.filter(
            lab=lab,
            student=request.user,
            attempt_number=new_attempt_number,
            is_draft=True,
        ).update(is_draft=False, submission=submission)

        return JsonResponse(
            {
                "success": True,
                "redirect_url": reverse("courses:course_dashboard", args=[lab.course.id]),
            }
        )

    except Exception as e:

        traceback.print_exc()
        return JsonResponse({"success": False, "error": str(e)})


@login_required
def submission_answers(request, pk):
    """Submission-un cavablarını JSON olaraq qaytar"""
    submission = _get_tenant_submission_or_404(request, pk)

    if submission.assignment.lab.created_by != request.user:
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
