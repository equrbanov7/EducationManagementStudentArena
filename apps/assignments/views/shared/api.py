"""
assignments/views/api.py
─────────────────────────
API helper views for assignments (AJAX endpoints).

Contains:
- search_groups
- students_by_groups

WP9a (2026-10-10): çağıranı olmayan ``search_students`` və
``remove_student_from_assignment`` silindi.
"""

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.http import JsonResponse

from apps.courses.models import CourseMembership
from apps.task_submission_core.public import can_user_access_course_roster
from core.search_text import tolerant_q

from ._helpers import _get_tenant_course_or_404

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
    # «234king» → «234 K ing»: qrup adı kod rejimində (sahib 2026-09-26)
    # 2026-09-28: `[:10]` limiti götürüldü — modal `q` göndərmir və kursun
    # 10-dan çox qrupu olanda qalanları seçmək mümkün deyildi (kurs qrupları azdır).
    group_q = tolerant_q(query, ("group_name",), compact=True)
    group_names = (
        CourseMembership.objects.filter(course=course, role="student")
        .filter(group_q if group_q is not None else Q())
        .exclude(group_name="")
        .values_list("group_name", flat=True)
        .distinct()
        .order_by("group_name")
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
