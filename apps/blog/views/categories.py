# blog/views/categories.py

from django.core.paginator import Paginator
from django.urls import reverse
from django.shortcuts import get_object_or_404, render

from ..models import Category, Post
from ..selectors import filter_posts_by_category_scope, get_popular_topics, get_sidebar_categories


def render_category_page(request, category, *, template_name="blog/category_detail.html"):
    published_posts = Post.objects.filter(is_published=True).select_related("category", "author")
    root_category = category.get_root()
    parent_category = category.parent
    post_list = filter_posts_by_category_scope(
        published_posts,
        category,
    ).order_by("-created_at")
    page_obj = Paginator(post_list, 6).get_page(request.GET.get("page"))

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
        "back_link_url": reverse("category_detail", args=[parent_category.slug]) if parent_category else reverse("home"),
    }

    return render(request, template_name, context)


def category_detail(request, slug):
    category = get_object_or_404(Category.objects.select_related("parent"), slug=slug)
    return render_category_page(request, category)
