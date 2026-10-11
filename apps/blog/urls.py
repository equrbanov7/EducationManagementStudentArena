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
    # URL auditi WP9a A2 (2026-10-10): giriş nöqtəsi olmayan «Suallar» səhifələri
    # (`questions/create|my/`, `questions/`) silindi; ``Question`` modeli və datası qalır.
]
