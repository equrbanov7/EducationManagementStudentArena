"""Blog — rollar-arası icazə helper-i (F7 rol-skeleti, 2026-07-02)."""


def _can_manage_blog_content(user):
    """
    Any authenticated user can create and manage their own posts.
    """
    return getattr(user, "is_authenticated", False)
