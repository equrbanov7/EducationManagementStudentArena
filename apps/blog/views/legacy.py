from django.shortcuts import redirect
from django.urls import reverse

from .categories import category_detail
from .comments import post_detail
from .posts import create_post
from .subscribe import subscribe_page


def _redirect_to_named_url(request, view_name, **kwargs):
    target_url = reverse(view_name, kwargs=kwargs)
    query_string = request.GET.urlencode()
    if query_string:
        target_url = f"{target_url}?{query_string}"
    return redirect(target_url, permanent=True)


def legacy_home(request):
    return _redirect_to_named_url(request, "home")


def legacy_about(request):
    return _redirect_to_named_url(request, "about")


def legacy_technology(request):
    return _redirect_to_named_url(request, "technology")


def legacy_subscribe(request):
    if request.method in {"GET", "HEAD"}:
        return _redirect_to_named_url(request, "subscribe")
    return subscribe_page(request)


def legacy_create_post(request):
    if request.method in {"GET", "HEAD"}:
        return _redirect_to_named_url(request, "create_post")
    return create_post(request)


def legacy_article_detail(request, slug):
    if request.method in {"GET", "HEAD"}:
        return _redirect_to_named_url(request, "article_detail", slug=slug)
    return post_detail(request, slug)


def legacy_category_detail(request, slug):
    if request.method in {"GET", "HEAD"}:
        return _redirect_to_named_url(request, "category_detail", slug=slug)
    return category_detail(request, slug)
