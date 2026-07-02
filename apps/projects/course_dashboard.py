"""Kurs dashboard-una projects bölməsinin kontribusiyası.

M2 (2026-07-02): apps/courses/views/shared/dashboard.py-dən köçürülüb —
ProjectSubmission sorğuları öz modulunda yaşayır, courses artıq projects-i
import etmir. Qeydiyyat: ProjectsConfig.ready(). Davranış birə-birdir.
"""

from django.db.models import Count

from apps.projects.models import ProjectSubmission


def build_course_dashboard_context(*, course, user, membership, can_manage, is_student):
    """Dashboard "Kurs işləri" bölməsi: müəllim hamısını, tələbə yalnız
    özünə təyin olunmuşları (arxivlənmişlər istisna) görür."""
    if can_manage:
        # MÜƏLLİM - bütün project-lər
        return {
            "projects": course.projects.all().order_by("-created_at"),
            "projects_with_user_data": [],
        }

    if not is_student:
        return {"projects": [], "projects_with_user_data": []}

    # TƏLƏBƏ - arxivlənmişlər istisna
    try:
        projects_qs = course.projects.filter(assigned_students=user).exclude(status="archived").order_by("-created_at")

        # Batch-fetch submission counts for this user across all projects
        # to avoid N+1 queries (one query instead of one per project).
        project_ids = list(projects_qs.values_list("id", flat=True))
        project_submission_counts_qs = (
            ProjectSubmission.objects.filter(project_id__in=project_ids, student=user)
            .values("project_id")
            .annotate(count=Count("id"))
        )
        project_submission_count = {row["project_id"]: row["count"] for row in project_submission_counts_qs}

        # Hər project üçün user-specific məlumat hazırla
        projects_with_user_data = []
        for p in projects_qs:
            user_attempts = project_submission_count.get(p.id, 0)
            is_deadline_passed = p.is_deadline_passed
            is_active = p.status == "active"
            can_submit = user_attempts < p.max_attempts and not is_deadline_passed and is_active
            attempts_left = p.max_attempts - user_attempts

            projects_with_user_data.append(
                {
                    "project": p,
                    "user_attempts": user_attempts,
                    "can_submit": can_submit,
                    "attempts_left": attempts_left,
                    "is_deadline_passed": is_deadline_passed,
                }
            )

        return {"projects": projects_qs, "projects_with_user_data": projects_with_user_data}
    except Exception:
        return {"projects": [], "projects_with_user_data": []}
