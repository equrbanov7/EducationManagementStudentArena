from django.urls import path

from . import views

urlpatterns = [
    # Ana səhifə və əsas səhifələr
    path("", views.home, name="home"),
    path("about/", views.about, name="about"),
    path("technology/", views.technology, name="technology"),
    path("subscribe/", views.subscribe_page, name="subscribe"),
    # --- Postlarla bağlı URL-lər ---
    path("posts/create/", views.create_post, name="create_post"),
    path("articles/<slug:slug>/", views.post_detail, name="article_detail"),
    path("posts/<int:pk>/edit/", views.post_edit_ajax, name="post_edit_ajax"),
    path("posts/<int:post_id>/review/", views.review_post, name="review_post"),
    path("posts/<int:post_id>/delete/", views.delete_post, name="delete_post"),
    path("posts/<int:post_id>/moderate/", views.teacher_moderate_post, name="teacher_moderate_post"),
    # ---- Category URL-ləri ----
    path("categories/<slug:slug>/", views.category_detail, name="category_detail"),
    # ---- Question URL-ləri ----
    path("questions/create/", views.create_question, name="create_question"),
    path("questions/my/", views.my_questions, name="my_questions"),
    path("questions/", views.questions_i_can_see, name="questions_i_can_see"),
]
