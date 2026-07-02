"""
blog/views — FASAD (F7 rol-skeleti, 2026-07-02, AGENTS §6).

Fayllar views/{public,author,moderator}/ rol paketlərinə bölünüb
(posts.py üç rola ayrılıb). urls.py/legacy_urls.py üçün import səthi dəyişmir.
"""

from .author import create_post, create_question, my_questions, post_edit_ajax, questions_i_can_see
from .moderator import delete_post, review_post, teacher_moderate_post
from .public import (
    about,
    category_detail,
    home,
    list_posts,
    logout_view,
    post_detail,
    register_view,
    resend_code_view,
    search_posts,
    subscribe_page,
    technology,
    verify_code_view,
    verify_email_link_view,
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
    "create_question",
    "my_questions",
    "questions_i_can_see",
    "register_view",
    "verify_code_view",
    "verify_email_link_view",
    "resend_code_view",
    "logout_view",
]
