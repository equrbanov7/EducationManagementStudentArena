"""
Business logic layer for blog app.
This module contains service functions that encapsulate business operations.
"""

from collections import defaultdict

from django.core.exceptions import ValidationError
from django.db.models import Q

from apps.accounts.models import ProfileRole
from apps.accounts.policies import get_user_role_level, is_superadmin_user, user_has_any_role
from apps.exams.models import StudentGroup
from apps.organizations.models import Membership, Organization
from core.constants import ROLE_LEVEL_TEACHER, OrganizationType
from core.rls import bypass_rls

from .models import Category, Post

APPROVAL_STATUS_FILTERS = {
    "all",
    Post.ApprovalStatus.PENDING,
    Post.ApprovalStatus.NEEDS_CHANGES,
    Post.ApprovalStatus.APPROVED,
}
PERSONAL_APPROVAL_ORG_FILTER = "__personal__"
_ORG_MODERATOR_ROLE_NAMES = frozenset(ProfileRole.ADMIN_EQUIVALENT_ROLE_NAMES)


def _institutional_memberships_qs():
    return Membership.objects.exclude(organization__org_type=OrganizationType.INDIVIDUAL)


def _active_institutional_memberships_qs():
    return _institutional_memberships_qs().filter(
        is_active=True,
        organization__status="active",
        organization__is_active=True,
    )


def _get_active_institutional_organization_id(user):
    active_organization = getattr(user, "active_organization", None)
    if not active_organization:
        return None
    if getattr(active_organization, "org_type", None) == OrganizationType.INDIVIDUAL:
        return None
    if not getattr(active_organization, "is_active", False):
        return None
    if getattr(active_organization, "status", "") != "active":
        return None
    return active_organization.id


def _active_admin_org_ids_for_user(user):
    """Return the institutional org ids the user may moderate as owner/admin."""
    if not user or not getattr(user, "is_authenticated", False) or is_superadmin_user(user):
        return set()

    active_org_id = _get_active_institutional_organization_id(user)
    with bypass_rls():
        admin_memberships = _active_institutional_memberships_qs().filter(
            user=user,
            role__name__in=_ORG_MODERATOR_ROLE_NAMES,
        )
        owned_orgs = Organization.objects.exclude(org_type=OrganizationType.INDIVIDUAL).filter(
            owner=user,
            status="active",
            is_active=True,
        )

        if active_org_id:
            if (
                admin_memberships.filter(organization_id=active_org_id).exists()
                or owned_orgs.filter(id=active_org_id).exists()
            ):
                return {active_org_id}
            return set()

        admin_org_ids = set(admin_memberships.values_list("organization_id", flat=True))
        admin_org_ids.update(owned_orgs.values_list("id", flat=True))
        return admin_org_ids


def _user_has_active_org_membership(user):
    """Return True if *user* has an active membership in a non-personal active organization."""
    with bypass_rls():
        return _active_institutional_memberships_qs().filter(user=user).exists()


def _user_has_any_org_membership(user):
    """Return True if *user* has any non-personal organization membership."""
    with bypass_rls():
        return _institutional_memberships_qs().filter(user=user).exists()


def _active_org_ids_for_user(user):
    with bypass_rls():
        return set(_active_institutional_memberships_qs().filter(user=user).values_list("organization_id", flat=True))


def author_requires_superadmin_post_review(author):
    if not author or not getattr(author, "is_authenticated", False):
        return False
    if is_superadmin_user(author):
        return False
    return not _user_has_active_org_membership(author)


def can_user_publish_post(user):
    """Determine whether *user* is allowed to create/publish a post.

    Returns ``(can_publish, reason)`` where *can_publish* is a bool and
    *reason* is a human-readable explanation when publishing is blocked.
    """
    if not user or not getattr(user, "is_authenticated", False):
        return False, "İstifadəçi daxil olmayıb."

    if is_superadmin_user(user):
        return True, ""

    if _user_has_any_org_membership(user):
        if _user_has_active_org_membership(user):
            return True, ""
        return (
            False,
            "Təşkilatınız tərəfindən üzvlüyünüz hələ təsdiqlənməyib.",
        )

    # Personal-only or no-org users can submit, but it will require superadmin review.
    return True, ""


def author_requires_post_approval(author):
    if not author or not getattr(author, "is_authenticated", False):
        return False
    if is_superadmin_user(author):
        return False
    # Students / lead-students always require approval (original logic).
    if user_has_any_role(author, {ProfileRole.STUDENT, ProfileRole.LEAD_STUDENT}):
        return True
    # Users outside any active non-personal organization require superadmin review.
    if author_requires_superadmin_post_review(author):
        return True
    if get_user_role_level(author) >= ROLE_LEVEL_TEACHER:
        return False
    return False


def can_user_manage_categories(user):
    return is_superadmin_user(user)


def resolve_post_category_selection(*, category=None, subcategory=None):
    if category is None:
        raise ValidationError({"category": "Please select a category."})

    if category.parent_id:
        raise ValidationError({"category": "Please select a top-level category."})

    if subcategory is None:
        return category

    if not isinstance(subcategory, Category):
        raise ValidationError({"subcategory": "Please select a valid subcategory."})

    if not subcategory.parent_id:
        raise ValidationError({"subcategory": "Please select a valid subcategory."})

    if subcategory.parent_id != category.id:
        raise ValidationError({"subcategory": "Selected subcategory does not belong to the chosen category."})

    return subcategory


def can_user_review_post(user, post):
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if not post or not post.requires_approval:
        return False
    if user == post.author:
        return False
    if is_superadmin_user(user):
        return True

    reviewer_admin_org_ids = _active_admin_org_ids_for_user(user)
    if reviewer_admin_org_ids:
        author_org_ids = _active_org_ids_for_user(post.author)
        return bool(reviewer_admin_org_ids & author_org_ids)

    reviewer_level = get_user_role_level(user)
    author_level = get_user_role_level(post.author)
    if reviewer_level < ROLE_LEVEL_TEACHER or reviewer_level <= author_level:
        return False

    reviewer_group_scope = StudentGroup.objects.filter(students=post.author).filter(Q(teacher=user) | Q(teachers=user))
    active_org_id = _get_active_institutional_organization_id(user)
    if active_org_id:
        reviewer_group_scope = reviewer_group_scope.filter(organization_id=active_org_id)
    return reviewer_group_scope.exists()


def can_user_moderate_post(user, post):
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if not post:
        return False
    if is_superadmin_user(user):
        return True

    reviewer_admin_org_ids = _active_admin_org_ids_for_user(user)
    if reviewer_admin_org_ids:
        return bool(reviewer_admin_org_ids & _active_org_ids_for_user(post.author))

    return can_user_review_post(user, post)


def normalize_approval_status(value, *, include_all=False, default=Post.ApprovalStatus.PENDING):
    normalized = (value or "").strip().lower()
    if include_all and normalized == "all":
        return "all"
    if normalized in APPROVAL_STATUS_FILTERS:
        return normalized
    return default


def _build_group_scope_for_reviewer(reviewer):
    if is_superadmin_user(reviewer):
        return StudentGroup.objects.filter(students__posts__isnull=False).distinct()

    reviewer_admin_org_ids = _active_admin_org_ids_for_user(reviewer)
    if reviewer_admin_org_ids:
        return StudentGroup.objects.filter(
            organization_id__in=reviewer_admin_org_ids,
            students__posts__isnull=False,
        ).distinct()

    active_org_id = _get_active_institutional_organization_id(reviewer)
    groups_qs = StudentGroup.objects.filter(Q(teacher=reviewer) | Q(teachers=reviewer))
    if active_org_id:
        groups_qs = groups_qs.filter(organization_id=active_org_id)
    return groups_qs.distinct()


def collect_reviewable_posts(reviewer, *, search="", status="pending", group_id="", organization_id=""):
    normalized_search = (search or "").strip()
    superadmin = is_superadmin_user(reviewer)
    reviewer_admin_org_ids = _active_admin_org_ids_for_user(reviewer)
    is_org_admin = bool(reviewer_admin_org_ids)
    reviewer_level = get_user_role_level(reviewer)
    default_status = "all" if (superadmin or is_org_admin) else Post.ApprovalStatus.PENDING
    normalized_status = normalize_approval_status(status, include_all=True, default=default_status)
    selected_group = str(group_id or "").strip()
    selected_organization = str(organization_id or "").strip()

    if not superadmin and reviewer_level < ROLE_LEVEL_TEACHER:
        return [], normalized_search, normalized_status, "", [], "", []

    groups_scope = _build_group_scope_for_reviewer(reviewer)
    available_groups = list(groups_scope.order_by("name").values("id", "name"))
    available_group_ids = {str(group["id"]) for group in available_groups}
    available_organizations = []

    if selected_group and selected_group not in available_group_ids:
        selected_group = ""

    if superadmin:
        with bypass_rls():
            available_organizations = list(
                _active_institutional_memberships_qs()
                .filter(user__posts__isnull=False)
                .values("organization_id", "organization__name")
                .distinct()
                .order_by("organization__name")
            )
            available_organizations = [
                {"id": row["organization_id"], "name": row["organization__name"]} for row in available_organizations
            ]
            active_institutional_author_ids = set(
                _active_institutional_memberships_qs().values_list("user_id", flat=True)
            )
            has_personal_authors = Post.objects.exclude(author_id__in=active_institutional_author_ids).exists()

        available_org_ids = {str(org["id"]) for org in available_organizations}
        if has_personal_authors:
            available_organizations.append({"id": PERSONAL_APPROVAL_ORG_FILTER, "name": "Şəxsi / qurumsuz"})
            available_org_ids.add(PERSONAL_APPROVAL_ORG_FILTER)
        if selected_organization and selected_organization not in available_org_ids:
            selected_organization = ""

    posts_qs = Post.objects.select_related("author", "author__profile", "category", "approved_by").order_by(
        "-approval_requested_at",
        "-updated_at",
        "-created_at",
    )
    if not superadmin and not is_org_admin:
        posts_qs = posts_qs.filter(requires_approval=True)

    if normalized_status != "all":
        posts_qs = posts_qs.filter(approval_status=normalized_status)

    if normalized_search:
        posts_qs = posts_qs.filter(
            Q(title__icontains=normalized_search)
            | Q(excerpt__icontains=normalized_search)
            | Q(content__icontains=normalized_search)
            | Q(author__username__icontains=normalized_search)
            | Q(author__first_name__icontains=normalized_search)
            | Q(author__last_name__icontains=normalized_search)
        )

    if superadmin:
        if selected_organization == PERSONAL_APPROVAL_ORG_FILTER:
            with bypass_rls():
                institutional_author_ids = list(
                    _active_institutional_memberships_qs().values_list("user_id", flat=True)
                )
            posts_qs = posts_qs.exclude(author_id__in=institutional_author_ids)
        elif selected_organization:
            with bypass_rls():
                org_author_ids = list(
                    _active_institutional_memberships_qs()
                    .filter(organization_id=selected_organization)
                    .values_list("user_id", flat=True)
                )
                org_author_ids.extend(
                    Organization.objects.filter(id=selected_organization).values_list("owner_id", flat=True)
                )
            posts_qs = posts_qs.filter(author_id__in=org_author_ids)
        if selected_group:
            posts_qs = posts_qs.filter(author__student_groups_as_student__id=selected_group)
    elif is_org_admin:
        if not reviewer_admin_org_ids:
            return [], normalized_search, normalized_status, selected_group, available_groups, "", []
        with bypass_rls():
            reviewer_author_ids = list(
                _active_institutional_memberships_qs()
                .filter(organization_id__in=reviewer_admin_org_ids)
                .values_list("user_id", flat=True)
            )
            reviewer_author_ids.extend(
                Organization.objects.filter(id__in=reviewer_admin_org_ids).values_list("owner_id", flat=True)
            )
        posts_qs = posts_qs.filter(author_id__in=reviewer_author_ids)
        if selected_group:
            posts_qs = posts_qs.filter(author__student_groups_as_student__id=selected_group)
    else:
        posts_qs = posts_qs.filter(author__student_groups_as_student__in=groups_scope).distinct()
        if selected_group:
            posts_qs = posts_qs.filter(author__student_groups_as_student__id=selected_group)

    posts = list(posts_qs)
    if not superadmin and not is_org_admin:
        posts = [post for post in posts if reviewer_level > get_user_role_level(post.author)]

    author_ids = {post.author_id for post in posts}
    author_group_names = defaultdict(list)
    author_organization_names = defaultdict(list)
    if author_ids:
        group_pairs_qs = StudentGroup.objects.filter(students__id__in=author_ids)
        if is_org_admin:
            group_pairs_qs = group_pairs_qs.filter(organization_id__in=reviewer_admin_org_ids)
        elif not superadmin:
            group_pairs_qs = group_pairs_qs.filter(Q(teacher=reviewer) | Q(teachers=reviewer))
        if selected_group:
            group_pairs_qs = group_pairs_qs.filter(id=selected_group)

        for student_id, group_name in group_pairs_qs.values_list("students__id", "name"):
            if not student_id or not group_name:
                continue
            if group_name not in author_group_names[student_id]:
                author_group_names[student_id].append(group_name)

        with bypass_rls():
            org_pairs_qs = _active_institutional_memberships_qs().filter(
                user_id__in=author_ids,
            )
            if is_org_admin and not superadmin:
                org_pairs_qs = org_pairs_qs.filter(organization_id__in=reviewer_admin_org_ids)
            if selected_organization and selected_organization != PERSONAL_APPROVAL_ORG_FILTER:
                org_pairs_qs = org_pairs_qs.filter(organization_id=selected_organization)

            for user_id, org_name in org_pairs_qs.values_list("user_id", "organization__name"):
                if not user_id or not org_name:
                    continue
                if org_name not in author_organization_names[user_id]:
                    author_organization_names[user_id].append(org_name)

    for author_id in author_ids:
        if not author_organization_names.get(author_id):
            author_organization_names[author_id].append("Şəxsi / qurumsuz")

    status_label_map = {
        Post.ApprovalStatus.PENDING: "Təsdiq gözləyir",
        Post.ApprovalStatus.NEEDS_CHANGES: "Düzəliş tələb olunur",
        Post.ApprovalStatus.APPROVED: "Təsdiqlənib",
    }
    status_class_map = {
        Post.ApprovalStatus.PENDING: "status-awaiting",
        Post.ApprovalStatus.NEEDS_CHANGES: "status-needs-changes",
        Post.ApprovalStatus.APPROVED: "status-published",
    }

    items = []
    for post in posts:
        author_name = (post.author.get_full_name() or "").strip() or post.author.username
        items.append(
            {
                "post": post,
                "author_name": author_name,
                "group_names": author_group_names.get(post.author_id, []),
                "organization_names": author_organization_names.get(post.author_id, []),
                "status_label": status_label_map.get(post.approval_status, post.approval_status),
                "status_class": status_class_map.get(post.approval_status, "status-draft"),
                "can_review": can_user_review_post(reviewer, post),
                "can_moderate": can_user_moderate_post(reviewer, post),
            }
        )

    return (
        items,
        normalized_search,
        normalized_status,
        selected_group,
        available_groups,
        selected_organization,
        available_organizations,
    )


def count_pending_reviewable_posts(reviewer):
    items, _, _, _, _, _, _ = collect_reviewable_posts(
        reviewer,
        status=Post.ApprovalStatus.PENDING,
    )
    return len(items)
