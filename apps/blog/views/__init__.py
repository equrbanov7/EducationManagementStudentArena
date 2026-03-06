# blog/views/__init__.py
# Re-export all views to maintain backward compatibility with urls.py

from .auth import (
    logout_view,
    register_view,
    resend_code_view,
    verify_code_view,
    verify_email_link_view,
)
from .categories import category_detail
from .comments import post_detail
from .pages import about, contact, home, technology
from .posts import (
    create_post,
    delete_post,
    list_posts,
    post_edit_ajax,
    review_post,
    search_posts,
)
from .profile import user_profile
from .questions import create_question, my_questions, questions_i_can_see
from .subscribe import subscribe_page

__all__ = [
    # Pages
    "home",
    "about",
    "technology",
    "contact",
    # Auth
    "register_view",
    "verify_code_view",
    "verify_email_link_view",
    "resend_code_view",
    "logout_view",
    # Posts
    "create_post",
    "post_edit_ajax",
    "review_post",
    "delete_post",
    "list_posts",
    "search_posts",
    # Comments (includes post_detail)
    "post_detail",
    # Subscribe
    "subscribe_page",
    # Categories
    "category_detail",
    # Questions
    "create_question",
    "my_questions",
    "questions_i_can_see",
    # Profile
    "user_profile",
]
