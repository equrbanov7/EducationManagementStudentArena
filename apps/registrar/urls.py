"""Registrar web URLs — elektron jurnal (müəllim üzü) + JSON əməl son nöqtələri.

Köhnə «Registrar idarəetməsi» konsolu (`idareetme/…`) 2026-09-10-da SİLİNDİ —
onun yerini kabinet bölməsi tutdu (`accounts:profile?section=registrar-catalog`).
"""

from django.urls import path

from . import (
    catalog_actions,
    correction_views,
    curriculum_actions,
    guest_roster_views,
    holiday_actions,
    individual_plan_views,
    journal_actions,
    journal_activation,
    journal_history,
    journal_lesson_lookup,
    lessons_log_views,
    pdf_views,
    schedule_views,
    semester_actions,
    subject_exempt_views,
    subject_merge_views,
    syllabus_views,
    views,
)

app_name = "registrar"

urlpatterns = [
    path("", views.journal_list, name="journal_list"),
    # Admin jurnal düzəlişi (üzrlü qayıb / sənədli korreksiya) — literal prefiks,
    # uuid catch-all-dan əvvəl.
    # URL auditi A11 (2026-10-10): köhnə `duzelis/` və `duzelis/<uuid>/` yönləndirmə şimləri
    # silindi — düzəliş rejimi `journal_detail?correct=1`-dir; JS-in işlətdiyi tətbiq/sil qalır.
    path("duzelis/<uuid:offering_id>/tetbiq/", correction_views.correction_apply, name="correction_apply"),
    path("duzelis/<uuid:offering_id>/sil/", correction_views.correction_delete, name="correction_delete"),
    # Ekran 03/04 — akademik kataloq əməlləri (JSON POST, `catalog.manage`).
    path("kataloq/emel/", catalog_actions.catalog_action, name="catalog_action"),
    # İxtisasın «Ətraflı» çekmecəsi — OXU (`catalog.view`), 2026-09-09.
    path("kataloq/ixtisas/", catalog_actions.program_detail, name="program_detail"),
    # «Fənləri birləşdir» (2026-10-19) — org-geniş `catalog.manage`; önizləmə → izlə təsdiq.
    path("kataloq/fenn-birlesdir/axtar/", subject_merge_views.subject_lookup, name="subject_merge_lookup"),
    path("kataloq/fenn-birlesdir/qruplar/", subject_merge_views.duplicate_groups, name="subject_merge_groups"),
    path("kataloq/fenn-birlesdir/onizle/", subject_merge_views.merge_preview, name="subject_merge_preview"),
    path("kataloq/fenn-birlesdir/tetbiq/", subject_merge_views.merge_apply, name="subject_merge_apply"),
    # Ekran 05 — tədris planı əməlləri (JSON POST, `plan.*` + state maşını).
    path("tedris-plani/emel/", curriculum_actions.curriculum_action, name="curriculum_action"),
    # Ekran 07 — semestr açılışı əməlləri (JSON POST, `semester.*`).
    path("semestr/emel/", semester_actions.semester_action, name="semester_action"),
    # «Akademik təqvim» → «Bayram və qeyri-iş günləri» əməlləri (JSON POST, org-wide `semester.open`), 2026-10-19.
    path("teqvim/bayram/emel/", holiday_actions.holiday_action, name="holiday_action"),
    # Ekran 06 «Qruplar» — rəsmi «Fərdi tədris planı» DOCX (qrup / ?student=<record>).
    path(
        "qrup/<uuid:group_id>/ferdi-plan.docx",
        individual_plan_views.group_individual_plan,
        name="group_individual_plan",
    ),
    # URL auditi A11 (2026-10-10): `analitika/` səhifəsi silindi — kabinet `?section=analytics`.
    # Ekran 21 — «Keçilmiş dərslər» hesabatının CSV ixracı (oxu-only, əhatəli).
    path("kecilmis-dersler/export.csv", lessons_log_views.lessons_log_csv, name="lessons_log_csv"),
    path("transkript.pdf", pdf_views.my_transcript_pdf, name="my_transcript_pdf"),
    path("cedvel/", schedule_views.schedule_view, name="schedule"),
    # URL auditi A11 (2026-10-10): `teqvim/` (kabinet `?section=academic-calendar`),
    # `cedvel/export.ics` (sahib: iCal ləğv — jurnal yekunu jurnalın «Export» xlsx-i ilə) və
    # `cedvel/slot/<uuid>/sil/` (slot redaktəsi `accounts/schedule-manage/editor/`-dədir) silindi.
    # Rəsmi transkript PDF-i (U9) — köhnə «Registrar idarəetməsi» konsolu
    # silinəndə (2026-09-10) bu səth TOXUNULMAZ qaldı: URL adı
    # (`student_transcript_pdf`), icazəsi və görünüşü eynidir, yalnız yol
    # `idareetme/` prefiksindən çıxarıldı. Literal prefiks — uuid catch-all-dan
    # ƏVVƏL durmalıdır.
    path("telebe/<uuid:pk>/transkript.pdf", pdf_views.student_transcript_pdf, name="student_transcript_pdf"),
    # «Təhsil aldığı yer haqqında arayış» (sahib 2026-10-19) — POST (möhür yazır), qapı transkriptlə eyni.
    path(
        "telebe/<uuid:pk>/arayis.pdf",
        pdf_views.student_enrollment_certificate_pdf,
        name="student_enrollment_certificate_pdf",
    ),
    # Rubrik qiymətləndirməsi `REGISTRAR_RUBRICS_ENABLED` söndürülü ikən 404 verir (sahib 2026-10-10).
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
    # «Fəndən azad et» / «Bərpa et» — tələbə qrupda qalır, yalnız bu jurnaldan çıxır (sahib 2026-10-15).
    path("<uuid:offering_id>/fenden-azad/", subject_exempt_views.subject_exempt_apply, name="journal_subject_exempt"),
    path(
        "<uuid:offering_id>/fenden-azad/berpa/",
        subject_exempt_views.subject_exempt_restore,
        name="journal_subject_exempt_restore",
    ),
    # Dərs modalının axtarışlı/lazy seçiciləri (QA 2026-09-05 P3-13) — uuid
    # catch-all-dan ƏVVƏL.
    path(
        "<uuid:offering_id>/ders-muellimleri/axtar/",
        journal_lesson_lookup.lesson_teacher_search,
        name="journal_lesson_teacher_search",
    ),
    path(
        "<uuid:offering_id>/ders-otaqlari/",
        journal_lesson_lookup.lesson_room_data,
        name="journal_lesson_rooms",
    ),
    # «Dəyişiklik tarixçəsi» paneli (UNEC P1-3) — JSON səhifələri, uuid catch-all-dan ƏVVƏL.
    path("<uuid:offering_id>/tarixce/", journal_history.history_json, name="journal_history"),
    # «Dərsi aktivləşdir» — bu günün cədvəl slotundan tək kliklə dərs sütunu (UNEC P1-1), POST.
    path(
        "<uuid:offering_id>/cedvel-dersi/<uuid:slot_id>/aktivlesdir/",
        journal_activation.activate_slot,
        name="journal_activate_slot",
    ),
    path("<uuid:offering_id>/ders/<uuid:lesson_id>/", journal_actions.lesson_action, name="journal_lesson_action"),
    path("<uuid:offering_id>/kollokvium/", journal_actions.kollokvium_save, name="journal_kollokvium_save"),
    path("<uuid:offering_id>/serbest/", journal_actions.selfwork_action, name="journal_selfwork_action"),
    path("<uuid:offering_id>/kurs-isi/", journal_actions.coursework_save, name="journal_coursework_save"),
    path("<uuid:offering_id>/", views.journal_detail, name="journal_detail"),
]
