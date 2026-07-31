"""build_profile_response — stage 4 (god-file refaktoru, FAZA 4)."""

from django.urls import reverse
from django.utils.translation import pgettext_lazy

from apps.notifications.models import NotificationType

from .._sections.labels import DIRECT_PROFILE_SECTION_TEMPLATES, build_section_titles
from ..constants import PROFILE_EXAM_NAV_SECTIONS
from ..contact_inbox import build_contact_inbox_context


class _Stage4Mixin:

    def _stage_4_context(self):
        """``self.context``-i yığır (render ETMİR — bax builder.run_context)."""
        self.section_titles = build_section_titles()
        self.shortcut_sections = []
        if self.capabilities["can_view_blog"]:
            self.shortcut_sections.append(
                {
                    "section": "blog",
                    "title": self.section_titles["blog"],
                    "url": reverse("home"),
                    "icon": "fas fa-house",
                    "source_url": reverse("home"),
                    "description": "Ana səhifə və məqalə bölməsini aç.",
                    "action_label": pgettext_lazy("nav", "home"),
                }
            )
        self.active_section_title = self.section_titles.get(
            self.active_section, pgettext_lazy("profile.sidebar", "title")
        )
        self.direct_profile_section = getattr(self.request, "direct_profile_section", "")
        self.direct_profile_section_templates = DIRECT_PROFILE_SECTION_TEMPLATES
        self.context = {
            "profile": self.profile,
            "user_roles": self.user_roles,
            "primary_user_role_label": self.primary_user_role_label,
            "active_section": self.active_section,
            "active_section_title": self.active_section_title,
            "direct_profile_section": self.direct_profile_section,
            "direct_profile_section_template": self.direct_profile_section_templates.get(
                self.direct_profile_section, ""
            ),
            "active_main_nav": "exams" if self.active_section in PROFILE_EXAM_NAV_SECTIONS else "",
            "allowed_sections": self.allowed_sections,
            "profile_base_url": reverse("accounts:profile"),
            "shortcut_sections": self.shortcut_sections,
            "role_capabilities": self.capabilities,
            "password_change_form": self.password_change_form,
            "user_posts": self.user_posts,
            "posts_count": self.posts_count,
            "post_category_tree": self.post_category_tree,
            "post_category_root_options": self.post_category_root_options,
            "post_category_subcategory_options": self.post_category_subcategory_options,
            "post_creation_requires_approval": self.post_creation_requires_approval,
            "posting_blocked": self.posting_blocked,
            "posting_blocked_reason": self.posting_blocked_reason,
            "my_courses": self.my_courses,
            "courses_count": self.courses_count,
            "my_exams": self.my_exams_list,
            "my_exams_dashboard": self.my_exams_dashboard,
            "my_exams_count": self.my_exams_count,
            "my_exams_search_query": self.my_exams_search_query,
            "my_exams_filter_type": self.my_exams_filter_type,
            "my_exams_page_obj": self.my_exams_page_obj,
            "my_exams_pagination_query": self.my_exams_pagination_query,
            "question_bank_banks": self.question_bank_banks,
            "question_bank_page_obj": self.question_bank_page_obj,
            "question_bank_search_query": self.question_bank_search_query,
            "question_bank_pagination_query": self.question_bank_pagination_query,
            "question_bank_create_next_url": self.question_bank_create_next_url,
            "question_bank_back_url": self.question_bank_back_url,
            "question_bank_language_choices": self.question_bank_language_choices,
            "question_bank_default_type_choices": self.question_bank_default_type_choices,
            "question_bank_exam_kind_choices": self.question_bank_exam_kind_choices,
            "question_bank_kind_filter": self.question_bank_kind_filter,
            "question_bank_kind_pills": self.question_bank_kind_pills,
            "question_bank_can_create": self.question_bank_can_create,
            **self._qsub_ctx,
            "unit_exams_page_obj": self.unit_exams_page_obj,
            "unit_exams_search_query": self.unit_exams_search_query,
            "unit_exams_total_count": self.unit_exams_total_count,
            "unit_exams_pagination_query": self.unit_exams_pagination_query,
            "my_created_courses": self.my_created_courses,
            "my_created_courses_count": self.my_created_courses_count,
            "assigned_exams_count": self.assigned_exams_count,
            "assigned_courses_count": self.assigned_courses_count,
            "assigned_tasks_count": self.assigned_tasks_count,
            "assigned_task_items": self.assigned_task_items,
            "assigned_task_counts": self.assigned_task_counts,
            "assigned_tasks_active_filter": self.assigned_tasks_active_filter,
            "assigned_tasks_search_query": self.assigned_tasks_search_query,
            "assigned_courses": self.assigned_courses,
            "assigned_courses_search_query": self.assigned_courses_search_query,
            "my_results_count": self.my_results_count,
            "my_result_items": self.my_result_items,
            "my_results_page_obj": self.my_results_page_obj,
            "my_result_counts": self.my_result_counts,
            "my_results_active_filter": self.my_results_active_filter,
            "my_results_search_query": self.my_results_search_query,
            "my_results_pagination_query": self.my_results_pagination_query,
            "my_results_page_param": self.my_results_page_param,
            "pending_answers_count": self.pending_answers_count,
            "pending_answer_items": self.pending_answer_items,
            "pending_answer_counts": self.pending_answer_counts,
            "pending_answers_active_filter": self.pending_answers_active_filter,
            "pending_answers_search_query": self.pending_answers_search_query,
            "pending_appeals_count": self.pending_appeals_count,
            "pending_review_count": self.pending_review_count,
            "evaluated_review_count": self.evaluated_review_count,
            "teacher_groups": self.teacher_groups,
            "teacher_groups_count": self.teacher_groups_count,
            "teacher_groups_filtered_count": self.teacher_groups_filtered_count,
            "teacher_groups_payload": self.teacher_groups_payload,
            "teacher_groups_page": self.teacher_groups_page,
            "teacher_groups_search_query": self.teacher_groups_search_query,
            "teacher_groups_pagination_query": self.teacher_groups_pagination_query,
            "selected_teacher_group": self.selected_teacher_group,
            "selected_group_students_page": self.selected_group_students_page,
            "selected_group_students_count": self.selected_group_students_count,
            "selected_group_students_filtered_count": self.selected_group_students_filtered_count,
            "group_students_search_query": self.group_students_search_query,
            "group_students_pagination_query": self.group_students_pagination_query,
            "organization_access_rows": self.organization_access_rows,
            "student_member_groups": self.student_member_groups,
            "student_member_groups_count": self.student_member_groups_count,
            "student_member_groups_more_count": self.student_member_groups_more_count,
            # Rol-əsaslı akademik məlumatlar (profil "Akademik məlumatlar" kartı).
            "academic_units": self.academic_units,
            "teacher_subjects": self.teacher_subjects,
            "student_records": self.student_records,
            "group_form": self.group_form,
            "can_multi_assign_group_teachers": self.can_multi_assign_group_teachers,
            "groups_section_return_url": self.groups_section_return_url,
            "pending_post_approval_items": self.pending_post_approval_page_obj or self.pending_post_approval_items,
            "pending_post_approval_count": self.pending_post_approval_count,
            "pending_post_approval_search_query": self.pending_post_approval_search_query,
            "pending_post_approval_filter_status": self.pending_post_approval_filter_status,
            "pending_post_approval_filter_group": self.pending_post_approval_filter_group,
            "pending_post_approval_filter_organization": self.pending_post_approval_filter_organization,
            "pending_post_approval_available_groups": self.pending_post_approval_available_groups,
            "pending_post_approval_available_organizations": self.pending_post_approval_available_organizations,
            "pending_post_approval_page_obj": self.pending_post_approval_page_obj,
            "pending_post_approval_pagination_query": self.pending_post_approval_pagination_query,
            "pending_post_approval_total_count": self.pending_post_approval_total_count,
            "pending_review_items": self.pending_review_page_obj or self.pending_review_items,
            "pending_review_search_query": self.pending_review_search_query,
            "pending_review_filter_type": self.pending_review_filter_type,
            "pending_review_filter_status": self.pending_review_filter_status,
            "pending_review_submitted_order": self.pending_review_submitted_order,
            "pending_review_filter_group": self.pending_review_filter_group,
            "pending_review_available_groups": self.pending_review_available_groups,
            "pending_review_total_count": len(self.pending_review_items),
            "pending_review_page_obj": self.pending_review_page_obj,
            "pending_review_pagination_query": self.pending_review_pagination_query,
            "evaluated_review_items": self.evaluated_review_page_obj or self.evaluated_review_items,
            "evaluated_review_search_query": self.evaluated_review_search_query,
            "evaluated_review_filter_type": self.evaluated_review_filter_type,
            "evaluated_review_filter_group": self.evaluated_review_filter_group,
            "evaluated_review_available_groups": self.evaluated_review_available_groups,
            "evaluated_review_submitted_order": self.evaluated_review_submitted_order,
            "evaluated_review_total_count": len(self.evaluated_review_items),
            "evaluated_review_page_obj": self.evaluated_review_page_obj,
            "evaluated_review_pagination_query": self.evaluated_review_pagination_query,
            "pending_student_invites": self.pending_student_invites,
            "pending_student_join_requests": self.pending_student_join_requests,
            "notifications_unread_count": self.notifications_unread_count,
            "in_app_unread_count": self.in_app_unread_count,
            "in_app_notifications_page": self.in_app_notifications_page,
            "notif_filter": self.notif_filter,
            "notif_type": self.notif_type,
            "notif_notification_types": NotificationType.choices,
            "notif_search_query": self.notif_search_query,
            "notif_pagination_query": self.notif_pagination_query,
            "pending_student_join_org_name": self.pending_student_join_org_name,
            "pending_student_join_message": self.pending_student_join_message,
            "student_can_leave_org": self.student_can_leave_org,
            "publish_notification_targets": self.publish_notification_targets,
            "role_assignment_section": self.role_assignment_section,
            "student_org_request_section": self.student_org_request_section,
            "student_org_management_section": self.student_org_management_section,
            "permission_editor_section": self.permission_editor_section,
            "manage_roles_section": self.manage_roles_section,
            "org_structure_section": self.org_structure_section,
            "org_faculties_section": self.org_faculties_section,
            "org_kafedras_section": self.org_kafedras_section,
            "org_members_section": self.org_members_section,
            "org_roles_section": self.org_roles_section,
            "audit_log_section": self.audit_log_section,
            "superadmin_org_inspector_section": self.superadmin_org_inspector_section,
            "superadmin_users_section": self.superadmin_users_section,
            "superadmin_ai_settings_section": self.superadmin_ai_settings_section,
            "superadmin_org_features_section": self.superadmin_org_features_section,
            "category_management_create_form": self.category_management_create_form,
            "category_management_edit_form": self.category_management_edit_form,
            "category_management_edit_item": self.category_management_edit_item,
            "category_management_page": self.category_management_page,
            "category_management_create_parent_options": self.category_management_create_parent_options,
            "category_management_create_selected_parent_id": self.category_management_create_selected_parent_id,
            "category_management_edit_parent_options": self.category_management_edit_parent_options,
            "category_management_edit_selected_parent_id": self.category_management_edit_selected_parent_id,
            "category_management_search_query": self.category_management_search_query,
            "category_management_page_param": self.category_management_page_param,
            "category_management_pagination_query": self.category_management_pagination_query,
            "category_management_total_count": self.category_management_total_count,
            "category_management_filtered_count": self.category_management_filtered_count,
            "superadmin_organizations_section": self.superadmin_organizations_section,
            "superadmin_pending_org_count": self.superadmin_organizations_section.get("pending_count", 0),
            "exam_rooms_section": self.exam_rooms_section,
            "kollokvium_windows_section": self.kollokvium_windows_section,
            "exam_chance_section": self.exam_chance_section,
            "can_manage_exam_rooms": self.capabilities.get("can_manage_exam_rooms", False),
            "is_teacher": self.capabilities["is_teacher"],
            "is_admin": self.capabilities["can_manage_org"],
            "is_superadmin": self.capabilities["is_superadmin"],
            "can_manage_org": self.capabilities["can_manage_org"],
            "can_view_owned_learning": self.capabilities["can_view_owned_learning"],
            "can_review_submissions": self.capabilities["can_review_submissions"],
            "can_approve_posts": self.capabilities["can_approve_posts"],
            "can_view_blog": self.capabilities["can_view_blog"],
            "can_manage_blog": self.capabilities["can_manage_blog"],
            "can_view_student_assignments": self.capabilities["can_view_student_assignments"],
            "statistics_data": self.statistics_data,
            "statistics_unit_layout": self.statistics_unit_layout,
            "statistics_filters": self.statistics_filters,
            "statistics_courses": self.statistics_courses,
            "statistics_groups": self.statistics_groups,
            "statistics_organizations": self.statistics_organizations,
            "statistics_has_active_filters": self.statistics_has_active_filters,
            "statistics_reset_url": self.statistics_reset_url,
            "statistics_org_page": self.statistics_org_page,
            "statistics_teacher_page": self.statistics_teacher_page,
            "statistics_course_page": self.statistics_course_page,
            "statistics_group_page": self.statistics_group_page,
            "statistics_teacher_course_page": self.statistics_teacher_course_page,
            "statistics_org_rows": self.statistics_org_rows,
            "statistics_teacher_rows": self.statistics_teacher_rows,
            "statistics_course_rows": self.statistics_course_rows,
            "statistics_group_rows": self.statistics_group_rows,
            "statistics_teacher_course_rows": self.statistics_teacher_course_rows,
            "statistics_org_page_param": self.statistics_org_page_param,
            "statistics_teacher_page_param": self.statistics_teacher_page_param,
            "statistics_course_page_param": self.statistics_course_page_param,
            "statistics_group_page_param": self.statistics_group_page_param,
            "statistics_teacher_course_page_param": self.statistics_teacher_course_page_param,
            "statistics_org_pagination_query": self.statistics_org_pagination_query,
            "statistics_teacher_pagination_query": self.statistics_teacher_pagination_query,
            "statistics_course_pagination_query": self.statistics_course_pagination_query,
            "statistics_group_pagination_query": self.statistics_group_pagination_query,
            "statistics_teacher_course_pagination_query": self.statistics_teacher_course_pagination_query,
        }
        self.context.update(
            {
                "review_items": self.context["pending_review_items"],
                "search_query": self.pending_review_search_query,
                "filter_type": self.pending_review_filter_type,
                "filter_status": self.pending_review_filter_status,
                "total_count": self.context["pending_review_total_count"],
                "pagination_query": self.pending_review_pagination_query,
                "organizations": self.superadmin_organizations_section.get("organizations", []),
                "all_modules": self.superadmin_organizations_section.get("all_modules", []),
                "profiles": self.manage_roles_section.get("profiles", []),
                "assignable_roles": self.manage_roles_section.get("assignable_roles", []),
                "roles": self.permission_editor_section.get("roles", []),
                "selected_role": self.permission_editor_section.get("selected_role"),
            }
        )
        self.context.update(self.student_org_management_section)
        self.context.update(
            build_contact_inbox_context(
                self.request, capabilities=self.capabilities, active_section=self.active_section
            )
        )
        if self.active_section == "my-appeals" and "my-appeals" in self.allowed_sections:
            from apps.appeals.public import build_my_appeals_context

            self.context.update(
                build_my_appeals_context(self.request, list_action=reverse("accounts:profile"), section="my-appeals")
            )
        if self.active_section == "manage-appeals" and "manage-appeals" in self.allowed_sections:
            from apps.appeals.public import build_manage_appeals_context
            from apps.appeals.public import can_open_appeal_management as _can_open_appeal_management

            if _can_open_appeal_management(self.request):
                self.context.update(
                    build_manage_appeals_context(
                        self.request, list_action=reverse("accounts:profile"), section="manage-appeals"
                    )
                )
        if self.active_section == "my-subjects" and "my-subjects" in self.allowed_sections:
            from apps.registrar.public import build_student_subjects_context

            self.context.update(build_student_subjects_context(self.request, organization=self.active_organization))
        if self.active_section == "my-transcript" and "my-transcript" in self.allowed_sections:
            from apps.registrar.public import build_student_transcript_context

            self.context.update(build_student_transcript_context(self.request, organization=self.active_organization))
        if self.active_section == "overall-academic" and "overall-academic" in self.allowed_sections:
            from apps.registrar.public import build_student_overall_academic_context

            self.context.update(
                build_student_overall_academic_context(self.request, organization=self.active_organization)
            )
        # U12 — registrar kabineti bölmələri (SPA panel): yalnız aktiv bölmə üçün
        # qurulur (lazy) ki, hər profil açılışında lazımsız sorğular işləməsin.
        _registrar_sections = {"my-schedule", "academic-calendar", "my-journal", "grade-approvals", "analytics"}
        if self.active_section in _registrar_sections and self.active_section in self.allowed_sections:
            from apps.registrar.public import build_profile_registrar_section

            self.context.update(
                build_profile_registrar_section(
                    self.request, organization=self.active_organization, section=self.active_section
                )
            )
