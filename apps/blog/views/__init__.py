"""
blog/views — FASAD (F7 rol-skeleti, 2026-07-02, AGENTS §6).

Fayllar views/{public,author,moderator}/ rol paketlərinə bölünüb
(posts.py üç rola ayrılıb). urls.py üçün import səthi dəyişmir (WP9a 2026-10-10:
köhnə ``legacy_urls.py`` ləqəbləri və «Suallar» səhifələri silindi).
"""

from .author import create_post, post_edit_ajax
from .moderator import delete_post, review_post, teacher_moderate_post
from .public import (
    about,
    category_detail,
    home,
    list_posts,
    post_detail,
    search_posts,
    subscribe_page,
    technology,
)

__all__ = [
    "home",
    "about",
    "technology",
    "create_post",
    "post_edit_ajax",
    "review_post",
    "delete_post",
    "teacher_moderate_post",
    "list_posts",
    "search_posts",
    "post_detail",
    "subscribe_page",
    "category_detail",
]
