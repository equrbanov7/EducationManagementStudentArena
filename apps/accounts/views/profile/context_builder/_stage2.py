"""build_profile_response — stage 2 (god-file refaktoru, FAZA 4)."""

from django.urls import reverse

from apps.accounts import profile_hooks

from ..._helpers import STUDENT_ORG_REQUEST_MESSAGE_MAX_LENGTH
from .._sections.review_queue import build_pending_review_context, build_review_results_context


class _Stage2Mixin:

    def _stage_2(self):
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
            self.pending_post_approval_count = profile_hooks.pending_posts_count(self.request.user)
        if "pending-post-approvals" in self.allowed_sections and self.active_section == "pending-post-approvals":
            # M2 (2026-07-02): blog implementasiyası profile_hooks üzərindən
            # (apps/blog/profile_sections.py) — davranış köhnə inline blokla eynidir.
            _pp = profile_hooks.pending_posts_section(
                self.request,
                have_category_options=bool(self.post_category_root_options),
            )
            self.pending_post_approval_items = _pp["items"]
            self.pending_post_approval_search_query = _pp["search_query"]
            self.pending_post_approval_filter_status = _pp["filter_status"]
            self.pending_post_approval_filter_group = _pp["filter_group"]
            self.pending_post_approval_available_groups = _pp["available_groups"]
            self.pending_post_approval_filter_organization = _pp["filter_organization"]
            self.pending_post_approval_available_organizations = _pp["available_organizations"]
            self.pending_post_approval_total_count = _pp["total_count"]
            self.pending_post_approval_count = _pp["count"]
            self.pending_post_approval_page_obj = _pp["page_obj"]
            self.pending_post_approval_pagination_query = _pp["pagination_query"]
            if _pp["category_options"] is not None:
                (
                    self.post_category_tree,
                    self.post_category_root_options,
                    self.post_category_subcategory_options,
                ) = _pp["category_options"]
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
        # «Müəllimlər» / «Tələbələr» kataloqu — RİM ilə eyni naxış: panel SPA-dır,
        # server yalnız çərçivəni verir (bax views/people/section.py müqaviləsi).
        # Bölmə aktiv deyilsə boş qalır; şablon `has_access` yoxlayır.
        self.people_section = {"kind": "", "has_access": False}
        # Sillabus — müəllim səthi. Bölmə aktiv deyilsə AĞIR sorğu getmir; şablon
        # `has_access` / `view_state` yoxlayır (bax views/syllabus/ müqaviləsi).
        self.syllabus_list_section = {"has_access": False, "rows": []}
        self.syllabus_editor_section = {"view_state": "missing", "nav": [], "panels": []}
        # Sillabus — KAFEDRA təsdiq səthi (ayrı icazə açarı: `syllabus.review`).
        self.syllabus_review_section = {"has_access": False, "has_scope": False, "rows": []}
        # «RİM mərkəzi» — panel SPA-dır, server yalnız icazə xəritəsini verir.
        self.rim_center_section = {
            "can_search": False,
            "can_set_password": False,
            "can_block": False,
            "can_soft_delete": False,
            "can_edit": False,
            "is_superadmin": False,
            "organization": None,
            "granted_permissions": [],
            "search_url": "",
            "action_url": "",
            "detail_url_template": "",
            "role_assignment_url": "",
            "editable_field_labels": {},
            "min_reason_length": 3,
            "max_reason_length": 300,
            "access_denied_message": "",
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
        # İmtahan zalı + kompüter/MAC bölməsi (superadmin / bayraqlı idarəçi).
        self.exam_rooms_section = {
            "is_superadmin": False,
            "org_options": [],
            "selected_org": None,
            "rooms": [],
            "room_managers": [],
            "post_next_url": "",
        }
        # Kollokvium bal-yazma pəncərələri (İmtahan Mərkəzi).
        self.kollokvium_windows_section = {
            "is_superadmin": False,
            "is_head": False,
            "org_options": [],
            "selected_org": None,
            "periods": [],
            "period": None,
            "k_rows": [],
            "faculties": [],
            "departments": [],
            "post_next_url": "",
        }
        # RİM — semestr sonu toplu jurnal bağlaması + bağlanma xəbərdarlığı.
        self.journal_close_section = {
            "is_superadmin": False,
            "org_options": [],
            "selected_org": None,
            "years": [],
            "selected_year": None,
            "periods": [],
            "period": None,
            "faculties": [],
            "departments": [],
            "selected_scope": "organization",
            "selected_unit_id": "",
            "preview": None,
            "notices": [],
            "post_next_url": "",
        }
        # Fənnin başqa müəllimə TƏHVİLİ (`journal.reassign`) — SPA çərçivəsi.
        self.handover_section = {
            "has_access": False,
            "access_denied_message": "",
            "scope_label": "",
            "teachers_url": "",
            "offerings_url": "",
            "options_url": "",
            "history_url": "",
            "action_url": "",
            "default_page_size": 25,
            "min_reason_length": 3,
            "max_reason_length": 1000,
            "max_bulk_rows": 100,
        }
        # İmtahan Mərkəzi — köçürülmüş imtahan nəticələrinin dəqiqləşdirilməsi.
        # Panel SPA-dır: burada YALNIZ çərçivə saxlanılır (URL + bayraq + sabit),
        # sətirlər JSON-la gəlir — 170 min sətirlik sübut qatı profil kontekstində
        # HEÇ VAXT hesablanmır.
        self.legacy_grade_review_section = {
            "has_access": False,
            "can_review": False,
            "access_denied_message": "",
            "observer_notice": "",
            "queue_url": "",
            "options_url": "",
            "faculty_url": "",
            "kafedra_url": "",
            "specialty_url": "",
            "group_url": "",
            "subject_url": "",
            "teacher_url": "",
            "action_url": "",
            "reasons": [],
            "default_page_size": 25,
            "min_note_length": 3,
            "max_note_length": 1000,
        }
        # İmtahan Mərkəzi — kağız imtahan balının əl ilə daxil edilməsi.
        self.exam_score_entry_section = {
            "is_superadmin": False,
            "org_options": [],
            "selected_org": None,
            "years": [],
            "selected_year": None,
            "periods": [],
            "period": None,
            "subjects": [],
            "selected_subject_id": "",
            "offerings": [],
            "offering": None,
            "rows": [],
            "reasons": [],
            "exam_score_max": 0,
            "journal_locked": False,
            "post_next_url": "",
        }
        # «İmtahan şansı ver» (ikinci şans) bölməsi (İmtahan Mərkəzi).
        self.exam_chance_section = {
            "selected_org": None,
            "exams": [],
            "groups": [],
            "recent_grants": [],
            "student_results": [],
            "filters": {},
            "years": [],
            "periods": [],
            "faculties": [],
            "kafedras": [],
            "selected_exam_id": "",
            "post_next_url": "",
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
