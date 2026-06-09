"""
Main profile view: ``user_profile``.

This is a GET-oriented context builder that assembles the (large) template
context for ``accounts/profile.html``. POST-form handling is delegated to
``post_handler.handle_profile_post``; input sanitization lives in ``search``;
shared helpers come from the ``_helpers`` and ``_dashboard_helpers`` packages.

Behavior is identical to the pre-refactor single-file implementation.
"""

from urllib.parse import urlencode

from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.shortcuts import render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.utils.translation import pgettext_lazy

from apps.courses.models import Course
from apps.exams.forms import StudentGroupForm
from apps.exams.models import Exam, StudentGroup
from apps.notifications.models import StudentOrganizationRequestStatus
from apps.notifications.services import (
    build_profile_notification_state,
    get_unread_count,
    get_user_notifications,
)
from core.cache import get_or_set_cached_profile_badge_counts
from core.rls import bypass_rls
from core.tenancy import restore_request_organization_from_profile

from ...forms import CustomPasswordChangeForm
from ...models import ProfileRole, UserProfile
from ...services.profile_actions import validate_profile_avatar_upload
from .._dashboard_helpers import (
    _collect_assigned_tasks,
    _collect_evaluated_review_items,
    _collect_my_results,
    _collect_pending_answer_items,
    _collect_pending_review_items,
)
from .._dashboard_helpers.cheap_counts import compute_profile_badge_counts
from .._helpers import (
    PROFILE_ROLE_LABELS,
    STUDENT_MEMBER_GROUPS_DISPLAY_LIMIT,
    STUDENT_ORG_MANAGEMENT_MIN_LEVEL,
    STUDENT_ORG_REQUEST_MESSAGE_MAX_LENGTH,
    _append_query_params,
    _assignable_profile_roles_for_user,
    _assigned_courses_queryset,
    _assigned_exams_queryset,
    _bind_active_role_context,
    _build_student_org_management_section,
    _build_student_org_request_section,
    _build_user_organization_access_rows,
    _collect_actor_permissions,
    _decorate_manage_role_profiles,
    _ensure_profile_admin_membership,
    _get_active_organization,
    _pending_student_request_queryset,
    _query_string,
    _role_capabilities,
    _tenant_scoped_courses,
    _tenant_scoped_exams,
)
from ..account_management import build_superadmin_user_management_context
from ..superadmin import build_superadmin_ai_settings_context
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

        for org in Organization.objects.filter(is_active=True, status="active").order_by("name"):
            targets.append(
                {
                    "value": f"org_{org.pk}",
                    "label": f'{_("target_org_prefix")}: {org.name}',
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
        for membership in org_memberships:
            if membership.organization_id in seen_org_ids:
                continue
            seen_org_ids.add(membership.organization_id)
            targets.append(
                {
                    "value": f"org_{membership.organization_id}",
                    "label": f'{_("target_org_prefix")}: {membership.organization.name} ({_("target_org_all_members")})',
                    "is_exclusive": False,
                }
            )

    if is_teacher:
        teacher_groups = StudentGroup.objects.filter(teacher=user).order_by("name")
        for group in teacher_groups:
            targets.append(
                {
                    "value": f"group_{group.pk}",
                    "label": f'{_("target_group_prefix")}: {group.name}',
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
    from apps.blog.models import Category, Post
    from apps.blog.selectors import build_post_category_picker_options, get_post_category_tree
    from apps.blog.services import (
        author_requires_post_approval,
        can_user_publish_post,
        collect_reviewable_posts,
        count_pending_reviewable_posts,
    )

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
    my_exams_page_obj = None
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

        if active_section == "my-exams":
            # --- Search ---
            my_exams_search_query = (request.GET.get("exam_q", "") or "").strip()
            if my_exams_search_query:
                my_exams_qs = my_exams_qs.filter(title__icontains=my_exams_search_query)

            # --- Filter by exam type ---
            my_exams_filter_type = (request.GET.get("exam_type", "") or "").strip()
            if my_exams_filter_type not in {"", "test", "written", "coding"}:
                my_exams_filter_type = ""
            if my_exams_filter_type:
                my_exams_qs = my_exams_qs.filter(exam_type=my_exams_filter_type)

            my_exams_count = my_exams_qs.count()
            # Kart redizaynı üçün: sual sayı + apellyasiya sayı (annotate) və
            # aktiv dil variantları (prefetch). Yalnız göstərilən səhifəyə tətbiq
            # olunur — baza queryset toxunulmur.
            from django.db.models import Prefetch

            from apps.exams.models import ExamLanguageVariant

            my_exams_display_qs = my_exams_qs.annotate(
                card_question_count=Count("questions", filter=Q(questions__is_active=True), distinct=True),
                card_appeal_count=Count("appeals", distinct=True),
            ).prefetch_related(
                Prefetch(
                    "language_variants",
                    queryset=ExamLanguageVariant.objects.filter(is_active=True).order_by("language"),
                    to_attr="active_language_variants",
                )
            )
            my_exams_page_obj = Paginator(my_exams_display_qs, 6).get_page(request.GET.get("exam_page"))
        else:
            # Yalnız sidebar/profile-info üçün ucuz sayğac.
            my_exams_count = my_exams_qs.count()

    if active_section == "question-bank" and "question-bank" in allowed_sections:
        from apps.exams.constants import EXAM_LANGUAGE_CHOICES
        from apps.exams.models import QuestionBank
        from apps.exams.services.question_bank_attach import accessible_banks
        from core.tenancy import get_request_organization

        organization = get_request_organization(request)
        question_bank_search_query = (request.GET.get("bank_q") or "").strip()[:120]
        question_bank_qs = accessible_banks(request.user, organization).annotate(
            lib_count=Count("library_questions", filter=Q(library_questions__is_active=True))
        )
        if question_bank_search_query:
            question_bank_qs = question_bank_qs.filter(
                Q(name__icontains=question_bank_search_query) | Q(subject__icontains=question_bank_search_query)
            )
        question_bank_qs = question_bank_qs.order_by("-created_at")

        question_bank_page_obj = Paginator(question_bank_qs, 9).get_page(request.GET.get("bank_page"))
        question_bank_banks = question_bank_page_obj.object_list
        question_bank_pagination_query = _query_string(
            section="question-bank",
            bank_q=question_bank_search_query,
        )
        question_bank_back_url = _append_query_params(
            reverse("accounts:profile"),
            section="question-bank",
            bank_q=question_bank_search_query,
            bank_page=request.GET.get("bank_page"),
        )
        question_bank_language_choices = EXAM_LANGUAGE_CHOICES
        question_bank_default_type_choices = QuestionBank.DEFAULT_QUESTION_TYPE_CHOICES

    user_posts = None
    posts_count = 0
    post_category_tree = []
    post_category_root_options = []
    post_category_subcategory_options = []
    post_creation_requires_approval = False
    posting_blocked = False
    posting_blocked_reason = ""
    if capabilities["can_manage_blog"]:
        user_posts_qs = (
            Post.objects.filter(author=request.user)
            .select_related("category")
            .prefetch_related("approval_logs")
            .order_by("-created_at")
        )
        # Sidebar/profile-info üçün ucuz sayğac hər zaman.
        posts_count = user_posts_qs.count()
        if active_section in {"posts", "create-post"}:
            user_posts = Paginator(user_posts_qs, 6).get_page(request.GET.get("page"))
            post_category_tree = get_post_category_tree()
            post_category_root_options, post_category_subcategory_options = build_post_category_picker_options(
                post_category_tree
            )
            post_creation_requires_approval = author_requires_post_approval(request.user)
            can_publish, blocked_reason = can_user_publish_post(request.user)
            posting_blocked = not can_publish
            posting_blocked_reason = blocked_reason

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
    if "groups" in allowed_sections and active_section == "groups":
        if active_organization is not None:
            current_role_level = (
                request.user._highest_role_level()
                if hasattr(request.user, "_highest_role_level")
                else ProfileRole.LEVELS.get(getattr(profile, "role", ProfileRole.MEMBER), 0)
            )
            can_multi_assign_group_teachers = capabilities["is_superadmin"] or (
                current_role_level >= ProfileRole.LEVELS.get(ProfileRole.TEACHER, 60)
            )
            group_form = StudentGroupForm(
                actor=request.user,
                organization=active_organization,
                can_multi_assign_teachers=can_multi_assign_group_teachers,
                is_superadmin=capabilities["is_superadmin"],
                auto_id="group_%s",
            )

            teacher_groups_qs = (
                StudentGroup.objects.filter(organization=active_organization)
                .select_related("teacher")
                .prefetch_related("students", "teachers")
                .order_by("name")
            )
            can_view_all_groups = capabilities["is_superadmin"] or capabilities["can_manage_org"]
            if not can_view_all_groups:
                teacher_groups_qs = teacher_groups_qs.filter(
                    Q(teacher=request.user) | Q(teachers=request.user)
                ).distinct()

            visible_teacher_groups_qs = teacher_groups_qs
            teacher_groups_count = visible_teacher_groups_qs.count()

            if teacher_groups_search_query:
                visible_teacher_groups_qs = visible_teacher_groups_qs.filter(
                    Q(name__icontains=teacher_groups_search_query)
                    | Q(teacher__username__icontains=teacher_groups_search_query)
                    | Q(teacher__first_name__icontains=teacher_groups_search_query)
                    | Q(teacher__last_name__icontains=teacher_groups_search_query)
                    | Q(students__username__icontains=teacher_groups_search_query)
                    | Q(students__first_name__icontains=teacher_groups_search_query)
                    | Q(students__last_name__icontains=teacher_groups_search_query)
                    | Q(students__profile__student_group_number__icontains=teacher_groups_search_query)
                ).distinct()

            teacher_groups_filtered_count = visible_teacher_groups_qs.count()
            teacher_groups_page = Paginator(visible_teacher_groups_qs, 8).get_page(request.GET.get("groups_page"))
            teacher_groups = list(teacher_groups_page.object_list)

            selected_group_id = (request.GET.get("group") or "").strip()
            if selected_group_id.isdigit():
                selected_teacher_group = teacher_groups_qs.filter(id=int(selected_group_id)).first()

            teacher_groups_pagination_query = urlencode(
                {
                    key: value
                    for key, value in {
                        "section": "groups",
                        "group_q": teacher_groups_search_query,
                        "group": selected_teacher_group.id if selected_teacher_group else "",
                        "student_q": group_students_search_query if selected_teacher_group else "",
                    }.items()
                    if value not in ("", None)
                }
            )

            if selected_teacher_group:
                students_qs = selected_teacher_group.students.select_related("profile").order_by(
                    "first_name", "last_name", "username", "id"
                )
                selected_group_students_count = students_qs.count()
                if group_students_search_query:
                    students_qs = students_qs.filter(
                        Q(username__icontains=group_students_search_query)
                        | Q(first_name__icontains=group_students_search_query)
                        | Q(last_name__icontains=group_students_search_query)
                        | Q(email__icontains=group_students_search_query)
                        | Q(profile__student_group_number__icontains=group_students_search_query)
                    )
                selected_group_students_filtered_count = students_qs.count()
                selected_group_students_page = Paginator(students_qs, 12).get_page(request.GET.get("students_page"))
                group_students_pagination_query = urlencode(
                    {
                        key: value
                        for key, value in {
                            "section": "groups",
                            "group": selected_teacher_group.id,
                            "group_q": teacher_groups_search_query,
                            "groups_page": teacher_groups_page.number if teacher_groups_page else "",
                            "student_q": group_students_search_query,
                        }.items()
                        if value not in ("", None)
                    }
                )

            for group in teacher_groups:
                student_ids = [student.id for student in group.students.all()]
                teacher_ids = [teacher.id for teacher in group.teachers.all()]
                if group.teacher_id and group.teacher_id not in teacher_ids:
                    teacher_ids.append(group.teacher_id)

                teacher_groups_payload[str(group.id)] = {
                    "name": group.name,
                    "primary_teacher": group.teacher_id,
                    "students": student_ids,
                    "teachers": teacher_ids,
                }
            if selected_teacher_group and str(selected_teacher_group.id) not in teacher_groups_payload:
                student_ids = [student.id for student in selected_teacher_group.students.all()]
                teacher_ids = [teacher.id for teacher in selected_teacher_group.teachers.all()]
                if selected_teacher_group.teacher_id and selected_teacher_group.teacher_id not in teacher_ids:
                    teacher_ids.append(selected_teacher_group.teacher_id)
                teacher_groups_payload[str(selected_teacher_group.id)] = {
                    "name": selected_teacher_group.name,
                    "primary_teacher": selected_teacher_group.teacher_id,
                    "students": student_ids,
                    "teachers": teacher_ids,
                }

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
    if active_section == "pending-review" and "pending-review" in allowed_sections:
        (
            pending_review_items,
            pending_review_search_query,
            pending_review_filter_type,
            pending_review_filter_status,
            pending_review_submitted_order,
            pending_review_filter_group,
            pending_review_available_groups,
        ) = _collect_pending_review_items(request)
        pending_review_page_obj = Paginator(pending_review_items, 15).get_page(request.GET.get("pr_page", 1))
        pr_extra = ["section=pending-review"]
        if pending_review_search_query:
            pr_extra.append(f"search={pending_review_search_query}")
        if pending_review_filter_type != "all":
            pr_extra.append(f"type={pending_review_filter_type}")
        if pending_review_filter_status != "all":
            pr_extra.append(f"status={pending_review_filter_status}")
        if pending_review_submitted_order != "oldest":
            pr_extra.append(f"submitted_order={pending_review_submitted_order}")
        if pending_review_filter_group:
            pr_extra.append(f"pr_group={pending_review_filter_group}")
        pending_review_pagination_query = "&".join(pr_extra)

    if active_section == "review-results" and "review-results" in allowed_sections:
        (
            evaluated_review_items,
            evaluated_review_search_query,
            evaluated_review_filter_type,
            evaluated_review_filter_group,
            evaluated_review_available_groups,
            evaluated_review_submitted_order,
        ) = _collect_evaluated_review_items(request)
        evaluated_review_page_obj = Paginator(evaluated_review_items, 15).get_page(request.GET.get("er_page", 1))
        er_extra = ["section=review-results"]
        if evaluated_review_search_query:
            er_extra.append(f"evaluated_search={evaluated_review_search_query}")
        if evaluated_review_filter_type != "all":
            er_extra.append(f"evaluated_type={evaluated_review_filter_type}")
        if evaluated_review_filter_group:
            er_extra.append(f"evaluated_group={evaluated_review_filter_group}")
        if evaluated_review_submitted_order != "newest":
            er_extra.append(f"evaluated_submitted_order={evaluated_review_submitted_order}")
        evaluated_review_pagination_query = "&".join(er_extra)

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
        from apps.organizations.models import Membership, Role

        role_assignment_search = request.GET.get("q", request.GET.get("search", ""))
        role_assignment_unassigned_search = request.GET.get("unassigned_search", "")
        role_assignment_section.update(
            {
                "organization": management_org,
                "search_query": role_assignment_search,
                "unassigned_search_query": role_assignment_unassigned_search,
                "can_assign_roles": management_can_assign_roles,
                "post_next_url": _append_query_params(
                    reverse("accounts:profile"),
                    section="role-assignment",
                    q=role_assignment_search,
                    unassigned_search=role_assignment_unassigned_search,
                    role_members_page=request.GET.get("role_members_page", ""),
                    role_pending_page=request.GET.get("role_pending_page", ""),
                ),
            }
        )

        if management_org is None:
            role_assignment_section["access_denied_message"] = "Aktiv təşkilat tapılmadı."
        elif not management_min_level_ok:
            role_assignment_section["access_denied_message"] = (
                "Bu bölmə üçün minimum müəllim və ya daha yüksək səviyyə tələb olunur."
            )
        else:
            members = (
                Membership.objects.filter(organization=management_org, is_active=True)
                .select_related("user", "role")
                .order_by("-role__level", "user__username")
            )
            if not capabilities["is_superadmin"]:
                members = members.filter(role__level__lt=management_user_level)

            assignable_roles = Role.objects.filter(organization=management_org, is_active=True).order_by("-level")
            if not capabilities["is_superadmin"]:
                assignable_roles = assignable_roles.filter(level__lt=management_user_level)

            if role_assignment_search:
                members = members.filter(
                    Q(user__username__icontains=role_assignment_search)
                    | Q(user__email__icontains=role_assignment_search)
                    | Q(user__first_name__icontains=role_assignment_search)
                    | Q(user__last_name__icontains=role_assignment_search)
                )

            unassigned_users = UserProfile.objects.filter(
                user__is_active=True, organization__isnull=True
            ).select_related(
                "user",
                "requested_organization",
            )
            if not capabilities["is_superadmin"]:
                pending_request_user_ids = _pending_student_request_queryset(
                    organization=management_org,
                    statuses=[StudentOrganizationRequestStatus.PENDING],
                ).values_list("user_id", flat=True)
                unassigned_users = unassigned_users.filter(
                    Q(user_id__in=pending_request_user_ids)
                    | Q(requested_organization=management_org)
                    | Q(
                        requested_organization__isnull=True,
                        requested_organization_name__iexact=management_org.name,
                    )
                )
            if role_assignment_unassigned_search:
                unassigned_users = unassigned_users.filter(
                    Q(user__username__icontains=role_assignment_unassigned_search)
                    | Q(user__email__icontains=role_assignment_unassigned_search)
                    | Q(user__first_name__icontains=role_assignment_unassigned_search)
                    | Q(user__last_name__icontains=role_assignment_unassigned_search)
                )

            role_assignment_members_page = request.GET.get("role_members_page")
            role_assignment_members_page_obj = Paginator(members, 12).get_page(role_assignment_members_page)

            role_assignment_pending_page = request.GET.get("role_pending_page")
            role_assignment_pending_page_obj = Paginator(unassigned_users.order_by("user__username"), 12).get_page(
                role_assignment_pending_page
            )

            role_assignment_section["members"] = role_assignment_members_page_obj
            role_assignment_section["assignable_roles"] = assignable_roles
            role_assignment_section["unassigned_users"] = role_assignment_pending_page_obj
            role_assignment_section["members_pagination_query"] = _query_string(
                section="role-assignment",
                q=role_assignment_search,
                unassigned_search=role_assignment_unassigned_search,
            )
            role_assignment_section["unassigned_pagination_query"] = _query_string(
                section="role-assignment",
                q=role_assignment_search,
                unassigned_search=role_assignment_unassigned_search,
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
        from apps.organizations.models import Role
        from apps.organizations.permissions import PERMISSION_CATEGORIES

        selected_permission_role_id = request.GET.get("role")
        permission_editor_section.update(
            {
                "organization": management_org,
                "permission_categories": PERMISSION_CATEGORIES,
                "actor_permissions": sorted(management_actor_permissions),
                "grantable_permissions": sorted(management_grantable_permissions),
                "can_manage_permissions": management_can_assign_roles,
            }
        )

        if management_org is None:
            permission_editor_section["access_denied_message"] = "Aktiv təşkilat tapılmadı."
        elif not capabilities["is_superadmin"] and not management_can_assign_roles:
            permission_editor_section["access_denied_message"] = (
                "Permission idarəetməsi üçün `role.assign` səlahiyyəti tələb olunur."
            )
        else:
            roles = Role.objects.filter(organization=management_org, is_active=True).order_by("-level")
            if not capabilities["is_superadmin"]:
                roles = roles.filter(level__lt=management_user_level)

            selected_permission_role = None
            if selected_permission_role_id:
                selected_permission_role = roles.filter(id=selected_permission_role_id).first()
            if selected_permission_role is None:
                selected_permission_role = roles.first()

            permission_editor_section["roles"] = roles
            permission_editor_section["selected_role"] = selected_permission_role

    if "manage-roles" in allowed_sections and active_section == "manage-roles":
        manage_roles_search = request.GET.get("manage_roles_search", "")
        manage_roles_org = _get_active_organization(request)
        _bind_active_role_context(
            request.user,
            manage_roles_org,
            memberships=getattr(request, "org_memberships", []),
            permissions=getattr(request, "org_permissions", []),
        )
        manage_roles_user_level = (
            request.user._highest_role_level() if hasattr(request.user, "_highest_role_level") else 0
        )
        assignable_roles = _assignable_profile_roles_for_user(request.user)
        manage_roles_section.update(
            {
                "search_query": manage_roles_search,
                "organization": manage_roles_org,
                "assignable_roles": assignable_roles,
                "post_next_url": _append_query_params(
                    reverse("accounts:profile"),
                    section="manage-roles",
                    manage_roles_search=manage_roles_search,
                ),
            }
        )

        if manage_roles_org is None:
            manage_roles_section["access_denied_message"] = "Rol idarəetməsi üçün aktiv təşkilat tapılmadı."
            manage_role_profiles = UserProfile.objects.none()
        else:
            manage_role_profiles = (
                UserProfile.objects.filter(
                    user__memberships__organization=manage_roles_org,
                    user__memberships__is_active=True,
                )
                .select_related("user")
                .prefetch_related("user__memberships__role")
                .distinct()
            )

            # Include the requesting superadmin's own profile even without a formal membership
            if capabilities["is_superadmin"] and not manage_role_profiles.filter(user=request.user).exists():
                own_profile_qs = (
                    UserProfile.objects.filter(user=request.user)
                    .select_related("user")
                    .prefetch_related("user__memberships__role")
                    .distinct()
                )
                manage_role_profiles = (manage_role_profiles | own_profile_qs).distinct()

        if manage_roles_search:
            manage_role_profiles = manage_role_profiles.filter(
                Q(user__username__icontains=manage_roles_search)
                | Q(user__email__icontains=manage_roles_search)
                | Q(user__first_name__icontains=manage_roles_search)
                | Q(user__last_name__icontains=manage_roles_search)
            )

        manage_roles_page = request.GET.get("manage_roles_page")
        manage_roles_page_obj = Paginator(manage_role_profiles.order_by("user__username"), 12).get_page(
            manage_roles_page
        )
        _decorate_manage_role_profiles(
            manage_roles_page_obj.object_list,
            actor_level=manage_roles_user_level,
            is_superadmin=capabilities["is_superadmin"],
            organization=manage_roles_org,
            actor_user=request.user,
        )

        manage_roles_section["profiles"] = manage_roles_page_obj
        manage_roles_section["profiles_pagination_query"] = _query_string(
            section="manage-roles",
            manage_roles_search=manage_roles_search,
        )

    # Superadmin "pending org" badge sidebar üçündür — ucuz `Organization.objects... .count()`-i hər zaman saxla.
    if "superadmin-organizations" in allowed_sections and active_section != "superadmin-organizations":
        from apps.organizations.models import Organization as _PendingOrg

        superadmin_organizations_section["pending_count"] = _PendingOrg.objects.filter(status="pending").count()

    if ("superadmin-org-features" in allowed_sections and active_section == "superadmin-org-features") or (
        "superadmin-organizations" in allowed_sections and active_section == "superadmin-organizations"
    ):
        from apps.organizations.models import REVIEW_VISIBILITY_FEATURES, Organization

        superadmin_organizations_queryset = (
            Organization.objects.select_related("owner")
            .annotate(active_member_count=Count("memberships", filter=Q(memberships__is_active=True)))
            .order_by("name")
        )
        organization_status_filter = (request.GET.get("status") or "").strip().lower()
        if organization_status_filter in {"active", "pending", "suspended"}:
            superadmin_organizations_queryset = superadmin_organizations_queryset.filter(
                status=organization_status_filter
            )
        elif organization_status_filter == "inactive":
            superadmin_organizations_queryset = superadmin_organizations_queryset.filter(is_active=False).exclude(
                status="suspended"
            )

        if "superadmin-org-features" in allowed_sections and active_section == "superadmin-org-features":
            superadmin_feature_org_page = request.GET.get("superadmin_feature_org_page")
            superadmin_org_features_page = Paginator(superadmin_organizations_queryset, 12).get_page(
                superadmin_feature_org_page
            )
            for organization in superadmin_org_features_page.object_list:
                organization.review_feature_items = [
                    {
                        "key": feature_name,
                        "label": feature_config["label"],
                        "short_label": feature_config["short_label"],
                        "enabled": organization.is_review_identity_reveal_enabled(feature_name),
                    }
                    for feature_name, feature_config in REVIEW_VISIBILITY_FEATURES.items()
                ]
            superadmin_org_features_section["organizations"] = superadmin_org_features_page
            superadmin_org_features_section["organizations_pagination_query"] = _query_string(
                section="superadmin-org-features"
            )
            superadmin_org_features_section["post_next_url"] = _append_query_params(
                reverse("accounts:profile"),
                section="superadmin-org-features",
                superadmin_feature_org_page=superadmin_feature_org_page,
            )

        if "superadmin-organizations" in allowed_sections and active_section == "superadmin-organizations":
            superadmin_org_page = request.GET.get("superadmin_org_page")
            superadmin_organizations_section["organizations"] = Paginator(
                superadmin_organizations_queryset, 12
            ).get_page(superadmin_org_page)
            superadmin_organizations_section["organization_access_rows"] = organization_access_rows
            superadmin_organizations_section["all_modules"] = [
                "accounts",
                "organizations",
                "courses",
                "exams",
                "assignments",
                "projects",
                "labs",
                "live_exam",
                "blog",
                "audit",
            ]
            superadmin_organizations_section["organizations_pagination_query"] = _query_string(
                section="superadmin-organizations"
            )
            superadmin_organizations_section["post_next_url"] = _append_query_params(
                reverse("accounts:profile"),
                section="superadmin-organizations",
                superadmin_org_page=superadmin_org_page,
            )
            superadmin_organizations_section["pending_count"] = Organization.objects.filter(status="pending").count()

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
    notif_filter = "all"
    notif_search_query = ""
    notif_pagination_query = ""
    in_app_notifications_page = None
    if active_section == "notifications":
        notif_filter = request.GET.get("notif_filter", "all")
        if notif_filter not in ("all", "unread", "read"):
            notif_filter = "all"
        notif_search_query = _normalize_public_profile_query_value(
            request.GET.get("notif_search"),
            max_length=100,
        )
        in_app_notifications_qs = get_user_notifications(
            user=request.user,
            filter_by=notif_filter,
            search_query=notif_search_query,
        )
        # recipient=user is the security boundary; bypass RLS so the profile inbox
        # shows the user's notifications across every organisation (see
        # get_user_notifications docstring).
        in_app_notifications_paginator = Paginator(in_app_notifications_qs, 10)
        with bypass_rls():
            in_app_notifications_page = in_app_notifications_paginator.get_page(request.GET.get("notif_page", 1))
            in_app_notifications_page.object_list = list(in_app_notifications_page.object_list)
        notif_pagination_query = _query_string(
            section="notifications",
            notif_filter=notif_filter,
            notif_search=notif_search_query,
        )

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
    if active_section == "statistics" and "statistics" in allowed_sections:
        from apps.accounts.services.statistics_selectors import (
            get_org_admin_statistics,
            get_student_statistics,
            get_superadmin_statistics,
            get_teacher_statistics,
        )
        from apps.organizations.models import Organization as _StatisticsOrganization

        stat_org = _get_active_organization(request)
        statistics_content_type = (request.GET.get("stat_content_type") or "all").strip().lower()
        if statistics_content_type not in {"all", "exam", "assignment", "lab", "project"}:
            statistics_content_type = "all"
        statistics_filters = {
            "date_from": (request.GET.get("stat_date_from") or "").strip(),
            "date_to": (request.GET.get("stat_date_to") or "").strip(),
            "course": (request.GET.get("stat_course") or "").strip() or None,
            "group": (request.GET.get("stat_group") or "").strip() or None,
            "content_type": statistics_content_type,
            "organization": (request.GET.get("stat_organization") or "").strip() or None,
        }
        statistics_has_active_filters = any(
            [
                statistics_filters["date_from"],
                statistics_filters["date_to"],
                statistics_filters["course"],
                statistics_filters["group"],
                statistics_filters["organization"],
                statistics_filters["content_type"] != "all",
            ]
        )

        selected_statistics_org = None
        if capabilities["is_superadmin"] and statistics_filters["organization"]:
            selected_statistics_org = (
                _StatisticsOrganization.objects.filter(
                    id=statistics_filters["organization"],
                    is_active=True,
                    status="active",
                )
                .only("id", "name")
                .first()
            )

        statistics_scope_org = selected_statistics_org or stat_org

        # Populate filter options
        if statistics_scope_org and not capabilities["is_superadmin"]:
            statistics_courses = list(
                Course.objects.filter(organization=statistics_scope_org).order_by("title").values("id", "title")[:100]
            )
        elif capabilities["is_superadmin"]:
            statistics_organizations = list(
                _StatisticsOrganization.objects.filter(is_active=True, status="active")
                .order_by("name")
                .values("id", "name")[:150]
            )
            superadmin_course_qs = Course.objects.all()
            if selected_statistics_org:
                superadmin_course_qs = superadmin_course_qs.filter(organization=selected_statistics_org)
            statistics_courses = list(superadmin_course_qs.order_by("title").values("id", "title")[:150])

        if statistics_scope_org:
            from apps.exams.models import StudentGroup as _SG

            statistics_groups = list(
                _SG.objects.filter(organization=statistics_scope_org).order_by("name").values("id", "name")[:100]
            )

        # Dashboard statistics are expensive (~44 aggregate queries) but do not
        # need to be real-time, so each (role, scope, filters) result is cached
        # briefly via core.cache.get_or_set_cached_statistics (FAZA 12).
        from core.cache import get_or_set_cached_statistics

        if capabilities["is_superadmin"]:
            statistics_data = get_or_set_cached_statistics(
                role="superadmin",
                scope_id="global",
                filters=statistics_filters,
                compute=lambda: get_superadmin_statistics(filters=statistics_filters),
            )
        elif capabilities["is_org_admin"]:
            if stat_org:
                statistics_data = get_or_set_cached_statistics(
                    role="org_admin",
                    scope_id=stat_org.pk,
                    filters=statistics_filters,
                    compute=lambda: get_org_admin_statistics(organization=stat_org, filters=statistics_filters),
                )
        elif capabilities["is_teacher"]:
            statistics_data = get_or_set_cached_statistics(
                role="teacher",
                scope_id=request.user.pk,
                filters={**statistics_filters, "_org": getattr(stat_org, "pk", None)},
                compute=lambda: get_teacher_statistics(request.user, organization=stat_org, filters=statistics_filters),
            )
        else:
            # Student / lead student / member
            statistics_data = get_or_set_cached_statistics(
                role="student",
                scope_id=request.user.pk,
                filters={**statistics_filters, "_org": getattr(stat_org, "pk", None)},
                compute=lambda: get_student_statistics(request.user, organization=stat_org, filters=statistics_filters),
            )

        statistics_base_query = _query_string(
            section="statistics",
            stat_date_from=statistics_filters["date_from"],
            stat_date_to=statistics_filters["date_to"],
            stat_course=statistics_filters["course"],
            stat_group=statistics_filters["group"],
            stat_content_type=(
                None if statistics_filters["content_type"] == "all" else statistics_filters["content_type"]
            ),
            stat_organization=statistics_filters["organization"],
        )

        if statistics_data.get("org_comparison"):
            statistics_org_page = Paginator(statistics_data["org_comparison"], 8).get_page(
                request.GET.get(statistics_org_page_param)
            )
            statistics_org_rows = list(statistics_org_page.object_list)
            statistics_org_pagination_query = statistics_base_query

        if statistics_data.get("teacher_overview"):
            statistics_teacher_page = Paginator(statistics_data["teacher_overview"], 8).get_page(
                request.GET.get(statistics_teacher_page_param)
            )
            statistics_teacher_rows = list(statistics_teacher_page.object_list)
            statistics_teacher_pagination_query = statistics_base_query

        if statistics_data.get("course_rankings"):
            statistics_course_page = Paginator(statistics_data["course_rankings"], 8).get_page(
                request.GET.get(statistics_course_page_param)
            )
            statistics_course_rows = list(statistics_course_page.object_list)
            statistics_course_pagination_query = statistics_base_query

        if statistics_data.get("group_comparison"):
            statistics_group_page = Paginator(statistics_data["group_comparison"], 8).get_page(
                request.GET.get(statistics_group_page_param)
            )
            statistics_group_rows = list(statistics_group_page.object_list)
            statistics_group_pagination_query = statistics_base_query

        if statistics_data.get("course_overview"):
            statistics_teacher_course_page = Paginator(statistics_data["course_overview"], 8).get_page(
                request.GET.get(statistics_teacher_course_page_param)
            )
            statistics_teacher_course_rows = list(statistics_teacher_course_page.object_list)
            statistics_teacher_course_pagination_query = statistics_base_query

        # ── AI summary (AJAX) ─────────────────────────────────────
        if request.GET.get("stat_ai_summary") == "1" and statistics_data:
            from apps.accounts.services.statistics_selectors import build_ai_stats_payload
            from apps.exams.services.ai_summary import generate_exam_statistics_summary

            role_label = (
                "superadmin"
                if capabilities["is_superadmin"]
                else (
                    "org_admin"
                    if capabilities["is_org_admin"]
                    else ("teacher" if capabilities["is_teacher"] else "student")
                )
            )
            ai_payload = build_ai_stats_payload(role=role_label, stats=statistics_data)
            result = generate_exam_statistics_summary(
                exam_title=f"Profil Statistikası ({role_label})",
                exam_type="profile_statistics",
                stats=ai_payload,
                user_id=request.user.pk,
            )
            from django.http import JsonResponse as _JR

            return _JR(result)

    section_titles = {
        "profile-info": pgettext_lazy("profile.section", "profile_info"),
        "notifications": pgettext_lazy("profile.section", "notifications"),
        "publish-notification": pgettext_lazy("profile.publish_notification", "title"),
        "posts": pgettext_lazy("profile.section", "posts"),
        "create-post": pgettext_lazy("profile.section", "create_post"),
        "create-category": _("Create category"),
        "category-management": _("Categories"),
        "courses": pgettext_lazy("profile.section", "my_courses"),
        "my-exams": pgettext_lazy("profile.section", "my_exams"),
        "my-courses": pgettext_lazy("profile.section", "my_created_courses"),
        "assigned-exams": pgettext_lazy("profile.section", "assigned_tasks"),
        "assigned-courses": pgettext_lazy("profile.section", "assigned_courses"),
        "my-results": pgettext_lazy("profile.section", "my_results"),
        "pending-answers": pgettext_lazy("accounts.pending_answers", "section_title"),
        "groups": pgettext_lazy("profile.section", "groups"),
        "pending-post-approvals": "Postların idarəetməsi",
        "pending-review": pgettext_lazy("profile.section", "pending_review"),
        "review-results": "Dəyərləndirilmiş nəticələr",
        "role-assignment": pgettext_lazy("profile.section", "role_assignment"),
        "student-organization-request": pgettext_lazy("profile.section", "join_organization"),
        "student-organization-management": pgettext_lazy("profile.section", "staff_management"),
        "permission-editor": pgettext_lazy("profile.section", "permissions"),
        "manage-roles": pgettext_lazy("profile.section", "manage_roles"),
        "superadmin-org-features": "Təşkilat özəllikləri",
        "superadmin-organizations": pgettext_lazy("profile.section", "superadmin_control"),
        "superadmin-users": pgettext_lazy("superadmin.users", "user_management_title"),
        "superadmin-ai": pgettext_lazy("superadmin.ai_settings", "title"),
        "superadmin-contact-messages": _("Contact Messages"),
        "blog": pgettext_lazy("nav", "home"),
        "edit-profile": pgettext_lazy("profile.section", "edit_profile"),
        "change-password": pgettext_lazy("profile.section", "change_password"),
        "statistics": pgettext_lazy("profile.section", "statistics"),
        "question-bank": "Sual Bankı",
        "my-appeals": pgettext_lazy("appeals.template", "Apellyasiyalarım"),
        "manage-appeals": pgettext_lazy("appeals.template", "Apellyasiyalar"),
    }

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
    direct_profile_section_templates = {
        "pending-answers": "accounts/profile/sections/_pending_answers.html",
        "pending-review": "accounts/profile/sections/_pending_review.html",
        "review-results": "accounts/profile/sections/_review_results.html",
        "student-organization-management": "accounts/profile/sections/_student_org_management.html",
        "student-organization-request": "accounts/profile/sections/_student_org_request.html",
        "manage-roles": "accounts/profile/sections/_manage_roles.html",
        "permission-editor": "accounts/profile/sections/_permission_editor.html",
        "superadmin-organizations": "accounts/profile/sections/_superadmin_organizations.html",
        "superadmin-ai": "accounts/profile/sections/_superadmin_ai_settings.html",
    }

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
        "my_exams": my_exams_page_obj,
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
