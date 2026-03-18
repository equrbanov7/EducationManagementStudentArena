# blog/views/pages.py

from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.shortcuts import render

from ..models import Category, Post
from ..selectors import DEFAULT_TECHNOLOGY_CATEGORY_SLUG, get_popular_topics, get_sidebar_categories
from .categories import render_category_page


def home(request):

    query = request.GET.get("q", "").strip()
    post_list = Post.objects.filter(is_published=True).select_related("category", "author").order_by("-created_at")

    if query:
        post_list = post_list.filter(
            Q(title__icontains=query) | Q(excerpt__icontains=query) | Q(content__icontains=query)
        ).distinct()

    paginator = Paginator(post_list, 6)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

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
    }

    return render(request, "blog/home.html", context)


def about(request):
    return render(request, "blog/about.html")


def technology(request):
    category = get_object_or_404(Category.objects.select_related("parent"), slug=DEFAULT_TECHNOLOGY_CATEGORY_SLUG)
    return render_category_page(request, category)
