"""Registrar web URLs — elektron jurnal (müəllim üzü) + registrar konsolu (K3)."""

from django.urls import path

from . import analytics_views, console_views, pdf_views, views

app_name = "registrar"

urlpatterns = [
    path("", views.journal_list, name="journal_list"),
    path("tesdiqler/", views.approvals_inbox, name="approvals_inbox"),
    path("analitika/", analytics_views.analytics_dashboard, name="analytics"),
    path("transkript.pdf", pdf_views.my_transcript_pdf, name="my_transcript_pdf"),
    path("teqvim/", views.calendar_view, name="calendar"),
    path("cedvel/", views.schedule_view, name="schedule"),
    path("cedvel/slot/<uuid:slot_id>/sil/", views.schedule_slot_delete, name="schedule_slot_delete"),
    # Registrar console (K3) — literal prefixes, must precede the uuid catch-all.
    path("idareetme/", console_views.registrar_console, name="console"),
    path("idareetme/proqram/yeni/", console_views.program_form_view, name="program_create"),
    path("idareetme/proqram/<uuid:pk>/", console_views.program_form_view, name="program_edit"),
    path("idareetme/fenn/yeni/", console_views.subject_form_view, name="subject_create"),
    path("idareetme/fenn/<uuid:pk>/", console_views.subject_form_view, name="subject_edit"),
    path("idareetme/plan/yeni/", console_views.curriculum_form_view, name="curriculum_create"),
    path("idareetme/plan/<uuid:pk>/redakte/", console_views.curriculum_form_view, name="curriculum_edit"),
    path("idareetme/plan/<uuid:pk>/", console_views.curriculum_detail, name="curriculum_detail"),
    path(
        "idareetme/plan/setir/<uuid:pk>/sil/", console_views.curriculum_subject_delete, name="curriculum_subject_delete"
    ),
    path("idareetme/fenn-acilisi/yeni/", console_views.offering_form_view, name="offering_create"),
    path("idareetme/fenn-acilisi/<uuid:pk>/", console_views.offering_form_view, name="offering_edit"),
    path("idareetme/telebe/yeni/", console_views.student_record_form_view, name="student_record_create"),
    path("idareetme/telebe/<uuid:pk>/", console_views.student_record_form_view, name="student_record_edit"),
    path("idareetme/telebe/<uuid:pk>/kocur/", console_views.student_transfer_view, name="student_transfer"),
    path("idareetme/telebe/<uuid:pk>/transkript.pdf", pdf_views.student_transcript_pdf, name="student_transcript_pdf"),
    path("<uuid:offering_id>/export.xlsx", pdf_views.journal_xlsx, name="journal_xlsx"),
    path("<uuid:offering_id>/", views.journal_detail, name="journal_detail"),
]
