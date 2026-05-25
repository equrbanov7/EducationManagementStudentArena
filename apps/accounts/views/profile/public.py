"""
Public user profile view.

Renders a user's public profile: only published posts and non-confidential
profile information are exposed. Safe for anonymous visitors.
"""

from django.contrib.auth import get_user_model
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import HttpResponseBadRequest, QueryDict
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_safe

from ...models import UserProfile
from .search import (
    _parse_public_profile_page_number,
    _sanitize_public_profile_search_query,
    _validate_public_profile_category,
)

User = get_user_model()


@require_safe
def public_user_profile(request, username):
    """
    Public user profile showing only published posts and non-confidential
    profile information.
    """
    from apps.blog.models import Category, Post
    from apps.blog.selectors import filter_posts_by_category_scope, get_flat_category_tree

    profile_user = get_object_or_404(User, username=username)

    if request.user.is_authenticated and request.user == profile_user:
        return redirect("accounts:profile")

    profile, _created = UserProfile.objects.get_or_create(user=profile_user)

    published_posts = (
        Post.objects.filter(author=profile_user, is_published=True).select_related("category").order_by("-created_at")
    )

    allowed_category_slugs = set(Category.objects.values_list("slug", flat=True))
    search_query, invalid_search_query = _sanitize_public_profile_search_query(request.GET.get("q"))
    selected_category, invalid_category = _validate_public_profile_category(
        request.GET.get("category"),
        allowed_slugs=allowed_category_slugs,
    )

    user_posts_list = published_posts
    if invalid_search_query and not search_query:
        user_posts_list = user_posts_list.none()
    elif search_query:
        user_posts_list = user_posts_list.filter(
            Q(title__icontains=search_query) | Q(excerpt__icontains=search_query) | Q(content__icontains=search_query)
        )

    if invalid_category:
        user_posts_list = user_posts_list.none()
    elif selected_category:
        selected_category_obj = Category.objects.select_related("parent").filter(slug=selected_category).first()
        if selected_category_obj:
            user_posts_list = filter_posts_by_category_scope(user_posts_list, selected_category_obj)
        else:
            user_posts_list = user_posts_list.none()

    category_items = get_flat_category_tree(posts_queryset=published_posts, include_empty=False)

    raw_page_number = request.GET.get("page")
    page_number = _parse_public_profile_page_number(raw_page_number)
    if raw_page_number not in (None, "") and page_number is None:
        return HttpResponseBadRequest("Invalid page parameter.")

    paginator = Paginator(user_posts_list, 6)
    posts = paginator.get_page(page_number)

    display_name = (f"{profile_user.first_name} {profile_user.last_name}").strip() or profile_user.username
    profile_bio = (profile.bio or "").strip()
    profile_location = (profile.location or "").strip()

    query_params = QueryDict(mutable=True)
    if search_query:
        query_params["q"] = search_query
    if selected_category:
        query_params["category"] = selected_category
    extra_query = query_params.urlencode()

    context = {
        "profile_user": profile_user,
        "profile": profile,
        "display_name": display_name,
        "search_query": search_query,
        "selected_category": selected_category,
        "extra_query": extra_query,
        "category_items": category_items,
        "published_posts_count": published_posts.count(),
        "category_count": len(category_items),
        "profile_bio": profile_bio,
        "profile_location": profile_location,
        "posts": posts,
    }
    return render(request, "accounts/public_profile.html", context)
