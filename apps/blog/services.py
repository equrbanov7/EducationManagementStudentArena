"""
Business logic layer for blog app.
This module contains service functions that encapsulate business operations.
"""

from collections import defaultdict

from django.db.models import Q

from apps.accounts.models import ProfileRole
from apps.accounts.policies import get_user_role_level, is_superadmin_user, user_has_any_role
from apps.exams.models import StudentGroup
from core.constants import ROLE_LEVEL_TEACHER

from .models import Post

APPROVAL_STATUS_FILTERS = {
    "all",
    Post.ApprovalStatus.PENDING,
    Post.ApprovalStatus.NEEDS_CHANGES,
    Post.ApprovalStatus.APPROVED,
}

def author_requires_post_approval(author):
    if not author or not getattr(author, "is_authenticated", False):
        return False
    if get_user_role_level(author) >= ROLE_LEVEL_TEACHER:
        return False
    return user_has_any_role(author, {ProfileRole.STUDENT, ProfileRole.LEAD_STUDENT})


def can_user_create_post_category(user):
    if not user or not getattr(user, "is_authenticated", False):
        return False
    return get_user_role_level(user) >= ROLE_LEVEL_TEACHER


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
    return StudentGroup.objects.filter(Q(teacher=reviewer) | Q(teachers=reviewer)).distinct()


def collect_reviewable_posts(reviewer, *, search="", status="pending", group_id=""):
    normalized_search = (search or "").strip()
    normalized_status = normalize_approval_status(status, include_all=True, default=Post.ApprovalStatus.PENDING)
    selected_group = str(group_id or "").strip()

    reviewer_level = get_user_role_level(reviewer)
    superadmin = is_superadmin_user(reviewer)
    if not superadmin and reviewer_level < ROLE_LEVEL_TEACHER:
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

    if superadmin:
        if selected_group:
            posts_qs = posts_qs.filter(author__student_groups_as_student__id=selected_group)
    else:
        posts_qs = posts_qs.filter(author__student_groups_as_student__in=groups_scope).distinct()
        if selected_group:
            posts_qs = posts_qs.filter(author__student_groups_as_student__id=selected_group)

    posts = list(posts_qs)
    if not superadmin:
        posts = [post for post in posts if reviewer_level > get_user_role_level(post.author)]

    author_ids = {post.author_id for post in posts}
    author_group_names = defaultdict(list)
    if author_ids:
        group_pairs_qs = StudentGroup.objects.filter(students__id__in=author_ids)
        if not superadmin:
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
