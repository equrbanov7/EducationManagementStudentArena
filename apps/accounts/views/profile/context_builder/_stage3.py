"""build_profile_response — stage 3 (god-file refaktoru, FAZA 4)."""

from django.urls import reverse

from apps.accounts import profile_hooks

from ..._helpers import (
    STUDENT_ORG_MANAGEMENT_MIN_LEVEL,
    _append_query_params,
    _build_student_org_management_section,
    _build_student_org_request_section,
    _collect_actor_permissions,
    _ensure_profile_admin_membership,
    _get_active_organization,
)
from ...account_management import build_superadmin_user_management_context
from ...superadmin import build_superadmin_ai_settings_context
from .._sections.manage_roles import build_manage_roles_section
from .._sections.notifications import build_notifications_context
from .._sections.permission_editor import build_permission_editor_section
from .._sections.role_assignment import build_role_assignment_section
from .._sections.statistics import build_statistics_section
from .._sections.superadmin_orgs import build_superadmin_orgs_sections
from ._helpers import _get_publish_notification_targets


class _Stage3Mixin:

    def _stage_3(self):
        self._empty_structure_section_base = {
            "organization": self.active_organization,
            "can_view": False,
            "search_query": "",
            "sort_value": "name",
            "head_candidates": [],
            "can_create": False,
            "can_edit": False,
            "can_delete": False,
            "can_assign_head": False,
            "pagination_query": "",
            "form_errors": {},
            "form_values": {},
            "notice": "",
            "profile_base_url": reverse("accounts:profile"),
            "embedded_in_profile": True,
        }
        self.org_faculties_section = {
            **self._empty_structure_section_base,
            "faculties": [],
            "faculties_page_obj": None,
            "faculty_total_count": 0,
            "kafedra_total_count": 0,
            "filtered_count": 0,
        }
        self.org_kafedras_section = {
            **self._empty_structure_section_base,
            "kafedras": [],
            "kafedras_page_obj": None,
            "kafedra_total_count": 0,
            "faculty_total_count": 0,
            "filtered_count": 0,
            "faculty_filter": "",
            "faculty_options": [],
            "teacher_options": [],
            "unassigned_teacher_count": 0,
            "can_assign_teachers": False,
        }
        self.org_members_section = {
            "organization": self.active_organization,
            "members": [],
            "members_page_obj": None,
            "roles": [],
            "current_role": "",
            "search_query": "",
            "can_view": False,
            "members_pagination_query": "section=org-members",
            "profile_base_url": reverse("accounts:profile"),
            "embedded_in_profile": True,
        }
        self.org_roles_section = {
            "organization": self.active_organization,
            "roles": [],
            "can_view": False,
            "profile_base_url": reverse("accounts:profile"),
            "embedded_in_profile": True,
        }
        self.audit_log_section = {
            "audit_logs": [],
            "current_organization": self.active_organization,
            "is_superadmin": self.capabilities["is_superadmin"],
            "embedded_in_profile": True,
        }
        self.management_org = None
        self.management_user_level = 0
        self.management_actor_permissions = set()
        self.management_grantable_permissions = set()
        self.management_can_assign_roles = False
        self.management_min_level_ok = False
        self._management_sections = {"role-assignment", "permission-editor", "student-organization-management"}
        if self.active_section in self._management_sections and (
            "role-assignment" in self.allowed_sections
            or "permission-editor" in self.allowed_sections
            or "student-organization-management" in self.allowed_sections
        ):
            from apps.organizations.public import get_user_org_role_level
            from core.permissions import has_permission

            self.management_org = _get_active_organization(self.request)
            if self.management_org:
                _ensure_profile_admin_membership(self.request.user, self.management_org)
                self.management_user_level = (
                    999
                    if self.capabilities["is_superadmin"]
                    else get_user_org_role_level(self.request.user, self.management_org)
                )
                self.management_actor_permissions, self.management_grantable_permissions = _collect_actor_permissions(
                    self.request.user, self.management_org, request=self.request
                )
                self.management_can_assign_roles = (
                    self.capabilities["is_superadmin"]
                    or has_permission(list(self.management_actor_permissions), "role.assign")
                    or has_permission(list(self.management_actor_permissions), "org.manage_members")
                )
                self.management_min_level_ok = self.capabilities["is_superadmin"] or self.management_user_level >= 50
        if "role-assignment" in self.allowed_sections and self.active_section == "role-assignment":
            self.role_assignment_section = build_role_assignment_section(
                self.request,
                self.role_assignment_section,
                management_org=self.management_org,
                management_can_assign_roles=self.management_can_assign_roles,
                management_min_level_ok=self.management_min_level_ok,
                management_user_level=self.management_user_level,
                capabilities=self.capabilities,
            )
        if (
            "student-organization-management" in self.allowed_sections
            and self.active_section == "student-organization-management"
        ):
            self.student_org_management_section = _build_student_org_management_section(
                request=self.request,
                organization=self.management_org,
                is_superadmin=self.capabilities["is_superadmin"],
                user_level=self.management_user_level,
                teacher_student_only=self.capabilities.get("teacher_has_student_org_access", False),
                can_manage_students=self.capabilities["is_superadmin"]
                or self.capabilities["is_org_admin"]
                or self.management_user_level >= STUDENT_ORG_MANAGEMENT_MIN_LEVEL
                or self.capabilities.get("teacher_can_manage_students", False),
                can_invite_members=self.capabilities["is_superadmin"]
                or self.capabilities["is_org_admin"]
                or self.management_user_level >= STUDENT_ORG_MANAGEMENT_MIN_LEVEL
                or self.capabilities.get("teacher_can_invite_members", False),
            )
            self.student_org_management_section["post_next_url"] = _append_query_params(
                reverse("accounts:profile"),
                section="student-organization-management",
                management_view=self.student_org_management_section["active_management_view"],
                student_tab=self.student_org_management_section["active_student_tab"],
                teacher_tab=self.student_org_management_section["active_teacher_tab"],
                staff_tab=self.student_org_management_section["active_staff_tab"],
                student_org_search=self.student_org_management_section["student_search_query"],
                student_org_pending_search=self.student_org_management_section["pending_search_query"],
                student_org_unassigned_search=self.student_org_management_section["unassigned_search_query"],
                student_org_sent_invite_search=self.student_org_management_section["sent_invite_search_query"],
                student_org_ts_search=self.student_org_management_section["teacher_staff_search_query"],
                organization_search=self.student_org_management_section["organization_search_query"],
                organization_status=self.student_org_management_section["organization_status_filter"],
                organization_type=self.student_org_management_section["organization_type_filter"],
            )
        if "student-organization-request" in self.allowed_sections and self.active_section in {
            "student-organization-request",
            "profile-info",
        }:
            self.student_org_request_section = _build_student_org_request_section(
                request=self.request, profile=self.profile
            )
            self.student_org_request_section["post_next_url"] = _append_query_params(
                reverse("accounts:profile"),
                section="student-organization-request",
                student_org_request_search=self.student_org_request_section["search_query"],
                student_org_request_type=self.student_org_request_section["org_type_filter"],
            )
        if "permission-editor" in self.allowed_sections and self.active_section == "permission-editor":
            self.permission_editor_section = build_permission_editor_section(
                self.request,
                self.permission_editor_section,
                management_org=self.management_org,
                management_actor_permissions=self.management_actor_permissions,
                management_grantable_permissions=self.management_grantable_permissions,
                management_can_assign_roles=self.management_can_assign_roles,
                management_user_level=self.management_user_level,
                capabilities=self.capabilities,
            )
        if "manage-roles" in self.allowed_sections and self.active_section == "manage-roles":
            self.manage_roles_section = build_manage_roles_section(
                self.request, self.manage_roles_section, capabilities=self.capabilities
            )
        if (
            self.active_section == "org-structure"
            and "org-structure" in self.allowed_sections
            and (self.active_organization is not None)
        ):
            from apps.organizations.public import build_organization_structure_context

            self.org_structure_section = build_organization_structure_context(self.request, self.active_organization)
            self.org_structure_section["embedded_in_profile"] = True
        if (
            self.active_section == "org-faculties"
            and "org-faculties" in self.allowed_sections
            and (self.active_organization is not None)
        ):
            from apps.organizations.public import build_organization_faculties_context

            self.org_faculties_section = build_organization_faculties_context(self.request, self.active_organization)
            self.org_faculties_section["embedded_in_profile"] = True
        if (
            self.active_section == "org-kafedras"
            and "org-kafedras" in self.allowed_sections
            and (self.active_organization is not None)
        ):
            from apps.organizations.public import build_organization_kafedras_context

            self.org_kafedras_section = build_organization_kafedras_context(self.request, self.active_organization)
            self.org_kafedras_section["embedded_in_profile"] = True
        if (
            self.active_section == "org-members"
            and "org-members" in self.allowed_sections
            and (self.active_organization is not None)
        ):
            from apps.organizations.public import build_organization_members_context

            self.org_members_section = build_organization_members_context(self.request, self.active_organization)
            self.org_members_section["embedded_in_profile"] = True
        if (
            self.active_section == "org-roles"
            and "org-roles" in self.allowed_sections
            and (self.active_organization is not None)
        ):
            from apps.organizations.public import build_organization_roles_context

            self.org_roles_section = build_organization_roles_context(self.request, self.active_organization)
            self.org_roles_section["embedded_in_profile"] = True
        if self.active_section == "audit-log" and "audit-log" in self.allowed_sections:
            from apps.audit.public import build_audit_log_context

            self.audit_log_section = build_audit_log_context(self.request)
            self.audit_log_section["embedded_in_profile"] = True
        self.superadmin_org_inspector_section = {}
        if self.active_section == "superadmin-org-inspector" and "superadmin-org-inspector" in self.allowed_sections:
            from ..._helpers.superadmin_inspector import build_superadmin_org_inspector_section

            self.superadmin_org_inspector_section = build_superadmin_org_inspector_section(
                self.request, is_superadmin=self.capabilities["is_superadmin"]
            )
        if "superadmin-organizations" in self.allowed_sections and self.active_section != "superadmin-organizations":
            from apps.organizations.models import Organization as _PendingOrg

            self.superadmin_organizations_section["pending_count"] = _PendingOrg.objects.filter(
                status="pending"
            ).count()
        if (
            "superadmin-org-features" in self.allowed_sections
            and self.active_section == "superadmin-org-features"
            or (
                "superadmin-organizations" in self.allowed_sections
                and self.active_section == "superadmin-organizations"
            )
        ):
            build_superadmin_orgs_sections(
                self.request,
                self.superadmin_org_features_section,
                self.superadmin_organizations_section,
                allowed_sections=self.allowed_sections,
                active_section=self.active_section,
                organization_access_rows=self.organization_access_rows,
            )
        if "superadmin-users" in self.allowed_sections and self.active_section == "superadmin-users":
            self.superadmin_users_section.update(
                build_superadmin_user_management_context(
                    self.request, base_url=reverse("accounts:profile"), include_section=True
                )
            )
        if "rim-center" in self.allowed_sections and self.active_section == "rim-center":
            from ...rim import build_rim_center_section

            self.rim_center_section.update(build_rim_center_section(self.request))
        if "superadmin-ai" in self.allowed_sections and self.active_section == "superadmin-ai":
            self.superadmin_ai_settings_section.update(build_superadmin_ai_settings_context())
            self.superadmin_ai_settings_section["post_next_url"] = _append_query_params(
                reverse("accounts:profile"), section="superadmin-ai"
            )
        if "superadmin-exam-rooms" in self.allowed_sections and self.active_section == "superadmin-exam-rooms":
            from .._sections.exam_rooms import build_exam_rooms_section

            build_exam_rooms_section(
                self.request,
                self.exam_rooms_section,
                is_superadmin=self.capabilities["is_superadmin"],
                active_organization=self.active_organization,
                allowed_sections=self.allowed_sections,
                active_section=self.active_section,
            )
        if "kollokvium-windows" in self.allowed_sections and self.active_section == "kollokvium-windows":
            from .._sections.kollokvium_windows import build_kollokvium_windows_section

            build_kollokvium_windows_section(
                self.request,
                self.kollokvium_windows_section,
                is_superadmin=self.capabilities["is_superadmin"],
                active_organization=self.active_organization,
                allowed_sections=self.allowed_sections,
                active_section=self.active_section,
            )
        if "exam-chance" in self.allowed_sections and self.active_section == "exam-chance":
            from .._sections.exam_chance import build_exam_chance_section

            build_exam_chance_section(
                self.request,
                self.exam_chance_section,
                active_organization=self.active_organization,
                allowed_sections=self.allowed_sections,
                active_section=self.active_section,
            )
        self._notif_ctx = build_notifications_context(self.request, active_section=self.active_section)
        self.notif_filter = self._notif_ctx["notif_filter"]
        self.notif_type = self._notif_ctx["notif_type"]
        self.notif_search_query = self._notif_ctx["notif_search_query"]
        self.notif_pagination_query = self._notif_ctx["notif_pagination_query"]
        self.in_app_notifications_page = self._notif_ctx["in_app_notifications_page"]
        self.publish_notification_targets = []
        if "publish-notification" in self.allowed_sections and self.active_section == "publish-notification":
            self.publish_notification_targets = _get_publish_notification_targets(self.request.user, self.capabilities)
        self.category_management_page = None
        self.category_management_create_parent_options = []
        self.category_management_create_selected_parent_id = ""
        self.category_management_edit_parent_options = []
        self.category_management_edit_selected_parent_id = ""
        self.category_management_search_query = ""
        self.category_management_page_param = "category_page"
        self.category_management_pagination_query = ""
        self.category_management_total_count = 0
        self.category_management_filtered_count = 0
        if {"create-category", "category-management"} & set(self.allowed_sections) and self.active_section in {
            "create-category",
            "category-management",
        }:
            self._cc = profile_hooks.create_category_section(self.category_management_create_form)
            self.category_management_create_form = self._cc["category_management_create_form"]
            self.category_management_create_parent_options = self._cc["category_management_create_parent_options"]
            self.category_management_create_selected_parent_id = self._cc[
                "category_management_create_selected_parent_id"
            ]
        if "category-management" in self.allowed_sections and self.active_section == "category-management":
            self._cm = profile_hooks.category_management_section(
                self.request,
                edit_form=self.category_management_edit_form,
                edit_item=self.category_management_edit_item,
                page_param=self.category_management_page_param,
            )
            self.category_management_search_query = self._cm["category_management_search_query"]
            self.category_management_total_count = self._cm["category_management_total_count"]
            self.category_management_filtered_count = self._cm["category_management_filtered_count"]
            self.category_management_page = self._cm["category_management_page"]
            self.category_management_pagination_query = self._cm["category_management_pagination_query"]
            self.category_management_edit_form = self._cm["category_management_edit_form"]
            self.category_management_edit_item = self._cm["category_management_edit_item"]
            self.category_management_edit_parent_options = self._cm["category_management_edit_parent_options"]
            self.category_management_edit_selected_parent_id = self._cm["category_management_edit_selected_parent_id"]
        self.statistics_data = {}
        self.statistics_filters = {}
        self.statistics_unit_layout = False
        self.statistics_courses = []
        self.statistics_groups = []
        self.statistics_organizations = []
        self.statistics_has_active_filters = False
        self.statistics_reset_url = _append_query_params(reverse("accounts:profile"), section="statistics")
        self.statistics_org_page = None
        self.statistics_teacher_page = None
        self.statistics_course_page = None
        self.statistics_group_page = None
        self.statistics_teacher_course_page = None
        self.statistics_org_rows = []
        self.statistics_teacher_rows = []
        self.statistics_course_rows = []
        self.statistics_group_rows = []
        self.statistics_teacher_course_rows = []
        self.statistics_org_page_param = "stats_org_page"
        self.statistics_teacher_page_param = "stats_teacher_page"
        self.statistics_course_page_param = "stats_course_page"
        self.statistics_group_page_param = "stats_group_page"
        self.statistics_teacher_course_page_param = "stats_teacher_course_page"
        self.statistics_org_pagination_query = ""
        self.statistics_teacher_pagination_query = ""
        self.statistics_course_pagination_query = ""
        self.statistics_group_pagination_query = ""
        self.statistics_teacher_course_pagination_query = ""
        if self.active_section == "statistics" and "statistics" in self.allowed_sections:
            from django.http import HttpResponse as _HttpResponse

            self._stats = build_statistics_section(self.request, capabilities=self.capabilities)
            if isinstance(self._stats, _HttpResponse):
                return self._stats
            self.statistics_filters = self._stats["statistics_filters"]
            self.statistics_data = self._stats["statistics_data"]
            self.statistics_courses = self._stats["statistics_courses"]
            self.statistics_groups = self._stats["statistics_groups"]
            self.statistics_organizations = self._stats["statistics_organizations"]
            self.statistics_has_active_filters = self._stats["statistics_has_active_filters"]
            self.statistics_unit_layout = self._stats["statistics_unit_layout"]
            self.statistics_org_page = self._stats["statistics_org_page"]
            self.statistics_org_rows = self._stats["statistics_org_rows"]
            self.statistics_org_pagination_query = self._stats["statistics_org_pagination_query"]
            self.statistics_teacher_page = self._stats["statistics_teacher_page"]
            self.statistics_teacher_rows = self._stats["statistics_teacher_rows"]
            self.statistics_teacher_pagination_query = self._stats["statistics_teacher_pagination_query"]
            self.statistics_course_page = self._stats["statistics_course_page"]
            self.statistics_course_rows = self._stats["statistics_course_rows"]
            self.statistics_course_pagination_query = self._stats["statistics_course_pagination_query"]
            self.statistics_group_page = self._stats["statistics_group_page"]
            self.statistics_group_rows = self._stats["statistics_group_rows"]
            self.statistics_group_pagination_query = self._stats["statistics_group_pagination_query"]
            self.statistics_teacher_course_page = self._stats["statistics_teacher_course_page"]
            self.statistics_teacher_course_rows = self._stats["statistics_teacher_course_rows"]
            self.statistics_teacher_course_pagination_query = self._stats["statistics_teacher_course_pagination_query"]
