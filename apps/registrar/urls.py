"""Registrar web URLs — elektron jurnal (müəllim üzü) + registrar konsolu (K3)."""

from django.urls import path

from . import (
    analytics_views,
    catalog_actions,
    console_views,
    correction_views,
    guest_roster_views,
    journal_actions,
    pdf_views,
    schedule_views,
    syllabus_views,
    views,
)

app_name = "registrar"

urlpatterns = [
    path("", views.journal_list, name="journal_list"),
    # Admin jurnal düzəlişi (üzrlü qayıb / sənədli korreksiya) — literal prefiks,
    # uuid catch-all-dan əvvəl.
    path("duzelis/", correction_views.correction_offering_list, name="correction_list"),
    path("duzelis/<uuid:offering_id>/", correction_views.correction_journal, name="correction_journal"),
    path("duzelis/<uuid:offering_id>/tetbiq/", correction_views.correction_apply, name="correction_apply"),
    path("duzelis/<uuid:offering_id>/sil/", correction_views.correction_delete, name="correction_delete"),
    # Ekran 03/04 — akademik kataloq əməlləri (JSON POST, `catalog.manage`).
    path("kataloq/emel/", catalog_actions.catalog_action, name="catalog_action"),
    path("analitika/", analytics_views.analytics_dashboard, name="analytics"),
    path("transkript.pdf", pdf_views.my_transcript_pdf, name="my_transcript_pdf"),
    path("teqvim/", schedule_views.calendar_view, name="calendar"),
    path("cedvel/", schedule_views.schedule_view, name="schedule"),
    path("cedvel/export.ics", pdf_views.schedule_ics, name="schedule_ics"),
    path("cedvel/slot/<uuid:slot_id>/sil/", schedule_views.schedule_slot_delete, name="schedule_slot_delete"),
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
    path("idareetme/rubrik/yeni/", console_views.rubric_form_view, name="rubric_create"),
    path("idareetme/rubrik/<uuid:pk>/", console_views.rubric_form_view, name="rubric_edit"),
    path("idareetme/telebe/yeni/", console_views.student_record_form_view, name="student_record_create"),
    path("idareetme/telebe/<uuid:pk>/", console_views.student_record_form_view, name="student_record_edit"),
    path("idareetme/telebe/<uuid:pk>/kocur/", console_views.student_transfer_view, name="student_transfer"),
    path("idareetme/telebe/<uuid:pk>/transkript.pdf", pdf_views.student_transcript_pdf, name="student_transcript_pdf"),
    path("<uuid:offering_id>/rubrik/<uuid:component_id>/", views.rubric_grade_view, name="rubric_grade"),
    path("<uuid:offering_id>/export.xlsx", pdf_views.journal_xlsx, name="journal_xlsx"),
    # «Sillabusa bax» — jurnal (müəllim) və kabinet (tələbə) üçün ORTAQ oxu səthi.
    path(
        "<uuid:offering_id>/sillabus.json",
        syllabus_views.offering_syllabus_json,
        name="offering_syllabus_json",
    ),
    path(
        "<uuid:offering_id>/sillabus.pdf",
        syllabus_views.offering_syllabus_pdf,
        name="offering_syllabus_pdf",
    ),
    # «Alt qrupdan tələbə əlavə et» (koordinator/dekanlıq) — uuid catch-all-dan ƏVVƏL.
    path(
        "<uuid:offering_id>/alt-qrup/qruplar/",
        guest_roster_views.guest_group_search,
        name="journal_guest_group_search",
    ),
    path(
        "<uuid:offering_id>/alt-qrup/telebeler/",
        guest_roster_views.guest_student_search,
        name="journal_guest_student_search",
    ),
    path(
        "<uuid:offering_id>/alt-qrup/onbaxis/",
        guest_roster_views.guest_add_preview,
        name="journal_guest_add_preview",
    ),
    path("<uuid:offering_id>/alt-qrup/elave/", guest_roster_views.guest_add, name="journal_guest_add"),
    path("<uuid:offering_id>/alt-qrup/cixar/", guest_roster_views.guest_remove, name="journal_guest_remove"),
    path("<uuid:offering_id>/ders/<uuid:lesson_id>/", journal_actions.lesson_action, name="journal_lesson_action"),
    path("<uuid:offering_id>/kollokvium/", journal_actions.kollokvium_save, name="journal_kollokvium_save"),
    path("<uuid:offering_id>/serbest/", journal_actions.selfwork_action, name="journal_selfwork_action"),
    path("<uuid:offering_id>/kurs-isi/", journal_actions.coursework_save, name="journal_coursework_save"),
    path("<uuid:offering_id>/", views.journal_detail, name="journal_detail"),
]
