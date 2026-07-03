"""Blog-un profil səhifəsinə verdiyi bölmə implementasiyaları.

M2 (2026-07-02): bu məntiq apps/accounts/views/profile/{_sections/posts.py,
_sections/category_management.py, context_builder/_stage2.py, public.py,
post_handler.py}-dən köçürülüb — accounts→blog import kənarlarını kəsir.
Qeydiyyat: BlogConfig.ready() → apps.accounts.profile_hooks. Davranış
birə-birdir (hook müqavilələri: accounts/profile_hooks.py).

Qeyd: accounts-un private sanitizer/format helper-lərinin importu qəsdəndir —
blog→accounts aşağı istiqamətli (icazəli) asılılıqdır.
"""

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Count, ProtectedError, Q
from django.http import HttpResponseBadRequest, QueryDict
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.translation import pgettext

from apps.blog.forms import CategoryManagementForm
from apps.blog.models import Category, Post
from apps.blog.selectors import (
    build_post_category_picker_options,
    filter_posts_by_category_scope,
    get_flat_category_tree,
    get_post_category_tree,
)
from apps.blog.services import (
    author_requires_post_approval,
    can_user_manage_categories,
    can_user_publish_post,
    collect_reviewable_posts,
    count_pending_reviewable_posts,
)

# ─────────────────────────── köməkçilər ───────────────────────────


def _parent_options(form) -> list:
    return [
        {
            "value": str(category.id),
            "label": category.localized_name,
            "attrs": "",
        }
        for category in form.fields["parent"].queryset
    ]


def _category_section_url(*, section="category-management", edit_category=None):
    query_params = QueryDict(mutable=True)
    query_params["section"] = section
    if edit_category:
        query_params["edit_category"] = str(edit_category)
    return f"{reverse('accounts:profile')}?{query_params.urlencode()}"


def _load_managed_category(raw_category_id):
    try:
        category_id = int(str(raw_category_id or "").strip())
    except (TypeError, ValueError):
        return None
    return Category.objects.select_related("parent").filter(pk=category_id).first()


# ─────────────────────────── posts bölməsi ───────────────────────────


def posts_section(request, *, capabilities, active_section) -> dict:
    """Bloq bölməsi üçün ``context`` açarları. Blog idarə etmə hüququ yoxdursa
    default-lar; varsa ucuz sayğac hər zaman, ağır siyahı yalnız posts/create-post
    aktiv olduqda. Davranış köhnə inline blokla eynidir."""
    result = {
        "user_posts": None,
        "posts_count": 0,
        "post_category_tree": [],
        "post_category_root_options": [],
        "post_category_subcategory_options": [],
        "post_creation_requires_approval": False,
        "posting_blocked": False,
        "posting_blocked_reason": "",
    }
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


# ──────────────── kateqoriya idarəetmə bölmələri ────────────────


def create_category_section(create_form) -> dict:
    """create-category / category-management aktiv olduqda yaratma formu + parent
    seçimlərini qaytarır."""
    if create_form is None:
        create_form = CategoryManagementForm()
    return {
        "category_management_create_form": create_form,
        "category_management_create_parent_options": _parent_options(create_form),
        "category_management_create_selected_parent_id": create_form["parent"].value() or "",
    }


def category_management_section(request, *, edit_form, edit_item, page_param) -> dict:
    """category-management bölməsi: axtarış, filtrlənmiş kateqoriya ağacı,
    səhifələmə və redaktə formu."""
    from apps.accounts.views._helpers.formatting import _query_string
    from apps.accounts.views.profile.search import _normalize_public_profile_query_value

    search_query = _normalize_public_profile_query_value(
        request.GET.get("category_search"),
        max_length=100,
    )
    normalized_search = search_query.casefold()
    managed_categories_queryset = Category.objects.annotate(direct_post_count=Count("posts")).order_by(
        "sort_order",
        "name_en",
        "name_az",
        "id",
    )
    category_tree = get_post_category_tree(category_queryset=managed_categories_queryset)
    filtered_category_tree = []

    def _category_matches_search(category):
        if not normalized_search:
            return True
        searchable_values = (
            category.name_az,
            category.name_en,
            category.name_ru,
            category.name_tr,
            category.slug,
        )
        return any(normalized_search in (value or "").casefold() for value in searchable_values)

    for root_category in category_tree:
        root_children = list(getattr(root_category, "child_categories", []))
        matching_children = [
            child_category for child_category in root_children if _category_matches_search(child_category)
        ]
        if normalized_search:
            root_matches = _category_matches_search(root_category)
            if not root_matches and not matching_children:
                continue
            visible_children = root_children if root_matches else matching_children
        else:
            visible_children = root_children

        root_category.total_child_count = len(root_children)
        root_category.can_delete = root_category.direct_post_count == 0 and not root_children
        root_category.child_categories = visible_children

        for child_category in visible_children:
            child_category.can_delete = child_category.direct_post_count == 0

        filtered_category_tree.append(root_category)

    page = Paginator(filtered_category_tree, 6).get_page(request.GET.get(page_param))

    edit_selected_parent_id = ""
    if edit_form is None:
        edit_item = _load_managed_category(request.GET.get("edit_category"))
        if edit_item is not None:
            edit_form = CategoryManagementForm(instance=edit_item)

    if edit_form is not None:
        edit_parent_options = _parent_options(edit_form)
        edit_selected_parent_id = edit_form["parent"].value() or ""
    else:
        edit_form = CategoryManagementForm()
        edit_parent_options = _parent_options(edit_form)

    return {
        "category_management_search_query": search_query,
        "category_management_total_count": len(category_tree),
        "category_management_filtered_count": len(filtered_category_tree),
        "category_management_page": page,
        "category_management_pagination_query": _query_string(
            section="category-management",
            category_search=search_query,
        ),
        "category_management_edit_form": edit_form,
        "category_management_edit_item": edit_item,
        "category_management_edit_parent_options": edit_parent_options,
        "category_management_edit_selected_parent_id": edit_selected_parent_id,
    }


# ──────────────── moderator: gözləyən post təsdiqləri ────────────────


def pending_posts_count(user) -> int:
    return count_pending_reviewable_posts(user)


def pending_posts_section(request, *, have_category_options) -> dict:
    """pending-post-approvals aktiv bölməsi üçün tam kontekst (davranış
    _stage2-dəki köhnə inline blokla eynidir)."""
    (
        items,
        search_query,
        filter_status,
        filter_group,
        available_groups,
        filter_organization,
        available_organizations,
    ) = collect_reviewable_posts(
        request.user,
        search=request.GET.get("approval_search"),
        status=request.GET.get("approval_status"),
        group_id=request.GET.get("approval_group"),
        organization_id=request.GET.get("approval_organization"),
    )
    total_count = len(items)
    count = count_pending_reviewable_posts(request.user)

    category_options = None
    if not have_category_options:
        post_category_tree = get_post_category_tree()
        root_options, subcategory_options = build_post_category_picker_options(post_category_tree)
        category_options = (post_category_tree, root_options, subcategory_options)

    page_obj = Paginator(items, 10).get_page(request.GET.get("approval_page", 1))

    extra = ["section=pending-post-approvals"]
    if search_query:
        extra.append(f"approval_search={search_query}")
    if filter_status and filter_status != "pending":
        extra.append(f"approval_status={filter_status}")
    if filter_group:
        extra.append(f"approval_group={filter_group}")
    if filter_organization:
        extra.append(f"approval_organization={filter_organization}")

    return {
        "items": items,
        "search_query": search_query,
        "filter_status": filter_status,
        "filter_group": filter_group,
        "available_groups": available_groups,
        "filter_organization": filter_organization,
        "available_organizations": available_organizations,
        "total_count": total_count,
        "count": count,
        "page_obj": page_obj,
        "pagination_query": "&".join(extra),
        "category_options": category_options,
    }


# ──────────────── public profil: dərc olunmuş postlar ────────────────


def public_posts_context(request, profile_user) -> dict:
    """Public profil səhifəsinin post siyahısı/filtr konteksti. ``response``
    dolu qayıdarsa view onu dərhal qaytarır (məs. səhv page parametri)."""
    from apps.accounts.views.profile.search import (
        _parse_public_profile_page_number,
        _sanitize_public_profile_search_query,
        _validate_public_profile_category,
    )

    published_posts = (
        Post.objects.filter(author=profile_user, is_published=True).select_related("category").order_by("-created_at")
    )

    allowed_category_slugs = set(Category.objects.values_list("slug", flat=True))
    search_query, invalid_search_query = _sanitize_public_profile_search_query(request.GET.get("q"))
    selected_category, invalid_category = _validate_public_profile_category(
        request.GET.get("category"),
        allowed_slugs=allowed_category_slugs,
    )

    user_posts_list = published_posts
    if invalid_search_query and not search_query:
        user_posts_list = user_posts_list.none()
    elif search_query:
        user_posts_list = user_posts_list.filter(
            Q(title__icontains=search_query) | Q(excerpt__icontains=search_query) | Q(content__icontains=search_query)
        )

    if invalid_category:
        user_posts_list = user_posts_list.none()
    elif selected_category:
        selected_category_obj = Category.objects.select_related("parent").filter(slug=selected_category).first()
        if selected_category_obj:
            user_posts_list = filter_posts_by_category_scope(user_posts_list, selected_category_obj)
        else:
            user_posts_list = user_posts_list.none()

    category_items = get_flat_category_tree(posts_queryset=published_posts, include_empty=False)

    raw_page_number = request.GET.get("page")
    page_number = _parse_public_profile_page_number(raw_page_number)
    if raw_page_number not in (None, "") and page_number is None:
        return {"response": HttpResponseBadRequest("Invalid page parameter."), "context": {}}

    paginator = Paginator(user_posts_list, 6)
    posts = paginator.get_page(page_number)

    query_params = QueryDict(mutable=True)
    if search_query:
        query_params["q"] = search_query
    if selected_category:
        query_params["category"] = selected_category

    return {
        "response": None,
        "context": {
            "search_query": search_query,
            "selected_category": selected_category,
            "extra_query": query_params.urlencode(),
            "category_items": category_items,
            "published_posts_count": published_posts.count(),
            "category_count": len(category_items),
            "posts": posts,
        },
    }


# ──────────────── profil POST: kateqoriya CRUD əməliyyatları ────────────────

_CATEGORY_FORMS = {"category-create", "category-management-save", "category-management-delete"}


def category_post_actions(request, *, submitted_form, allowed_sections):
    """Profil POST axınında kateqoriya CRUD budağı. Bu POST kateqoriyalara aid
    deyilsə ``None`` (post_handler öz fallback-ına düşür). Davranış köhnə
    inline elif-budağı ilə eynidir."""
    if submitted_form not in _CATEGORY_FORMS:
        return None

    def _result(
        *, response=None, active_section="category-management", create_form=None, edit_form=None, edit_item=None
    ):
        return {
            "response": response,
            "active_section": active_section,
            "create_form": create_form,
            "edit_form": edit_form,
            "edit_item": edit_item,
        }

    if not {"create-category", "category-management"} & set(allowed_sections) or not can_user_manage_categories(
        request.user
    ):
        messages.error(request, pgettext("blog.category.message", "Bu bölməni yalnız SuperAdmin idarə edə bilər."))
        return _result(response=redirect(f"{reverse('accounts:profile')}?section=profile-info"))

    if submitted_form == "category-management-delete":
        category_to_delete = _load_managed_category(request.POST.get("category_id"))
        if category_to_delete is None:
            messages.error(request, pgettext("blog.category.message", "Silinəcək kateqoriya tapılmadı."))
            return _result(response=redirect(_category_section_url(section="category-management")))

        deleted_category_name = category_to_delete.localized_full_name
        try:
            category_to_delete.delete()
        except ProtectedError:
            messages.error(
                request,
                pgettext(
                    "blog.category.message",
                    "Bu kateqoriyanı silmək olmur. Ona bağlı alt kateqoriya və ya post mövcuddur.",
                ),
            )
        else:
            messages.success(
                request,
                pgettext("blog.category.message", '"{name}" uğurla silindi.').format(name=deleted_category_name),
            )
        return _result(response=redirect(_category_section_url(section="category-management")))

    if submitted_form == "category-create":
        bound_form = CategoryManagementForm(request.POST)

        if bound_form.is_valid():
            saved_category = bound_form.save()
            # Ayrı-ayrı tam mesajlar (söz sırası dillərə görə dəyişdiyi üçün
            # "{label} ..." kompozisiyasından qaçılır).
            if saved_category.parent_id:
                created_msg = pgettext("blog.category.message", 'Alt kateqoriya "{name}" uğurla yaradıldı.')
            else:
                created_msg = pgettext("blog.category.message", 'Kateqoriya "{name}" uğurla yaradıldı.')
            messages.success(request, created_msg.format(name=saved_category.localized_full_name))
            return _result(response=redirect(_category_section_url(section="create-category")))

        messages.error(
            request,
            pgettext("blog.category.message", "Kateqoriya yaradılmadı. Zəhmət olmasa xətaları düzəldin."),
        )
        return _result(active_section="create-category", create_form=bound_form)

    # category-management-save
    submitted_category_id = request.POST.get("category_id")
    edit_item = _load_managed_category(submitted_category_id)
    if submitted_category_id and edit_item is None:
        messages.error(request, pgettext("blog.category.message", "Redaktə ediləcək kateqoriya tapılmadı."))
        return _result(response=redirect(_category_section_url(section="category-management")))

    bound_form = CategoryManagementForm(request.POST, instance=edit_item)

    if bound_form.is_valid():
        saved_category = bound_form.save()
        if saved_category.parent_id:
            updated_msg = pgettext("blog.category.message", 'Alt kateqoriya "{name}" uğurla yeniləndi.')
        else:
            updated_msg = pgettext("blog.category.message", 'Kateqoriya "{name}" uğurla yeniləndi.')
        messages.success(request, updated_msg.format(name=saved_category.localized_full_name))
        return _result(response=redirect(_category_section_url(section="category-management")))

    messages.error(
        request,
        pgettext("blog.category.message", "Kateqoriya yadda saxlanmadı. Zəhmət olmasa xətaları düzəldin."),
    )
    return _result(active_section="category-management", edit_form=bound_form, edit_item=edit_item)


def _post_moderation_views():
    """Post-moderasiya view-ları (lazy — view moduldan dövri import olmasın)."""
    from apps.blog.views.moderator.post_management import (
        org_moderate_post,
        org_post_management,
        superadmin_delete_post,
        superadmin_post_management,
    )

    return {
        "superadmin_post_management": superadmin_post_management,
        "superadmin_delete_post": superadmin_delete_post,
        "org_post_management": org_post_management,
        "org_moderate_post": org_moderate_post,
    }


def register_all():
    """BlogConfig.ready() → accounts profile_hooks qeydiyyatı."""
    from apps.accounts import profile_hooks

    profile_hooks.register("posts_section", posts_section)
    profile_hooks.register("create_category_section", create_category_section)
    profile_hooks.register("category_management_section", category_management_section)
    profile_hooks.register("pending_posts_count", pending_posts_count)
    profile_hooks.register("pending_posts_section", pending_posts_section)
    profile_hooks.register("public_posts_context", public_posts_context)
    profile_hooks.register("category_post_actions", category_post_actions)
    profile_hooks.register("post_moderation_views", _post_moderation_views)
