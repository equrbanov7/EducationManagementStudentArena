"""Rollar-arası kurs-roster API-ləri (F2 rol-skeleti, 2026-07-02).

Əvvəl student.py daxilində idi; bu endpointlər imtahan/lab yaratma
formalarında MÜƏLLİM tərəfindən istifadə olunur — shared qatına köçürüldü.
"""

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse

from apps.courses.models import CourseMembership

from ...lab_access import can_user_access_course_roster


@login_required
def api_get_groups(request, course_id):
    """Kurs qruplarını qaytarır"""
    from ._helpers import _get_tenant_course_or_404

    course = _get_tenant_course_or_404(request, course_id)

    # Authorization check: user must be course owner or have teacher/assistant role
    if not can_user_access_course_roster(request.user, course):
        raise PermissionDenied("You do not have permission to access this course roster.")

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
    from ._helpers import _get_tenant_course_or_404

    course = _get_tenant_course_or_404(request, course_id)

    # Authorization check: user must be course owner or have teacher/assistant role
    if not can_user_access_course_roster(request.user, course):
        raise PermissionDenied("You do not have permission to access this course roster.")

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
