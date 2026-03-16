# blog/views/__init__.py
# Re-export all views to maintain backward compatibility with urls.py

from .categories import category_detail
from .comments import post_detail
from .pages import about, home, technology
from .posts import (
    create_post,
    delete_post,
    list_posts,
    post_edit_ajax,
    review_post,
    search_posts,
)

from .questions import create_question, my_questions, questions_i_can_see
from .subscribe import subscribe_page

__all__ = [
    # Pages
    "home",
    "about",
    "technology",
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
  
]
