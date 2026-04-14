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
from apps.organizations.models import Membership
from core.constants import ROLE_LEVEL_TEACHER
from core.rls import bypass_rls

from .models import Category, Post

APPROVAL_STATUS_FILTERS = {
    "all",
    Post.ApprovalStatus.PENDING,
    Post.ApprovalStatus.NEEDS_CHANGES,
    Post.ApprovalStatus.APPROVED,
}


def _user_has_active_org_membership(user):
    """Return True if *user* has at least one active Membership in an active Organization."""
    with bypass_rls():
        return Membership.objects.filter(
            user=user,
            is_active=True,
            organization__status="active",
        ).exists()


def _user_has_any_membership(user):
    """Return True if *user* has any Membership record (active or not)."""
    with bypass_rls():
        return Membership.objects.filter(user=user).exists()


def can_user_publish_post(user):
    """Determine whether *user* is allowed to create/publish a post.

    Returns ``(can_publish, reason)`` where *can_publish* is a bool and
    *reason* is a human-readable explanation when publishing is blocked.
    """
    if not user or not getattr(user, "is_authenticated", False):
        return False, "İstifadəçi daxil olmayıb."

    if is_superadmin_user(user):
        return True, ""

    if _user_has_any_membership(user):
        if _user_has_active_org_membership(user):
            return True, ""
        return (
            False,
            "Təşkilatınız tərəfindən üzvlüyünüz hələ təsdiqlənməyib.",
        )

    # No membership at all – allowed but will require superadmin review.
    return True, ""


def author_requires_post_approval(author):
    if not author or not getattr(author, "is_authenticated", False):
        return False
    if is_superadmin_user(author):
        return False
    if get_user_role_level(author) >= ROLE_LEVEL_TEACHER:
        return False
    # Students / lead-students always require approval (original logic).
    if user_has_any_role(author, {ProfileRole.STUDENT, ProfileRole.LEAD_STUDENT}):
        return True
    # Users with no active org membership require superadmin review.
    if not _user_has_active_org_membership(author):
        return True
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

    reviewer_level = get_user_role_level(user)

    # Org admin / org owner can manage any post that requires approval.
    if reviewer_level >= ProfileRole.LEVELS.get(ProfileRole.ORG_ADMIN, 80):
        return True

    author_level = get_user_role_level(post.author)
    if reviewer_level < ROLE_LEVEL_TEACHER or reviewer_level <= author_level:
        return False

    return StudentGroup.objects.filter(students=post.author).filter(Q(teacher=user) | Q(teachers=user)).exists()


def normalize_approval_status(value, *, include_all=False, default=Post.ApprovalStatus.PENDING):
    normalized = (value or "").strip().lower()
    if include_all and normalized == "all":
        return "all"
    if normalized in APPROVAL_STATUS_FILTERS:
        return normalized
    return default


def _build_group_scope_for_reviewer(reviewer):
    if is_superadmin_user(reviewer):
        return StudentGroup.objects.filter(students__posts__requires_approval=True).distinct()
    reviewer_level = get_user_role_level(reviewer)
    if reviewer_level >= ProfileRole.LEVELS.get(ProfileRole.ORG_ADMIN, 80):
        return StudentGroup.objects.filter(students__posts__requires_approval=True).distinct()
    return StudentGroup.objects.filter(Q(teacher=reviewer) | Q(teachers=reviewer)).distinct()


def collect_reviewable_posts(reviewer, *, search="", status="pending", group_id=""):
    normalized_search = (search or "").strip()
    normalized_status = normalize_approval_status(status, include_all=True, default=Post.ApprovalStatus.PENDING)
    selected_group = str(group_id or "").strip()

    reviewer_level = get_user_role_level(reviewer)
    superadmin = is_superadmin_user(reviewer)
    # Org admin / org owner see all posts just like a superadmin.
    is_elevated = superadmin or reviewer_level >= ProfileRole.LEVELS.get(ProfileRole.ORG_ADMIN, 80)
    if not is_elevated and reviewer_level < ROLE_LEVEL_TEACHER:
        return [], normalized_search, normalized_status, "", []

    groups_scope = _build_group_scope_for_reviewer(reviewer)
    available_groups = list(groups_scope.order_by("name").values("id", "name"))
    available_group_ids = {str(group["id"]) for group in available_groups}

    if selected_group and selected_group not in available_group_ids:
        selected_group = ""

    posts_qs = (
        Post.objects.filter(requires_approval=True)
        .select_related("author", "author__profile", "category", "approved_by")
        .order_by("-approval_requested_at", "-updated_at", "-created_at")
    )

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

    if is_elevated:
        if selected_group:
            posts_qs = posts_qs.filter(author__student_groups_as_student__id=selected_group)
    else:
        posts_qs = posts_qs.filter(author__student_groups_as_student__in=groups_scope).distinct()
        if selected_group:
            posts_qs = posts_qs.filter(author__student_groups_as_student__id=selected_group)

    posts = list(posts_qs)
    if not is_elevated:
        posts = [post for post in posts if reviewer_level > get_user_role_level(post.author)]

    author_ids = {post.author_id for post in posts}
    author_group_names = defaultdict(list)
    if author_ids:
        group_pairs_qs = StudentGroup.objects.filter(students__id__in=author_ids)
        if not is_elevated:
            group_pairs_qs = group_pairs_qs.filter(Q(teacher=reviewer) | Q(teachers=reviewer))
        if selected_group:
            group_pairs_qs = group_pairs_qs.filter(id=selected_group)

        for student_id, group_name in group_pairs_qs.values_list("students__id", "name"):
            if not student_id or not group_name:
                continue
            if group_name not in author_group_names[student_id]:
                author_group_names[student_id].append(group_name)

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
                "status_label": status_label_map.get(post.approval_status, post.approval_status),
                "status_class": status_class_map.get(post.approval_status, "status-draft"),
            }
        )

    return items, normalized_search, normalized_status, selected_group, available_groups


def count_pending_reviewable_posts(reviewer):
    items, _, _, _, _ = collect_reviewable_posts(
        reviewer,
        status=Post.ApprovalStatus.PENDING,
    )
    return len(items)
