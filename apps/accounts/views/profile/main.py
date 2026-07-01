"""
Main profile view: ``user_profile``.

This is a GET-oriented context builder that assembles the (large) template
context for ``accounts/profile.html``. POST-form handling is delegated to
``post_handler.handle_profile_post``; input sanitization lives in ``search``;
shared helpers come from the ``_helpers`` and ``_dashboard_helpers`` packages.

Behavior is identical to the pre-refactor single-file implementation.
"""

from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.shortcuts import render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.utils.translation import pgettext_lazy

from apps.courses.models import Course
from apps.exams.models import Exam, StudentGroup
from apps.notifications.models import NotificationType
from apps.notifications.services import build_profile_notification_state, get_unread_count
from core.cache import get_or_set_cached_profile_badge_counts
from core.tenancy import restore_request_organization_from_profile

from ...forms import CustomPasswordChangeForm
from ...models import ProfileRole, UserProfile
from ...services.profile_actions import validate_profile_avatar_upload
from .._dashboard_helpers import (
    _collect_assigned_tasks,
    _collect_my_results,
    _collect_pending_answer_items,
)
from .._dashboard_helpers.cheap_counts import compute_profile_badge_counts
from .._helpers import (
    PROFILE_ROLE_LABELS,
    STUDENT_MEMBER_GROUPS_DISPLAY_LIMIT,
    STUDENT_ORG_MANAGEMENT_MIN_LEVEL,
    STUDENT_ORG_REQUEST_MESSAGE_MAX_LENGTH,
    _append_query_params,
    _assigned_courses_queryset,
    _assigned_exams_queryset,
    _build_student_org_management_section,
    _build_student_org_request_section,
    _build_user_organization_access_rows,
    _collect_actor_permissions,
    _ensure_profile_admin_membership,
    _get_active_organization,
    _query_string,
    _role_capabilities,
    _tenant_scoped_courses,
    _tenant_scoped_exams,
)
from ..account_management import build_superadmin_user_management_context
from ..superadmin import build_superadmin_ai_settings_context
from ._sections.exams import build_my_exams_context
from ._sections.groups import build_groups_context
from ._sections.labels import DIRECT_PROFILE_SECTION_TEMPLATES, build_section_titles
from ._sections.manage_roles import build_manage_roles_section
from ._sections.notifications import build_notifications_context
from ._sections.permission_editor import build_permission_editor_section
from ._sections.posts import build_posts_context
from ._sections.question_bank import build_question_bank_context
from ._sections.review_queue import build_pending_review_context, build_review_results_context
from ._sections.role_assignment import build_role_assignment_section
from ._sections.statistics import build_statistics_section
from ._sections.superadmin_orgs import build_superadmin_orgs_sections
from ._sections.unit_exams import build_unit_exams_context
from .constants import (
    PROFILE_EXAM_NAV_SECTIONS,
    PROFILE_SECTIONS_ALLOWING_MULTI_ORG_PROFILE_FALLBACK,
    PROFILE_SECTIONS_REQUIRING_ORG_CONTEXT,
)
from .contact_inbox import (
    build_contact_inbox_context,
    handle_contact_reply_post,
)
from .post_handler import _load_managed_category, handle_profile_post
from .search import _normalize_public_profile_query_value

User = get_user_model()


def _build_effective_user_roles(user, profile):
    role_names = []

    if getattr(user, "is_superuser", False):
        role_names.append(ProfileRole.SUPERADMIN)

    if hasattr(user, "get_all_roles"):
        for role_name in user.get_all_roles():
            normalized_role_name = ProfileRole.normalize_membership_role_name(role_name)
            if normalized_role_name in PROFILE_ROLE_LABELS and normalized_role_name not in role_names:
                role_names.append(normalized_role_name)

    fallback_role_name = ProfileRole.normalize_membership_role_name(getattr(profile, "role", ""))
    if fallback_role_name in PROFILE_ROLE_LABELS and fallback_role_name not in role_names:
        role_names.append(fallback_role_name)

    role_names.sort(key=lambda role_name: (ProfileRole.LEVELS.get(role_name, 0), role_name), reverse=True)
    return [
        {
            "name": role_name,
            "label": PROFILE_ROLE_LABELS.get(role_name, role_name.replace("_", " ").title()),
        }
        for role_name in role_names
    ]


def _restore_profile_org_context(request, profile, active_section):
    """
    Re-hydrate the active organization for org-bound profile sections when the
    session lost its tenant selection but the profile still points at a valid org.
    """
    if active_section not in PROFILE_SECTIONS_REQUIRING_ORG_CONTEXT:
        return
    restore_request_organization_from_profile(
        request,
        profile=profile,
        allow_multi_org_restore=active_section in PROFILE_SECTIONS_ALLOWING_MULTI_ORG_PROFILE_FALLBACK,
    )


def _get_publish_notification_targets(user, capabilities):
    """Return list of target options for notification publishing based on role."""
    from apps.exams.models import StudentGroup
    from apps.organizations.models import Membership

    targets = []
    is_superadmin = capabilities["is_superadmin"]
    is_org_admin = capabilities["is_org_admin"]
    is_teacher = capabilities["is_teacher"]

    if is_superadmin:
        # "All users" is exclusive — if selected, ignore specific org selections
        targets.append(
            {
                "value": "all",
                "label": _("target_all_users"),
                "is_exclusive": True,
            }
        )
        from apps.organizations.models import Organization

        # QEYD: tərcümə çağırışları f-string İÇİNDƏ OLMAMALIDIR — xgettext
        # (makemessages) onları görmür və tərcümələri obsolete edir.
        org_prefix_label = _("target_org_prefix")
        for org in Organization.objects.filter(is_active=True, status="active").order_by("name"):
            targets.append(
                {
                    "value": f"org_{org.pk}",
                    "label": f"{org_prefix_label}: {org.name}",
                    "is_exclusive": False,
                }
            )
        return targets

    # Non-superadmin targets are cumulative: a user can be both an organization
    # admin (e.g. an owner) and a teacher, in which case they should be able to
    # target the whole organization as well as their own student groups.
    if is_org_admin:
        # Get user's active org memberships
        org_memberships = (
            Membership.objects.filter(user=user, is_active=True, organization__is_active=True)
            .select_related("organization")
            .order_by("organization__name", "organization_id", "-role__level", "id")
        )
        seen_org_ids = set()
        org_prefix_label = _("target_org_prefix")
        all_members_label = _("target_org_all_members")
        for membership in org_memberships:
            if membership.organization_id in seen_org_ids:
                continue
            seen_org_ids.add(membership.organization_id)
            targets.append(
                {
                    "value": f"org_{membership.organization_id}",
                    "label": f"{org_prefix_label}: {membership.organization.name} ({all_members_label})",
                    "is_exclusive": False,
                }
            )

    if is_teacher:
        teacher_groups = StudentGroup.objects.filter(teacher=user).order_by("name")
        group_prefix_label = _("target_group_prefix")
        for group in teacher_groups:
            targets.append(
                {
                    "value": f"group_{group.pk}",
                    "label": f"{group_prefix_label}: {group.name}",
                    "is_exclusive": False,
                }
            )
    return targets


@login_required
def user_profile(request):
    """
    User profile page with edit functionality.
    Ensures profile exists before rendering.
    Now accessible to ALL users (not just teachers).
    """
    from apps.blog.forms import CategoryManagementForm
    from apps.blog.models import Category
    from apps.blog.selectors import build_post_category_picker_options, get_post_category_tree
    from apps.blog.services import collect_reviewable_posts, count_pending_reviewable_posts

    # Ensure profile exists (get_or_create for safety)
    profile, _created = UserProfile.objects.get_or_create(user=request.user)
    requested_section = request.GET.get("section", "profile-info")
    _restore_profile_org_context(request, profile, requested_section)

    capabilities = _role_capabilities(request.user, profile)
    notification_state = build_profile_notification_state(user=request.user, profile=profile)
    pending_student_invites = notification_state["pending_student_invites"]
    pending_student_join_requests = notification_state["pending_student_join_requests"]
    pending_student_join_org_name = notification_state["pending_student_join_org_name"]
    pending_student_join_message = notification_state["pending_student_join_message"]
    student_can_leave_org = notification_state["student_can_leave_org"]
    org_notification_count = notification_state["unread_count"]
    in_app_unread_count = get_unread_count(user=request.user)
    notifications_unread_count = org_notification_count + in_app_unread_count

    # Avatar validation moved to services.profile_actions.validate_profile_avatar_upload
    # (FAZA 8). Kept as a thin local alias so the call sites below read cleanly.
    _validate_avatar_upload = validate_profile_avatar_upload

    # Get active section from URL parameter (default: profile-info)
    allowed_sections = capabilities["allowed_sections"]
    active_section = requested_section if requested_section in allowed_sections else "profile-info"
    if active_section == "delete-account":
        active_section = "profile-info"
    password_change_form = CustomPasswordChangeForm(request.user)
    category_management_create_form = None
    category_management_edit_form = None
    category_management_edit_item = None

    if request.method == "POST":
        # Inline reply from the contact-messages section. Short-circuits
        # the generic profile POST handler because the action is owned
        # entirely by the contact inbox module.
        contact_reply_response = handle_contact_reply_post(
            request,
            capabilities=capabilities,
        )
        if contact_reply_response is not None:
            return contact_reply_response

        post_result = handle_profile_post(
            request,
            profile=profile,
            capabilities=capabilities,
            allowed_sections=allowed_sections,
            active_section=active_section,
            password_change_form=password_change_form,
            validate_avatar_upload=_validate_avatar_upload,
        )
        if post_result["response"] is not None:
            return post_result["response"]
        active_section = post_result["active_section"]
        password_change_form = post_result["password_change_form"]
        category_management_create_form = post_result["category_management_create_form"]
        category_management_edit_form = post_result["category_management_edit_form"]
        category_management_edit_item = post_result["category_management_edit_item"]

    # Get user's roles
    user_roles = _build_effective_user_roles(request.user, profile)
    primary_user_role_label = user_roles[0]["label"] if user_roles else ""
    active_organization = _get_active_organization(request)
    organization_access_rows = _build_user_organization_access_rows(
        request.user,
        active_organization=active_organization,
        include_active_superadmin_org=capabilities["is_superadmin"],
        profile_section="superadmin-organizations" if capabilities["is_superadmin"] else "profile-info",
    )

    teacher_courses = _tenant_scoped_courses(request, Course.objects.filter(owner=request.user))
    created_courses_qs = teacher_courses.order_by("-created_at")
    enrolled_courses_qs = _assigned_courses_queryset(request, request.user).order_by("-created_at")
    my_exams_qs = _tenant_scoped_exams(request, Exam.objects.filter(author=request.user)).order_by("-created_at")

    # P3 — Sidebar badge sayğacları (student: assigned/results/pending; reviewer:
    # pending/evaluated) hər profil yüklənməsində ~13-17 COUNT/aggregate sorğusu
    # idi və konkurent yük altında "normal" latency-ni domino edirdi (k6 normal
    # p95 ≈ 5.2s). Bunlar istifadəçinin öz datasıdır, kiçik staleness məqbuldur →
    # per (user, aktiv org) qısa TTL ilə cache. Aktiv bölmənin sayğacı aşağıda
    # təzə (heavy collector) dəyərlə üzərinə yazılır, beləcə açıq bölmə dəqiq qalır.
    profile_badge_counts = get_or_set_cached_profile_badge_counts(
        user_id=request.user.pk,
        org_id=active_organization.pk if active_organization is not None else None,
        compute=lambda: compute_profile_badge_counts(
            request,
            request.user,
            capabilities=capabilities,
            my_exams_qs=my_exams_qs,
            teacher_courses=teacher_courses,
        ),
    )

    if capabilities["is_student"]:
        visible_courses_qs = enrolled_courses_qs
    else:
        visible_courses_qs = created_courses_qs

    # P1.1 — Sidebar/profile-info üçün hər zaman ucuz sayğacları saxla,
    # ağır siyahıları yalnız aktiv bölmə üçün hesabla.
    courses_count = visible_courses_qs.count()
    my_courses = []
    if active_section == "courses":
        my_courses = list(visible_courses_qs[:10])

    my_created_courses = []
    my_created_courses_count = 0
    my_exams_count = 0
    my_exams_search_query = ""
    my_exams_filter_type = ""
    my_exams_list = []
    my_exams_dashboard = None
    question_bank_banks = []
    question_bank_page_obj = None
    question_bank_search_query = ""
    question_bank_pagination_query = _query_string(section="question-bank")
    question_bank_create_next_url = _append_query_params(reverse("accounts:profile"), section="question-bank")
    question_bank_back_url = question_bank_create_next_url
    question_bank_language_choices = []
    question_bank_default_type_choices = []
    if capabilities["can_view_owned_learning"]:
        # Sayğac sidebar/profile-info üçün hər zaman ucuz olaraq qalır.
        my_created_courses_count = created_courses_qs.count()
        if active_section == "my-courses":
            my_created_courses = list(created_courses_qs[:10])

        # "my-exams" bölməsi `_sections.exams`-ə çıxarılıb (context-fragment).
        _my_exams_ctx = build_my_exams_context(request, my_exams_qs=my_exams_qs, active_section=active_section)
        my_exams_count = _my_exams_ctx["my_exams_count"]
        my_exams_list = _my_exams_ctx["my_exams_list"]
        my_exams_dashboard = _my_exams_ctx["my_exams_dashboard"]
        my_exams_search_query = _my_exams_ctx["my_exams_search_query"]
        my_exams_filter_type = _my_exams_ctx["my_exams_filter_type"]

    # "unit-exams" bölməsi `_sections.unit_exams`-ə çıxarılıb (context-fragment).
    _unit_exams_ctx = build_unit_exams_context(
        request, allowed_sections=allowed_sections, active_section=active_section
    )
    unit_exams_page_obj = _unit_exams_ctx["unit_exams_page_obj"]
    unit_exams_search_query = _unit_exams_ctx["unit_exams_search_query"]
    unit_exams_total_count = _unit_exams_ctx["unit_exams_total_count"]
    unit_exams_pagination_query = _unit_exams_ctx["unit_exams_pagination_query"]

    # "question-bank" bölməsi `_sections.question_bank`-ə çıxarılıb (context-fragment).
    _qb_ctx = build_question_bank_context(request, allowed_sections=allowed_sections, active_section=active_section)
    question_bank_banks = _qb_ctx["question_bank_banks"]
    question_bank_page_obj = _qb_ctx["question_bank_page_obj"]
    question_bank_search_query = _qb_ctx["question_bank_search_query"]
    question_bank_pagination_query = _qb_ctx["question_bank_pagination_query"]
    question_bank_back_url = _qb_ctx["question_bank_back_url"]
    question_bank_language_choices = _qb_ctx["question_bank_language_choices"]
    question_bank_default_type_choices = _qb_ctx["question_bank_default_type_choices"]

    # "posts" / "create-post" bölmələri `_sections.posts`-a çıxarılıb (context-fragment).
    _posts_ctx = build_posts_context(request, capabilities=capabilities, active_section=active_section)
    user_posts = _posts_ctx["user_posts"]
    posts_count = _posts_ctx["posts_count"]
    post_category_tree = _posts_ctx["post_category_tree"]
    post_category_root_options = _posts_ctx["post_category_root_options"]
    post_category_subcategory_options = _posts_ctx["post_category_subcategory_options"]
    post_creation_requires_approval = _posts_ctx["post_creation_requires_approval"]
    posting_blocked = _posts_ctx["posting_blocked"]
    posting_blocked_reason = _posts_ctx["posting_blocked_reason"]

    assigned_exams_count = 0
    assigned_courses_count = 0
    assigned_tasks_count = 0
    my_results_count = 0
    assigned_task_items = []
    assigned_task_counts = {
        "all": 0,
        "exams": 0,
        "courses": 0,
        "assignments": 0,
        "labs": 0,
        "independent": 0,
    }
    assigned_tasks_active_filter = "all"
    assigned_tasks_search_query = ""
    assigned_courses = []
    assigned_courses_search_query = ""
    my_result_items = []
    my_results_page_obj = None
    my_results_search_query = ""
    my_results_pagination_query = ""
    my_results_page_param = "results_page"
    my_result_counts = {
        "all": 0,
        "exams": 0,
        "courses": 0,
        "labs": 0,
        "independent": 0,
    }
    my_results_active_filter = "all"
    pending_answer_items = []
    pending_answer_counts = {
        "all": 0,
        "exams": 0,
        "written_exams": 0,
        "practical_exams": 0,
        "courses": 0,
        "labs": 0,
        "independent": 0,
    }
    pending_answers_active_filter = "all"
    pending_answers_search_query = ""
    pending_answers_count = 0
    if capabilities["can_view_student_assignments"]:
        assigned_exams_qs = _assigned_exams_queryset(request, request.user, active_only=True).order_by(
            "-start_datetime",
            "-created_at",
        )
        # Sidebar üçün ucuz sayğaclar — hər zaman.
        assigned_exams_count = assigned_exams_qs.count()
        assigned_courses_count = enrolled_courses_qs.count()

        # P3 — Sidebar badge-ləri yuxarıda bir dəfə cached olaraq hesablanıb
        # (profile_badge_counts). Aktiv bölmə üçün aşağıda təzə dəyər götürülür.

        # Ağır siyahılar yalnız müvafiq aktiv bölmə üçün.
        if active_section == "assigned-exams":
            assigned_task_items, assigned_task_counts, assigned_tasks_active_filter = _collect_assigned_tasks(
                request,
                filter_type=request.GET.get("assigned_type"),
                search=request.GET.get("assigned_search"),
            )
            assigned_tasks_count = assigned_task_counts.get("all", 0)
            assigned_tasks_search_query = (request.GET.get("assigned_search", "") or "").strip()
        else:
            # P3 — sidebar badge cached dəyərdən (yuxarıda hesablanıb).
            assigned_tasks_count = profile_badge_counts.get("assigned_tasks", 0)

        if active_section == "assigned-courses":
            assigned_courses_search_query = (request.GET.get("assigned_course_search", "") or "").strip()
            assigned_courses_qs = enrolled_courses_qs
            if assigned_courses_search_query:
                assigned_courses_qs = assigned_courses_qs.filter(
                    Q(title__icontains=assigned_courses_search_query)
                    | Q(description__icontains=assigned_courses_search_query)
                )
            assigned_courses = list(assigned_courses_qs[:20])

        if active_section == "my-results":
            my_result_items, my_result_counts, my_results_active_filter = _collect_my_results(
                request,
                filter_type=request.GET.get("results_type"),
                search=request.GET.get("results_search"),
            )
            my_results_search_query = (request.GET.get("results_search", "") or "").strip()
            my_results_page_obj = Paginator(my_result_items, 6).get_page(request.GET.get(my_results_page_param))
            my_result_items = my_results_page_obj
            my_results_pagination_query = _query_string(
                section="my-results",
                results_type=my_results_active_filter,
                results_search=my_results_search_query,
            )
            my_results_count = my_result_counts.get("all", 0)
        else:
            # P3 — sidebar badge cached dəyərdən.
            my_results_count = profile_badge_counts.get("my_results", 0)

        if active_section == "pending-answers":
            (
                pending_answer_items,
                pending_answer_counts,
                pending_answers_active_filter,
                pending_answers_search_query,
            ) = _collect_pending_answer_items(
                request,
                search=request.GET.get("pending_search"),
                filter_type=request.GET.get("pending_type"),
            )
            pending_answers_count = pending_answer_counts.get("all", 0)
        else:
            # P3 — sidebar badge cached dəyərdən.
            pending_answers_count = profile_badge_counts.get("pending_answers", 0)

    # P3 — reviewer badge sayğacları (pending/evaluated) yuxarıdakı cached dəstdən
    # gəlir. 4 aggregate sorğusu artıq compute_review_badge_counts daxilindədir və
    # yalnız cache miss-də (per user+org, qısa TTL) işləyir — beləcə hər profil
    # yüklənməsində bu ağır blok hot path-dən çıxır.
    pending_review_count = profile_badge_counts.get("pending_review", 0)
    evaluated_review_count = profile_badge_counts.get("evaluated_review", 0)

    teacher_groups = []
    teacher_groups_count = 0
    teacher_groups_filtered_count = 0
    teacher_groups_payload = {}
    teacher_groups_page = None
    teacher_groups_search_query = (request.GET.get("group_q") or "").strip()
    teacher_groups_pagination_query = ""
    selected_teacher_group = None
    selected_group_students_page = None
    selected_group_students_count = 0
    selected_group_students_filtered_count = 0
    group_students_search_query = (request.GET.get("student_q") or "").strip()
    group_students_pagination_query = ""
    # student_member_groups profile-info üçün də göstərilir, ona görə yüngül
    # variantı her zaman hazırlayırıq.
    student_member_groups_qs = (
        StudentGroup.objects.filter(students=request.user)
        .select_related("organization", "teacher")
        .order_by("organization__name", "name")
        .distinct()
    )
    student_member_groups_count = student_member_groups_qs.count()
    student_member_groups = list(student_member_groups_qs[:STUDENT_MEMBER_GROUPS_DISPLAY_LIMIT])
    student_member_groups_more_count = max(0, student_member_groups_count - len(student_member_groups))
    group_form = None
    can_multi_assign_group_teachers = False
    groups_section_return_url = f"{reverse('accounts:profile')}?section=groups"
    # "groups" bölməsi `_sections.groups`-a çıxarılıb (context-fragment). Köhnə
    # iç-içə `if groups: if org:` indi tək şərtdir; davranış eynidir.
    if "groups" in allowed_sections and active_section == "groups" and active_organization is not None:
        _groups_ctx = build_groups_context(
            request,
            profile=profile,
            capabilities=capabilities,
            active_organization=active_organization,
            teacher_groups_search_query=teacher_groups_search_query,
            group_students_search_query=group_students_search_query,
        )
        can_multi_assign_group_teachers = _groups_ctx["can_multi_assign_group_teachers"]
        group_form = _groups_ctx["group_form"]
        teacher_groups = _groups_ctx["teacher_groups"]
        teacher_groups_count = _groups_ctx["teacher_groups_count"]
        teacher_groups_filtered_count = _groups_ctx["teacher_groups_filtered_count"]
        teacher_groups_page = _groups_ctx["teacher_groups_page"]
        teacher_groups_pagination_query = _groups_ctx["teacher_groups_pagination_query"]
        selected_teacher_group = _groups_ctx["selected_teacher_group"]
        selected_group_students_count = _groups_ctx["selected_group_students_count"]
        selected_group_students_filtered_count = _groups_ctx["selected_group_students_filtered_count"]
        selected_group_students_page = _groups_ctx["selected_group_students_page"]
        group_students_pagination_query = _groups_ctx["group_students_pagination_query"]
        teacher_groups_payload = _groups_ctx["teacher_groups_payload"]

    pending_post_approval_items = []
    pending_post_approval_count = 0
    pending_post_approval_search_query = ""
    pending_post_approval_filter_status = "pending"
    pending_post_approval_filter_group = ""
    pending_post_approval_filter_organization = ""
    pending_post_approval_available_groups = []
    pending_post_approval_available_organizations = []
    pending_post_approval_page_obj = None
    pending_post_approval_pagination_query = ""
    pending_post_approval_total_count = 0
    # Sidebar badge üçün ucuz sayğacı bölmə qeyri-aktiv olanda da göstər.
    if "pending-post-approvals" in allowed_sections and active_section != "pending-post-approvals":
        pending_post_approval_count = count_pending_reviewable_posts(request.user)
    if "pending-post-approvals" in allowed_sections and active_section == "pending-post-approvals":
        (
            pending_post_approval_items,
            pending_post_approval_search_query,
            pending_post_approval_filter_status,
            pending_post_approval_filter_group,
            pending_post_approval_available_groups,
            pending_post_approval_filter_organization,
            pending_post_approval_available_organizations,
        ) = collect_reviewable_posts(
            request.user,
            search=request.GET.get("approval_search"),
            status=request.GET.get("approval_status"),
            group_id=request.GET.get("approval_group"),
            organization_id=request.GET.get("approval_organization"),
        )
        pending_post_approval_total_count = len(pending_post_approval_items)
        pending_post_approval_count = count_pending_reviewable_posts(request.user)
        # Moderator "Redaktə et" modalı posts bölməsi ilə eyni `_post_edit_modal.html`-i
        # istifadə edir → kateqoriya select-lərinin dolması üçün picker option-larını
        # burada da qururuq (bu bölmə `can_manage_blog`-dan asılı deyil).
        if not post_category_root_options:
            post_category_tree = get_post_category_tree()
            post_category_root_options, post_category_subcategory_options = build_post_category_picker_options(
                post_category_tree
            )
        pending_post_approval_page_obj = Paginator(pending_post_approval_items, 10).get_page(
            request.GET.get("approval_page", 1)
        )
        extra = []
        extra.append("section=pending-post-approvals")
        if pending_post_approval_search_query:
            extra.append(f"approval_search={pending_post_approval_search_query}")
        if pending_post_approval_filter_status and pending_post_approval_filter_status != "pending":
            extra.append(f"approval_status={pending_post_approval_filter_status}")
        if pending_post_approval_filter_group:
            extra.append(f"approval_group={pending_post_approval_filter_group}")
        if pending_post_approval_filter_organization:
            extra.append(f"approval_organization={pending_post_approval_filter_organization}")
        pending_post_approval_pagination_query = "&".join(extra)

    pending_review_items = []
    pending_review_search_query = ""
    pending_review_filter_type = "all"
    pending_review_filter_status = "all"
    pending_review_submitted_order = "oldest"
    pending_review_filter_group = ""
    pending_review_available_groups = []
    pending_review_page_obj = None
    pending_review_pagination_query = ""
    evaluated_review_items = []
    evaluated_review_search_query = ""
    evaluated_review_filter_type = "all"
    evaluated_review_filter_group = ""
    evaluated_review_available_groups = []
    evaluated_review_submitted_order = "newest"
    evaluated_review_page_obj = None
    evaluated_review_pagination_query = ""
    # "pending-review" / "review-results" bölmələri `_sections.review_queue`-ya çıxarılıb.
    if active_section == "pending-review" and "pending-review" in allowed_sections:
        _pr = build_pending_review_context(request)
        pending_review_items = _pr["pending_review_items"]
        pending_review_search_query = _pr["pending_review_search_query"]
        pending_review_filter_type = _pr["pending_review_filter_type"]
        pending_review_filter_status = _pr["pending_review_filter_status"]
        pending_review_submitted_order = _pr["pending_review_submitted_order"]
        pending_review_filter_group = _pr["pending_review_filter_group"]
        pending_review_available_groups = _pr["pending_review_available_groups"]
        pending_review_page_obj = _pr["pending_review_page_obj"]
        pending_review_pagination_query = _pr["pending_review_pagination_query"]

    if active_section == "review-results" and "review-results" in allowed_sections:
        _er = build_review_results_context(request)
        evaluated_review_items = _er["evaluated_review_items"]
        evaluated_review_search_query = _er["evaluated_review_search_query"]
        evaluated_review_filter_type = _er["evaluated_review_filter_type"]
        evaluated_review_filter_group = _er["evaluated_review_filter_group"]
        evaluated_review_available_groups = _er["evaluated_review_available_groups"]
        evaluated_review_submitted_order = _er["evaluated_review_submitted_order"]
        evaluated_review_page_obj = _er["evaluated_review_page_obj"]
        evaluated_review_pagination_query = _er["evaluated_review_pagination_query"]

    role_assignment_section = {
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
    student_org_management_section = {
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
        # `context.update(student_org_management_section)` aşağıda bu açarı
        # top-level kontekstə qaldırır. Skelet variantında boş string-lə
        # default verilir ki, ProfileContextContractTest pozulmasın.
        "post_next_url": "",
    }
    # Sidebar `student_org_request_section.pending_invites_count` badge-i hər
    # bölmədə görünməlidir, ona görə default olaraq notification_state-dən
    # gələn ucuz dəyərləri buraya köçürürük. Tam dataset yalnız profile-info
    # və ya öz tab-ı üçün `_build_student_org_request_section`-dən doldurulur.
    student_org_request_section = {
        "organizations": [],
        "search_query": "",
        "org_type_filter": "",
        "pending_invites": list(pending_student_invites or []),
        "pending_invites_count": len(pending_student_invites or []),
        "has_pending_invites": bool(pending_student_invites),
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
    permission_editor_section = {
        "organization": None,
        "roles": [],
        "selected_role": None,
        "permission_categories": {},
        "actor_permissions": [],
        "grantable_permissions": [],
        "can_manage_permissions": False,
        "access_denied_message": "",
    }
    manage_roles_section = {
        "profiles": [],
        "assignable_roles": [],
        "search_query": "",
        "organization": None,
        "access_denied_message": "",
        "profiles_page_param": "manage_roles_page",
        "profiles_pagination_query": "",
    }
    superadmin_users_section = {
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
    superadmin_ai_settings_section = {
        "config": None,
        "model_choices": [],
        "rate_info": {},
        "cost_estimates": {},
        "post_next_url": "",
    }
    superadmin_org_features_section = {
        "organizations": [],
        "organizations_page_param": "superadmin_feature_org_page",
        "organizations_pagination_query": "",
        "post_next_url": "",
    }
    superadmin_organizations_section = {
        "organizations": [],
        "organization_access_rows": [],
        "all_modules": [],
        "organizations_page_param": "superadmin_org_page",
        "organizations_pagination_query": "",
        "post_next_url": "",
        "pending_count": 0,
    }
    org_structure_section = {
        "organization": active_organization,
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
    _empty_structure_section_base = {
        "organization": active_organization,
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
    org_faculties_section = {
        **_empty_structure_section_base,
        "faculties": [],
        "faculties_page_obj": None,
        "faculty_total_count": 0,
        "kafedra_total_count": 0,
        "filtered_count": 0,
    }
    org_kafedras_section = {
        **_empty_structure_section_base,
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
    org_members_section = {
        "organization": active_organization,
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
    org_roles_section = {
        "organization": active_organization,
        "roles": [],
        "can_view": False,
        "profile_base_url": reverse("accounts:profile"),
        "embedded_in_profile": True,
    }
    audit_log_section = {
        "audit_logs": [],
        "current_organization": active_organization,
        "is_superadmin": capabilities["is_superadmin"],
        "embedded_in_profile": True,
    }

    management_org = None
    management_user_level = 0
    management_actor_permissions = set()
    management_grantable_permissions = set()
    management_can_assign_roles = False
    management_min_level_ok = False
    _management_sections = {
        "role-assignment",
        "permission-editor",
        "student-organization-management",
    }
    if active_section in _management_sections and (
        "role-assignment" in allowed_sections
        or "permission-editor" in allowed_sections
        or "student-organization-management" in allowed_sections
    ):
        from apps.organizations.permissions import has_permission
        from apps.organizations.services import get_user_org_role_level

        management_org = _get_active_organization(request)
        if management_org:
            _ensure_profile_admin_membership(request.user, management_org)
            management_user_level = (
                999 if capabilities["is_superadmin"] else get_user_org_role_level(request.user, management_org)
            )
            management_actor_permissions, management_grantable_permissions = _collect_actor_permissions(
                request.user,
                management_org,
                request=request,
            )
            management_can_assign_roles = (
                capabilities["is_superadmin"]
                or has_permission(
                    list(management_actor_permissions),
                    "role.assign",
                )
                or has_permission(
                    list(management_actor_permissions),
                    "org.manage_members",
                )
            )
            management_min_level_ok = capabilities["is_superadmin"] or management_user_level >= 50

    if "role-assignment" in allowed_sections and active_section == "role-assignment":
        role_assignment_section = build_role_assignment_section(
            request,
            role_assignment_section,
            management_org=management_org,
            management_can_assign_roles=management_can_assign_roles,
            management_min_level_ok=management_min_level_ok,
            management_user_level=management_user_level,
            capabilities=capabilities,
        )
    if "student-organization-management" in allowed_sections and active_section == "student-organization-management":
        student_org_management_section = _build_student_org_management_section(
            request=request,
            organization=management_org,
            is_superadmin=capabilities["is_superadmin"],
            user_level=management_user_level,
            teacher_student_only=capabilities.get("teacher_has_student_org_access", False),
            can_manage_students=(
                capabilities["is_superadmin"]
                or capabilities["is_org_admin"]
                or management_user_level >= STUDENT_ORG_MANAGEMENT_MIN_LEVEL
                or capabilities.get("teacher_can_manage_students", False)
            ),
            can_invite_members=(
                capabilities["is_superadmin"]
                or capabilities["is_org_admin"]
                or management_user_level >= STUDENT_ORG_MANAGEMENT_MIN_LEVEL
                or capabilities.get("teacher_can_invite_members", False)
            ),
        )
        student_org_management_section["post_next_url"] = _append_query_params(
            reverse("accounts:profile"),
            section="student-organization-management",
            management_view=student_org_management_section["active_management_view"],
            student_tab=student_org_management_section["active_student_tab"],
            teacher_tab=student_org_management_section["active_teacher_tab"],
            staff_tab=student_org_management_section["active_staff_tab"],
            student_org_search=student_org_management_section["student_search_query"],
            student_org_pending_search=student_org_management_section["pending_search_query"],
            student_org_unassigned_search=student_org_management_section["unassigned_search_query"],
            student_org_sent_invite_search=student_org_management_section["sent_invite_search_query"],
            student_org_ts_search=student_org_management_section["teacher_staff_search_query"],
            organization_search=student_org_management_section["organization_search_query"],
            organization_status=student_org_management_section["organization_status_filter"],
            organization_type=student_org_management_section["organization_type_filter"],
        )

    # `_profile_org_invites.html` profile-info üçün də student_org_request_section-ın
    # bir neçə açarına müraciət edir (has_pending_invites/current_organization/pending_invites).
    # Ona görə profile-info və müvafiq tab üçün hazırlayırıq.
    if "student-organization-request" in allowed_sections and active_section in {
        "student-organization-request",
        "profile-info",
    }:
        student_org_request_section = _build_student_org_request_section(request=request, profile=profile)
        student_org_request_section["post_next_url"] = _append_query_params(
            reverse("accounts:profile"),
            section="student-organization-request",
            student_org_request_search=student_org_request_section["search_query"],
            student_org_request_type=student_org_request_section["org_type_filter"],
        )

    if "permission-editor" in allowed_sections and active_section == "permission-editor":
        permission_editor_section = build_permission_editor_section(
            request,
            permission_editor_section,
            management_org=management_org,
            management_actor_permissions=management_actor_permissions,
            management_grantable_permissions=management_grantable_permissions,
            management_can_assign_roles=management_can_assign_roles,
            management_user_level=management_user_level,
            capabilities=capabilities,
        )
    if "manage-roles" in allowed_sections and active_section == "manage-roles":
        manage_roles_section = build_manage_roles_section(request, manage_roles_section, capabilities=capabilities)
    if active_section == "org-structure" and "org-structure" in allowed_sections and active_organization is not None:
        from apps.organizations.views import build_organization_structure_context

        org_structure_section = build_organization_structure_context(request, active_organization)
        org_structure_section["embedded_in_profile"] = True

    if active_section == "org-faculties" and "org-faculties" in allowed_sections and active_organization is not None:
        from apps.organizations.structure_views import build_organization_faculties_context

        org_faculties_section = build_organization_faculties_context(request, active_organization)
        org_faculties_section["embedded_in_profile"] = True

    if active_section == "org-kafedras" and "org-kafedras" in allowed_sections and active_organization is not None:
        from apps.organizations.structure_views import build_organization_kafedras_context

        org_kafedras_section = build_organization_kafedras_context(request, active_organization)
        org_kafedras_section["embedded_in_profile"] = True

    if active_section == "org-members" and "org-members" in allowed_sections and active_organization is not None:
        from apps.organizations.views import build_organization_members_context

        org_members_section = build_organization_members_context(request, active_organization)
        org_members_section["embedded_in_profile"] = True

    if active_section == "org-roles" and "org-roles" in allowed_sections and active_organization is not None:
        from apps.organizations.views import build_organization_roles_context

        org_roles_section = build_organization_roles_context(request, active_organization)
        org_roles_section["embedded_in_profile"] = True

    if active_section == "audit-log" and "audit-log" in allowed_sections:
        from apps.audit.views import build_audit_log_context

        audit_log_section = build_audit_log_context(request)
        audit_log_section["embedded_in_profile"] = True

    # Superadmin təşkilat baxışı — istənilən təşkilatın imtahan/nəticə/bank/kurs
    # siyahılarına read-only drill-down. Yalnız aktiv olduqda qurulur (performans).
    superadmin_org_inspector_section = {}
    if active_section == "superadmin-org-inspector" and "superadmin-org-inspector" in allowed_sections:
        from .._helpers.superadmin_inspector import build_superadmin_org_inspector_section

        superadmin_org_inspector_section = build_superadmin_org_inspector_section(
            request, is_superadmin=capabilities["is_superadmin"]
        )

    # Superadmin "pending org" badge sidebar üçündür — ucuz `Organization.objects... .count()`-i hər zaman saxla.
    if "superadmin-organizations" in allowed_sections and active_section != "superadmin-organizations":
        from apps.organizations.models import Organization as _PendingOrg

        superadmin_organizations_section["pending_count"] = _PendingOrg.objects.filter(status="pending").count()

    if ("superadmin-org-features" in allowed_sections and active_section == "superadmin-org-features") or (
        "superadmin-organizations" in allowed_sections and active_section == "superadmin-organizations"
    ):
        build_superadmin_orgs_sections(
            request,
            superadmin_org_features_section,
            superadmin_organizations_section,
            allowed_sections=allowed_sections,
            active_section=active_section,
            organization_access_rows=organization_access_rows,
        )
    if "superadmin-users" in allowed_sections and active_section == "superadmin-users":
        superadmin_users_section.update(
            build_superadmin_user_management_context(
                request,
                base_url=reverse("accounts:profile"),
                include_section=True,
            )
        )

    if "superadmin-ai" in allowed_sections and active_section == "superadmin-ai":
        superadmin_ai_settings_section.update(build_superadmin_ai_settings_context())
        superadmin_ai_settings_section["post_next_url"] = _append_query_params(
            reverse("accounts:profile"),
            section="superadmin-ai",
        )

    # InAppNotification data for profile notifications section.
    # Sidebar yalnız `notifications_unread_count`-dan istifadə edir; tam siyahını
    # yalnız notifications bölməsi açıq olduqda hazırla.
    # "notifications" bölməsi `_sections.notifications`-ə çıxarılıb (context-fragment).
    _notif_ctx = build_notifications_context(request, active_section=active_section)
    notif_filter = _notif_ctx["notif_filter"]
    notif_type = _notif_ctx["notif_type"]
    notif_search_query = _notif_ctx["notif_search_query"]
    notif_pagination_query = _notif_ctx["notif_pagination_query"]
    in_app_notifications_page = _notif_ctx["in_app_notifications_page"]

    # Publish-notification data (teacher groups, org info)
    publish_notification_targets = []
    if "publish-notification" in allowed_sections and active_section == "publish-notification":
        publish_notification_targets = _get_publish_notification_targets(request.user, capabilities)

    category_management_page = None
    category_management_create_parent_options = []
    category_management_create_selected_parent_id = ""
    category_management_edit_parent_options = []
    category_management_edit_selected_parent_id = ""
    category_management_search_query = ""
    category_management_page_param = "category_page"
    category_management_pagination_query = ""
    category_management_total_count = 0
    category_management_filtered_count = 0
    if {"create-category", "category-management"} & set(allowed_sections) and active_section in {
        "create-category",
        "category-management",
    }:
        if category_management_create_form is None:
            category_management_create_form = CategoryManagementForm()

        category_management_create_parent_options = [
            {
                "value": str(category.id),
                "label": category.localized_name,
                "attrs": "",
            }
            for category in category_management_create_form.fields["parent"].queryset
        ]
        category_management_create_selected_parent_id = category_management_create_form["parent"].value() or ""

    if "category-management" in allowed_sections and active_section == "category-management":
        category_management_search_query = _normalize_public_profile_query_value(
            request.GET.get("category_search"),
            max_length=100,
        )
        normalized_category_search = category_management_search_query.casefold()
        managed_categories_queryset = Category.objects.annotate(direct_post_count=Count("posts")).order_by(
            "sort_order",
            "name_en",
            "name_az",
            "id",
        )
        category_management_tree = get_post_category_tree(category_queryset=managed_categories_queryset)
        filtered_category_tree = []

        def _category_matches_search(category):
            if not normalized_category_search:
                return True
            searchable_values = (
                category.name_az,
                category.name_en,
                category.name_ru,
                category.name_tr,
                category.slug,
            )
            return any(normalized_category_search in (value or "").casefold() for value in searchable_values)

        for root_category in category_management_tree:
            root_children = list(getattr(root_category, "child_categories", []))
            matching_children = [
                child_category for child_category in root_children if _category_matches_search(child_category)
            ]
            if normalized_category_search:
                root_matches = _category_matches_search(root_category)
                if not root_matches and not matching_children:
                    continue
                visible_children = root_children if root_matches else matching_children
            else:
                visible_children = root_children

            root_category.total_child_count = len(root_children)
            root_category.can_delete = root_category.direct_post_count == 0 and not root_children
            root_category.child_categories = visible_children

            for child_category in visible_children:
                child_category.can_delete = child_category.direct_post_count == 0

            filtered_category_tree.append(root_category)

        category_management_total_count = len(category_management_tree)
        category_management_filtered_count = len(filtered_category_tree)
        category_management_page = Paginator(filtered_category_tree, 6).get_page(
            request.GET.get(category_management_page_param)
        )
        category_management_pagination_query = _query_string(
            section="category-management",
            category_search=category_management_search_query,
        )

        if category_management_edit_form is None:
            category_management_edit_item = _load_managed_category(request.GET.get("edit_category"))
            if category_management_edit_item is not None:
                category_management_edit_form = CategoryManagementForm(instance=category_management_edit_item)

        if category_management_edit_form is not None:
            category_management_edit_parent_options = [
                {
                    "value": str(category.id),
                    "label": category.localized_name,
                    "attrs": "",
                }
                for category in category_management_edit_form.fields["parent"].queryset
            ]
            category_management_edit_selected_parent_id = category_management_edit_form["parent"].value() or ""
        else:
            category_management_edit_form = CategoryManagementForm()
            category_management_edit_parent_options = [
                {
                    "value": str(category.id),
                    "label": category.localized_name,
                    "attrs": "",
                }
                for category in category_management_edit_form.fields["parent"].queryset
            ]

    # ── Statistics section context ────────────────────────────────────
    statistics_data = {}
    statistics_filters = {}
    # Tyutor (və gələcəkdə digər unit-scoped, qeyri-admin rollar) üçün
    # statistics template-i admin kart düzümünü istifadə etsin deyə flag.
    statistics_unit_layout = False
    statistics_courses = []
    statistics_groups = []
    statistics_organizations = []
    statistics_has_active_filters = False
    statistics_reset_url = _append_query_params(reverse("accounts:profile"), section="statistics")
    statistics_org_page = None
    statistics_teacher_page = None
    statistics_course_page = None
    statistics_group_page = None
    statistics_teacher_course_page = None
    statistics_org_rows = []
    statistics_teacher_rows = []
    statistics_course_rows = []
    statistics_group_rows = []
    statistics_teacher_course_rows = []
    statistics_org_page_param = "stats_org_page"
    statistics_teacher_page_param = "stats_teacher_page"
    statistics_course_page_param = "stats_course_page"
    statistics_group_page_param = "stats_group_page"
    statistics_teacher_course_page_param = "stats_teacher_course_page"
    statistics_org_pagination_query = ""
    statistics_teacher_pagination_query = ""
    statistics_course_pagination_query = ""
    statistics_group_pagination_query = ""
    statistics_teacher_course_pagination_query = ""
    # "statistics" bölməsi `_sections.statistics`-ə çıxarılıb (context-fragment).
    # AJAX AI-summary üçün funksiya JsonResponse qaytarır (erkən-return).
    if active_section == "statistics" and "statistics" in allowed_sections:
        from django.http import HttpResponse as _HttpResponse

        _stats = build_statistics_section(request, capabilities=capabilities)
        if isinstance(_stats, _HttpResponse):
            return _stats
        statistics_filters = _stats["statistics_filters"]
        statistics_data = _stats["statistics_data"]
        statistics_courses = _stats["statistics_courses"]
        statistics_groups = _stats["statistics_groups"]
        statistics_organizations = _stats["statistics_organizations"]
        statistics_has_active_filters = _stats["statistics_has_active_filters"]
        statistics_unit_layout = _stats["statistics_unit_layout"]
        statistics_org_page = _stats["statistics_org_page"]
        statistics_org_rows = _stats["statistics_org_rows"]
        statistics_org_pagination_query = _stats["statistics_org_pagination_query"]
        statistics_teacher_page = _stats["statistics_teacher_page"]
        statistics_teacher_rows = _stats["statistics_teacher_rows"]
        statistics_teacher_pagination_query = _stats["statistics_teacher_pagination_query"]
        statistics_course_page = _stats["statistics_course_page"]
        statistics_course_rows = _stats["statistics_course_rows"]
        statistics_course_pagination_query = _stats["statistics_course_pagination_query"]
        statistics_group_page = _stats["statistics_group_page"]
        statistics_group_rows = _stats["statistics_group_rows"]
        statistics_group_pagination_query = _stats["statistics_group_pagination_query"]
        statistics_teacher_course_page = _stats["statistics_teacher_course_page"]
        statistics_teacher_course_rows = _stats["statistics_teacher_course_rows"]
        statistics_teacher_course_pagination_query = _stats["statistics_teacher_course_pagination_query"]

    # Bölmə başlıqları `_sections.labels`-ə çıxarılıb (per-request, eager tərcümə).
    section_titles = build_section_titles()

    shortcut_sections = []
    if capabilities["can_view_blog"]:
        shortcut_sections.append(
            {
                "section": "blog",
                "title": section_titles["blog"],
                "url": reverse("home"),
                "icon": "fas fa-house",
                "source_url": reverse("home"),
                "description": "Ana səhifə və məqalə bölməsini aç.",
                "action_label": pgettext_lazy("nav", "home"),
            }
        )

    active_section_title = section_titles.get(active_section, pgettext_lazy("profile.sidebar", "title"))
    direct_profile_section = getattr(request, "direct_profile_section", "")
    direct_profile_section_templates = DIRECT_PROFILE_SECTION_TEMPLATES

    context = {
        "profile": profile,
        "user_roles": user_roles,
        "primary_user_role_label": primary_user_role_label,
        "active_section": active_section,
        "active_section_title": active_section_title,
        "direct_profile_section": direct_profile_section,
        "direct_profile_section_template": direct_profile_section_templates.get(direct_profile_section, ""),
        "active_main_nav": "exams" if active_section in PROFILE_EXAM_NAV_SECTIONS else "",
        "allowed_sections": allowed_sections,
        "profile_base_url": reverse("accounts:profile"),
        "shortcut_sections": shortcut_sections,
        "role_capabilities": capabilities,
        "password_change_form": password_change_form,
        "user_posts": user_posts,
        "posts_count": posts_count,
        "post_category_tree": post_category_tree,
        "post_category_root_options": post_category_root_options,
        "post_category_subcategory_options": post_category_subcategory_options,
        "post_creation_requires_approval": post_creation_requires_approval,
        "posting_blocked": posting_blocked,
        "posting_blocked_reason": posting_blocked_reason,
        "my_courses": my_courses,
        "courses_count": courses_count,
        "my_exams": my_exams_list,
        "my_exams_dashboard": my_exams_dashboard,
        "my_exams_count": my_exams_count,
        "my_exams_search_query": my_exams_search_query,
        "my_exams_filter_type": my_exams_filter_type,
        "question_bank_banks": question_bank_banks,
        "question_bank_page_obj": question_bank_page_obj,
        "question_bank_search_query": question_bank_search_query,
        "question_bank_pagination_query": question_bank_pagination_query,
        "question_bank_create_next_url": question_bank_create_next_url,
        "question_bank_back_url": question_bank_back_url,
        "question_bank_language_choices": question_bank_language_choices,
        "question_bank_default_type_choices": question_bank_default_type_choices,
        "unit_exams_page_obj": unit_exams_page_obj,
        "unit_exams_search_query": unit_exams_search_query,
        "unit_exams_total_count": unit_exams_total_count,
        "unit_exams_pagination_query": unit_exams_pagination_query,
        "my_created_courses": my_created_courses,
        "my_created_courses_count": my_created_courses_count,
        "assigned_exams_count": assigned_exams_count,
        "assigned_courses_count": assigned_courses_count,
        "assigned_tasks_count": assigned_tasks_count,
        "assigned_task_items": assigned_task_items,
        "assigned_task_counts": assigned_task_counts,
        "assigned_tasks_active_filter": assigned_tasks_active_filter,
        "assigned_tasks_search_query": assigned_tasks_search_query,
        "assigned_courses": assigned_courses,
        "assigned_courses_search_query": assigned_courses_search_query,
        "my_results_count": my_results_count,
        "my_result_items": my_result_items,
        "my_results_page_obj": my_results_page_obj,
        "my_result_counts": my_result_counts,
        "my_results_active_filter": my_results_active_filter,
        "my_results_search_query": my_results_search_query,
        "my_results_pagination_query": my_results_pagination_query,
        "my_results_page_param": my_results_page_param,
        "pending_answers_count": pending_answers_count,
        "pending_answer_items": pending_answer_items,
        "pending_answer_counts": pending_answer_counts,
        "pending_answers_active_filter": pending_answers_active_filter,
        "pending_answers_search_query": pending_answers_search_query,
        "pending_review_count": pending_review_count,
        "evaluated_review_count": evaluated_review_count,
        "teacher_groups": teacher_groups,
        "teacher_groups_count": teacher_groups_count,
        "teacher_groups_filtered_count": teacher_groups_filtered_count,
        "teacher_groups_payload": teacher_groups_payload,
        "teacher_groups_page": teacher_groups_page,
        "teacher_groups_search_query": teacher_groups_search_query,
        "teacher_groups_pagination_query": teacher_groups_pagination_query,
        "selected_teacher_group": selected_teacher_group,
        "selected_group_students_page": selected_group_students_page,
        "selected_group_students_count": selected_group_students_count,
        "selected_group_students_filtered_count": selected_group_students_filtered_count,
        "group_students_search_query": group_students_search_query,
        "group_students_pagination_query": group_students_pagination_query,
        "organization_access_rows": organization_access_rows,
        "student_member_groups": student_member_groups,
        "student_member_groups_count": student_member_groups_count,
        "student_member_groups_more_count": student_member_groups_more_count,
        "group_form": group_form,
        "can_multi_assign_group_teachers": can_multi_assign_group_teachers,
        "groups_section_return_url": groups_section_return_url,
        "pending_post_approval_items": pending_post_approval_page_obj or pending_post_approval_items,
        "pending_post_approval_count": pending_post_approval_count,
        "pending_post_approval_search_query": pending_post_approval_search_query,
        "pending_post_approval_filter_status": pending_post_approval_filter_status,
        "pending_post_approval_filter_group": pending_post_approval_filter_group,
        "pending_post_approval_filter_organization": pending_post_approval_filter_organization,
        "pending_post_approval_available_groups": pending_post_approval_available_groups,
        "pending_post_approval_available_organizations": pending_post_approval_available_organizations,
        "pending_post_approval_page_obj": pending_post_approval_page_obj,
        "pending_post_approval_pagination_query": pending_post_approval_pagination_query,
        "pending_post_approval_total_count": pending_post_approval_total_count,
        "pending_review_items": pending_review_page_obj or pending_review_items,
        "pending_review_search_query": pending_review_search_query,
        "pending_review_filter_type": pending_review_filter_type,
        "pending_review_filter_status": pending_review_filter_status,
        "pending_review_submitted_order": pending_review_submitted_order,
        "pending_review_filter_group": pending_review_filter_group,
        "pending_review_available_groups": pending_review_available_groups,
        "pending_review_total_count": len(pending_review_items),
        "pending_review_page_obj": pending_review_page_obj,
        "pending_review_pagination_query": pending_review_pagination_query,
        "evaluated_review_items": evaluated_review_page_obj or evaluated_review_items,
        "evaluated_review_search_query": evaluated_review_search_query,
        "evaluated_review_filter_type": evaluated_review_filter_type,
        "evaluated_review_filter_group": evaluated_review_filter_group,
        "evaluated_review_available_groups": evaluated_review_available_groups,
        "evaluated_review_submitted_order": evaluated_review_submitted_order,
        "evaluated_review_total_count": len(evaluated_review_items),
        "evaluated_review_page_obj": evaluated_review_page_obj,
        "evaluated_review_pagination_query": evaluated_review_pagination_query,
        "pending_student_invites": pending_student_invites,
        "pending_student_join_requests": pending_student_join_requests,
        "notifications_unread_count": notifications_unread_count,
        "in_app_unread_count": in_app_unread_count,
        "in_app_notifications_page": in_app_notifications_page,
        "notif_filter": notif_filter,
        "notif_type": notif_type,
        "notif_notification_types": NotificationType.choices,
        "notif_search_query": notif_search_query,
        "notif_pagination_query": notif_pagination_query,
        "pending_student_join_org_name": pending_student_join_org_name,
        "pending_student_join_message": pending_student_join_message,
        "student_can_leave_org": student_can_leave_org,
        "publish_notification_targets": publish_notification_targets,
        "role_assignment_section": role_assignment_section,
        "student_org_request_section": student_org_request_section,
        "student_org_management_section": student_org_management_section,
        "permission_editor_section": permission_editor_section,
        "manage_roles_section": manage_roles_section,
        "org_structure_section": org_structure_section,
        "org_faculties_section": org_faculties_section,
        "org_kafedras_section": org_kafedras_section,
        "org_members_section": org_members_section,
        "org_roles_section": org_roles_section,
        "audit_log_section": audit_log_section,
        "superadmin_org_inspector_section": superadmin_org_inspector_section,
        "superadmin_users_section": superadmin_users_section,
        "superadmin_ai_settings_section": superadmin_ai_settings_section,
        "superadmin_org_features_section": superadmin_org_features_section,
        "category_management_create_form": category_management_create_form,
        "category_management_edit_form": category_management_edit_form,
        "category_management_edit_item": category_management_edit_item,
        "category_management_page": category_management_page,
        "category_management_create_parent_options": category_management_create_parent_options,
        "category_management_create_selected_parent_id": category_management_create_selected_parent_id,
        "category_management_edit_parent_options": category_management_edit_parent_options,
        "category_management_edit_selected_parent_id": category_management_edit_selected_parent_id,
        "category_management_search_query": category_management_search_query,
        "category_management_page_param": category_management_page_param,
        "category_management_pagination_query": category_management_pagination_query,
        "category_management_total_count": category_management_total_count,
        "category_management_filtered_count": category_management_filtered_count,
        "superadmin_organizations_section": superadmin_organizations_section,
        "superadmin_pending_org_count": superadmin_organizations_section.get("pending_count", 0),
        "is_teacher": capabilities["is_teacher"],
        "is_admin": capabilities["can_manage_org"],
        "is_superadmin": capabilities["is_superadmin"],
        "can_manage_org": capabilities["can_manage_org"],
        "can_view_owned_learning": capabilities["can_view_owned_learning"],
        "can_review_submissions": capabilities["can_review_submissions"],
        "can_approve_posts": capabilities["can_approve_posts"],
        "can_view_blog": capabilities["can_view_blog"],
        "can_manage_blog": capabilities["can_manage_blog"],
        "can_view_student_assignments": capabilities["can_view_student_assignments"],
        "statistics_data": statistics_data,
        "statistics_unit_layout": statistics_unit_layout,
        "statistics_filters": statistics_filters,
        "statistics_courses": statistics_courses,
        "statistics_groups": statistics_groups,
        "statistics_organizations": statistics_organizations,
        "statistics_has_active_filters": statistics_has_active_filters,
        "statistics_reset_url": statistics_reset_url,
        "statistics_org_page": statistics_org_page,
        "statistics_teacher_page": statistics_teacher_page,
        "statistics_course_page": statistics_course_page,
        "statistics_group_page": statistics_group_page,
        "statistics_teacher_course_page": statistics_teacher_course_page,
        "statistics_org_rows": statistics_org_rows,
        "statistics_teacher_rows": statistics_teacher_rows,
        "statistics_course_rows": statistics_course_rows,
        "statistics_group_rows": statistics_group_rows,
        "statistics_teacher_course_rows": statistics_teacher_course_rows,
        "statistics_org_page_param": statistics_org_page_param,
        "statistics_teacher_page_param": statistics_teacher_page_param,
        "statistics_course_page_param": statistics_course_page_param,
        "statistics_group_page_param": statistics_group_page_param,
        "statistics_teacher_course_page_param": statistics_teacher_course_page_param,
        "statistics_org_pagination_query": statistics_org_pagination_query,
        "statistics_teacher_pagination_query": statistics_teacher_pagination_query,
        "statistics_course_pagination_query": statistics_course_pagination_query,
        "statistics_group_pagination_query": statistics_group_pagination_query,
        "statistics_teacher_course_pagination_query": statistics_teacher_course_pagination_query,
    }

    context.update(
        {
            "review_items": context["pending_review_items"],
            "search_query": pending_review_search_query,
            "filter_type": pending_review_filter_type,
            "filter_status": pending_review_filter_status,
            "total_count": context["pending_review_total_count"],
            "pagination_query": pending_review_pagination_query,
            "organizations": superadmin_organizations_section.get("organizations", []),
            "all_modules": superadmin_organizations_section.get("all_modules", []),
            "profiles": manage_roles_section.get("profiles", []),
            "assignable_roles": manage_roles_section.get("assignable_roles", []),
            "roles": permission_editor_section.get("roles", []),
            "selected_role": permission_editor_section.get("selected_role"),
        }
    )
    context.update(student_org_management_section)

    # Contact inbox (public contact form) — only populated for superadmins.
    # Returns the unread badge count on every render plus the full list
    # when the section is actually being viewed.
    context.update(
        build_contact_inbox_context(
            request,
            capabilities=capabilities,
            active_section=active_section,
        )
    )

    # "Apellyasiyalarım" bölməsi — yalnız aktiv olduqda sorğu et (ucuz saxla).
    # Tenant/sahiblik scope-u selektor səviyyəsində (yalnız öz apellyasiyaları)
    # qorunur; əlavə icazə build_my_appeals_context daxilində tələb olunmur.
    if active_section == "my-appeals" and "my-appeals" in allowed_sections:
        from apps.appeals.views import build_my_appeals_context

        context.update(
            build_my_appeals_context(
                request,
                list_action=reverse("accounts:profile"),
                section="my-appeals",
            )
        )

    # "Apellyasiyalar" (müəllim/reviewer) idarəetmə bölməsi — dashboard daxili.
    if active_section == "manage-appeals" and "manage-appeals" in allowed_sections:
        from apps.appeals.views import _can_open_appeal_management, build_manage_appeals_context

        if _can_open_appeal_management(request):
            context.update(
                build_manage_appeals_context(
                    request,
                    list_action=reverse("accounts:profile"),
                    section="manage-appeals",
                )
            )

    return render(request, "accounts/profile.html", context)
