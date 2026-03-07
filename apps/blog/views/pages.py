# blog/views/pages.py

from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.shortcuts import render

from ..models import Category, Post


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

    categories = (
        Category.objects.annotate(post_count=Count("posts", filter=Q(posts__is_published=True)))
        .filter(post_count__gt=0)
        .order_by("name")
    )

    context = {
        "page_obj": page_obj,
        "categories": categories,
        "search_query": query,
        "query": query,  # Also pass as 'query' for template compatibility
    }

    return render(request, "blog/home.html", context)


def about(request):
    return render(request, "blog/about.html")


def technology(request):

    TECH_CATEGORIES = [
        "proqramlasdirma",
        "suni-intellekt",
        "python",
        "django",
        "texnologiya",
        "backend",
    ]

    post_list = (
        Post.objects.filter(category__slug__in=TECH_CATEGORIES)
        .select_related("category", "author")
        .order_by("-created_at")
    )

    paginator = Paginator(post_list, 6)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    return render(request, "blog/technology.html", {"page_obj": page_obj})
