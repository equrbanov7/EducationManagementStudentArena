"""Açıq (anonim/oxucu) səth (F7 rol-skeleti, 2026-07-02)."""

from .auth import logout_view, register_view, resend_code_view, verify_code_view, verify_email_link_view
from .categories import category_detail, render_category_page
from .detail import post_detail
from .listing import list_posts, search_posts
from .pages import about, home, technology
from .subscribe import subscribe_page

__all__ = [
    "home",
    "about",
    "technology",
    "category_detail",
    "render_category_page",
    "post_detail",
    "list_posts",
    "search_posts",
    "subscribe_page",
    "register_view",
    "verify_code_view",
    "verify_email_link_view",
    "resend_code_view",
    "logout_view",
]
