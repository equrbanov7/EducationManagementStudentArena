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
from django.db import transaction
from django.http import JsonResponse
from django.utils import timezone
from django.utils.translation import pgettext
from django.views.decorators.http import require_http_methods

from apps.courses.models import CourseMembership
from core.helpers import parse_form_datetime

from ..shared._helpers import _get_tenant_assignment_or_404, _get_tenant_course_or_404

User = get_user_model()

logger = logging.getLogger(__name__)


def _course_student_users(course, raw_ids):
    """``students[]`` → YALNIZ bu kursun tələbə üzvləri (2026-09-28).

    Əvvəl ``User.objects.filter(id__in=...)`` idi — istənilən istifadəçi id-si
    (başqa kurs/tenant, müəllim) tapşırığa bağlana bilirdi.
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


def _local_input_value(value):
    """``datetime-local`` input dəyəri — UTC yox, layihə vaxt qurşağında.

    Əvvəl UTC ``strftime`` qaytarılırdı; toxunulmamış redaktə hər saxlamada
    tarixi qurşaq fərqi qədər (Bakı: −4 saat) sürüşdürürdü.
    """
    if not value:
        return ""
    return timezone.localtime(value).strftime("%Y-%m-%dT%H:%M")


def _clean_status(raw_value, fallback):
    """Status yalnız model seçimlərindən biri ola bilər; əks halda ``fallback``."""
    from apps.assignments.models import Assignment

    valid = {key for key, _label in Assignment.STATUS_CHOICES}
    return raw_value if raw_value in valid else fallback


def _edit_target_payload(course, assigned_ids):
    """Redaktə modalı üçün qrup + «qrupda olub təyin olunmayan» tələbələr.

    Modal qrupu işarələyəndə qrupun bütün tələbələrini avtomatik seçir;
    ``group_excluded_student_ids`` olmadan qismən seçim toxunulmamış
    saxlamada bütün qrupa genişlənirdi (2026-09-28).
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
# Create Assignment
# ════════════════════════════════════════════════════════════════════════════


@login_required
@require_http_methods(["POST"])
@transaction.atomic
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
    from apps.notifications.public import notify_task_assignment

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
            start_date=parse_form_datetime(request.POST.get("start_date")),
            deadline=parse_form_datetime(request.POST.get("deadline")),
            max_attempts=request.POST.get("max_attempts", 1),
            max_score=request.POST.get("max_score", 100),
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
            assignment.assigned_students.set(_course_student_users(course, student_ids))
        elif group_names:
            # Qrup seçilib - qrupdakı bütün tələbələri əlavə et
            assignment.assigned_students.set(_course_group_students(course, group_names))

        if assignment.status in {"active", "published"}:
            notify_task_assignment(
                task=assignment,
                user_ids=assignment.assigned_students.values_list("id", flat=True),
                task_kind="assignment",
            )

        messages.success(request, pgettext("assignments.views.message", "assignment_created"))
        return JsonResponse({"success": True, "assignment_id": assignment.id})

    except Exception:

        transaction.set_rollback(True)
        logger.exception("Unexpected error in create_assignment")
        return JsonResponse({"success": False, "error": "An unexpected error occurred."}, status=500)


# ════════════════════════════════════════════════════════════════════════════
# Edit Assignment
# ════════════════════════════════════════════════════════════════════════════


@login_required
@require_http_methods(["GET", "POST"])
@transaction.atomic
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

        # Tələbələrin qrupları + həmin qruplarda təyin OLUNMAYANLAR
        assigned_groups, excluded_ids = _edit_target_payload(assignment.course, assigned_student_ids)

        data = {
            "id": assignment.id,
            "title": assignment.title,
            "description": assignment.description,
            "start_date": _local_input_value(assignment.start_date),
            "deadline": _local_input_value(assignment.deadline),
            "max_attempts": assignment.max_attempts,
            "max_score": assignment.max_score,
            "status": assignment.status,
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
        previous_status = assignment.status
        previous_recipient_ids = set(assignment.assigned_students.values_list("id", flat=True))
        assignment.title = request.POST.get("title")
        assignment.description = request.POST.get("description", "")
        assignment.start_date = parse_form_datetime(request.POST.get("start_date"))
        assignment.deadline = parse_form_datetime(request.POST.get("deadline"))
        assignment.max_attempts = request.POST.get("max_attempts") or assignment.max_attempts
        # Modalda max_score sahəsi yoxdur — göndərilməyibsə mövcud dəyər qalır (əvvəl 100-ə sıfırlanırdı).
        assignment.max_score = request.POST.get("max_score") or assignment.max_score
        assignment.status = _clean_status(request.POST.get("status"), assignment.status)
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
            assignment.assigned_students.set(_course_student_users(assignment.course, student_ids))
        elif group_names:
            assignment.assigned_students.set(_course_group_students(assignment.course, group_names))
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
            from apps.notifications.public import notify_task_assignment

            notify_task_assignment(
                task=assignment,
                user_ids=new_recipient_ids,
                task_kind="assignment",
            )

        messages.success(request, pgettext("assignments.views.message", "assignment_updated"))
        return JsonResponse({"success": True, "message": pgettext("assignments.views.message", "assignment_updated")})

    except Exception:

        transaction.set_rollback(True)
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
