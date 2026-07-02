"""Kurs dashboard-una assignments bölməsinin kontribusiyası.

M2 (2026-07-02): bu məntiq apps/courses/views/shared/dashboard.py-dən
köçürülüb — Submission sorğuları öz modulunda yaşayır, courses artıq
assignments-i import etmir. Qeydiyyat: AssignmentsConfig.ready().
Davranış birə-birdir (bax dashboard_sources provider müqaviləsi).
"""

from django.db.models import Count

from apps.assignments.models import Submission


def build_course_dashboard_context(*, course, user, membership, can_manage, is_student):
    """Dashboard "Sərbəst işlər" bölməsi: müəllim hamısını, tələbə yalnız
    özünə təyin olunmuşları (arxivlənmişlər istisna) görür."""
    if can_manage:
        # MÜƏLLİM - bütün assignment-lar
        return {
            "assignments": course.assignments.all().order_by("-created_at"),
            "assignments_with_user_data": [],
        }

    if not is_student:
        return {"assignments": [], "assignments_with_user_data": []}

    # TƏLƏBƏ - arxivlənmişlər istisna (status != 'inactive' filter)
    assignments_qs = (
        course.assignments.filter(assigned_students=user).exclude(status="inactive").order_by("-created_at")
    )

    # Batch-fetch submission counts for this user across all assignments
    # to avoid N+1 queries (one query instead of one per assignment).
    assignment_ids = list(assignments_qs.values_list("id", flat=True))
    submission_counts_qs = (
        Submission.objects.filter(assignment_id__in=assignment_ids, user=user)
        .values("assignment_id")
        .annotate(count=Count("id"))
    )
    submission_count_by_assignment = {row["assignment_id"]: row["count"] for row in submission_counts_qs}

    # Hər assignment üçün user-specific məlumat hazırla
    assignments_with_user_data = []
    for a in assignments_qs:
        user_attempts = submission_count_by_assignment.get(a.id, 0)
        is_deadline_passed = a.is_deadline_passed if hasattr(a, "is_deadline_passed") else False
        is_active = a.status in {"active", "published"}
        can_submit = user_attempts < a.max_attempts and not is_deadline_passed and is_active
        attempts_left = a.max_attempts - user_attempts

        assignments_with_user_data.append(
            {
                "assignment": a,
                "user_attempts": user_attempts,
                "can_submit": can_submit,
                "attempts_left": attempts_left,
                "is_deadline_passed": is_deadline_passed,
            }
        )

    return {
        "assignments": assignments_qs,
        "assignments_with_user_data": assignments_with_user_data,
    }
