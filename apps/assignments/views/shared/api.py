"""
assignments/views/api.py
─────────────────────────
API helper views for assignments (AJAX endpoints).

Contains:
- search_students
- search_groups
- students_by_groups
- remove_student_from_assignment
"""

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.http import JsonResponse

from apps.courses.models import CourseMembership
from apps.task_submission_core.access import can_user_access_course_roster

from ._helpers import _get_tenant_assignment_or_404, _get_tenant_course_or_404

# ════════════════════════════════════════════════════════════════════════════
# Search Students
# ════════════════════════════════════════════════════════════════════════════


@login_required
def search_students(request):
    """
    ┌─────────────────────────────────────────────────────────────────────────┐
    │ Tələbə axtarışı (AJAX)                                                  │
    │ GET /assignments/api/students/?q=<query>&course_id=<id>                 │
    │                                                                         │
    │ Select2 dropdown üçün istifadə olunur                                   │
    └─────────────────────────────────────────────────────────────────────────┘
    """
    query = request.GET.get("q", "")
    course_id = request.GET.get("course_id")

    if not course_id:
        return JsonResponse({"results": []})

    course = _get_tenant_course_or_404(request, course_id)

    # Authorization check: user must be course owner or have teacher/assistant role
    if not can_user_access_course_roster(request.user, course):
        raise PermissionDenied("You do not have permission to access this course roster.")

    # Kursda olan tələbələri axtar
    student_memberships = (
        course.memberships.filter(role="student")
        .filter(
            Q(user__username__icontains=query)
            | Q(user__first_name__icontains=query)
            | Q(user__last_name__icontains=query)
        )
        .select_related("user")[:10]
    )

    results = [
        {
            "id": m.user.id,
            "text": (f"{m.user.get_full_name()} ({m.user.username})" if m.user.first_name else m.user.username),
            "group_name": m.group_name or "",
        }
        for m in student_memberships
    ]

    return JsonResponse({"results": results})


# ════════════════════════════════════════════════════════════════════════════
# Search Groups
# ════════════════════════════════════════════════════════════════════════════


@login_required
def search_groups(request):
    """
    ┌─────────────────────────────────────────────────────────────────────────┐
    │ Qrup axtarışı (AJAX)                                                    │
    │ GET /assignments/api/groups/?q=<query>&course_id=<id>                   │
    │                                                                         │
    │ Kursdakı unique group_name-ləri qaytarır                                │
    └─────────────────────────────────────────────────────────────────────────┘
    """
    query = request.GET.get("q", "")
    course_id = request.GET.get("course_id")

    if not course_id:
        return JsonResponse({"results": []})

    course = _get_tenant_course_or_404(request, course_id)

    # Authorization check: user must be course owner or have teacher/assistant role
    if not can_user_access_course_roster(request.user, course):
        raise PermissionDenied("You do not have permission to access this course roster.")

    # Unique qrup adlarını tap
    group_names = (
        CourseMembership.objects.filter(course=course, group_name__icontains=query)
        .exclude(group_name="")
        .values_list("group_name", flat=True)
        .distinct()[:10]
    )

    results = [{"id": name, "text": name} for name in group_names]

    return JsonResponse({"results": results})


# ════════════════════════════════════════════════════════════════════════════
# Students By Groups
# ════════════════════════════════════════════════════════════════════════════


@login_required
def students_by_groups(request):
    """
    ┌─────────────────────────────────────────────────────────────────────────┐
    │ Qruplara görə tələbələri qaytarır (AJAX)                                │
    │ GET /assignments/api/students-by-groups/?course_id=<id>&groups=<g1,g2>  │
    │                                                                         │
    │ Modal-da qrup seçildikdə tələbə listini yeniləmək üçün                  │
    └─────────────────────────────────────────────────────────────────────────┘
    """
    course_id = request.GET.get("course_id")
    groups_param = request.GET.get("groups", "")

    if not course_id or not groups_param:
        return JsonResponse({"students": []})

    course = _get_tenant_course_or_404(request, course_id)

    # Authorization check: user must be course owner or have teacher/assistant role
    if not can_user_access_course_roster(request.user, course):
        raise PermissionDenied("You do not have permission to access this course roster.")

    group_names = [g.strip() for g in groups_param.split(",") if g.strip()]

    if not group_names:
        return JsonResponse({"students": []})

    # Qruplardakı tələbələri tap
    memberships = (
        CourseMembership.objects.filter(course=course, group_name__in=group_names, role="student")
        .select_related("user")
        .order_by("group_name", "user__first_name")
    )

    # Dublikatları çıxar
    students = []
    seen = set()
    for m in memberships:
        if m.user.id not in seen:
            seen.add(m.user.id)
            students.append(
                {
                    "id": m.user.id,
                    "name": m.user.get_full_name() or m.user.username,
                    "group_name": m.group_name,
                }
            )

    return JsonResponse({"students": students})


# ════════════════════════════════════════════════════════════════════════════
# Remove Student From Assignment (Manual Override)
# ════════════════════════════════════════════════════════════════════════════


@login_required
def remove_student_from_assignment(request, pk):
    """
    ┌─────────────────────────────────────────────────────────────────────────┐
    │ Tələbəni tapşırıqdan çıxar (müəllim tərəfindən manual override)         │
    │ POST /assignments/<pk>/remove-student/                                  │
    │                                                                         │
    │ Body: student_id=<id>                                                   │
    │                                                                         │
    │ Bu əməliyyat yalnız assignment.assigned_students M2M-ə təsir edir;      │
    │ tələbənin qrupu və ya kurs üzvlüyü dəyişmir.                            │
    └─────────────────────────────────────────────────────────────────────────┘
    """
    from core.permissions import request_has_permission

    if request.method != "POST":
        return JsonResponse({"success": False, "error": "Method not allowed."}, status=405)

    assignment = _get_tenant_assignment_or_404(request, pk)

    # The user must own the course AND have the assignment.edit permission.
    if (
        not request.user.is_teacher_or_above
        or assignment.course.owner != request.user
        or not request_has_permission(request, "assignment.edit")
    ):
        raise PermissionDenied("You do not have permission to modify this assignment.")

    student_id = (request.POST.get("student_id") or "").strip()
    if not student_id or not student_id.isdigit():
        return JsonResponse({"success": False, "error": "A valid student_id is required."}, status=400)

    membership = (
        CourseMembership.objects.filter(course=assignment.course, user_id=int(student_id))
        .select_related("user")
        .first()
    )
    if not membership:
        return JsonResponse({"success": False, "error": "Student not found."}, status=404)

    student = membership.user
    assignment.assigned_students.remove(student)

    return JsonResponse(
        {
            "success": True,
            "message": f"{student.get_full_name() or student.username} tapşırıqdan çıxarıldı.",
        }
    )
