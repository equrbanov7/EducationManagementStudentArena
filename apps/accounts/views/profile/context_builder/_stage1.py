"""build_profile_response — stage 1 (god-file refaktoru, FAZA 4)."""

from django.core.paginator import Paginator
from django.db.models import Q
from django.urls import reverse

from apps.accounts import profile_hooks
from apps.courses.models import Course, CourseMembership
from apps.exams.models import Exam, StudentGroup
from apps.notifications.public import build_profile_notification_state, get_unread_count
from core.cache import get_or_set_cached_profile_badge_counts

from ....forms import CustomPasswordChangeForm
from ....models import UserProfile
from ....services.profile_actions import validate_profile_avatar_upload
from ..._dashboard_helpers import _collect_assigned_tasks, _collect_my_results, _collect_pending_answer_items
from ..._dashboard_helpers.cheap_counts import compute_profile_badge_counts
from ..._helpers import (
    STUDENT_MEMBER_GROUPS_DISPLAY_LIMIT,
    _append_query_params,
    _assigned_courses_queryset,
    _assigned_exams_queryset,
    _build_user_organization_access_rows,
    _get_active_organization,
    _query_string,
    _role_capabilities,
    _tenant_scoped_courses,
    _tenant_scoped_exams,
)
from .._sections.exams import build_my_exams_context
from .._sections.groups import build_groups_context
from .._sections.question_bank import build_question_bank_context
from .._sections.question_submissions import build_question_submissions_context
from .._sections.unit_exams import build_unit_exams_context
from ..contact_inbox import handle_contact_reply_post
from ..post_handler import handle_profile_post
from ._helpers import _build_effective_user_roles, _restore_profile_org_context


class _Stage1Mixin:
    @staticmethod
    def _attach_course_group_summaries(courses):
        course_ids = [course.id for course in courses]
        if not course_ids:
            return

        memberships = (
            CourseMembership.objects.filter(
                course_id__in=course_ids,
                role="student",
            )
            .exclude(group_name="")
            .values_list("course_id", "group_name")
            .order_by("course_id", "group_name")
        )
        groups_by_course = {}
        for course_id, group_name in memberships:
            cleaned = (group_name or "").strip()
            if cleaned:
                groups_by_course.setdefault(course_id, set()).add(cleaned)

        for course in courses:
            group_names = sorted(groups_by_course.get(course.id, set()))
            course.profile_group_names = group_names
            course.profile_group_count = len(group_names)

    def _stage_1(self):
        """
        User profile page with edit functionality.
        Ensures profile exists before rendering.
        Now accessible to ALL users (not just teachers).
        """
        self.profile, self._created = UserProfile.objects.get_or_create(user=self.request.user)
        self.requested_section = self.request.GET.get("section", "profile-info")
        _restore_profile_org_context(self.request, self.profile, self.requested_section)
        self.capabilities = _role_capabilities(self.request.user, self.profile)
        self.notification_state = build_profile_notification_state(user=self.request.user, profile=self.profile)
        self.pending_student_invites = self.notification_state["pending_student_invites"]
        self.pending_student_join_requests = self.notification_state["pending_student_join_requests"]
        self.pending_student_join_org_name = self.notification_state["pending_student_join_org_name"]
        self.pending_student_join_message = self.notification_state["pending_student_join_message"]
        self.student_can_leave_org = self.notification_state["student_can_leave_org"]
        self.org_notification_count = self.notification_state["unread_count"]
        self.in_app_unread_count = get_unread_count(user=self.request.user)
        self.notifications_unread_count = self.org_notification_count + self.in_app_unread_count
        self._validate_avatar_upload = validate_profile_avatar_upload
        self.allowed_sections = self.capabilities["allowed_sections"]
        self.active_section = (
            self.requested_section if self.requested_section in self.allowed_sections else "profile-info"
        )
        if self.active_section == "delete-account":
            self.active_section = "profile-info"
        self.password_change_form = CustomPasswordChangeForm(self.request.user)
        self.category_management_create_form = None
        self.category_management_edit_form = None
        self.category_management_edit_item = None
        if self.request.method == "POST":
            self.contact_reply_response = handle_contact_reply_post(self.request, capabilities=self.capabilities)
            if self.contact_reply_response is not None:
                return self.contact_reply_response
            self.post_result = handle_profile_post(
                self.request,
                profile=self.profile,
                capabilities=self.capabilities,
                allowed_sections=self.allowed_sections,
                active_section=self.active_section,
                password_change_form=self.password_change_form,
                validate_avatar_upload=self._validate_avatar_upload,
            )
            if self.post_result["response"] is not None:
                return self.post_result["response"]
            self.active_section = self.post_result["active_section"]
            self.password_change_form = self.post_result["password_change_form"]
            self.category_management_create_form = self.post_result["category_management_create_form"]
            self.category_management_edit_form = self.post_result["category_management_edit_form"]
            self.category_management_edit_item = self.post_result["category_management_edit_item"]
        self.user_roles = _build_effective_user_roles(self.request.user, self.profile)
        self.primary_user_role_label = self.user_roles[0]["label"] if self.user_roles else ""
        self.active_organization = _get_active_organization(self.request)
        self.organization_access_rows = _build_user_organization_access_rows(
            self.request.user,
            active_organization=self.active_organization,
            include_active_superadmin_org=self.capabilities["is_superadmin"],
            profile_section="superadmin-organizations" if self.capabilities["is_superadmin"] else "profile-info",
        )
        self.teacher_courses = _tenant_scoped_courses(
            self.request,
            Course.objects.filter(
                Q(owner=self.request.user)
                | Q(memberships__user=self.request.user, memberships__role__in=["teacher", "assistant"])
            ).distinct(),
        )
        self.created_courses_qs = self.teacher_courses.order_by("-created_at")
        self.enrolled_courses_qs = _assigned_courses_queryset(self.request, self.request.user).order_by("-created_at")
        self.my_exams_qs = _tenant_scoped_exams(self.request, Exam.objects.filter(author=self.request.user)).order_by(
            "-created_at"
        )
        self.profile_badge_counts = get_or_set_cached_profile_badge_counts(
            user_id=self.request.user.pk,
            org_id=self.active_organization.pk if self.active_organization is not None else None,
            compute=lambda: compute_profile_badge_counts(
                self.request,
                self.request.user,
                capabilities=self.capabilities,
                my_exams_qs=self.my_exams_qs,
                teacher_courses=self.teacher_courses,
            ),
        )
        if self.capabilities["is_student"]:
            self.visible_courses_qs = self.enrolled_courses_qs
        else:
            self.visible_courses_qs = self.created_courses_qs
        self.courses_count = self.visible_courses_qs.count()
        self.my_courses = []
        if self.active_section == "courses":
            self.my_courses = list(self.visible_courses_qs[:10])
        self.my_created_courses = []
        self.my_created_courses_count = 0
        self.my_exams_count = 0
        self.my_exams_search_query = ""
        self.my_exams_filter_type = ""
        self.my_exams_list = []
        self.my_exams_dashboard = None
        self.question_bank_banks = []
        self.question_bank_page_obj = None
        self.question_bank_search_query = ""
        self.question_bank_pagination_query = _query_string(section="question-bank")
        self.question_bank_create_next_url = _append_query_params(reverse("accounts:profile"), section="question-bank")
        self.question_bank_back_url = self.question_bank_create_next_url
        self.question_bank_language_choices = []
        self.question_bank_default_type_choices = []
        self.question_bank_can_create = False
        if self.capabilities["can_view_owned_learning"]:
            self.my_created_courses_count = self.created_courses_qs.count()
            if self.active_section == "my-courses":
                self.my_created_courses = list(self.created_courses_qs[:10])
                self._attach_course_group_summaries(self.my_created_courses)
            self._my_exams_ctx = build_my_exams_context(
                self.request, my_exams_qs=self.my_exams_qs, active_section=self.active_section
            )
            self.my_exams_count = self._my_exams_ctx["my_exams_count"]
            self.my_exams_list = self._my_exams_ctx["my_exams_list"]
            self.my_exams_dashboard = self._my_exams_ctx["my_exams_dashboard"]
            self.my_exams_search_query = self._my_exams_ctx["my_exams_search_query"]
            self.my_exams_filter_type = self._my_exams_ctx["my_exams_filter_type"]
        self._unit_exams_ctx = build_unit_exams_context(
            self.request, allowed_sections=self.allowed_sections, active_section=self.active_section
        )
        self.unit_exams_page_obj = self._unit_exams_ctx["unit_exams_page_obj"]
        self.unit_exams_search_query = self._unit_exams_ctx["unit_exams_search_query"]
        self.unit_exams_total_count = self._unit_exams_ctx["unit_exams_total_count"]
        self.unit_exams_pagination_query = self._unit_exams_ctx["unit_exams_pagination_query"]
        self._qb_ctx = build_question_bank_context(
            self.request, allowed_sections=self.allowed_sections, active_section=self.active_section
        )
        self._qsub_ctx = build_question_submissions_context(
            self.request, allowed_sections=self.allowed_sections, active_section=self.active_section
        )
        self.question_bank_banks = self._qb_ctx["question_bank_banks"]
        self.question_bank_page_obj = self._qb_ctx["question_bank_page_obj"]
        self.question_bank_search_query = self._qb_ctx["question_bank_search_query"]
        self.question_bank_pagination_query = self._qb_ctx["question_bank_pagination_query"]
        self.question_bank_back_url = self._qb_ctx["question_bank_back_url"]
        self.question_bank_language_choices = self._qb_ctx["question_bank_language_choices"]
        self.question_bank_default_type_choices = self._qb_ctx["question_bank_default_type_choices"]
        self.question_bank_can_create = self._qb_ctx["question_bank_can_create"]
        self._posts_ctx = profile_hooks.posts_section(
            self.request, capabilities=self.capabilities, active_section=self.active_section
        )
        self.user_posts = self._posts_ctx["user_posts"]
        self.posts_count = self._posts_ctx["posts_count"]
        self.post_category_tree = self._posts_ctx["post_category_tree"]
        self.post_category_root_options = self._posts_ctx["post_category_root_options"]
        self.post_category_subcategory_options = self._posts_ctx["post_category_subcategory_options"]
        self.post_creation_requires_approval = self._posts_ctx["post_creation_requires_approval"]
        self.posting_blocked = self._posts_ctx["posting_blocked"]
        self.posting_blocked_reason = self._posts_ctx["posting_blocked_reason"]
        self.assigned_exams_count = 0
        self.assigned_courses_count = 0
        self.assigned_tasks_count = 0
        self.my_results_count = 0
        self.assigned_task_items = []
        self.assigned_task_counts = {"all": 0, "exams": 0, "courses": 0, "assignments": 0, "labs": 0, "independent": 0}
        self.assigned_tasks_active_filter = "all"
        self.assigned_tasks_search_query = ""
        self.assigned_courses = []
        self.assigned_courses_search_query = ""
        self.my_result_items = []
        self.my_results_page_obj = None
        self.my_results_search_query = ""
        self.my_results_pagination_query = ""
        self.my_results_page_param = "results_page"
        self.my_result_counts = {"all": 0, "exams": 0, "courses": 0, "labs": 0, "independent": 0}
        self.my_results_active_filter = "all"
        self.pending_answer_items = []
        self.pending_answer_counts = {
            "all": 0,
            "exams": 0,
            "written_exams": 0,
            "practical_exams": 0,
            "courses": 0,
            "labs": 0,
            "independent": 0,
        }
        self.pending_answers_active_filter = "all"
        self.pending_answers_search_query = ""
        self.pending_answers_count = 0
        if self.capabilities["can_view_student_assignments"]:
            self.assigned_exams_qs = _assigned_exams_queryset(
                self.request, self.request.user, active_only=True
            ).order_by("-start_datetime", "-created_at")
            self.assigned_exams_count = self.assigned_exams_qs.count()
            self.assigned_courses_count = self.enrolled_courses_qs.count()
            if self.active_section == "assigned-exams":
                self.assigned_task_items, self.assigned_task_counts, self.assigned_tasks_active_filter = (
                    _collect_assigned_tasks(
                        self.request,
                        filter_type=self.request.GET.get("assigned_type"),
                        search=self.request.GET.get("assigned_search"),
                    )
                )
                self.assigned_tasks_count = self.assigned_task_counts.get("all", 0)
                self.assigned_tasks_search_query = (self.request.GET.get("assigned_search", "") or "").strip()
            else:
                self.assigned_tasks_count = self.profile_badge_counts.get("assigned_tasks", 0)
            if self.active_section == "assigned-courses":
                self.assigned_courses_search_query = (self.request.GET.get("assigned_course_search", "") or "").strip()
                self.assigned_courses_qs = self.enrolled_courses_qs
                if self.assigned_courses_search_query:
                    self.assigned_courses_qs = self.assigned_courses_qs.filter(
                        Q(title__icontains=self.assigned_courses_search_query)
                        | Q(description__icontains=self.assigned_courses_search_query)
                    )
                self.assigned_courses = list(self.assigned_courses_qs[:20])
            if self.active_section == "my-results":
                self.my_result_items, self.my_result_counts, self.my_results_active_filter = _collect_my_results(
                    self.request,
                    filter_type=self.request.GET.get("results_type"),
                    search=self.request.GET.get("results_search"),
                )
                self.my_results_search_query = (self.request.GET.get("results_search", "") or "").strip()
                self.my_results_page_obj = Paginator(self.my_result_items, 6).get_page(
                    self.request.GET.get(self.my_results_page_param)
                )
                self.my_result_items = self.my_results_page_obj
                self.my_results_pagination_query = _query_string(
                    section="my-results",
                    results_type=self.my_results_active_filter,
                    results_search=self.my_results_search_query,
                )
                self.my_results_count = self.my_result_counts.get("all", 0)
            else:
                self.my_results_count = self.profile_badge_counts.get("my_results", 0)
            if self.active_section == "pending-answers":
                (
                    self.pending_answer_items,
                    self.pending_answer_counts,
                    self.pending_answers_active_filter,
                    self.pending_answers_search_query,
                ) = _collect_pending_answer_items(
                    self.request,
                    search=self.request.GET.get("pending_search"),
                    filter_type=self.request.GET.get("pending_type"),
                )
                self.pending_answers_count = self.pending_answer_counts.get("all", 0)
            else:
                self.pending_answers_count = self.profile_badge_counts.get("pending_answers", 0)
        self.pending_appeals_count = 0
        if self.capabilities.get("can_manage_appeals"):
            from apps.appeals.public import count_pending_manage_appeals

            self.pending_appeals_count = count_pending_manage_appeals(self.request)
        self.pending_review_count = self.profile_badge_counts.get("pending_review", 0)
        self.evaluated_review_count = self.profile_badge_counts.get("evaluated_review", 0)
        self.teacher_groups = []
        self.teacher_groups_count = 0
        self.teacher_groups_filtered_count = 0
        self.teacher_groups_payload = {}
        self.teacher_groups_page = None
        self.teacher_groups_search_query = (self.request.GET.get("group_q") or "").strip()
        self.teacher_groups_pagination_query = ""
        self.selected_teacher_group = None
        self.selected_group_students_page = None
        self.selected_group_students_count = 0
        self.selected_group_students_filtered_count = 0
        self.group_students_search_query = (self.request.GET.get("student_q") or "").strip()
        self.group_students_pagination_query = ""
        self.student_member_groups_qs = (
            StudentGroup.objects.filter(students=self.request.user)
            .select_related("organization", "teacher")
            .order_by("organization__name", "name")
            .distinct()
        )
        self.student_member_groups_count = self.student_member_groups_qs.count()
        self.student_member_groups = list(self.student_member_groups_qs[:STUDENT_MEMBER_GROUPS_DISPLAY_LIMIT])
        self.student_member_groups_more_count = max(
            0, self.student_member_groups_count - len(self.student_member_groups)
        )

        # ── Rol-əsaslı akademik məlumatlar (profil "Akademik məlumatlar" kartı) ──
        # Müəllim/dekan/kafedra müdiri → fakültə/kafedra (Membership.scope_unit);
        # müəllim → tədris etdiyi fənlər (taught_offerings); tələbə → İxtisas +
        # akademik struktur (academic_records → program + group). Yalnız profil
        # məlumat bölməsində hesablanır (əlavə sorğu digər bölmələrdə olmasın).
        self.academic_units = []
        self.teacher_subjects = []
        self.student_records = []
        if self.active_organization is not None and self.active_section == "profile-info":
            caps = self.capabilities
            if caps.get("is_teacher") or caps.get("is_unit_manager"):
                from apps.organizations.models import Membership
                from core.constants import OrgUnitType

                # Fakültə/kafedra ayrı sahələr kimi göstərilir — hər ikisi
                # Membership.scope_unit-dən avtomatik hesablanır, istifadəçi
                # tərəfindən dəyişdirilə bilməz (bax [[project_group_sector_variability]]).
                faculty_types = {
                    OrgUnitType.FACULTY,
                    OrgUnitType.DEANERY,
                    OrgUnitType.INSTITUTE,
                    OrgUnitType.RECTORATE,
                    OrgUnitType.VICE_RECTORATE,
                }
                department_types = {OrgUnitType.CHAIR, OrgUnitType.DEPARTMENT}

                seen_units = set()
                for membership in Membership.objects.filter(
                    user=self.request.user, is_active=True, organization=self.active_organization
                ).select_related("scope_unit"):
                    unit = membership.scope_unit
                    if unit is None or unit.id in seen_units:
                        continue
                    seen_units.add(unit.id)

                    faculty_unit = None
                    department_unit = None
                    for node in [unit, *unit.get_ancestors()]:
                        if department_unit is None and node.unit_type in department_types:
                            department_unit = node
                        if faculty_unit is None and node.unit_type in faculty_types:
                            faculty_unit = node

                    self.academic_units.append(
                        {
                            "unit": unit,
                            "faculty": faculty_unit,
                            "department": department_unit,
                        }
                    )
            if caps.get("is_teacher"):
                seen_subjects = set()
                for offering in (
                    self.request.user.taught_offerings.filter(organization=self.active_organization)
                    .select_related("subject", "group")
                    .order_by("subject__name")
                ):
                    key = (offering.subject_id, offering.group_id)
                    if key not in seen_subjects:
                        seen_subjects.add(key)
                        self.teacher_subjects.append(offering)
            if caps.get("is_student"):
                self.student_records = list(
                    self.request.user.academic_records.filter(
                        is_active=True, organization=self.active_organization
                    ).select_related("program", "group")
                )

        self.group_form = None
        self.can_multi_assign_group_teachers = False
        self.groups_section_return_url = f"{reverse('accounts:profile')}?section=groups"
        if (
            "groups" in self.allowed_sections
            and self.active_section == "groups"
            and (self.active_organization is not None)
        ):
            self._groups_ctx = build_groups_context(
                self.request,
                profile=self.profile,
                capabilities=self.capabilities,
                active_organization=self.active_organization,
                teacher_groups_search_query=self.teacher_groups_search_query,
                group_students_search_query=self.group_students_search_query,
            )
            self.can_multi_assign_group_teachers = self._groups_ctx["can_multi_assign_group_teachers"]
            self.group_form = self._groups_ctx["group_form"]
            self.teacher_groups = self._groups_ctx["teacher_groups"]
            self.teacher_groups_count = self._groups_ctx["teacher_groups_count"]
            self.teacher_groups_filtered_count = self._groups_ctx["teacher_groups_filtered_count"]
            self.teacher_groups_page = self._groups_ctx["teacher_groups_page"]
            self.teacher_groups_pagination_query = self._groups_ctx["teacher_groups_pagination_query"]
            self.selected_teacher_group = self._groups_ctx["selected_teacher_group"]
            self.selected_group_students_count = self._groups_ctx["selected_group_students_count"]
            self.selected_group_students_filtered_count = self._groups_ctx["selected_group_students_filtered_count"]
            self.selected_group_students_page = self._groups_ctx["selected_group_students_page"]
            self.group_students_pagination_query = self._groups_ctx["group_students_pagination_query"]
            self.teacher_groups_payload = self._groups_ctx["teacher_groups_payload"]
