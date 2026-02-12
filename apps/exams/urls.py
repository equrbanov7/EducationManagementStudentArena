# exams/urls.py
from django.urls import path

from . import views

app_name = "exams"

urlpatterns = [
    # ==========================
    # STUDENT - Exam Lists (sabit)
    # ==========================
    path("available/", views.student_exam_list, name="student_exam_list"),
    path("assigned/", views.assigned_student_exam_list, name="assigned_exam_list"),
    path("my-history/", views.student_exam_history, name="student_exam_history"),
    path("code-check/", views.exam_code_check, name="exam_code_check"),
    # ==========================
    # TEACHER - Exams CRUD (sabit)
    # ==========================
    path("", views.teacher_exam_list, name="teacher_exam_list"),
    path("create/", views.createAndEditExamView, name="create_exam"),
    path(
        "pending-work/", views.teacher_pending_attempts, name="teacher_pending_attempts"
    ),
    # ==========================
    # TEACHER - Student Groups (sabit)
    # ==========================
    path("groups/", views.teacher_group_list, name="teacher_group_list"),
    path("groups/create/", views.teacher_create_group, name="teacher_create_group"),
    path(
        "groups/<int:group_id>/update/",
        views.teacher_update_group,
        name="teacher_update_group",
    ),
    path(
        "groups/<int:group_id>/delete/",
        views.teacher_delete_group,
        name="teacher_delete_group",
    ),
    # ==========================
    # SLUG - Teacher Attempts (spesifik)
    # ==========================
    path(
        "<slug:slug>/attempt/<int:attempt_id>/check/",
        views.teacher_check_attempt,
        name="teacher_check_attempt",
    ),
    path(
        "<slug:slug>/attempt/<int:attempt_id>/view/",
        views.teacher_view_attempt,
        name="teacher_view_attempt",
    ),
    # ==========================
    # SLUG - Student Taking Exam (spesifik)
    # ==========================
    path("<slug:slug>/start/", views.start_exam, name="start_exam"),
    path(
        "<slug:slug>/attempt/<int:attempt_id>/result/",
        views.exam_result,
        name="exam_result",
    ),
    path("<slug:slug>/attempt/<int:attempt_id>/", views.take_exam, name="take_exam"),
    # ==========================
    # SLUG - Teacher Question Bank
    # ==========================
    path("<slug:slug>/test-bank/", views.test_question_bank, name="test_question_bank"),
    path(
        "<slug:slug>/create-bank/",
        views.create_question_bank,
        name="create_question_bank",
    ),
    path(
        "<slug:slug>/process-bank/",
        views.process_question_bank,
        name="process_question_bank",
    ),
    # ==========================
    # SLUG - Teacher Questions
    # ==========================
    path(
        "<slug:slug>/add-question/", views.add_exam_question, name="add_exam_question"
    ),
    path(
        "<slug:slug>/questions/<int:question_id>/edit/",
        views.edit_exam_question,
        name="edit_exam_question",
    ),
    path(
        "<slug:slug>/questions/<int:question_id>/delete/",
        views.delete_exam_question,
        name="delete_exam_question",
    ),
    # ==========================
    # SLUG - Teacher Exam Ops
    # ==========================
    path(
        "<slug:slug>/results/", views.teacher_exam_results, name="teacher_exam_results"
    ),
    path(
        "<slug:slug>/toggle-active/",
        views.toggle_exam_active,
        name="toggle_exam_active",
    ),
    path("<slug:slug>/edit/", views.createAndEditExamView, name="edit_exam"),
    path("<slug:slug>/delete/", views.delete_exam, name="delete_exam"),
    # ✅ ƏN AXIRDA: Teacher exam detail (generic)
    path("<slug:slug>/", views.teacher_exam_detail, name="teacher_exam_detail"),
]
