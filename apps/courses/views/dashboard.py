"""
courses/views/dashboard.py
───────────────────────────
Course dashboard view - the main course page showing all course content.

Contains:
- CourseDashboardView (large view with role-based context building)
"""

from collections import defaultdict
from urllib.parse import urlencode

from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.db.models import Count
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import pgettext
from django.views.generic import DetailView

from apps.assignments.models import Submission
from apps.courses.forms import CourseResourceForm, CourseTopicForm
from apps.courses.models import Course, CourseMembership
from apps.exams.features import without_disabled_practical_exams
from apps.exams.models import Exam, ExamAttempt, StudentGroup
from apps.labs.models import LabAssignment, LabSubmission
from apps.projects.models import ProjectSubmission
from core.helpers import (
    ASSIGNED_TASK_FILTER_CHOICES,
    REVIEW_EDIT_LOCK_WINDOW,
    _safe_same_origin_redirect_path,
    _tenant_scoped_courses,
)
from core.tenancy import get_request_organization, scoped_by_organization

from ._helpers import _student_users_queryset

User = get_user_model()


# ════════════════════════════════════════════════════════════════════════════
# Course Dashboard
# ════════════════════════════════════════════════════════════════════════════


class CourseDashboardView(LoginRequiredMixin, DetailView):
    """
    ┌─────────────────────────────────────────────────────────────────────────┐
    │ Kurs Dashboard View                                                     │
    │ GET /courses/<course_id>/dashboard/                                     │
    │                                                                         │
    │ Tələbə yalnız özünə təyin olunmuş işləri görür.                         │
    │ Müəllim bütün işləri görür və idarə edir.                               │
    └─────────────────────────────────────────────────────────────────────────┘
    """

    model = Course
    template_name = "courses/course_dashboard.html"
    context_object_name = "course"
    pk_url_kwarg = "course_id"

    def get_queryset(self):
        return _tenant_scoped_courses(self.request).select_related("owner", "owner__profile")

    def get_object(self, queryset=None):
        course = super().get_object(queryset=queryset)
        membership = CourseMembership.objects.filter(course=course, user=self.request.user).first()
        is_owner = course.owner_id == self.request.user.id

        if not is_owner and membership is None:
            raise PermissionDenied(pgettext("courses.view.permission", "no_access_this_course"))

        self._membership = membership
        return course

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        course = self.get_object()
        user = self.request.user

        # ═══════════════════════════════════════════════════════════════════
        # 1. İSTİFADƏÇİ ROLUNU TƏYİN ET
        # ═══════════════════════════════════════════════════════════════════
        membership = getattr(self, "_membership", None)
        user_role = membership.role if membership else None

        # ─────────────────────────────────────────────────────────────────────
        # Context-ə rol məlumatlarını əlavə et
        # ─────────────────────────────────────────────────────────────────────
        context["is_owner"] = course.owner_id == user.id
        context["is_teacher"] = context["is_owner"] or user_role in {"teacher", "assistant"}
        context["is_student"] = user_role == "student"
        context["is_assistant"] = user_role == "assistant"
        context["can_manage_course"] = context["is_owner"] or context["is_assistant"] or user_role == "teacher"
        context["can_view_members"] = context["can_manage_course"]
        context["user_role"] = user_role
        context["membership"] = membership

        requested_profile_section = (self.request.GET.get("from_section") or "").strip()
        valid_profile_sections = {"my-courses", "assigned-courses", "courses", "assigned-exams"}
        if requested_profile_section not in valid_profile_sections:
            requested_profile_section = "assigned-courses" if context["is_student"] else "my-courses"

        profile_return_params = {"section": requested_profile_section}
        if requested_profile_section == "assigned-exams":
            assigned_type = (self.request.GET.get("assigned_type") or "").strip().lower()
            if assigned_type in ASSIGNED_TASK_FILTER_CHOICES:
                profile_return_params["assigned_type"] = assigned_type

        fallback_profile_return_url = f"{reverse('accounts:profile')}?{urlencode(profile_return_params)}"
        explicit_return_url = _safe_same_origin_redirect_path(
            self.request,
            self.request.GET.get("return_to") or self.request.GET.get("next"),
        )
        if explicit_return_url == self.request.get_full_path():
            explicit_return_url = ""

        context["profile_return_section"] = requested_profile_section
        context["profile_return_url"] = explicit_return_url or fallback_profile_return_url

        # ═══════════════════════════════════════════════════════════════════
        # 2. MÖVZULAR & RESURSLAR (Hamı görür)
        # ═══════════════════════════════════════════════════════════════════
        context["topics"] = course.topics.all().order_by("order")
        context["resources"] = course.resources.all().order_by("-created_at")

        # ═══════════════════════════════════════════════════════════════════
        # 3. ÜZVLƏR (Yalnız owner və assistant görür)
        # ═══════════════════════════════════════════════════════════════════
        if context["can_view_members"]:
            context["members"] = course.memberships.select_related("user").order_by("group_name", "joined_at")
        else:
            context["members"] = []

        # ═══════════════════════════════════════════════════════════════════
        # 4. SƏRBƏST İŞLƏR (Assignments)
        # ───────────────────────────────────────────────────────────────────
        # Müəllim: Bütün assignment-ları görür
        # Tələbə: Yalnız özünə təyin olunmuşları görür (arxivlənmişlər istisna)
        # ═══════════════════════════════════════════════════════════════════
        if context["can_manage_course"]:
            # MÜƏLLİM - bütün assignment-lar
            context["assignments"] = course.assignments.all().order_by("-created_at")
            context["assignments_with_user_data"] = []

        elif context["is_student"]:
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

            context["assignments"] = assignments_qs
            context["assignments_with_user_data"] = assignments_with_user_data
        else:
            context["assignments"] = []
            context["assignments_with_user_data"] = []

        # ═══════════════════════════════════════════════════════════════════
        # 5. KURS İŞLƏRİ (Projects)
        # ───────────────────────────────────────────────────────────────────
        # Müəllim: Bütün project-ləri görür
        # Tələbə: Yalnız özünə təyin olunmuşları görür (arxivlənmişlər istisna)
        # ═══════════════════════════════════════════════════════════════════
        if context["can_manage_course"]:
            # MÜƏLLİM - bütün project-lər
            context["projects"] = course.projects.all().order_by("-created_at")
            context["projects_with_user_data"] = []

        elif context["is_student"]:
            # TƏLƏBƏ - arxivlənmişlər istisna
            try:
                projects_qs = (
                    course.projects.filter(assigned_students=user).exclude(status="archived").order_by("-created_at")
                )

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

                context["projects"] = projects_qs
                context["projects_with_user_data"] = projects_with_user_data
            except Exception:
                context["projects"] = []
                context["projects_with_user_data"] = []
        else:
            context["projects"] = []
            context["projects_with_user_data"] = []

        # ═══════════════════════════════════════════════════════════════════
        # 7. İMTAHANLAR
        # ───────────────────────────────────────────────────────────────────

        if context["can_manage_course"]:
            # MÜƏLLİM - bu kursa bağlı bütün imtahanları görür
            context["course_exams"] = without_disabled_practical_exams(
                scoped_by_organization(
                    Exam.objects.filter(course=course),
                    self.request,
                )
            ).order_by("-created_at")

            # Müəllimin bütün imtahanları (kurs ilə əlaqələndirmək üçün)
            context["teacher_exams"] = without_disabled_practical_exams(
                scoped_by_organization(
                    Exam.objects.filter(author=user).exclude(course=course),
                    self.request,
                )
            ).order_by("-created_at")[:10]

        elif context["is_student"]:
            # TƏLƏBƏ - yalnız aktiv və ona icazəli imtahanları görür
            all_course_exams = list(
                without_disabled_practical_exams(
                    scoped_by_organization(
                        Exam.objects.filter(course=course, is_active=True),
                        self.request,
                    )
                )
            )

            # Batch-fetch all this user's non-draft attempts for all exams in one query,
            # grouped by exam_id to avoid N+1 (one query instead of two per exam).
            exam_ids = [exam.id for exam in all_course_exams]
            all_user_attempts = (
                ExamAttempt.objects.filter(exam_id__in=exam_ids, user=user)
                .exclude(status="draft")
                .order_by("-started_at")
            )
            attempts_by_exam: dict[int, list] = defaultdict(list)
            for attempt in all_user_attempts:
                attempts_by_exam[attempt.exam_id].append(attempt)

            exams_with_data = []
            for exam in all_course_exams:
                if exam.can_user_see(user):
                    # Use pre-fetched attempts instead of per-exam queries.
                    exam_attempts = attempts_by_exam.get(exam.id, [])
                    last_attempt = exam_attempts[0] if exam_attempts else None
                    attempt_count = len(exam_attempts)
                    attempts_left = (
                        max(exam.max_attempts_per_user - attempt_count, 0) if exam.max_attempts_per_user else None
                    )
                    can_start_without_code, _ = exam.can_user_start(user, code=None)
                    is_exam_window_open = not exam.is_before_start() and not exam.is_after_end()
                    has_attempts_left = attempts_left is None or attempts_left > 0
                    requires_code = bool(exam.access_code and is_exam_window_open and has_attempts_left)

                    exams_with_data.append(
                        {
                            "exam": exam,
                            "last_attempt": last_attempt,
                            "attempt_count": attempt_count,
                            "attempts_left": attempts_left,
                            "can_start": can_start_without_code or requires_code,
                            "requires_code": requires_code,
                        }
                    )

            context["course_exams"] = []
            context["exams_with_data"] = exams_with_data
        else:
            context["course_exams"] = []
            context["exams_with_data"] = []

        # ═══════════════════════════════════════════════════════════════════
        # 6. LAB İŞLƏRİ
        # ───────────────────────────────────────────────────────────────────
        # Müəllim: Bütün lab-ları görür
        # Tələbə: Yalnız özünə təyin olunmuşları görür + user-specific data
        # ═══════════════════════════════════════════════════════════════════

        if context["can_manage_course"]:
            # MÜƏLLİM - bütün lab-lar
            context["labs"] = course.labs.all().order_by("-created_at")
            context["labs_with_user_data"] = []

        elif context["is_student"]:
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
            lab_assignments_by_lab = {
                la.lab_id: la for la in LabAssignment.objects.filter(lab_id__in=lab_ids, student=user)
            }

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

            context["labs"] = []
            context["labs_with_user_data"] = labs_with_user_data

        else:
            context["labs"] = []
            context["labs_with_user_data"] = []

        # ═══════════════════════════════════════════════════════════════════
        # 7. FORMALAR VƏ MODAL ÜÇÜN DATA (Yalnız owner üçün)
        # ═══════════════════════════════════════════════════════════════════
        if context["is_owner"]:
            # ─────────────────────────────────────────────────────────────────
            # Form instance-ları
            # ─────────────────────────────────────────────────────────────────
            context["topic_form"] = CourseTopicForm()
            context["resource_form"] = CourseResourceForm()

            # ─────────────────────────────────────────────────────────────────
            # Kursdakı qruplar (modal-da seçim üçün)
            # ─────────────────────────────────────────────────────────────────
            context["assignment_groups"] = list(
                course.memberships.filter(role="student")
                .exclude(group_name__isnull=True)
                .exclude(group_name__exact="")
                .values_list("group_name", flat=True)
                .distinct()
                .order_by("group_name")
            )

            # ─────────────────────────────────────────────────────────────────
            # Kursa əlavə olunmamış istifadəçilər (üzv əlavə etmək üçün)
            # ─────────────────────────────────────────────────────────────────
            course_user_ids = course.memberships.values_list("user_id", flat=True)
            user_org = get_request_organization(self.request)
            user_candidates = User.objects.exclude(id__in=course_user_ids)
            if user_org is not None:
                user_candidates = user_candidates.filter(profile__organization=user_org)
            context["all_users"] = _student_users_queryset(user_candidates).order_by("username")

            # ─────────────────────────────────────────────────────────────────
            # Bütün qruplar (StudentGroup modelindən)
            # ─────────────────────────────────────────────────────────────────
            try:
                qs = StudentGroup.objects.filter(teacher=user)
                if user_org is not None:
                    qs = qs.filter(organization=user_org)
                context["all_groups"] = qs.order_by("name")
            except ImportError:
                context["all_groups"] = []
        else:
            # Owner deyilsə boş saxla
            context["all_users"] = []
            context["all_groups"] = []
            context["assignment_groups"] = []

        return context
