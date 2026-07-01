"""build_profile_response — stage 2 (god-file refaktoru, FAZA 4)."""

from django.core.paginator import Paginator
from django.urls import reverse

from ..._helpers import STUDENT_ORG_REQUEST_MESSAGE_MAX_LENGTH
from .._sections.review_queue import build_pending_review_context, build_review_results_context


class _Stage2Mixin:

    def _stage_2(self):
        from apps.blog.selectors import build_post_category_picker_options, get_post_category_tree
        from apps.blog.services import collect_reviewable_posts, count_pending_reviewable_posts

        self.pending_post_approval_items = []
        self.pending_post_approval_count = 0
        self.pending_post_approval_search_query = ""
        self.pending_post_approval_filter_status = "pending"
        self.pending_post_approval_filter_group = ""
        self.pending_post_approval_filter_organization = ""
        self.pending_post_approval_available_groups = []
        self.pending_post_approval_available_organizations = []
        self.pending_post_approval_page_obj = None
        self.pending_post_approval_pagination_query = ""
        self.pending_post_approval_total_count = 0
        if "pending-post-approvals" in self.allowed_sections and self.active_section != "pending-post-approvals":
            self.pending_post_approval_count = count_pending_reviewable_posts(self.request.user)
        if "pending-post-approvals" in self.allowed_sections and self.active_section == "pending-post-approvals":
            (
                self.pending_post_approval_items,
                self.pending_post_approval_search_query,
                self.pending_post_approval_filter_status,
                self.pending_post_approval_filter_group,
                self.pending_post_approval_available_groups,
                self.pending_post_approval_filter_organization,
                self.pending_post_approval_available_organizations,
            ) = collect_reviewable_posts(
                self.request.user,
                search=self.request.GET.get("approval_search"),
                status=self.request.GET.get("approval_status"),
                group_id=self.request.GET.get("approval_group"),
                organization_id=self.request.GET.get("approval_organization"),
            )
            self.pending_post_approval_total_count = len(self.pending_post_approval_items)
            self.pending_post_approval_count = count_pending_reviewable_posts(self.request.user)
            if not self.post_category_root_options:
                self.post_category_tree = get_post_category_tree()
                self.post_category_root_options, self.post_category_subcategory_options = (
                    build_post_category_picker_options(self.post_category_tree)
                )
            self.pending_post_approval_page_obj = Paginator(self.pending_post_approval_items, 10).get_page(
                self.request.GET.get("approval_page", 1)
            )
            self.extra = []
            self.extra.append("section=pending-post-approvals")
            if self.pending_post_approval_search_query:
                self.extra.append(f"approval_search={self.pending_post_approval_search_query}")
            if self.pending_post_approval_filter_status and self.pending_post_approval_filter_status != "pending":
                self.extra.append(f"approval_status={self.pending_post_approval_filter_status}")
            if self.pending_post_approval_filter_group:
                self.extra.append(f"approval_group={self.pending_post_approval_filter_group}")
            if self.pending_post_approval_filter_organization:
                self.extra.append(f"approval_organization={self.pending_post_approval_filter_organization}")
            self.pending_post_approval_pagination_query = "&".join(self.extra)
        self.pending_review_items = []
        self.pending_review_search_query = ""
        self.pending_review_filter_type = "all"
        self.pending_review_filter_status = "all"
        self.pending_review_submitted_order = "oldest"
        self.pending_review_filter_group = ""
        self.pending_review_available_groups = []
        self.pending_review_page_obj = None
        self.pending_review_pagination_query = ""
        self.evaluated_review_items = []
        self.evaluated_review_search_query = ""
        self.evaluated_review_filter_type = "all"
        self.evaluated_review_filter_group = ""
        self.evaluated_review_available_groups = []
        self.evaluated_review_submitted_order = "newest"
        self.evaluated_review_page_obj = None
        self.evaluated_review_pagination_query = ""
        if self.active_section == "pending-review" and "pending-review" in self.allowed_sections:
            self._pr = build_pending_review_context(self.request)
            self.pending_review_items = self._pr["pending_review_items"]
            self.pending_review_search_query = self._pr["pending_review_search_query"]
            self.pending_review_filter_type = self._pr["pending_review_filter_type"]
            self.pending_review_filter_status = self._pr["pending_review_filter_status"]
            self.pending_review_submitted_order = self._pr["pending_review_submitted_order"]
            self.pending_review_filter_group = self._pr["pending_review_filter_group"]
            self.pending_review_available_groups = self._pr["pending_review_available_groups"]
            self.pending_review_page_obj = self._pr["pending_review_page_obj"]
            self.pending_review_pagination_query = self._pr["pending_review_pagination_query"]
        if self.active_section == "review-results" and "review-results" in self.allowed_sections:
            self._er = build_review_results_context(self.request)
            self.evaluated_review_items = self._er["evaluated_review_items"]
            self.evaluated_review_search_query = self._er["evaluated_review_search_query"]
            self.evaluated_review_filter_type = self._er["evaluated_review_filter_type"]
            self.evaluated_review_filter_group = self._er["evaluated_review_filter_group"]
            self.evaluated_review_available_groups = self._er["evaluated_review_available_groups"]
            self.evaluated_review_submitted_order = self._er["evaluated_review_submitted_order"]
            self.evaluated_review_page_obj = self._er["evaluated_review_page_obj"]
            self.evaluated_review_pagination_query = self._er["evaluated_review_pagination_query"]
        self.role_assignment_section = {
            "organization": None,
            "members": [],
            "assignable_roles": [],
            "search_query": "",
            "unassigned_search_query": "",
            "unassigned_users": [],
            "can_assign_roles": False,
            "access_denied_message": "",
            "members_page_param": "role_members_page",
            "members_pagination_query": "",
            "unassigned_page_param": "role_pending_page",
            "unassigned_pagination_query": "",
            "post_next_url": "",
        }
        self.student_org_management_section = {
            "organization": None,
            "students": [],
            "pending_requested_students": [],
            "unassigned_students": [],
            "sent_student_invites": [],
            "student_search_query": "",
            "pending_search_query": "",
            "unassigned_search_query": "",
            "sent_invite_search_query": "",
            "access_denied_message": "",
            "can_manage_students": False,
            "students_page_param": "student_org_members_page",
            "students_pagination_query": "",
            "pending_page_param": "student_org_pending_page",
            "pending_pagination_query": "",
            "unassigned_page_param": "student_org_unassigned_page",
            "unassigned_pagination_query": "",
            "sent_invites_page_param": "student_org_sent_invites_page",
            "sent_invites_pagination_query": "",
            "post_next_url": "",
        }
        self.student_org_request_section = {
            "organizations": [],
            "search_query": "",
            "org_type_filter": "",
            "pending_invites": list(self.pending_student_invites or []),
            "pending_invites_count": len(self.pending_student_invites or []),
            "has_pending_invites": bool(self.pending_student_invites),
            "pending_student_requests": [],
            "pending_student_requests_count": 0,
            "has_pending_student_requests": False,
            "pending_request_org_ids": set(),
            "current_organization": None,
            "pending_requested_organization": None,
            "pending_requested_org_name": "",
            "pending_request_message": "",
            "selected_org_id": "",
            "page_param": "student_org_request_page",
            "pagination_query": "",
            "post_next_url": "",
            "request_message_max_length": STUDENT_ORG_REQUEST_MESSAGE_MAX_LENGTH,
        }
        self.permission_editor_section = {
            "organization": None,
            "roles": [],
            "selected_role": None,
            "permission_categories": {},
            "actor_permissions": [],
            "grantable_permissions": [],
            "can_manage_permissions": False,
            "access_denied_message": "",
        }
        self.manage_roles_section = {
            "profiles": [],
            "assignable_roles": [],
            "search_query": "",
            "organization": None,
            "access_denied_message": "",
            "profiles_page_param": "manage_roles_page",
            "profiles_pagination_query": "",
        }
        self.superadmin_users_section = {
            "users": [],
            "user_rows": [],
            "status_tabs": [],
            "role_options": [],
            "organization_options": [],
            "sort_options": [],
            "search_query": "",
            "status_filter": "all",
            "role_filter": "",
            "organization_filter": "",
            "group_filter": "",
            "department_filter": "",
            "sort_filter": "newest",
            "pagination_query": "",
            "page_param": "user_page",
            "post_next_url": "",
            "reset_url": "",
            "filtered_count": 0,
            "total_count": 0,
            "active_count": 0,
            "blocked_count": 0,
            "deleted_count": 0,
            "embedded_in_profile": True,
        }
        self.superadmin_ai_settings_section = {
            "config": None,
            "model_choices": [],
            "rate_info": {},
            "cost_estimates": {},
            "post_next_url": "",
        }
        self.superadmin_org_features_section = {
            "organizations": [],
            "organizations_page_param": "superadmin_feature_org_page",
            "organizations_pagination_query": "",
            "post_next_url": "",
        }
        self.superadmin_organizations_section = {
            "organizations": [],
            "organization_access_rows": [],
            "all_modules": [],
            "organizations_page_param": "superadmin_org_page",
            "organizations_pagination_query": "",
            "post_next_url": "",
            "pending_count": 0,
        }
        self.org_structure_section = {
            "organization": self.active_organization,
            "units": [],
            "faculties": [],
            "kafedras": [],
            "faculty_count": 0,
            "kafedra_count": 0,
            "unit_total_count": 0,
            "can_create_faculty": False,
            "can_create_kafedra": False,
            "faculty_parent_options": [],
            "form_errors": {},
            "form_values": {},
            "notice": "",
            "profile_base_url": reverse("accounts:profile"),
            "embedded_in_profile": True,
        }
