from django.urls import path

from .views import (
    create_question,
    delete_post,
    my_questions,
    post_edit_ajax,
    questions_i_can_see,
    review_post,
    user_profile,
)
from .views.legacy import (
    legacy_about,
    legacy_article_detail,
    legacy_category_detail,
    legacy_create_post,
    legacy_home,
    legacy_subscribe,
    legacy_technology,
)

urlpatterns = [
    path("", legacy_home),
    path("about/", legacy_about),
    path("technology/", legacy_technology),
    path("subscribe/", legacy_subscribe),
    path("users/<str:username>/", user_profile),
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
