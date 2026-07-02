from django.contrib.auth import get_user_model
from django.shortcuts import get_object_or_404, redirect
from django.urls import path, reverse

from .views import (
    create_question,
    delete_post,
    my_questions,
    post_edit_ajax,
    questions_i_can_see,
    review_post,
)
from .views.public.legacy import (
    legacy_about,
    legacy_article_detail,
    legacy_category_detail,
    legacy_create_post,
    legacy_home,
    legacy_subscribe,
    legacy_technology,
)


def _legacy_user_profile(request, username):
    """Redirect the old blog user-profile URL to the accounts app profile pages."""
    User = get_user_model()
    if request.user.is_authenticated and request.user.username == username:
        target_url = reverse("accounts:profile")
    else:
        profile_user = get_object_or_404(User, username=username)
        target_url = reverse("accounts:public_profile", kwargs={"username": profile_user.username})

    query_string = request.GET.urlencode()
    if query_string:
        target_url = f"{target_url}?{query_string}"
    return redirect(target_url)


urlpatterns = [
    path("", legacy_home),
    path("about/", legacy_about),
    path("technology/", legacy_technology),
    path("subscribe/", legacy_subscribe),
    path("users/<str:username>/", _legacy_user_profile, name="user_profile"),
    path("posts/create/", legacy_create_post),
    path("posts/<slug:slug>/", legacy_article_detail),
    path("post/<int:pk>/edit/", post_edit_ajax),
    path("post/<int:post_id>/review/", review_post),
    path("post/<int:post_id>/delete/", delete_post),
    path("category/<slug:slug>/", legacy_category_detail),
    path("questions/create/", create_question),
    path("questions/my/", my_questions),
    path("questions/", questions_i_can_see),
]
