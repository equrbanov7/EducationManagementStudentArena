"""
assignments/views/crud.py
──────────────────────
CRUD operations for assignments.

Contains:
- create_assignment
- edit_assignment
- delete_assignment
"""

import logging

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.utils.translation import pgettext
from django.views.decorators.http import require_http_methods

from apps.courses.models import CourseMembership

from ._helpers import _get_tenant_assignment_or_404, _get_tenant_course_or_404

User = get_user_model()

logger = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════════════════════
# Create Assignment
# ════════════════════════════════════════════════════════════════════════════


@login_required
@require_http_methods(["POST"])
def create_assignment(request, course_id):
    """
    ┌─────────────────────────────────────────────────────────────────────────┐
    │ Kurs işi yaratma                                                        │
    │ POST /assignments/create/<course_id>/                                      │
    │                                                                         │
    │ Tələb olunan fieldlər: title, start_date, deadline                      │
    │ Opsional: description, max_attempts, max_score, status                  │
    │ Təyin etmə: group_names[] və ya students[]                              │
    └─────────────────────────────────────────────────────────────────────────┘
    """
    from apps.assignments.models import Assignment
    from apps.notifications.services import notify_task_assignment

    course = _get_tenant_course_or_404(request, course_id)

    # İcazə yoxlaması - yalnız kurs sahibi
    if not request.user.is_teacher_or_above or course.owner != request.user:
        return JsonResponse(
            {"success": False, "error": pgettext("assignments.views.message", "permission_denied")},
            status=403,
        )

    try:
        # Assignment yarat
        assignment = Assignment.objects.create(
            course=course,
            title=request.POST.get("title"),
            description=request.POST.get("description", ""),
            start_date=request.POST.get("start_date"),
            deadline=request.POST.get("deadline"),
            max_attempts=request.POST.get("max_attempts", 1),
            max_score=request.POST.get("max_score", 100),
            status=request.POST.get("status", "active"),
        )

        # ════════════════════════════════════════════════════════════
        # TƏLƏBƏLƏRİ TƏYİN ETMƏ MƏNTİQİ:
        # 1. Əgər student_ids varsa → YALNIZ seçilmiş tələbələr
        # 2. Əgər student_ids yoxdur, amma group_names varsa → Bütün qrup
        # ════════════════════════════════════════════════════════════
        group_names = request.POST.getlist("group_names[]")
        student_ids = request.POST.getlist("students[]")

        if student_ids:
            # Konkret tələbələr seçilib
            students = User.objects.filter(id__in=student_ids)
            assignment.assigned_students.set(students)
        elif group_names:
            # Qrup seçilib - qrupdakı bütün tələbələri əlavə et
            group_students = User.objects.filter(
                course_memberships__course=course,
                course_memberships__group_name__in=group_names,
                course_memberships__role="student",
            ).distinct()
            assignment.assigned_students.set(group_students)

        if assignment.status in {"active", "published"}:
            notify_task_assignment(
                task=assignment,
                user_ids=assignment.assigned_students.values_list("id", flat=True),
                task_kind="assignment",
            )

        messages.success(request, pgettext("assignments.views.message", "assignment_created"))
        return JsonResponse({"success": True, "assignment_id": assignment.id})

    except Exception:
        logger.exception("Unexpected error in create_assignment")
        return JsonResponse({"success": False, "error": "An unexpected error occurred."}, status=500)


# ════════════════════════════════════════════════════════════════════════════
# Edit Assignment
# ════════════════════════════════════════════════════════════════════════════


@login_required
@require_http_methods(["GET", "POST"])
def edit_assignment(request, pk):
    """
    ┌─────────────────────────────────────────────────────────────────────────┐
    │ Kurs işini redaktə etmək                                                │
    │ GET  /assignments/<pk>/edit/ → JSON data qaytarır                          │
    │ POST /assignments/<pk>/edit/ → Yeniləyir                                   │
    └─────────────────────────────────────────────────────────────────────────┘
    """
    assignment = _get_tenant_assignment_or_404(request, pk)

    # İcazə yoxlaması
    if not request.user.is_teacher_or_above or assignment.course.owner != request.user:
        return JsonResponse(
            {"success": False, "error": pgettext("assignments.views.message", "permission_denied")},
            status=403,
        )

    # ─────────────────────────────────────────────────────────────────────────
    # GET - Mövcud məlumatları JSON olaraq qaytar
    # ─────────────────────────────────────────────────────────────────────────
    if request.method == "GET":
        assigned_students = list(assignment.assigned_students.values("id", "username", "first_name", "last_name"))
        assigned_student_ids = [s["id"] for s in assigned_students]

        # Tələbələrin qruplarını tap
        assigned_groups = list(
            CourseMembership.objects.filter(course=assignment.course, user_id__in=assigned_student_ids, role="student")
            .exclude(group_name="")
            .values_list("group_name", flat=True)
            .distinct()
        )

        data = {
            "id": assignment.id,
            "title": assignment.title,
            "description": assignment.description,
            "start_date": (assignment.start_date.strftime("%Y-%m-%dT%H:%M") if assignment.start_date else ""),
            "deadline": (assignment.deadline.strftime("%Y-%m-%dT%H:%M") if assignment.deadline else ""),
            "max_attempts": assignment.max_attempts,
            "max_score": assignment.max_score,
            "status": assignment.status,
            "group_names": assigned_groups,
            "student_ids": assigned_student_ids,
            "students": [
                {
                    "id": s["id"],
                    "name": f"{s['first_name']} {s['last_name']}".strip() or s["username"],
                }
                for s in assigned_students
            ],
        }
        return JsonResponse({"success": True, "data": data})

    # ─────────────────────────────────────────────────────────────────────────
    # POST - Yenilə
    # ─────────────────────────────────────────────────────────────────────────
    try:
        previous_status = assignment.status
        previous_recipient_ids = set(assignment.assigned_students.values_list("id", flat=True))
        assignment.title = request.POST.get("title")
        assignment.description = request.POST.get("description", "")
        assignment.start_date = request.POST.get("start_date")
        assignment.deadline = request.POST.get("deadline")
        assignment.max_attempts = request.POST.get("max_attempts", 1)
        assignment.max_score = request.POST.get("max_score", 100)
        assignment.status = request.POST.get("status", "active")
        assignment.save()

        # ════════════════════════════════════════════════════════════
        # TƏLƏBƏLƏRİ TƏYİN ETMƏ MƏNTİQİ:
        # 1. Əgər student_ids varsa → YALNIZ seçilmiş tələbələr
        # 2. Əgər student_ids yoxdur, amma group_names varsa → Bütün qrup
        # 3. Heç biri yoxdursa → Boş
        # ════════════════════════════════════════════════════════════
        group_names = request.POST.getlist("group_names[]")
        student_ids = request.POST.getlist("students[]")

        if student_ids:
            students = User.objects.filter(id__in=student_ids)
            assignment.assigned_students.set(students)
        elif group_names:
            group_students = User.objects.filter(
                course_memberships__course=assignment.course,
                course_memberships__group_name__in=group_names,
                course_memberships__role="student",
            ).distinct()
            assignment.assigned_students.set(group_students)
        else:
            assignment.assigned_students.clear()

        current_recipient_ids = set(assignment.assigned_students.values_list("id", flat=True))
        should_notify_all = previous_status not in {"active", "published"} and assignment.status in {
            "active",
            "published",
        }
        new_recipient_ids = (
            current_recipient_ids if should_notify_all else (current_recipient_ids - previous_recipient_ids)
        )
        if new_recipient_ids and assignment.status in {"active", "published"}:
            from apps.notifications.services import notify_task_assignment

            notify_task_assignment(
                task=assignment,
                user_ids=new_recipient_ids,
                task_kind="assignment",
            )

        messages.success(request, pgettext("assignments.views.message", "assignment_updated"))
        return JsonResponse({"success": True, "message": pgettext("assignments.views.message", "assignment_updated")})

    except Exception:
        logger.exception("Unexpected error in edit_assignment")
        return JsonResponse({"success": False, "error": "An unexpected error occurred."}, status=500)


# ════════════════════════════════════════════════════════════════════════════
# Delete Assignment
# ════════════════════════════════════════════════════════════════════════════


@login_required
@require_http_methods(["POST"])
def delete_assignment(request, pk):
    """
    ┌─────────────────────────────────────────────────────────────────────────┐
    │ Kurs işini silmək                                                       │
    │ POST /assignments/<pk>/delete/                                             │
    └─────────────────────────────────────────────────────────────────────────┘
    """
    assignment = _get_tenant_assignment_or_404(request, pk)

    if not request.user.is_teacher_or_above or assignment.course.owner != request.user:
        return JsonResponse(
            {"success": False, "error": pgettext("assignments.views.message", "permission_denied")},
            status=403,
        )

    try:
        assignment.delete()
        messages.success(request, pgettext("assignments.views.message", "assignment_deleted"))
        return JsonResponse({"success": True, "message": pgettext("assignments.views.message", "assignment_deleted")})
    except Exception:
        logger.exception("Unexpected error in delete_assignment")
        return JsonResponse({"success": False, "error": "An unexpected error occurred."}, status=500)
