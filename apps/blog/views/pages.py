# blog/views/pages.py
import re
from urllib.parse import urlencode

from django.core.paginator import Paginator
from django.db.models import Q
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, render

from ..models import Category, Post
from ..selectors import DEFAULT_TECHNOLOGY_CATEGORY_SLUG, get_popular_topics, get_sidebar_categories
from .categories import render_category_page

HOME_SEARCH_MAX_LENGTH = 200
_PAGE_NUMBER_RE = re.compile(r"^[0-9]+$")


def _normalize_home_search_query(raw_value, *, max_length=HOME_SEARCH_MAX_LENGTH):
    return " ".join(str(raw_value or "").split())[:max_length]


def _parse_home_page_number(raw_value):
    normalized = str(raw_value or "").strip()
    if not normalized:
        return None
    if not _PAGE_NUMBER_RE.fullmatch(normalized):
        return None
    return int(normalized)


def home(request):
    query = _normalize_home_search_query(request.GET.get("q"))
    post_list = Post.objects.filter(is_published=True).select_related("category", "author").order_by("-created_at")

    if query:
        post_list = post_list.filter(
            Q(title__icontains=query) | Q(excerpt__icontains=query) | Q(content__icontains=query)
        ).distinct()

    raw_page_number = request.GET.get("page")
    page_number = _parse_home_page_number(raw_page_number)
    if raw_page_number not in (None, "") and page_number is None:
        return HttpResponseBadRequest("Invalid page parameter.")

    paginator = Paginator(post_list, 6)
    page_obj = paginator.get_page(page_number)
    extra_query = urlencode({"q": query}) if query else ""

    categories = get_sidebar_categories(
        posts_queryset=Post.objects.filter(is_published=True),
        include_empty=True,
    )
    popular_topics = get_popular_topics(limit=5)

    context = {
        "page_obj": page_obj,
        "categories": categories,
        "popular_topics": popular_topics,
        "active_category_slug": "",
        "search_query": query,
        "query": query,  # Also pass as 'query' for template compatibility
        "extra_query": extra_query,
    }

    return render(request, "blog/home.html", context)


def about(request):
    return render(request, "blog/about.html")


def technology(request):
    category = get_object_or_404(Category.objects.select_related("parent"), slug=DEFAULT_TECHNOLOGY_CATEGORY_SLUG)
    return render_category_page(request, category)
