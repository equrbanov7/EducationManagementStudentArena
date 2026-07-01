"""Profil "posts" / "create-post" bölmələri üçün context-fragment qurucusu."""

from django.core.paginator import Paginator

from apps.blog.models import Post
from apps.blog.selectors import build_post_category_picker_options, get_post_category_tree
from apps.blog.services import author_requires_post_approval, can_user_publish_post


def _defaults() -> dict:
    return {
        "user_posts": None,
        "posts_count": 0,
        "post_category_tree": [],
        "post_category_root_options": [],
        "post_category_subcategory_options": [],
        "post_creation_requires_approval": False,
        "posting_blocked": False,
        "posting_blocked_reason": "",
    }


def build_posts_context(request, *, capabilities, active_section) -> dict:
    """Bloq bölməsi üçün ``context`` açarları. Blog idarə etmə hüququ yoxdursa
    default-lar; varsa ucuz sayğac hər zaman, ağır siyahı yalnız posts/create-post
    aktiv olduqda. Davranış köhnə inline blokla eynidir."""
    result = _defaults()
    if not capabilities["can_manage_blog"]:
        return result

    user_posts_qs = (
        Post.objects.filter(author=request.user)
        .select_related("category")
        .prefetch_related("approval_logs")
        .order_by("-created_at")
    )
    # Sidebar/profile-info üçün ucuz sayğac hər zaman.
    result["posts_count"] = user_posts_qs.count()
    if active_section in {"posts", "create-post"}:
        result["user_posts"] = Paginator(user_posts_qs, 6).get_page(request.GET.get("page"))
        post_category_tree = get_post_category_tree()
        result["post_category_tree"] = post_category_tree
        root_options, subcategory_options = build_post_category_picker_options(post_category_tree)
        result["post_category_root_options"] = root_options
        result["post_category_subcategory_options"] = subcategory_options
        result["post_creation_requires_approval"] = author_requires_post_approval(request.user)
        can_publish, blocked_reason = can_user_publish_post(request.user)
        result["posting_blocked"] = not can_publish
        result["posting_blocked_reason"] = blocked_reason
    return result
