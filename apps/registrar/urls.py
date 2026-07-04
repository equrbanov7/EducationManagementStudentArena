"""Registrar web URLs — elektron jurnal (müəllim üzü)."""

from django.urls import path

from . import views

app_name = "registrar"

urlpatterns = [
    path("", views.journal_list, name="journal_list"),
    path("cedvel/", views.schedule_view, name="schedule"),
    path("cedvel/slot/<uuid:slot_id>/sil/", views.schedule_slot_delete, name="schedule_slot_delete"),
    # Registrar console (K3) — literal prefixes, must precede the uuid catch-all.
    path("idareetme/", views.registrar_console, name="console"),
    path("idareetme/proqram/yeni/", views.program_form_view, name="program_create"),
    path("idareetme/proqram/<uuid:pk>/", views.program_form_view, name="program_edit"),
    path("idareetme/fenn/yeni/", views.subject_form_view, name="subject_create"),
    path("idareetme/fenn/<uuid:pk>/", views.subject_form_view, name="subject_edit"),
    path("idareetme/plan/yeni/", views.curriculum_form_view, name="curriculum_create"),
    path("idareetme/plan/<uuid:pk>/redakte/", views.curriculum_form_view, name="curriculum_edit"),
    path("idareetme/plan/<uuid:pk>/", views.curriculum_detail, name="curriculum_detail"),
    path("idareetme/plan/setir/<uuid:pk>/sil/", views.curriculum_subject_delete, name="curriculum_subject_delete"),
    path("idareetme/fenn-acilisi/yeni/", views.offering_form_view, name="offering_create"),
    path("idareetme/fenn-acilisi/<uuid:pk>/", views.offering_form_view, name="offering_edit"),
    path("<uuid:offering_id>/", views.journal_detail, name="journal_detail"),
]
