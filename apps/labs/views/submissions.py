"""
Labs Views - Submissions & Grading
Submission idarəetməsi və qiymətləndirmə
"""

import json
import os
import traceback
from datetime import datetime
from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
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

from ..models import LabAnswer, LabAssignment, LabSubmission
from ._helpers import (
    _get_tenant_submission_or_404,
    _get_tenant_lab_or_404,
    _lab_back_url,
    _normalize_extensions,
    _tenant_scoped_questions,
    _validate_and_prepare_lab_upload,
)


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


@login_required
def lab_submissions(request, pk):
    """Lab cavablarını göstər - müəllim üçün"""
    lab = _get_tenant_lab_or_404(request, pk)

    if lab.created_by != request.user:
        messages.error(request, pgettext("labs.view.permission", "permission_denied"))
        return redirect("courses:course_dashboard", pk=lab.course.id)

    # Bütün submission-lar
    submissions = LabSubmission.objects.filter(assignment__lab=lab).select_related("assignment__student")

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
        "submissions": page_obj.object_list,
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

    if lab.created_by != request.user:
        messages.error(request, pgettext("labs.view.permission", "permission_denied"))
        return redirect(reverse("labs:lab_submissions", kwargs={"pk": lab.id}))

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
        messages.warning(request, "Silmək üçün ən azı bir cavab seçin.")
        return redirect(redirect_url)

    submissions_qs = LabSubmission.objects.filter(assignment__lab=lab, id__in=submission_ids)
    deleted_count = submissions_qs.count()
    if deleted_count == 0:
        messages.warning(request, "Seçilən cavablar tapılmadı.")
        return redirect(redirect_url)

    submissions_qs.delete()
    messages.success(request, f"{deleted_count} cavab silindi.")
    return redirect(redirect_url)


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
