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
from django.utils.translation import pgettext
from django.views.generic import DetailView

from apps.courses import dashboard_sources
from apps.courses.forms import CourseResourceForm, CourseTopicForm
from apps.courses.models import Course, CourseMembership
from apps.exams.models import Exam, ExamAttempt, StudentGroup
from apps.exams.public import DEFAULT_EXAM_LANGUAGE, available_language_options, without_disabled_practical_exams
from core.helpers import (
    ASSIGNED_TASK_FILTER_CHOICES,
    _safe_same_origin_redirect_path,
    _tenant_scoped_courses,
)
from core.tenancy import get_request_organization, scoped_by_organization

from ..shared._helpers import _student_users_queryset

User = get_user_model()


def _build_exam_language_modal_context(exam):
    options = [
        {
            "language": option["language"],
            "display_name": option["display_name"],
        }
        for option in available_language_options(exam)
    ]
    codes = {option["language"] for option in options}
    default_language = ""
    if DEFAULT_EXAM_LANGUAGE in codes:
        default_language = DEFAULT_EXAM_LANGUAGE
    elif options:
        default_language = options[0]["language"]

    return {
        "language_options": options,
        "language_options_id": f"course-exam-language-options-{exam.id}",
        "default_language": default_language,
    }


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
        # prefetch_related("resources"): _topic_accordion.html hər topic üçün
        # resources-i həm sayır (badge), həm iterate edir — prefetch olmasa hər
        # ikisi topic başına ayrı sorğu idi (N+1).
        context["topics"] = course.topics.prefetch_related("resources").order_by("order")
        context["resources"] = course.resources.all().order_by("-created_at")

        # ═══════════════════════════════════════════════════════════════════
        # 3. ÜZVLƏR (Yalnız owner və assistant görür)
        # ═══════════════════════════════════════════════════════════════════
        if context["can_view_members"]:
            context["members"] = course.memberships.select_related("user").order_by("group_name", "joined_at")
        else:
            context["members"] = []

        # ═══════════════════════════════════════════════════════════════════
        # 4-6. TASK BÖLMƏLƏRİ (assignments / projects / labs)
        # ───────────────────────────────────────────────────────────────────
        # M2 (2026-07-02): hər task modulu öz bölmə kontekstini
        # dashboard_sources registry-si ilə verir (AppConfig.ready()-də
        # qeydiyyat) — courses artıq task modellərini import etmir.
        # ═══════════════════════════════════════════════════════════════════
        context.update(
            {
                "assignments": [],
                "assignments_with_user_data": [],
                "projects": [],
                "projects_with_user_data": [],
                "labs": [],
                "labs_with_user_data": [],
            }
        )
        context.update(
            dashboard_sources.build_context(
                course=course,
                user=user,
                membership=membership,
                can_manage=context["can_manage_course"],
                is_student=context["is_student"],
            )
        )

        # ═══════════════════════════════════════════════════════════════════
        # 7. İMTAHANLAR
        # ───────────────────────────────────────────────────────────────────

        if context["can_manage_course"]:
            # MÜƏLLİM - bu kursa bağlı bütün imtahanları görür.
            # questions_total annotate: exam_section.html course_exams loop-unda
            # hər imtahanın sual sayını göstərir — annotate olmasa N+1.
            context["course_exams"] = (
                without_disabled_practical_exams(
                    scoped_by_organization(
                        Exam.objects.filter(course=course),
                        self.request,
                    )
                )
                .annotate(questions_total=Count("questions", distinct=True))
                .order_by("-created_at")
            )

            # Müəllimin bütün imtahanları (kurs ilə əlaqələndirmək üçün).
            # questions_total annotate: _exam_modals.html teacher_exams loop-unda
            # hər imtahan üçün sual sayını göstərir — annotate olmasa N+1.
            context["teacher_exams"] = (
                without_disabled_practical_exams(
                    scoped_by_organization(
                        Exam.objects.filter(author=user).exclude(course=course),
                        self.request,
                    )
                )
                .annotate(questions_total=Count("questions", distinct=True))
                .order_by("-created_at")[:10]
            )

        elif context["is_student"]:
            # TƏLƏBƏ - yalnız aktiv və ona icazəli imtahanları görür
            all_course_exams = list(
                without_disabled_practical_exams(
                    scoped_by_organization(
                        Exam.objects.filter(course=course, is_active=True),
                        self.request,
                    )
                ).annotate(questions_total=Count("questions", distinct=True))
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
                            **_build_exam_language_modal_context(exam),
                        }
                    )

            context["course_exams"] = []
            context["exams_with_data"] = exams_with_data
        else:
            context["course_exams"] = []
            context["exams_with_data"] = []

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
