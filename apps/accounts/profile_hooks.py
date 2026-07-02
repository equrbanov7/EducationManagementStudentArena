"""Profil səhifəsinə kontent-modul kontribusiyaları üçün hook registry.

M2 (2026-07-02, AGENTS §5 pattern 3): accounts profil view-ları əvvəllər blog
modellərini/servislərini birbaşa import edirdi — accounts↔blog dövri
asılılığı. İndi blog öz bölmə implementasiyalarını `BlogConfig.ready()`-də
bura qeyd edir (bax apps/blog/profile_sections.py); accounts blog-u tanımır.

Default-lar NEYTRALDIR: blog qeydiyyatı olmadan profil "boş bölmə" davranışı
göstərir (açarlar mövcuddur, siyahılar boş, formalar None).
"""


def _default_posts_section(request, *, capabilities, active_section):
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


def _default_create_category_section(create_form):
    return {
        "category_management_create_form": create_form,
        "category_management_create_parent_options": [],
        "category_management_create_selected_parent_id": "",
    }


def _default_category_management_section(request, *, edit_form, edit_item, page_param):
    return {
        "category_management_search_query": "",
        "category_management_total_count": 0,
        "category_management_filtered_count": 0,
        "category_management_page": None,
        "category_management_pagination_query": "",
        "category_management_edit_form": edit_form,
        "category_management_edit_item": edit_item,
        "category_management_edit_parent_options": [],
        "category_management_edit_selected_parent_id": "",
    }


def _default_pending_posts_count(user):
    return 0


def _default_pending_posts_section(request, *, have_category_options):
    return {
        "items": [],
        "search_query": "",
        "filter_status": "pending",
        "filter_group": "",
        "available_groups": [],
        "filter_organization": "",
        "available_organizations": [],
        "total_count": 0,
        "count": 0,
        "page_obj": None,
        "pagination_query": "",
        "category_options": None,
    }


def _default_public_posts_context(request, profile_user):
    return {
        "response": None,
        "context": {
            "search_query": "",
            "selected_category": "",
            "extra_query": "",
            "category_items": [],
            "published_posts_count": 0,
            "category_count": 0,
            "posts": None,
        },
    }


def _default_category_post_actions(request, *, submitted_form, allowed_sections):
    # None = "bu POST mənlik deyil" — post_handler öz fallback axınına düşür.
    return None


def _default_post_moderation_views():
    return {}


_HOOKS = {
    "posts_section": _default_posts_section,
    "create_category_section": _default_create_category_section,
    "category_management_section": _default_category_management_section,
    "pending_posts_count": _default_pending_posts_count,
    "pending_posts_section": _default_pending_posts_section,
    "public_posts_context": _default_public_posts_context,
    "category_post_actions": _default_category_post_actions,
    "post_moderation_views": _default_post_moderation_views,
}


def register(name, fn):
    """Hook implementasiyasını qeyd et (naməlum ad üçün KeyError)."""
    if name not in _HOOKS:
        raise KeyError(f"Naməlum profile hook: {name!r}")
    _HOOKS[name] = fn


def posts_section(request, *, capabilities, active_section):
    return _HOOKS["posts_section"](request, capabilities=capabilities, active_section=active_section)


def create_category_section(create_form):
    return _HOOKS["create_category_section"](create_form)


def category_management_section(request, *, edit_form, edit_item, page_param):
    return _HOOKS["category_management_section"](
        request, edit_form=edit_form, edit_item=edit_item, page_param=page_param
    )


def pending_posts_count(user):
    return _HOOKS["pending_posts_count"](user)


def pending_posts_section(request, *, have_category_options):
    return _HOOKS["pending_posts_section"](request, have_category_options=have_category_options)


def public_posts_context(request, profile_user):
    return _HOOKS["public_posts_context"](request, profile_user)


def category_post_actions(request, *, submitted_form, allowed_sections):
    return _HOOKS["category_post_actions"](request, submitted_form=submitted_form, allowed_sections=allowed_sections)


def post_moderation_view(name):
    """Qeydli post-moderasiya view-ını qaytarır; yoxdursa 404 verən stub."""
    view = _HOOKS["post_moderation_views"]().get(name)
    if view is not None:
        return view

    def _not_available(request, *args, **kwargs):
        from django.http import Http404

        raise Http404

    return _not_available
