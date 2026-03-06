"""
Labs Views - Bütün view-lar pk istifadə edir
"""

import json
import os
import traceback
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import pgettext
from django.views.decorators.http import require_http_methods, require_POST

from apps.courses.models import Course, CourseMembership
from core.permissions import request_has_permission
from core.tenancy import scoped_by_organization_id
from core.upload_security import randomize_uploaded_filename, validate_uploaded_file

from .models import Lab, LabAnswer, LabAssignment, LabBlock, LabQuestion, LabSubmission

ASSIGNED_TASK_FILTER_CHOICES = {"all", "exams", "courses", "assignments", "labs", "independent"}
REVIEW_EDIT_LOCK_WINDOW = timedelta(minutes=5)
DEFAULT_LAB_ALLOWED_EXTENSIONS = {
    ".zip",
    ".pdf",
    ".doc",
    ".docx",
    ".txt",
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".py",
    ".java",
    ".cpp",
    ".c",
    ".rar",
    ".7z",
}


def _normalize_extensions(raw_extensions):
    extensions = {f".{ext.strip().lstrip('.').lower()}" for ext in (raw_extensions or "").split(",") if ext.strip()}
    return extensions or set(DEFAULT_LAB_ALLOWED_EXTENSIONS)


def _parse_max_size_mb(raw_value, *, fallback=25):
    try:
        parsed = int(raw_value)
    except (TypeError, ValueError):
        parsed = fallback
    return max(1, parsed)


def _validate_and_prepare_lab_upload(uploaded_file, *, allowed_extensions, max_size_mb):
    validate_uploaded_file(
        uploaded_file,
        allowed_extensions=allowed_extensions,
        max_size_mb=max_size_mb,
    )
    randomize_uploaded_filename(uploaded_file)
    return uploaded_file


def _tenant_scoped_courses(request, queryset=None):
    base_queryset = queryset if queryset is not None else Course.objects.all()
    return scoped_by_organization_id(
        base_queryset,
        request,
        org_id_field="organization_id",
        fallback_org_field="owner__profile__organization",
    )


def _tenant_scoped_labs(request, queryset=None):
    base_queryset = queryset if queryset is not None else Lab.objects.all()
    return base_queryset.filter(course__in=_tenant_scoped_courses(request))


def _tenant_scoped_blocks(request, queryset=None):
    base_queryset = queryset if queryset is not None else LabBlock.objects.all()
    return base_queryset.filter(lab__in=_tenant_scoped_labs(request))


def _tenant_scoped_questions(request, queryset=None):
    base_queryset = queryset if queryset is not None else LabQuestion.objects.all()
    return base_queryset.filter(block__in=_tenant_scoped_blocks(request))


def _tenant_scoped_submissions(request, queryset=None):
    base_queryset = queryset if queryset is not None else LabSubmission.objects.all()
    return base_queryset.filter(assignment__lab__in=_tenant_scoped_labs(request))


def _get_tenant_course_or_404(request, course_id):
    return get_object_or_404(_tenant_scoped_courses(request), id=course_id)


def _get_tenant_lab_or_404(request, lab_id):
    return get_object_or_404(_tenant_scoped_labs(request), id=lab_id)


def _get_tenant_block_or_404(request, block_id):
    return get_object_or_404(_tenant_scoped_blocks(request), id=block_id)


def _get_tenant_question_or_404(request, question_id):
    return get_object_or_404(_tenant_scoped_questions(request), id=question_id)


def _get_tenant_submission_or_404(request, submission_id):
    return get_object_or_404(_tenant_scoped_submissions(request), id=submission_id)


def _lab_back_url(request, lab):
    source_section = (request.GET.get("from_section") or "").strip()
    if source_section == "assigned-exams":
        params = {"section": "assigned-exams"}
        assigned_type = (request.GET.get("assigned_type") or "").strip().lower()
        if assigned_type in ASSIGNED_TASK_FILTER_CHOICES:
            params["assigned_type"] = assigned_type
        return f"{reverse('accounts:profile')}?{urlencode(params)}"

    return reverse("courses:course_dashboard", kwargs={"course_id": lab.course.id})


def _can_delete_lab_content(request):
    return request_has_permission(request, "lab.delete") or request_has_permission(request, "course.delete")


# ════════════════��══════════════════════════════════════════════════════════════
# LAB CRUD
# ═══════════════════════════════════════════════════════════════════════════════


@login_required
@require_POST
def create_lab(request, course_id):
    """Lab yarat"""

    course = _get_tenant_course_or_404(request, course_id)

    if course.owner != request.user:
        return JsonResponse(
            {"success": False, "error": pgettext("labs.view.permission", "permission_denied")}, status=403
        )

    try:
        allowed_extensions = _normalize_extensions(request.POST.get("allowed_extensions", ""))
        max_file_size_mb = _parse_max_size_mb(request.POST.get("max_file_size_mb", 50), fallback=50)
        teacher_file = request.FILES.get("teacher_files")
        if teacher_file is not None:
            _validate_and_prepare_lab_upload(
                teacher_file,
                allowed_extensions=allowed_extensions,
                max_size_mb=max_file_size_mb,
            )

        # Seçilmiş qruplar və tələbələr
        group_names = request.POST.getlist("group_names[]")
        student_ids = request.POST.getlist("student_ids[]")

        lab = Lab.objects.create(
            course=course,
            title=request.POST.get("title"),
            description=request.POST.get("description", ""),
            start_datetime=request.POST.get("start_datetime"),
            end_datetime=request.POST.get("end_datetime"),
            max_score=request.POST.get("max_score", 100),
            max_attempts=request.POST.get("max_attempts", 1),  # Cəhd sayı
            status="draft",
            questions_per_student=request.POST.get("questions_per_student", 0),
            allow_late_submission=request.POST.get("allow_late_submission") == "on",
            late_penalty_percent=request.POST.get("late_penalty_percent", 0),
            allow_file_upload=request.POST.get("allow_file_upload") == "on",
            allow_link_submission=request.POST.get("allow_link_submission") == "on",
            max_file_size_mb=max_file_size_mb,
            allowed_extensions=",".join(ext.lstrip(".") for ext in sorted(allowed_extensions)),
            teacher_instructions=request.POST.get("teacher_instructions", ""),
            allowed_groups=",".join(group_names) if group_names else "",
            allowed_students=",".join(student_ids) if student_ids else "",
            created_by=request.user,
        )

        if teacher_file is not None:
            lab.teacher_files = teacher_file
            lab.save()

        return JsonResponse({"success": True, "lab_id": lab.id})

    except ValidationError as exc:
        return JsonResponse({"success": False, "error": exc.messages[0]}, status=400)
    except Exception as e:
        import traceback

        traceback.print_exc()
        return JsonResponse({"success": False, "error": str(e)}, status=400)


@login_required
@require_http_methods(["GET", "POST"])
def edit_lab(request, pk):
    """Lab redaktə et"""
    lab = _get_tenant_lab_or_404(request, pk)

    if lab.created_by != request.user:
        return JsonResponse(
            {"success": False, "error": pgettext("labs.view.permission", "permission_denied")}, status=403
        )

    if request.method == "GET":
        # Mövcud qrupları al
        group_names = []
        if lab.allowed_groups:
            group_names = [g.strip() for g in lab.allowed_groups.split(",") if g.strip()]

        # Mövcud tələbə ID-lərini al
        student_ids = []
        if lab.allowed_students:
            student_ids = [int(x) for x in lab.allowed_students.split(",") if x.strip().isdigit()]
        selected_student_ids_set = set(student_ids)
        group_student_ids = set(
            CourseMembership.objects.filter(
                course=lab.course,
                role="student",
                group_name__in=group_names,
            ).values_list("user_id", flat=True)
        )
        group_excluded_student_ids = sorted(group_student_ids - selected_student_ids_set)

        data = {
            "id": lab.id,
            "title": lab.title or "",
            "description": lab.description or "",
            "start_datetime": (lab.start_datetime.strftime("%Y-%m-%dT%H:%M") if lab.start_datetime else ""),
            "end_datetime": (lab.end_datetime.strftime("%Y-%m-%dT%H:%M") if lab.end_datetime else ""),
            "max_score": lab.max_score or 100,
            "max_attempts": getattr(lab, "max_attempts", 1) or 1,
            "status": lab.status or "draft",
            "questions_per_student": lab.questions_per_student or 0,
            "allow_late_submission": lab.allow_late_submission,
            "late_penalty_percent": lab.late_penalty_percent or 0,
            "allow_file_upload": lab.allow_file_upload,
            "allow_link_submission": lab.allow_link_submission,
            "max_file_size_mb": lab.max_file_size_mb or 50,
            "allowed_extensions": lab.allowed_extensions or "zip,pdf,docx,png,jpg,txt,py,java,cpp",
            "teacher_instructions": lab.teacher_instructions or "",
            "teacher_files_url": lab.teacher_files.url if lab.teacher_files else None,
            "group_names": group_names,
            "student_ids": student_ids,
            "group_excluded_student_ids": group_excluded_student_ids,
        }
        return JsonResponse({"success": True, "data": data})

    # POST - yenilə
    try:
        group_names = request.POST.getlist("group_names[]")
        student_ids = request.POST.getlist("student_ids[]")

        lab.title = request.POST.get("title")
        lab.description = request.POST.get("description", "")
        lab.start_datetime = request.POST.get("start_datetime") or None
        lab.end_datetime = request.POST.get("end_datetime") or None
        lab.max_score = int(request.POST.get("max_score", 100) or 100)
        lab.status = request.POST.get("status", "draft")

        # max_attempts field varsa
        if hasattr(lab, "max_attempts"):
            lab.max_attempts = int(request.POST.get("max_attempts", 1) or 1)

        lab.questions_per_student = int(request.POST.get("questions_per_student", 0) or 0)
        lab.allow_late_submission = request.POST.get("allow_late_submission") == "on"
        lab.late_penalty_percent = int(request.POST.get("late_penalty_percent", 0) or 0)
        lab.allow_file_upload = request.POST.get("allow_file_upload") == "on"
        lab.allow_link_submission = request.POST.get("allow_link_submission") == "on"
        lab.max_file_size_mb = _parse_max_size_mb(request.POST.get("max_file_size_mb", 50), fallback=50)
        lab.allowed_extensions = request.POST.get("allowed_extensions", "")
        lab.teacher_instructions = request.POST.get("teacher_instructions", "")
        lab.allowed_groups = ",".join(group_names) if group_names else ""
        lab.allowed_students = ",".join(student_ids) if student_ids else ""

        teacher_file = request.FILES.get("teacher_files")
        if teacher_file is not None:
            allowed_extensions = _normalize_extensions(lab.allowed_extensions)
            _validate_and_prepare_lab_upload(
                teacher_file,
                allowed_extensions=allowed_extensions,
                max_size_mb=lab.max_file_size_mb,
            )
            lab.teacher_files = teacher_file

        lab.save()
        return JsonResponse({"success": True})

    except ValidationError as exc:
        return JsonResponse({"success": False, "error": exc.messages[0]}, status=400)
    except Exception as e:
        import traceback

        traceback.print_exc()
        return JsonResponse({"success": False, "error": str(e)}, status=400)


@login_required
@require_POST
def delete_lab(request, pk):
    """Lab sil"""
    lab = _get_tenant_lab_or_404(request, pk)

    if lab.created_by != request.user:
        return JsonResponse(
            {"success": False, "error": pgettext("labs.view.permission", "permission_denied")}, status=403
        )

    if not _can_delete_lab_content(request):
        return JsonResponse(
            {"success": False, "error": pgettext("labs.view.permission", "permission_denied")}, status=403
        )

    course_id = lab.course.id
    lab.delete()
    messages.success(request, pgettext("labs.view.message", "lab_deleted"))
    return JsonResponse(
        {
            "success": True,
            "redirect_url": reverse("courses:course_dashboard", args=[course_id]),
        }
    )


@login_required
@require_POST
def publish_lab(request, pk):
    """Lab yayımla"""
    lab = _get_tenant_lab_or_404(request, pk)

    if lab.created_by != request.user:
        return JsonResponse(
            {"success": False, "error": pgettext("labs.view.permission", "permission_denied")}, status=403
        )

    lab.status = "published"
    lab.save()
    messages.success(request, pgettext("labs.view.message", "lab_published"))
    return JsonResponse({"success": True})


# ═══════════════════════════════════════════════════════════════════════════════
# BLOCK CRUD
# ═══════════════════════════════════════════════════════════════════════════════


@login_required
def manage_blocks(request, pk):
    """Blokları idarə et"""
    lab = _get_tenant_lab_or_404(request, pk)

    if lab.created_by != request.user:
        messages.error(request, pgettext("labs.view.permission", "permission_denied"))
        return redirect("courses:course_dashboard", pk=lab.course.id)

    blocks = lab.blocks.all().order_by("order")

    context = {
        "lab": lab,
        "blocks": blocks,
    }

    return render(request, "labs/manage_blocks.html", context)


@login_required
@require_POST
def create_block(request, pk):
    """Blok yarat"""
    lab = _get_tenant_lab_or_404(request, pk)

    if lab.created_by != request.user:
        return JsonResponse(
            {"success": False, "error": pgettext("labs.view.permission", "permission_denied")}, status=403
        )

    try:
        questions_to_pick = int(request.POST.get("questions_to_pick", 0) or 0)
        if questions_to_pick < 0:
            questions_to_pick = 0

        block = LabBlock.objects.create(
            lab=lab,
            title=request.POST.get("title"),
            description=request.POST.get("description", ""),
            order=lab.blocks.count() + 1,
            questions_to_pick=questions_to_pick,
        )
        messages.success(request, pgettext("labs.view.message", "block_created"))
        return JsonResponse({"success": True, "block_id": block.id})

    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=400)


@login_required
@require_http_methods(["GET", "POST"])
def edit_block(request, pk):
    """Blok redaktə et"""
    block = _get_tenant_block_or_404(request, pk)

    if block.lab.created_by != request.user:
        return JsonResponse(
            {"success": False, "error": pgettext("labs.view.permission", "permission_denied")}, status=403
        )

    if request.method == "GET":
        data = {
            "id": block.id,
            "title": block.title,
            "description": block.description,
            "order": block.order,
            "questions_to_pick": block.questions_to_pick,
        }
        return JsonResponse({"success": True, "data": data})

    try:
        questions_to_pick = int(request.POST.get("questions_to_pick", 0) or 0)
        if questions_to_pick < 0:
            questions_to_pick = 0

        block.title = request.POST.get("title")
        block.description = request.POST.get("description", "")
        block.questions_to_pick = questions_to_pick
        block.save()
        return JsonResponse({"success": True})

    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=400)


@login_required
@require_POST
def delete_block(request, pk):
    """Blok sil"""
    block = _get_tenant_block_or_404(request, pk)

    if block.lab.created_by != request.user:
        return JsonResponse(
            {"success": False, "error": pgettext("labs.view.permission", "permission_denied")}, status=403
        )

    block.delete()
    return JsonResponse({"success": True})


# ═══════════════════════════════════════════════════════════════════════════════
# QUESTION CRUD
# ═══════════════════════════════════════════════════════════════════════════════


@login_required
@require_POST
def create_question(request, block_id):
    """Sual yarat"""
    block = _get_tenant_block_or_404(request, block_id)

    if block.lab.created_by != request.user:
        return JsonResponse(
            {"success": False, "error": pgettext("labs.view.permission", "permission_denied")}, status=403
        )

    try:
        attachment = request.FILES.get("attachment")
        if attachment is not None:
            allowed_extensions = _normalize_extensions(block.lab.allowed_extensions)
            _validate_and_prepare_lab_upload(
                attachment,
                allowed_extensions=allowed_extensions,
                max_size_mb=block.lab.max_file_size_mb or 25,
            )

        question = LabQuestion.objects.create(
            block=block,
            question_number=block.questions.count() + 1,
            question_text=request.POST.get("question_text"),
            points=request.POST.get("points", 0),
        )

        if attachment is not None:
            question.attachment = attachment
            question.save()

        return JsonResponse({"success": True, "question_id": question.id})

    except ValidationError as exc:
        return JsonResponse({"success": False, "error": exc.messages[0]}, status=400)
    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=400)


@login_required
@require_http_methods(["GET", "POST"])
def edit_question(request, pk):
    """Sual redaktə et"""
    question = _get_tenant_question_or_404(request, pk)

    if question.block.lab.created_by != request.user:
        return JsonResponse(
            {"success": False, "error": pgettext("labs.view.permission", "permission_denied")}, status=403
        )

    if request.method == "GET":
        data = {
            "id": question.id,
            "question_text": question.question_text,
            "points": question.points,
            "question_number": question.question_number,
        }
        return JsonResponse({"success": True, "data": data})

    try:
        question.question_text = request.POST.get("question_text")
        question.points = request.POST.get("points", 0)
        question.save()
        return JsonResponse({"success": True})

    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=400)


@login_required
@require_POST
def delete_question(request, pk):
    """Sual sil"""
    question = _get_tenant_question_or_404(request, pk)

    if question.block.lab.created_by != request.user:
        return JsonResponse(
            {"success": False, "error": pgettext("labs.view.permission", "permission_denied")}, status=403
        )

    question.delete()
    return JsonResponse({"success": True})


@login_required
@require_POST
def import_questions(request, block_id):
    """
    Sualları toplu import et.

    Format dəstəyi:
    - 1. Sual metni
    - 1) Sual metni
    - 2. Başqa sual
    - Nömrəsiz sətir = əvvəlki sualın davamı
    """
    import re

    block = _get_tenant_block_or_404(request, block_id)

    if block.lab.created_by != request.user:
        return JsonResponse(
            {"success": False, "error": pgettext("labs.view.permission", "permission_denied")}, status=403
        )

    try:
        questions_text = request.POST.get("questions_text", "")

        if not questions_text.strip():
            return JsonResponse(
                {"success": False, "error": pgettext("labs.view.error", "empty_text_submitted")}, status=400
            )

        # Regex pattern: başda rəqəm + nöqtə və ya mötərizə
        # Məs: "1. " və ya "2) " və ya "10. "
        pattern = re.compile(r"^\s*(\d+)[\.\)]\s+(.+)", re.MULTILINE)

        lines = questions_text.split("\n")
        questions = []
        current_question = None

        for line in lines:
            line = line.strip()
            if not line:
                continue

            match = pattern.match(line)
            if match:
                # Yeni sual başlayır
                if current_question:
                    questions.append(current_question)

                num, text = match.groups()
                current_question = text.strip()
            else:
                # Əvvəlki sualın davamı
                if current_question:
                    current_question += " " + line

        # Sonuncu sualı əlavə et
        if current_question:
            questions.append(current_question)

        if not questions:
            return JsonResponse(
                {
                    "success": False,
                    "error": pgettext("labs.view.error", "import_no_questions_found_format"),
                },
                status=400,
            )

        # Sualları DB-yə əlavə et
        count = block.questions.count()
        created_count = 0

        for i, text in enumerate(questions, start=1):
            LabQuestion.objects.create(
                block=block,
                question_number=count + i,
                question_text=text,
            )
            created_count += 1

        return JsonResponse(
            {
                "success": True,
                "count": created_count,
                "message": pgettext("labs.view.message", "import_success_with_count").format(count=created_count),
            }
        )

    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=400)


# ═══════════════════════════════════════════════════════════════════════════════
# SUBMISSIONS & GRADING
# ═══════════════════════════════════════════════════════════════════════════════


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
def preview_randomization(request, pk):
    """Randomizasiyanı önizlə"""
    lab = _get_tenant_lab_or_404(request, pk)

    if lab.created_by != request.user:
        messages.error(request, pgettext("labs.view.permission", "permission_denied"))
        return redirect("courses:course_dashboard", pk=lab.course.id)

    # Kurs tələbələrini al

    memberships = CourseMembership.objects.filter(course=lab.course, role="student").select_related("user")

    # Seçilmiş tələbə
    selected_student_id = request.GET.get("student")
    selected_student = None
    questions = []

    if selected_student_id:
        try:
            from django.contrib.auth import get_user_model

            User = get_user_model()
            selected_student = User.objects.get(id=selected_student_id)

            # Bu tələbə üçün assignment yarat/al
            assignment = LabAssignment.get_or_create_for_student(lab, selected_student)
            questions = assignment.assigned_questions.all().order_by("block__order", "question_number")
        except Exception:
            pass

    context = {
        "lab": lab,
        "memberships": memberships,
        "selected_student": selected_student,
        "questions": questions,
    }

    return render(request, "labs/preview_randomization.html", context)


@login_required
@require_POST
def update_questions_per_student(request, pk):
    """Lab üçün tələbə başına sual sayını yenilə"""
    lab = _get_tenant_lab_or_404(request, pk)

    if lab.created_by != request.user:
        messages.error(request, pgettext("labs.view.permission", "permission_denied"))
        return redirect("courses:course_dashboard", pk=lab.course.id)

    try:
        value = int(request.POST.get("questions_per_student", 0) or 0)
        if value < 0:
            value = 0
    except (TypeError, ValueError):
        value = 0

    lab.questions_per_student = value
    lab.save(update_fields=["questions_per_student", "updated_at"])

    # Mövcud assignment-ları yeni ayara görə yenilə.
    for assignment in lab.assignments.all():
        assignment.assign_questions()

    messages.success(request, "Tələbə başına sual sayı yeniləndi.")
    return redirect("labs:manage_blocks", pk=lab.id)


# ═══════════════════════════════════════════════════════════════════════════════
# STUDENT VIEWS
# ═══════════════════════════════════════════════════════════════════════════════


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


# ═══════════════════════════════════════════════════════════════════════════════
# API
# ═══════════════════════════════════════════════════════════════════════════════


@login_required
def api_get_groups(request, course_id):
    """Kurs qruplarını qaytarır"""

    course = _get_tenant_course_or_404(request, course_id)

    # Authorization check: Only course owner can access roster data
    if not request.user.is_teacher_or_above or course.owner != request.user:
        return JsonResponse({"error": "Permission denied"}, status=403)

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

    course = _get_tenant_course_or_404(request, course_id)

    # Authorization check: Only course owner can access roster data
    if not request.user.is_teacher_or_above or course.owner != request.user:
        return JsonResponse({"error": "Permission denied"}, status=403)

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
