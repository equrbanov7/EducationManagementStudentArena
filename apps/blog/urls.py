from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

urlpatterns = [
    # Ana səhifə və əsas səhifələr
    path("", views.home, name="home"),
    path("about/", views.about, name="about"),
    path("technology/", views.technology, name="technology"),
    path("subscribe/", views.subscribe_page, name="subscribe"),
    path("contact/", views.contact, name="contact"),
    # --- Auth (istifadəçi qeydiyyatı və giriş) ---
    path("register/", views.register_view, name="register"),
    path("verify-code/", views.verify_code_view, name="verify_code"),
    path("verify-email/", views.verify_email_link_view, name="verify_email_link"),
    path("resend-code/", views.resend_code_view, name="resend_code"),
    path(
        "login/",
        auth_views.LoginView.as_view(template_name="blog/login.html"),
        name="login",
    ),
    path("logout/", views.logout_view, name="logout"),
    path(
        "password-reset/",
        auth_views.PasswordResetView.as_view(template_name="blog/password_reset.html"),
        name="password_reset",
    ),
    path(
        "password-reset/done/",
        auth_views.PasswordResetDoneView.as_view(template_name="blog/password_reset_done.html"),
        name="password_reset_done",
    ),
    path(
        "reset/<uidb64>/<token>/",
        auth_views.PasswordResetConfirmView.as_view(template_name="blog/password_reset_confirm.html"),
        name="password_reset_confirm",
    ),
    path(
        "reset/done/",
        auth_views.PasswordResetCompleteView.as_view(template_name="blog/password_reset_complete.html"),
        name="password_reset_complete",
    ),
    # --- User profil səhifəsi ---
    path("users/<str:username>/", views.user_profile, name="user_profile"),
    # --- Postlarla bağlı URL-lər ---
    path("posts/create/", views.create_post, name="create_post"),
    path("posts/<slug:slug>/", views.post_detail, name="post_detail"),
    path("post/<int:pk>/edit/", views.post_edit_ajax, name="post_edit_ajax"),
    path("post/<int:post_id>/review/", views.review_post, name="review_post"),
    path("post/<int:post_id>/delete/", views.delete_post, name="delete_post"),
    # ---- Category URL-ləri ----
    path("category/<slug:slug>/", views.category_detail, name="category_detail"),
    # ---- Question URL-ləri ----
    path("questions/create/", views.create_question, name="create_question"),
    path("questions/my/", views.my_questions, name="my_questions"),
    path("questions/", views.questions_i_can_see, name="questions_i_can_see"),
]
