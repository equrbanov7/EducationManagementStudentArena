"""Profil "create-category" / "category-management" bölmələri üçün
context-fragment qurucuları.

Form dəyişənləri (`create_form`, `edit_form`, `edit_item`) POST emalından gəlir;
funksiyalar onları qəbul edir və (lazım olduqda yaradıb) geri qaytarır. Davranış
köhnə inline bloklarla eynidir.
"""

from django.core.paginator import Paginator
from django.db.models import Count

from apps.accounts.views._helpers.formatting import _query_string
from apps.accounts.views.profile.post_handler import _load_managed_category
from apps.accounts.views.profile.search import _normalize_public_profile_query_value
from apps.blog.forms import CategoryManagementForm
from apps.blog.models import Category
from apps.blog.selectors import get_post_category_tree


def _parent_options(form) -> list:
    return [
        {
            "value": str(category.id),
            "label": category.localized_name,
            "attrs": "",
        }
        for category in form.fields["parent"].queryset
    ]


def build_create_category_context(create_form) -> dict:
    """create-category / category-management aktiv olduqda yaratma formu + parent
    seçimlərini qaytarır."""
    if create_form is None:
        create_form = CategoryManagementForm()
    return {
        "category_management_create_form": create_form,
        "category_management_create_parent_options": _parent_options(create_form),
        "category_management_create_selected_parent_id": create_form["parent"].value() or "",
    }


def build_category_management_context(request, *, edit_form, edit_item, page_param) -> dict:
    """category-management bölməsi: axtarış, filtrlənmiş kateqoriya ağacı,
    səhifələmə və redaktə formu."""
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
