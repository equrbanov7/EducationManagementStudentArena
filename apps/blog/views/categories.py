# blog/views/categories.py

from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, render

from ..models import Category, Post


def category_detail(request, slug):
    # 1. Hazırkı seçilmiş kateqoriyanı tapırıq (yoxdursa 404 qaytarır)
    category = get_object_or_404(Category, slug=slug)

    # 2. YALNIZ bu kateqoriyaya aid olan və yayımlanmış postları tapırıq
    posts = Post.objects.filter(category=category, is_published=True).order_by("-created_at")

    # 3. Sidebar üçün bütün kateqoriyaları və post saylarını hesablayırıq (Home view-dakı kimi)
    categories = (
        Category.objects.annotate(post_count=Count("posts", filter=Q(posts__is_published=True)))
        .filter(post_count__gt=0)
        .order_by("name")
    )

    context = {
        "category": category,  # Başlıqda adını yazmaq üçün
        "posts": posts,  # Süzülmüş postlar
        "categories": categories,  # Sidebar üçün siyahı
    }

    return render(request, "blog/category_detail.html", context)
