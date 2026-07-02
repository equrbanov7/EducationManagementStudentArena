"""Blog — açıq siyahı/axtarış endpointləri (F7 rol-skeleti, 2026-07-02)."""

from django.shortcuts import render

from ...models import Post


def list_posts(request):
    """
    Bütün postların siyahısı (əgər ayrıca page istəyirsənsə).
    """
    posts = Post.objects.select_related("category", "author").order_by("-created_at")
    return render(request, "blog/post_list.html", {"posts": posts})


def search_posts(request):
    """
    Sadə search: ?q=... ilə title və excerpt-də axtarır.
    """
    query = request.GET.get("q", "").strip()
    posts = Post.objects.all()

    if query:
        posts = posts.filter(title__icontains=query) | posts.filter(excerpt__icontains=query)

    posts = posts.order_by("-created_at")

    return render(
        request,
        "blog/search_results.html",
        {
            "posts": posts,
            "query": query,
        },
    )
