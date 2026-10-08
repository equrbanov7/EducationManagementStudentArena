"""
projects/views/crud.py
──────────────────────
CRUD operations for projects.

Contains:
- create_project
- edit_project
- delete_project
"""

import logging

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import JsonResponse
from django.utils import timezone
from django.utils.translation import pgettext
from django.views.decorators.http import require_http_methods

from apps.courses.models import CourseMembership
from core.helpers import parse_form_datetime

from ..shared._helpers import _get_tenant_course_or_404, _get_tenant_project_or_404

User = get_user_model()

logger = logging.getLogger(__name__)


def _course_student_users(course, raw_ids):
    """``students[]`` → YALNIZ bu kursun tələbə üzvləri (2026-09-28).

    Əvvəl ``User.objects.filter(id__in=...)`` idi — istənilən istifadəçi id-si
    (başqa kurs/tenant, müəllim) layihəyə bağlana bilirdi.
    """
    ids = {int(value) for value in raw_ids if str(value).strip().isdigit()}
    if not ids:
        return User.objects.none()
    return User.objects.filter(
        id__in=ids,
        course_memberships__course=course,
        course_memberships__role="student",
    ).distinct()


def _course_group_students(course, group_names):
    return User.objects.filter(
        course_memberships__course=course,
        course_memberships__group_name__in=group_names,
        course_memberships__role="student",
    ).distinct()


def _clean_status(raw_value, fallback):
    """Status yalnız model seçimlərindən biri ola bilər; əks halda ``fallback``."""
    from apps.projects.models import Project

    valid = {key for key, _label in Project.STATUS_CHOICES}
    return raw_value if raw_value in valid else fallback


def _local_input_value(value):
    """``datetime-local`` dəyəri layihə vaxt qurşağında (UTC ``strftime`` hər
    toxunulmamış saxlamada tarixi −4 saat sürüşdürürdü)."""
    if not value:
        return ""
    return timezone.localtime(value).strftime("%Y-%m-%dT%H:%M")


def _edit_target_payload(course, assigned_ids):
    """Redaktə modalı üçün qruplar + «qrupda olub təyin olunmayan» tələbələr.

    ``group_excluded_student_ids`` olmadan modal qrupun bütün tələbələrini
    avtomatik seçir və qismən seçim toxunulmamış saxlamada genişlənirdi.
    """
    memberships = CourseMembership.objects.filter(course=course, role="student").exclude(group_name="")
    group_names = sorted(set(memberships.filter(user_id__in=assigned_ids).values_list("group_name", flat=True)))
    excluded_ids = sorted(
        set(
            memberships.filter(group_name__in=group_names)
            .exclude(user_id__in=assigned_ids)
            .values_list("user_id", flat=True)
        )
    )
    return group_names, excluded_ids


# ════════════════════════════════════════════════════════════════════════════
# Create Project
# ════════════════════════════════════════════════════════════════════════════


@login_required
@require_http_methods(["POST"])
@transaction.atomic
def create_project(request, course_id):
    """
    ┌─────────────────────────────────────────────────────────────────────────┐
    │ Kurs işi yaratma                                                        │
    │ POST /projects/create/<course_id>/                                      │
    │                                                                         │
    │ Tələb olunan fieldlər: title, start_date, deadline                      │
    │ Opsional: description, max_attempts, max_score, status                  │
    │ Təyin etmə: group_names[] və ya students[]                              │
    └─────────────────────────────────────────────────────────────────────────┘
    """
    from apps.notifications.public import notify_task_assignment
    from apps.projects.models import Project

    course = _get_tenant_course_or_404(request, course_id)

    # İcazə yoxlaması - yalnız kurs sahibi
    if not request.user.is_teacher_or_above or course.owner != request.user:
        return JsonResponse(
            {"success": False, "error": pgettext("projects.views.message", "permission_denied")},
            status=403,
        )

    try:
        # Project yarat
        project = Project.objects.create(
            course=course,
            title=request.POST.get("title"),
            description=request.POST.get("description", ""),
            start_date=parse_form_datetime(request.POST.get("start_date")),
            deadline=parse_form_datetime(request.POST.get("deadline")),
            max_attempts=request.POST.get("max_attempts") or 1,
            max_score=request.POST.get("max_score") or 100,
            status=_clean_status(request.POST.get("status"), "active"),
        )

        # ════════════════════════════════════════════════════════════
        # TƏLƏBƏLƏRİ TƏYİN ETMƏ MƏNTİQİ:
        # 1. Əgər student_ids varsa → YALNIZ seçilmiş tələbələr
        # 2. Əgər student_ids yoxdur, amma group_names varsa → Bütün qrup
        # ════════════════════════════════════════════════════════════
        group_names = request.POST.getlist("group_names[]")
        student_ids = request.POST.getlist("students[]")

        if student_ids:
            # Konkret tələbələr seçilib (yalnız bu kursun tələbələri)
            project.assigned_students.set(_course_student_users(course, student_ids))
        elif group_names:
            # Qrup seçilib - qrupdakı bütün tələbələri əlavə et
            project.assigned_students.set(_course_group_students(course, group_names))

        if project.status == "active":
            notify_task_assignment(
                task=project,
                user_ids=project.assigned_students.values_list("id", flat=True),
                task_kind="project",
            )

        messages.success(request, pgettext("projects.views.message", "project_created"))
        return JsonResponse({"success": True, "project_id": project.id})

    except ValidationError as exc:
        # 2026-10-08: oxunmayan tarix-saat («gg.aa.iiii ss:dd») — aydın mesaj, 500 yox.
        transaction.set_rollback(True)
        return JsonResponse({"success": False, "error": exc.messages[0]}, status=400)
    except Exception:

        transaction.set_rollback(True)
        logger.exception("Unexpected error in create_project")
        return JsonResponse({"success": False, "error": "An unexpected error occurred."}, status=500)


# ════════════════════════════════════════════════════════════════════════════
# Edit Project
# ════════════════════════════════════════════════════════════════════════════


@login_required
@require_http_methods(["GET", "POST"])
@transaction.atomic
def edit_project(request, pk):
    """
    ┌─────────────────────────────────────────────────────────────────────────┐
    │ Kurs işini redaktə etmək                                                │
    │ GET  /projects/<pk>/edit/ → JSON data qaytarır                          │
    │ POST /projects/<pk>/edit/ → Yeniləyir                                   │
    └─────────────────────────────────────────────────────────────────────────┘
    """
    project = _get_tenant_project_or_404(request, pk)

    # İcazə yoxlaması
    if not request.user.is_teacher_or_above or project.course.owner != request.user:
        return JsonResponse(
            {"success": False, "error": pgettext("projects.views.message", "permission_denied")},
            status=403,
        )

    # ─────────────────────────────────────────────────────────────────────────
    # GET - Mövcud məlumatları JSON olaraq qaytar
    # ─────────────────────────────────────────────────────────────────────────
    if request.method == "GET":
        assigned_students = list(project.assigned_students.values("id", "username", "first_name", "last_name"))
        assigned_student_ids = [s["id"] for s in assigned_students]

        # Tələbələrin qrupları + həmin qruplarda təyin OLUNMAYANLAR
        assigned_groups, excluded_ids = _edit_target_payload(project.course, assigned_student_ids)

        data = {
            "id": project.id,
            "title": project.title,
            "description": project.description,
            "start_date": _local_input_value(project.start_date),
            "deadline": _local_input_value(project.deadline),
            "max_attempts": project.max_attempts,
            "max_score": project.max_score,
            "status": project.status,
            "group_names": assigned_groups,
            "group_excluded_student_ids": excluded_ids,
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
        previous_status = project.status
        previous_recipient_ids = set(project.assigned_students.values_list("id", flat=True))
        project.title = request.POST.get("title")
        project.description = request.POST.get("description", "")
        project.start_date = parse_form_datetime(request.POST.get("start_date"))
        project.deadline = parse_form_datetime(request.POST.get("deadline"))
        project.max_attempts = request.POST.get("max_attempts") or project.max_attempts
        project.max_score = request.POST.get("max_score") or project.max_score
        project.status = _clean_status(request.POST.get("status"), project.status)
        project.save()

        # ════════════════════════════════════════════════════════════
        # TƏLƏBƏLƏRİ TƏYİN ETMƏ MƏNTİQİ:
        # 1. Əgər student_ids varsa → YALNIZ seçilmiş tələbələr
        # 2. Əgər student_ids yoxdur, amma group_names varsa → Bütün qrup
        # 3. Heç biri yoxdursa → Boş
        # ════════════════════════════════════════════════════════════
        group_names = request.POST.getlist("group_names[]")
        student_ids = request.POST.getlist("students[]")

        if student_ids:
            project.assigned_students.set(_course_student_users(project.course, student_ids))
        elif group_names:
            project.assigned_students.set(_course_group_students(project.course, group_names))
        else:
            project.assigned_students.clear()

        current_recipient_ids = set(project.assigned_students.values_list("id", flat=True))
        should_notify_all = previous_status != "active" and project.status == "active"
        new_recipient_ids = (
            current_recipient_ids if should_notify_all else (current_recipient_ids - previous_recipient_ids)
        )
        if new_recipient_ids and project.status == "active":
            from apps.notifications.public import notify_task_assignment

            notify_task_assignment(
                task=project,
                user_ids=new_recipient_ids,
                task_kind="project",
            )

        messages.success(request, pgettext("projects.views.message", "project_updated"))
        return JsonResponse({"success": True, "message": pgettext("projects.views.message", "project_updated")})

    except ValidationError as exc:
        # 2026-10-08: oxunmayan tarix-saat («gg.aa.iiii ss:dd») — aydın mesaj, 500 yox.
        transaction.set_rollback(True)
        return JsonResponse({"success": False, "error": exc.messages[0]}, status=400)
    except Exception:

        transaction.set_rollback(True)
        logger.exception("Unexpected error in edit_project")
        return JsonResponse({"success": False, "error": "An unexpected error occurred."}, status=500)


# ════════════════════════════════════════════════════════════════════════════
# Delete Project
# ════════════════════════════════════════════════════════════════════════════


@login_required
@require_http_methods(["POST"])
def delete_project(request, pk):
    """
    ┌─────────────────────────────────────────────────────────────────────────┐
    │ Kurs işini silmək                                                       │
    │ POST /projects/<pk>/delete/                                             │
    └─────────────────────────────────────────────────────────────────────────┘
    """
    project = _get_tenant_project_or_404(request, pk)

    if not request.user.is_teacher_or_above or project.course.owner != request.user:
        return JsonResponse(
            {"success": False, "error": pgettext("projects.views.message", "permission_denied")},
            status=403,
        )

    try:
        project.delete()
        messages.success(request, pgettext("projects.views.message", "project_deleted"))
        return JsonResponse({"success": True, "message": pgettext("projects.views.message", "project_deleted")})
    except Exception:
        logger.exception("Unexpected error in delete_project")
        return JsonResponse({"success": False, "error": "An unexpected error occurred."}, status=500)
