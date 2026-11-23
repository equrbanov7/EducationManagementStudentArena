# blog/views/categories.py
import re

from django.core.paginator import Paginator
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, render
from django.urls import reverse

from ...models import Category, Post
from ...selectors import category_page_navigation
from ..shared.module_gate import posts_module_required

_PAGE_NUMBER_RE = re.compile(r"^[0-9]+$")


def _parse_category_page_number(raw_value):
    normalized = str(raw_value or "").strip()
    if not normalized:
        return None
    if not _PAGE_NUMBER_RE.fullmatch(normalized):
        return None
    return int(normalized)


def render_category_page(request, category, *, template_name="blog/category_detail.html"):
    published_posts = Post.objects.filter(is_published=True).select_related("category", "author")
    root_category = category.get_root()
    parent_category = category.parent
    raw_page_number = request.GET.get("page")
    page_number = _parse_category_page_number(raw_page_number)
    if raw_page_number not in (None, "") and page_number is None:
        return HttpResponseBadRequest("Invalid page parameter.")
    subtree_ids, categories, popular_topics = category_page_navigation(category, root_category, published_posts)
    post_list = published_posts.filter(category_id__in=subtree_ids).order_by("-created_at")
    page_obj = Paginator(post_list, 6).get_page(page_number)

    context = {
        "category": category,
        "root_category": root_category,
        "category_ancestors": category.get_ancestors(include_self=False),
        "page_obj": page_obj,
        "categories": categories,
        "popular_topics": popular_topics,
        "active_category_slug": category.slug,
        "back_link_url": (
            reverse("category_detail", args=[parent_category.slug]) if parent_category else reverse("home")
        ),
    }

    return render(request, template_name, context)


@posts_module_required
def category_detail(request, slug):
    category = get_object_or_404(Category.objects.select_related("parent"), slug=slug)
    return render_category_page(request, category)
