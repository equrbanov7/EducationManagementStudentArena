"""Kurs dashboard-una labs bölməsinin kontribusiyası.

M2 (2026-07-02): apps/courses/views/shared/dashboard.py-dən köçürülüb —
LabAssignment/LabSubmission sorğuları öz modulunda yaşayır, courses artıq
labs-ı import etmir. Qeydiyyat: LabsConfig.ready(). Davranış birə-birdir.
"""

from collections import defaultdict

from django.utils import timezone

from apps.labs.models import LabAssignment, LabSubmission
from core.helpers import REVIEW_EDIT_LOCK_WINDOW


def build_course_dashboard_context(*, course, user, membership, can_manage, is_student):
    """Dashboard "Lab işləri" bölməsi: müəllim hamısını, tələbə yalnız özünə
    (ID və ya qrup filtri ilə) təyin olunmuş publish edilmiş lab-ları görür."""
    if can_manage:
        # MÜƏLLİM - bütün lab-lar
        return {"labs": course.labs.all().order_by("-created_at"), "labs_with_user_data": []}

    if not is_student:
        return {"labs": [], "labs_with_user_data": []}

    # TƏLƏBƏ - yalnız özünə təyin olunmuş lab-ları görür

    # Tələbənin qrup adını al
    student_group = ""
    if membership and hasattr(membership, "group_name"):
        student_group = membership.group_name or ""

    labs_with_user_data = []

    # Fetch all published labs with their M2M allowed_students pre-loaded
    # in a single query to avoid per-lab allowed_student lookups (N+1).
    published_labs = list(
        course.labs.filter(status="published").prefetch_related("allowed_students").order_by("-created_at")
    )

    # Batch-fetch LabAssignments for this student across all labs.
    lab_ids = [lab.id for lab in published_labs]
    lab_assignments_by_lab = {la.lab_id: la for la in LabAssignment.objects.filter(lab_id__in=lab_ids, student=user)}

    # Batch-fetch LabSubmissions for all LabAssignments belonging to this student.
    student_assignment_ids = [la.id for la in lab_assignments_by_lab.values()]
    submissions_by_assignment: dict[int, list] = defaultdict(list)
    for sub in LabSubmission.objects.filter(assignment_id__in=student_assignment_ids).order_by("-submitted_at"):
        submissions_by_assignment[sub.assignment_id].append(sub)

    # Published olan lab-ları yoxla
    for lab in published_labs:

        # This lab assigned to the student?
        is_assigned = False

        # Allowed students - use pre-fetched M2M (no extra query per lab)
        allowed_student_ids = {s.id for s in lab.allowed_students.all()}

        # Allowed groups - vergüllə ayrılmış qrup adları
        allowed_group_names = []
        if lab.allowed_groups and lab.allowed_groups.strip():
            for g in lab.allowed_groups.split(","):
                g = g.strip()
                if g:
                    allowed_group_names.append(g)

        # ƏSAS MƏNTİQ:
        # 1. Əgər hər iki filtr boşdursa → HAMIYA AÇIQ DEYİL, heç kim görməsin
        # 2. Əgər student ID siyahısında varsa → görür
        # 3. Əgər qrup siyahısında varsa → görür

        has_any_filter = len(allowed_student_ids) > 0 or len(allowed_group_names) > 0

        if not has_any_filter:
            is_assigned = False
        else:
            # Filtr var - yoxla
            # Student ID ilə yoxla
            if user.id in allowed_student_ids:
                is_assigned = True

            # Qrup adı ilə yoxla
            if not is_assigned and student_group and student_group in allowed_group_names:
                is_assigned = True

        # Əgər təyin olunmayıbsa, skip et
        if not is_assigned:
            continue

        # Use pre-fetched LabAssignment and LabSubmissions.
        assignment = lab_assignments_by_lab.get(lab.id)

        submissions_list: list = []
        attempt_count = 0
        has_submitted = False
        latest_submission = None

        if assignment:
            submissions_list = submissions_by_assignment.get(assignment.id, [])
            attempt_count = len(submissions_list)
            has_submitted = attempt_count > 0
            latest_submission = submissions_list[0] if has_submitted else None

        max_attempts = lab.max_attempts or 1
        can_submit = (attempt_count < max_attempts) and lab.is_open
        can_show_grade = bool(
            latest_submission
            and latest_submission.status == "graded"
            and latest_submission.graded_at
            and timezone.now() >= latest_submission.graded_at + REVIEW_EDIT_LOCK_WINDOW
        )

        labs_with_user_data.append(
            {
                "lab": lab,
                "has_submitted": has_submitted,
                "submission": latest_submission,
                "submissions": submissions_list,
                "attempt_count": attempt_count,
                "max_attempts": max_attempts,
                "attempts_left": max_attempts - attempt_count,
                "can_submit": can_submit,
                "can_show_grade": can_show_grade,
            }
        )

    return {"labs": [], "labs_with_user_data": labs_with_user_data}
