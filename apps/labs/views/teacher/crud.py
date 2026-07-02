"""
Labs Views - Lab CRUD Operations
Lab yaratma, redaktə, silmə və yayımlama
"""

import logging

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.urls import reverse
from django.utils.translation import pgettext
from django.views.decorators.http import require_http_methods, require_POST

from ...models import Lab
from ..shared._helpers import (
    _get_tenant_course_or_404,
    _get_tenant_lab_or_404,
    _normalize_extensions,
    _parse_max_size_mb,
    _validate_and_prepare_lab_upload,
)

logger = logging.getLogger(__name__)
User = get_user_model()


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
            created_by=request.user,
        )

        if student_ids:
            valid_ids = [int(sid) for sid in student_ids if str(sid).isdigit()]
            lab.allowed_students.set(User.objects.filter(pk__in=valid_ids))

        if teacher_file is not None:
            lab.teacher_files = teacher_file
            lab.save()

        return JsonResponse({"success": True, "lab_id": lab.id})

    except ValidationError as exc:
        return JsonResponse({"success": False, "error": exc.messages[0]}, status=400)
    except Exception:
        logger.exception("Unexpected error in create_lab")
        return JsonResponse({"success": False, "error": "An unexpected error occurred."}, status=500)


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
        student_ids = list(lab.allowed_students.values_list("id", flat=True))

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
        previous_status = lab.status
        from apps.notifications.public import get_lab_assigned_user_ids, notify_task_assignment

        previous_recipient_ids = get_lab_assigned_user_ids(lab)
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

        # Update allowed_students M2M relation
        valid_ids = [int(sid) for sid in student_ids if str(sid).isdigit()]
        lab.allowed_students.set(User.objects.filter(pk__in=valid_ids))

        current_recipient_ids = get_lab_assigned_user_ids(lab)
        should_notify_all = previous_status != "published" and lab.status == "published"
        new_recipient_ids = (
            current_recipient_ids if should_notify_all else (current_recipient_ids - previous_recipient_ids)
        )
        if new_recipient_ids and lab.status == "published":
            notify_task_assignment(
                task=lab,
                user_ids=new_recipient_ids,
                task_kind="lab",
            )

        return JsonResponse({"success": True})

    except ValidationError as exc:
        return JsonResponse({"success": False, "error": exc.messages[0]}, status=400)
    except Exception:
        logger.exception("Unexpected error in edit_lab")
        return JsonResponse({"success": False, "error": "An unexpected error occurred."}, status=500)


@login_required
@require_POST
def delete_lab(request, pk):
    """Lab sil"""
    lab = _get_tenant_lab_or_404(request, pk)

    if lab.created_by != request.user:
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
    from apps.notifications.public import get_lab_assigned_user_ids, notify_task_assignment

    notify_task_assignment(
        task=lab,
        user_ids=get_lab_assigned_user_ids(lab),
        task_kind="lab",
    )
    messages.success(request, pgettext("labs.view.message", "lab_published"))
    return JsonResponse({"success": True})
