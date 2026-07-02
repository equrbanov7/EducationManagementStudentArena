# blog/views/categories.py
import re

from django.core.paginator import Paginator
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, render
from django.urls import reverse

from ...models import Category, Post
from ...selectors import filter_posts_by_category_scope, get_popular_topics, get_sidebar_categories

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
    post_list = filter_posts_by_category_scope(
        published_posts,
        category,
    ).order_by("-created_at")
    raw_page_number = request.GET.get("page")
    page_number = _parse_category_page_number(raw_page_number)
    if raw_page_number not in (None, "") and page_number is None:
        return HttpResponseBadRequest("Invalid page parameter.")
    page_obj = Paginator(post_list, 6).get_page(page_number)

    categories = get_sidebar_categories(
        posts_queryset=published_posts,
        active_category=category,
        include_empty=True,
    )
    popular_topics = get_popular_topics(active_category=category, limit=5)

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


def category_detail(request, slug):
    category = get_object_or_404(Category.objects.select_related("parent"), slug=slug)
    return render_category_page(request, category)
