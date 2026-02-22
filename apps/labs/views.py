"""
Labs Views - Bütün view-lar pk istifadə edir
"""

import json
import os
import traceback
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST

from apps.courses.models import Course, CourseMembership

from .models import Lab, LabAnswer, LabAssignment, LabBlock, LabQuestion, LabSubmission

ASSIGNED_TASK_FILTER_CHOICES = {"all", "courses", "assignments", "labs", "independent"}


def _lab_back_url(request, lab):
    source_section = (request.GET.get("from_section") or "").strip()
    if source_section == "assigned-exams":
        params = {"section": "assigned-exams"}
        assigned_type = (request.GET.get("assigned_type") or "").strip().lower()
        if assigned_type in ASSIGNED_TASK_FILTER_CHOICES:
            params["assigned_type"] = assigned_type
        return f"{reverse('accounts:profile')}?{urlencode(params)}"

    return reverse("courses:course_dashboard", kwargs={"course_id": lab.course.id})

# ════════════════��══════════════════════════════════════════════════════════════
# LAB CRUD
# ═══════════════════════════════════════════════════════════════════════════════


@login_required
@require_POST
def create_lab(request, course_id):
    """Lab yarat"""

    course = get_object_or_404(Course, id=course_id)

    if course.owner != request.user:
        return JsonResponse({"success": False, "error": "İcazəniz yoxdur"}, status=403)

    try:
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
            max_file_size_mb=request.POST.get("max_file_size_mb", 50),
            allowed_extensions=request.POST.get("allowed_extensions", ""),
            teacher_instructions=request.POST.get("teacher_instructions", ""),
            allowed_groups=",".join(group_names) if group_names else "",
            allowed_students=",".join(student_ids) if student_ids else "",
            created_by=request.user,
        )

        if "teacher_files" in request.FILES:
            lab.teacher_files = request.FILES["teacher_files"]
            lab.save()

        return JsonResponse({"success": True, "lab_id": lab.id})

    except Exception as e:
        import traceback

        traceback.print_exc()
        return JsonResponse({"success": False, "error": str(e)}, status=400)


@login_required
@require_http_methods(["GET", "POST"])
def edit_lab(request, pk):
    """Lab redaktə et"""
    lab = get_object_or_404(Lab, id=pk)

    if lab.created_by != request.user:
        return JsonResponse({"success": False, "error": "İcazəniz yoxdur"}, status=403)

    if request.method == "GET":
        # Mövcud qrupları al
        group_names = []
        if lab.allowed_groups:
            group_names = [g.strip() for g in lab.allowed_groups.split(",") if g.strip()]

        # Mövcud tələbə ID-lərini al
        student_ids = []
        if lab.allowed_students:
            student_ids = [int(x) for x in lab.allowed_students.split(",") if x.strip().isdigit()]

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
        lab.max_file_size_mb = int(request.POST.get("max_file_size_mb", 50) or 50)
        lab.allowed_extensions = request.POST.get("allowed_extensions", "")
        lab.teacher_instructions = request.POST.get("teacher_instructions", "")
        lab.allowed_groups = ",".join(group_names) if group_names else ""
        lab.allowed_students = ",".join(student_ids) if student_ids else ""

        if "teacher_files" in request.FILES:
            lab.teacher_files = request.FILES["teacher_files"]

        lab.save()
        return JsonResponse({"success": True})

    except Exception as e:
        import traceback

        traceback.print_exc()
        return JsonResponse({"success": False, "error": str(e)}, status=400)


@login_required
@require_POST
def delete_lab(request, pk):
    """Lab sil"""
    lab = get_object_or_404(Lab, id=pk)

    if lab.created_by != request.user:
        return JsonResponse({"success": False, "error": "İcazəniz yoxdur"}, status=403)

    course_id = lab.course.id
    lab.delete()
    messages.success(request, "Lab silindi!")
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
    lab = get_object_or_404(Lab, id=pk)

    if lab.created_by != request.user:
        return JsonResponse({"success": False, "error": "İcazəniz yoxdur"}, status=403)

    lab.status = "published"
    lab.save()
    messages.success(request, "Lab yayımlandı!")
    return JsonResponse({"success": True})


# ═══════════════════════════════════════════════════════════════════════════════
# BLOCK CRUD
# ═══════════════════════════════════════════════════════════════════════════════


@login_required
def manage_blocks(request, pk):
    """Blokları idarə et"""
    lab = get_object_or_404(Lab, id=pk)

    if lab.created_by != request.user:
        messages.error(request, "İcazəniz yoxdur")
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
    lab = get_object_or_404(Lab, id=pk)

    if lab.created_by != request.user:
        return JsonResponse({"success": False, "error": "İcazəniz yoxdur"}, status=403)

    try:
        block = LabBlock.objects.create(
            lab=lab,
            title=request.POST.get("title"),
            description=request.POST.get("description", ""),
            order=lab.blocks.count() + 1,
        )
        messages.success(request, "Blok yaradıldı!")
        return JsonResponse({"success": True, "block_id": block.id})

    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=400)


@login_required
@require_http_methods(["GET", "POST"])
def edit_block(request, pk):
    """Blok redaktə et"""
    block = get_object_or_404(LabBlock, id=pk)

    if block.lab.created_by != request.user:
        return JsonResponse({"success": False, "error": "İcazəniz yoxdur"}, status=403)

    if request.method == "GET":
        data = {
            "id": block.id,
            "title": block.title,
            "description": block.description,
            "order": block.order,
        }
        return JsonResponse({"success": True, "data": data})

    try:
        block.title = request.POST.get("title")
        block.description = request.POST.get("description", "")
        block.save()
        return JsonResponse({"success": True})

    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=400)


@login_required
@require_POST
def delete_block(request, pk):
    """Blok sil"""
    block = get_object_or_404(LabBlock, id=pk)

    if block.lab.created_by != request.user:
        return JsonResponse({"success": False, "error": "İcazəniz yoxdur"}, status=403)

    block.delete()
    return JsonResponse({"success": True})


# ═══════════════════════════════════════════════════════════════════════════════
# QUESTION CRUD
# ═══════════════════════════════════════════════════════════════════════════════


@login_required
@require_POST
def create_question(request, block_id):
    """Sual yarat"""
    block = get_object_or_404(LabBlock, id=block_id)

    if block.lab.created_by != request.user:
        return JsonResponse({"success": False, "error": "İcazəniz yoxdur"}, status=403)

    try:
        question = LabQuestion.objects.create(
            block=block,
            question_number=block.questions.count() + 1,
            question_text=request.POST.get("question_text"),
            points=request.POST.get("points", 0),
        )

        if "attachment" in request.FILES:
            question.attachment = request.FILES["attachment"]
            question.save()

        return JsonResponse({"success": True, "question_id": question.id})

    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=400)


@login_required
@require_http_methods(["GET", "POST"])
def edit_question(request, pk):
    """Sual redaktə et"""
    question = get_object_or_404(LabQuestion, id=pk)

    if question.block.lab.created_by != request.user:
        return JsonResponse({"success": False, "error": "İcazəniz yoxdur"}, status=403)

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
    question = get_object_or_404(LabQuestion, id=pk)

    if question.block.lab.created_by != request.user:
        return JsonResponse({"success": False, "error": "İcazəniz yoxdur"}, status=403)

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

    block = get_object_or_404(LabBlock, id=block_id)

    if block.lab.created_by != request.user:
        return JsonResponse({"success": False, "error": "İcazəniz yoxdur"}, status=403)

    try:
        questions_text = request.POST.get("questions_text", "")

        if not questions_text.strip():
            return JsonResponse({"success": False, "error": "Boş mətn göndərildi"}, status=400)

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
                    "error": 'Heç bir sual tapılmadı. Format: "1. Sual metni" və ya "1) Sual metni"',
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
                "message": f"{created_count} sual uğurla əlavə edildi",
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
    lab = get_object_or_404(Lab, id=pk)

    if lab.created_by != request.user:
        messages.error(request, "İcazəniz yoxdur")
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
    submission = get_object_or_404(LabSubmission, id=pk)
    lab = submission.assignment.lab

    if lab.created_by != request.user:
        messages.error(request, "İcazəniz yoxdur")
        return redirect("labs:lab_submissions", pk=lab.id)

    if request.method == "POST":
        try:
            submission.score = request.POST.get("score")
            submission.feedback = request.POST.get("feedback", "")
            submission.status = "graded"
            submission.graded_by = request.user
            submission.graded_at = timezone.now()
            submission.save()

            messages.success(request, "Qiymət uğurla saxlanıldı!")
            return redirect("labs:lab_submissions", pk=lab.id)
        except Exception as e:
            messages.error(request, f"Xəta: {str(e)}")

    # Bu cəhdin cavablarını al
    try:
        # attempt_number field varsa
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

        # Əgər boşdursa, submission-a bağlı cavabları yoxla
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
        # Field yoxdursa, bütün cavabları göstər
        answers = (
            LabAnswer.objects.filter(lab=lab, student=submission.assignment.student, is_draft=False)
            .select_related("question")
            .order_by("question__block__order", "question__question_number")
        )

    context = {
        "submission": submission,
        "lab": lab,
        "answers": answers,
    }

    return render(request, "labs/grade_submission.html", context)


@login_required
def preview_randomization(request, pk):
    """Randomizasiyanı önizlə"""
    lab = get_object_or_404(Lab, id=pk)

    if lab.created_by != request.user:
        messages.error(request, "İcazəniz yoxdur")
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


# ═══════════════════════════════════════════════════════════════════════════════
# STUDENT VIEWS
# ═══════════════════════════════════════════════════════════════════════════════


@login_required
def lab_detail(request, pk):
    """Lab detalları - Tələbə görünüşü"""
    lab = get_object_or_404(Lab, id=pk)

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

    # Saved answers
    saved_answers = {}
    if request.user.is_authenticated:
        answers = LabAnswer.objects.filter(lab=lab, student=request.user)
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
    lab = get_object_or_404(Lab, id=pk)

    now = timezone.now()
    if lab.start_datetime and lab.end_datetime:
        is_open = lab.status == "published" and lab.start_datetime <= now <= lab.end_datetime
    else:
        is_open = lab.status == "published"

    if not is_open:
        return JsonResponse({"success": False, "error": "Lab bağlıdır"})

    try:
        # Cari cəhd nömrəsini tap
        assignment = LabAssignment.objects.filter(lab=lab, student=request.user).first()
        current_attempt = 1
        if assignment:
            submitted_count = LabSubmission.objects.filter(assignment=assignment).count()
            current_attempt = submitted_count + 1

        if request.content_type == "application/json":
            data = json.loads(request.body)
            question_id = data.get("question_id")
            answer = data.get("answer", "")
            answer_file = None
        else:
            question_id = request.POST.get("question_id")
            answer = request.POST.get("answer", "")
            answer_file = request.FILES.get("answer_file")

        question = get_object_or_404(LabQuestion, id=question_id)

        # Bu cəhd üçün cavab yarat/yenilə
        lab_answer, created = LabAnswer.objects.get_or_create(
            lab=lab,
            question=question,
            student=request.user,
            attempt_number=current_attempt,
            defaults={"answer": answer, "is_draft": True},
        )

        if not created:
            lab_answer.answer = answer
            lab_answer.is_draft = True

        if answer_file:
            lab_answer.answer_file = answer_file

        lab_answer.save()

        return JsonResponse({"success": True})

    except Exception as e:

        traceback.print_exc()
        return JsonResponse({"success": False, "error": str(e)})


@login_required
@require_POST
def submit_lab(request, pk):
    """Labı göndər"""
    lab = get_object_or_404(Lab, id=pk)

    now = timezone.now()
    if lab.start_datetime and lab.end_datetime:
        is_open = lab.status == "published" and lab.start_datetime <= now <= lab.end_datetime
    else:
        is_open = lab.status == "published"

    if not is_open and not lab.allow_late_submission:
        return JsonResponse({"success": False, "error": "Lab bağlıdır"})

    try:
        assignment = LabAssignment.objects.filter(lab=lab, student=request.user).first()
        if not assignment:
            return JsonResponse({"success": False, "error": "Təyinat tapılmadı"})

        current_attempts = LabSubmission.objects.filter(assignment=assignment).count()
        max_attempts = lab.max_attempts or 1

        if current_attempts >= max_attempts:
            return JsonResponse({"success": False, "error": "Cəhd sayınız bitib"})

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

    course = get_object_or_404(Course, id=course_id)

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

    course = get_object_or_404(Course, id=course_id)
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
    submission = get_object_or_404(LabSubmission, id=pk)

    if submission.assignment.lab.created_by != request.user:
        return JsonResponse({"success": False, "error": "İcazəniz yoxdur"}, status=403)

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
    lab = get_object_or_404(Lab, id=pk)

    assignment = LabAssignment.objects.filter(lab=lab, student=request.user).first()
    if not assignment:
        messages.error(request, "Təyinat tapılmadı")
        return redirect("courses:course_dashboard", pk=lab.course.id)

    all_submissions = LabSubmission.objects.filter(assignment=assignment).order_by("attempt_number")

    if not all_submissions.exists():
        messages.error(request, "Göndəriş tapılmadı")
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
                    duration = f"{hours} saat {minutes} dəqiqə"
                else:
                    duration = f"{minutes} dəqiqə"

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

    context = {
        "lab": lab,
        "submission": submission,
        "all_submissions": all_submissions,
        "answers": answers,
        "duration": duration,
        "attempt_number": attempt_number,
        "total_attempts": total_attempts,
    }

    return render(request, "labs/my_lab_answers.html", context)
