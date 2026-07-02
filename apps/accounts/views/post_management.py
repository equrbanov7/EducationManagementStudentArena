"""Post-moderasiya view-larının shim qatı.

M2 (2026-07-02): real implementasiya apps/blog/views/moderator/
post_management.py-dədir və BlogConfig.ready()-də profile_hooks-a qeyd olunur.
Bu modul yalnız URL/fasad səthini (accounts.views.*) dəyişməz saxlayır —
accounts artıq blog-u import etmir.
"""

from apps.accounts import profile_hooks


def superadmin_post_management(request):
    return profile_hooks.post_moderation_view("superadmin_post_management")(request)


def superadmin_delete_post(request, post_id):
    return profile_hooks.post_moderation_view("superadmin_delete_post")(request, post_id)


def org_post_management(request):
    return profile_hooks.post_moderation_view("org_post_management")(request)


def org_moderate_post(request, post_id):
    return profile_hooks.post_moderation_view("org_moderate_post")(request, post_id)
