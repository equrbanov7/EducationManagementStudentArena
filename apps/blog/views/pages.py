# blog/views/pages.py
import re
from urllib.parse import urlencode

from django.core.paginator import Paginator
from django.db.models import Q
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils.translation import gettext as _

from ..models import Category, Post
from ..selectors import (
    DEFAULT_TECHNOLOGY_CATEGORY_SLUG,
    filter_posts_by_category_scope,
    get_popular_topics,
    get_sidebar_categories,
)
from .categories import render_category_page

HOME_SEARCH_MAX_LENGTH = 200
_PAGE_NUMBER_RE = re.compile(r"^[0-9]+$")


def _normalize_home_search_query(raw_value, *, max_length=HOME_SEARCH_MAX_LENGTH):
    return " ".join(str(raw_value or "").split())[:max_length]


def _normalize_home_category_slug(raw_value, *, max_length=120):
    return str(raw_value or "").strip()[:max_length]


def _parse_home_page_number(raw_value):
    normalized = str(raw_value or "").strip()
    if not normalized:
        return None
    if not _PAGE_NUMBER_RE.fullmatch(normalized):
        return None
    return int(normalized)


def home(request):
    query = _normalize_home_search_query(request.GET.get("q"))
    category_slug = _normalize_home_category_slug(request.GET.get("category"))
    selected_category = None

    published_posts = Post.objects.filter(is_published=True).select_related("category", "author")
    post_list = published_posts.order_by("-created_at")

    if category_slug:
        selected_category = get_object_or_404(
            Category.objects.select_related("parent", "parent__parent"), slug=category_slug
        )
        post_list = filter_posts_by_category_scope(post_list, selected_category)

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
    extra_query_params = {}
    if query:
        extra_query_params["q"] = query
    if selected_category is not None:
        extra_query_params["category"] = selected_category.slug
    extra_query = urlencode(extra_query_params)

    categories = get_sidebar_categories(
        posts_queryset=published_posts,
        include_empty=True,
    )
    popular_topics = get_popular_topics(limit=5)

    clear_filter_query = urlencode({"q": query}) if query else ""
    clear_category_filter_url = reverse("home")
    if clear_filter_query:
        clear_category_filter_url = f"{clear_category_filter_url}?{clear_filter_query}"

    context = {
        "page_obj": page_obj,
        "categories": categories,
        "popular_topics": popular_topics,
        "active_category_slug": selected_category.slug if selected_category else "",
        "selected_category": selected_category,
        "selected_category_display_name": (
            selected_category.localized_full_name
            if selected_category and selected_category.parent_id
            else (selected_category.localized_name if selected_category else "")
        ),
        "clear_category_filter_url": clear_category_filter_url,
        "search_query": query,
        "query": query,  # Also pass as 'query' for template compatibility
        "extra_query": extra_query,
        # --- SEO ---------------------------------------------------------
        # `seo_is_home` makes the shared head partial emit the homepage-only
        # Organization / WebSite / SoftwareApplication JSON-LD that helps
        # Google understand the brand (and become eligible for sitelinks).
        "seo_is_home": True,
        "seo_title": "EMSArena – Təhsil İdarəetmə və Onlayn İmtahan Platforması",
        "seo_description": (
            "EMSArena universitetlər, məktəblər, kurs mərkəzləri və müəllimlər "
            "üçün LMS, onlayn imtahan, elektron jurnal, qiymətləndirmə və "
            "analitika platformasıdır."
        ),
    }

    return render(request, "blog/home.html", context)


def about(request):
    return render(
        request,
        "blog/about.html",
        {
            "seo_title": _("Haqqımızda – EMSArena"),
            "seo_description": _(
                "EMSArena təhsil idarəetmə, LMS və onlayn imtahan platformasıdır. "
                "Komandamız, missiyamız və platformanın imkanları haqqında məlumat."
            ),
            "seo_breadcrumbs": [
                {"name": _("Ana səhifə"), "url": request.build_absolute_uri("/")},
                {"name": _("Haqqımızda"), "url": request.build_absolute_uri()},
            ],
        },
    )


def technology(request):
    category = get_object_or_404(Category.objects.select_related("parent"), slug=DEFAULT_TECHNOLOGY_CATEGORY_SLUG)
    return render_category_page(request, category)
