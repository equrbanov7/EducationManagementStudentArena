from django.urls import path
from django.contrib.auth import views as auth_views
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
    path(
        "login/",
        auth_views.LoginView.as_view(template_name="blog/login.html"),
        name="login",
    ),
    path("logout/", views.logout_view, name="logout"),

    # --- User profil səhifəsi ---
    path("users/<str:username>/", views.user_profile, name="user_profile"),

    # --- Postlarla bağlı URL-lər ---
    path("posts/create/", views.create_post, name="create_post"),
    path("posts/<slug:slug>/", views.post_detail, name="post_detail"),
    path("posts/<int:post_id>/edit/", views.edit_post, name="edit_post"),
    # 1. EDIT üçün endpoint (AJAX-la formanı gətirmək və POST qəbul etmək üçün)
    path("posts/<int:post_id>/edit/", views.edit_post, name="edit_post"), 

    # 2. DELETE üçün endpoint (Silinməni təsdiqləmək üçün)
    path("posts/<int:post_id>/delete/", views.delete_post, name="delete_post"),

    # ---- Category URL-ləri ----
    path("category/<slug:slug>/", views.category_detail, name="category_detail"),

    # ---- Question URL-ləri ----
    path("questions/create/", views.create_question, name="create_question"),
    path("questions/my/", views.my_questions, name="my_questions"),
    path("questions/", views.questions_i_can_see, name="questions_i_can_see"),

    # --- Exam URL-ləri ---

    # Müəllim üçün imtahan siyahısı
    path("exams/", views.teacher_exam_list, name="teacher_exam_list"),

    # ⭐ Tələbə üçün imtahan siyahısı
    path("exams/available/", views.student_exam_list, name="student_exam_list"),

    # İmtahan yaratmaq (müəllim)
    path("exams/create/", views.create_exam, name="create_exam"),

    # Slug-lı bütün exam URL-ləri – MÜTLƏQ bunlardan sonra gəlməlidir
    path("exams/<slug:slug>/", views.teacher_exam_detail, name="teacher_exam_detail"),
    path(
        "exams/<slug:slug>/add-question/",
        views.add_exam_question,
        name="add_exam_question",
    ),
    path(
        "exams/<slug:slug>/toggle-active/",
        views.toggle_exam_active,
        name="toggle_exam_active",
    ),
    path("exams/<slug:slug>/edit/", views.edit_exam, name="edit_exam"),
    path("exams/<slug:slug>/delete/", views.delete_exam, name="delete_exam"),
    path(
        "exams/<slug:slug>/questions/<int:question_id>/edit/",
        views.edit_exam_question,
        name="edit_exam_question",
    ),
    path(
        "exams/<slug:slug>/questions/<int:question_id>/delete/",
        views.delete_exam_question,
        name="delete_exam_question",
    ),

    # --- Student tərəfi (imtahan vermək) ---
    path("exams/<slug:slug>/start/", views.start_exam, name="start_exam"),
    path(
        "exams/<slug:slug>/attempt/<int:attempt_id>/",
        views.take_exam,
        name="take_exam",
    ),
    path(
        "exams/<slug:slug>/attempt/<int:attempt_id>/result/",
        views.exam_result,
        name="exam_result",
    ),

    # --- Teacher statistikası ---
    path(
        "exams/<slug:slug>/results/",
        views.teacher_exam_results,
        name="teacher_exam_results",
    ),
]
