"""
Database query layer for blog app.
This module contains selector functions that handle database queries.
"""

import logging
from collections import defaultdict

from django.core.cache import cache
from django.db.models import Count

from .models import Category, Post

logger = logging.getLogger(__name__)

DEFAULT_TECHNOLOGY_CATEGORY_SLUG = "technology"

# ─────────────────────────────────────────────────────────────────────────────
# Cache TTLs (seconds)
# ─────────────────────────────────────────────────────────────────────────────
_NAVBAR_CATEGORIES_TTL = 300  # 5 min — low mutation rate
_SIDEBAR_CATEGORIES_TTL = 120  # 2 min — invalidated on post publish
_POPULAR_TOPICS_TTL = 300  # 5 min — low mutation rate

_CACHE_KEY_NAVBAR = "emsarena:blog:navbar_categories"
_CACHE_KEY_SIDEBAR = "emsarena:blog:sidebar_categories"
_CACHE_KEY_POPULAR_TOPICS = "emsarena:blog:popular_topics"


def _safe_cache_get(key):
    try:
        return cache.get(key)
    except Exception:
        logger.warning("Redis unavailable; cache lookup failed for key %s", key)
        return None


def _static_category_sort_key(category):
    return (
        0 if category.is_default else 1,
        category.sort_order,
        category.localized_name.lower(),
        category.id,
    )


def _category_post_count_sort_key(category):
    return (
        -getattr(category, "post_count", 0),
        -getattr(category, "direct_post_count", 0),
        0 if category.is_default else 1,
        category.sort_order,
        category.localized_name.lower(),
        category.id,
    )


def _load_categories(category_queryset=None):
    queryset = category_queryset if category_queryset is not None else Category.objects.all()
    categories = list(queryset.select_related("parent"))
    return sorted(categories, key=_static_category_sort_key)


def _build_children_map(categories):
    children_by_parent = defaultdict(list)
    for category in categories:
        children_by_parent[category.parent_id].append(category)
    return children_by_parent


def _build_direct_post_count_map(posts_queryset):
    queryset = (posts_queryset if posts_queryset is not None else Post.objects.filter(is_published=True)).exclude(
        category__isnull=True
    )
    return {row["category_id"]: row["total"] for row in queryset.values("category_id").annotate(total=Count("id"))}


def get_category_subtree_ids(category, *, category_queryset=None):
    categories = _load_categories(category_queryset)
    children_by_parent = _build_children_map(categories)

    subtree_ids = []
    pending = [category.id]

    while pending:
        current_id = pending.pop()
        subtree_ids.append(current_id)
        pending.extend(child.id for child in children_by_parent.get(current_id, []))

    return subtree_ids


def filter_posts_by_category_scope(posts_queryset, category, *, category_queryset=None):
    subtree_ids = get_category_subtree_ids(category, category_queryset=category_queryset)
    return posts_queryset.filter(category_id__in=subtree_ids)


def get_flat_category_tree(
    *,
    posts_queryset=None,
    include_empty=False,
    category_queryset=None,
    root_category=None,
    sort_by_post_count=False,
):
    categories = _load_categories(category_queryset)
    if not categories:
        return []

    children_by_parent = _build_children_map(categories)
    direct_post_counts = _build_direct_post_count_map(posts_queryset)

    def populate_post_counts(node):
        direct_post_count = direct_post_counts.get(node.id, 0)
        total_post_count = direct_post_count

        node.child_categories = list(children_by_parent.get(node.id, []))
        node.direct_post_count = direct_post_count

        for child in node.child_categories:
            total_post_count += populate_post_counts(child)

        node.post_count = total_post_count
        if sort_by_post_count:
            node.child_categories.sort(key=_category_post_count_sort_key)
        return total_post_count

    flattened_categories = []

    def flatten(node, depth, root_category):
        if not include_empty and node.post_count <= 0:
            return

        node.tree_depth = depth
        node.display_name = f'{"-- " * depth}{node.localized_name}' if depth else node.localized_name
        node.sidebar_name = node.localized_name
        node.root_category = root_category
        flattened_categories.append(node)

        for child in node.child_categories:
            flatten(child, depth + 1, root_category)

    root_categories = children_by_parent.get(None, [])
    if root_category is not None:
        root_category_id = getattr(root_category, "pk", root_category)
        root_categories = [category for category in root_categories if category.pk == root_category_id]

    for current_root in root_categories:
        populate_post_counts(current_root)
        current_root.root_category = current_root

    if sort_by_post_count:
        root_categories = sorted(root_categories, key=_category_post_count_sort_key)

    for current_root in root_categories:
        flatten(current_root, 0, current_root)

    return flattened_categories


def get_sidebar_categories(*, posts_queryset=None, active_category=None, include_empty=False):
    root_category = active_category.get_root() if active_category else None

    # Use cached result only for the common global call (no active category filter)
    use_cache = active_category is None and posts_queryset is None
    if use_cache:
        cache_key = f"{_CACHE_KEY_SIDEBAR}:{include_empty}"
        cached = _safe_cache_get(cache_key)
        if cached is not None:
            return cached

    categories = get_flat_category_tree(
        posts_queryset=posts_queryset,
        include_empty=include_empty,
        root_category=root_category,
        sort_by_post_count=True,
    )

    if active_category is None:
        result = categories
    else:
        nested_categories = [category for category in categories if category.tree_depth > 0]
        if not nested_categories:
            result = categories
        else:
            for category in nested_categories:
                category.tree_depth = max(category.tree_depth - 1, 0)
            result = nested_categories

    if use_cache:
        try:
            cache.set(cache_key, result, timeout=_SIDEBAR_CATEGORIES_TTL)
        except Exception:
            logger.warning("Redis unavailable; sidebar categories cache not populated")

    return result


def get_post_category_tree(*, category_queryset=None):
    categories = _load_categories(category_queryset)
    if not categories:
        return []

    children_by_parent = _build_children_map(categories)
    root_categories = list(children_by_parent.get(None, []))

    for root_category in root_categories:
        root_category.child_categories = list(children_by_parent.get(root_category.id, []))

    return root_categories


def build_post_category_picker_options(category_tree):
    root_options = []
    subcategory_options = []

    for root_category in category_tree:
        root_options.append(
            {
                "value": str(root_category.id),
                "label": root_category.localized_name,
                "attrs": "",
            }
        )

        for child_category in getattr(root_category, "child_categories", []):
            subcategory_options.append(
                {
                    "value": str(child_category.id),
                    "label": child_category.localized_name,
                    "attrs": f'data-parent-id="{root_category.id}"',
                }
            )

    return root_options, subcategory_options


def get_navbar_categories():
    cached = _safe_cache_get(_CACHE_KEY_NAVBAR)
    if cached is not None:
        return cached
    navbar_categories = get_flat_category_tree(include_empty=True)
    result = [category for category in navbar_categories if category.tree_depth == 0 and category.show_in_navbar]
    try:
        cache.set(_CACHE_KEY_NAVBAR, result, timeout=_NAVBAR_CATEGORIES_TTL)
    except Exception:
        logger.warning("Redis unavailable; navbar categories cache not populated")
    return result


def invalidate_blog_listing_cache() -> None:
    """Remove all cached blog listing data (categories, popular topics).

    Call this whenever posts or categories are added, modified, or deleted.
    """
    try:
        keys_to_delete = [
            _CACHE_KEY_NAVBAR,
            f"{_CACHE_KEY_SIDEBAR}:True",
            f"{_CACHE_KEY_SIDEBAR}:False",
            f"{_CACHE_KEY_POPULAR_TOPICS}:5",
            f"{_CACHE_KEY_POPULAR_TOPICS}:10",
        ]
        cache.delete_many(keys_to_delete)
    except Exception:
        logger.warning("Redis unavailable; could not invalidate blog listing cache")


def get_popular_topics(*, active_category=None, limit=5):
    root_category = active_category.get_root() if active_category else None

    # Use cached result only for the common global call (no category filter)
    if active_category is None:
        cache_key = f"{_CACHE_KEY_POPULAR_TOPICS}:{limit}"
        cached = _safe_cache_get(cache_key)
        if cached is not None:
            return cached

    categories = get_flat_category_tree(
        include_empty=True,
        root_category=root_category,
        sort_by_post_count=True,
    )

    if not categories:
        result = []
    elif root_category is not None:
        child_topics = [category for category in categories if category.tree_depth == 1]
        result = child_topics[:limit] if child_topics else []
    else:
        root_topics = [category for category in categories if category.tree_depth == 0]
        result = root_topics[:limit]

    if active_category is None:
        try:
            cache.set(cache_key, result, timeout=_POPULAR_TOPICS_TTL)
        except Exception:
            logger.warning("Redis unavailable; popular topics cache not populated")

    return result
