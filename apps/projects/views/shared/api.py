"""
projects/views/api.py
─────────────────────
API helper views for projects (AJAX endpoints).

Contains:
- api_get_groups
- api_get_students
"""

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse

from apps.courses.models import CourseMembership
from apps.task_submission_core.public import can_user_access_course_roster

from ._helpers import _get_tenant_course_or_404

# ════════════════════════════════════════════════════════════════════════════
# API Get Groups
# ════════════════════════════════════════════════════════════════════════════


@login_required
def api_get_groups(request):
    """
    ┌─────────────────────────────────────────────────────────────────────────┐
    │ Kursdakı qrupları qaytarır (AJAX)                                       │
    │ GET /projects/api/groups/?course_id=<id>                                │
    └─────────────────────────────────────────────────────────────────────────┘
    """
    course_id = request.GET.get("course_id")

    if not course_id:
        return JsonResponse({"groups": []})

    course = _get_tenant_course_or_404(request, course_id)

    # Authorization check: user must be course owner or have teacher/assistant role
    if not can_user_access_course_roster(request.user, course):
        raise PermissionDenied("You do not have permission to access this course roster.")

    # Unique qrup adlarını tap
    groups = (
        CourseMembership.objects.filter(course=course, role="student")
        .exclude(group_name="")
        .exclude(group_name__isnull=True)
        .values_list("group_name", flat=True)
        .distinct()
        .order_by("group_name")
    )

    return JsonResponse({"groups": [{"id": i, "name": name} for i, name in enumerate(groups, 1)]})


# ════════════════════════════════════════════════════════════════════════════
# API Get Students
# ════════════════════════════════════════════════════════════════════════════


@login_required
def api_get_students(request):
    """
    ┌─────────────────────────────────────────────────────────────────────────┐
    │ Qruplardakı tələbələri qaytarır (AJAX)                                  │
    │ GET /projects/api/students/?course_id=<id>&groups=<g1,g2>               │
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
