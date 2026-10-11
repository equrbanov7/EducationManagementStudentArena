from django.urls import path

from . import views

app_name = "labs"

urlpatterns = [
    # ═══════════════════════════════════════════════════════════════════
    # Lab CRUD
    # ═══════════════════════════════════════════════════════════════════
    path("create/<int:course_id>/", views.create_lab, name="create_lab"),
    path("<int:pk>/edit/", views.edit_lab, name="edit_lab"),
    path("<int:pk>/delete/", views.delete_lab, name="delete_lab"),
    # WP9a (2026-10-10): `<pk>/publish/` silindi — status redaktə modalından təyin olunur.
    # ═══════════════════════════════════════════════════════════════════
    # Block CRUD
    # ═══════════════════════════════════════════════════════════════════
    path("<int:pk>/blocks/", views.manage_blocks, name="manage_blocks"),
    path(
        "<int:pk>/questions-per-student/",
        views.update_questions_per_student,
        name="update_questions_per_student",
    ),
    path("<int:pk>/blocks/create/", views.create_block, name="create_block"),
    path("blocks/<int:pk>/edit/", views.edit_block, name="edit_block"),
    path("blocks/<int:pk>/delete/", views.delete_block, name="delete_block"),
    # ═══════════════════════════════════════════════════════════════════
    # Question CRUD
    # ═══════════════════════════════════════════════════════════════════
    path(
        "blocks/<int:block_id>/questions/create/",
        views.create_question,
        name="create_question",
    ),
    path("questions/<int:pk>/edit/", views.edit_question, name="edit_question"),
    path("questions/<int:pk>/delete/", views.delete_question, name="delete_question"),
    path(
        "blocks/<int:block_id>/questions/import/",
        views.import_questions,
        name="import_questions",
    ),
    # ═══════════════════════════════════════════════════════════════════
    # Submissions & Grading
    # ═══════════════════════════════════════════════════════════════════
    path("<int:pk>/submissions/", views.lab_submissions, name="lab_submissions"),
    path(
        "<int:pk>/submissions/delete/",
        views.delete_submissions,
        name="delete_submissions",
    ),
    path(
        "submissions/<int:pk>/grade-page/",
        views.grade_submission_page,
        name="grade_submission_page",
    ),
    # ═══════════════════════════════════════════════════════════════════
    # Preview
    # ═══════════════════════════════════════════════════════════════════
    path("<int:pk>/preview/", views.preview_randomization, name="preview_randomization"),
    # ═══════════════════════════════════════════════════════════════════
    # Student (Lab Detail & Submit)
    # ═══════════════════════════════════════════════════════════════════
    path("<int:pk>/", views.lab_detail, name="lab_detail"),
    path("<int:pk>/submit/", views.submit_lab, name="submit_lab"),
    path("<int:pk>/auto-save/", views.auto_save_answer, name="auto_save_answer"),
    path("<int:pk>/my-answers/", views.my_lab_answers, name="my_lab_answers"),
    # ═══════════════════════════════════════════════════════════════════
    # API
    # ═══════════════════════════════════════════════════════════════════
    path("api/groups/<int:course_id>/", views.api_get_groups, name="api_get_groups"),
    path("api/students/<int:course_id>/", views.api_get_students, name="api_get_students"),
    # WP9a (2026-10-10): `submissions/<pk>/answers/` JSON-u silindi — qiymət səhifəsi cavabları
    # server tərəfdə render edir.
]
