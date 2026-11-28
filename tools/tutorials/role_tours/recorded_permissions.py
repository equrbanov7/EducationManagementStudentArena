"""Action gates for controls actually shown in the synthetic role-tour chapters.

The installer unions these with the cabinet sections and linked FAQ guides. A
read-only list, filter, or exam tab must not inherit an adjacent write action.
"""

# A landing page can itself be privileged (the external tabs are independent of
# their cabinet menu). Bind by section ID, never by the translated menu caption.
_SECTION_FLAGS = {
    "exam-score-entry": "faq_enter_paper_scores",
    "external-rooms": "faq_supervise_rooms",
    "external-language": "can_view_language_cohorts",
    "remote-journal-access": "faq_grant_remote_journal",
    "superadmin-exam-rooms": "faq_manage_exam_rooms",
}

# Only match the clicked control within this section. For instance «Yeni qrup»
# in the academic registry is unrelated to language or laboratory groups.
_CONTROLS = {
    "external-rooms": {
        "Hesabatlar": "faq_exam_center",
        "Zal idarəetmə": "faq_manage_exam_rooms",
        "Bütün otaqları göstər": "faq_designate_exam_halls",
    },
    "external-language": {"Səviyyə qrupu yaratma formasını aç": "can_manage_language_cohorts"},
    "groups-registry": {"Yeni qrup": "faq_manage_academic_groups", "Redaktə": "faq_manage_academic_groups"},
    "my-exams": {"Yeni imtahan": "faq_create_quiz", "İlk imtahanı yarat": "faq_create_quiz"},
    "my-appeals": {"Yeni apellyasiya müraciəti": "faq_lodge_appeal"},
    "question-bank": {"Yeni bank": "faq_create_question_bank"},
    "question-submissions": {"Yeni göndəriş": "faq_submit_own_questions"},
    "journal-hygiene": {"Uyğun olanların hamısını seç": "faq_apply_journal_hygiene"},
    "subject-folders": {"Yeni qovluq": "faq_manage_folder"},
    "syllabus-list": {"Yeni versiya yarat": "faq_edit_syllabus"},
    "schedule-manage": {
        "Avtomatik cədvəl": "faq_manage_schedule",
        "Bu xanaya dərs əlavə et": "faq_manage_schedule",
        "Filtrlə Excel-ə ixrac et": "faq_export_schedule",
    },
    "workload-distribution": {"Tapşırıq yarat": "faq_manage_workload_row", "Sətir əlavə et": "faq_manage_workload_row"},
    "workload-center": {"Yeni tapşırıq": "faq_manage_workload_row"},
    "programs-registry": {"Redaktə": "faq_manage_programs", "Yeni ixtisas": "faq_manage_programs"},
    "subject-catalog": {"Redaktə": "can_manage_catalog", "Yeni fənn": "can_manage_catalog"},
    "curriculum-editor": {"Yeni plan": "faq_edit_curriculum", "Yeni versiya": "faq_edit_curriculum"},
    "semester-opening": {"Plandan açılış yarat": "faq_open_semester"},
    "student-admission": {"Tək tələbə əlavə et": "faq_import_students"},
    "teacher-intake": {"Tək müəllim əlavə et": "faq_import_staff"},
    "surveys-builder": {"Redaktə et": "faq_manage_surveys"},
    "hr-contracts": {
        "Müqavilə əlavə et": "faq_manage_hr_contracts",
        "Redaktə": "faq_manage_hr_contracts",
        "Yenilə": "faq_manage_hr_contracts",
    },
    "my-courses": {"Yeni kurs": "faq_create_course", "İlk kursu yarat": "faq_create_course"},
    "applications": {"Yeni müraciət": "can_create_support"},
    "org-faculties": {"Yeni fakültə": "faq_create_org_unit"},
    "org-kafedras": {"Yeni kafedra": "faq_create_org_unit"},
    "role-assignment": {
        "Rolu yenilə": "faq_assign_roles",
        "Təşkilata əlavə et": "faq_assign_roles",
        "Əlavə rol ver": "faq_assign_roles",
    },
    "org-roles": {"İcazələri redaktə et": "faq_edit_role_permissions"},
}


def chapter_flags(chapters):
    """Return the union of exact operation flags for a full, seekable recording."""
    flags = set()
    for chapter in chapters:
        section = chapter.get("section")
        if section in _SECTION_FLAGS:
            flags.add(_SECTION_FLAGS[section])
        parts = chapter.get("title", "").split(" · ")
        if len(parts) < 2:
            continue
        controls = _CONTROLS.get(section, {})
        flags.update(controls[label] for label in parts[1:] if label in controls)
        if section == "groups-registry" and any(label.endswith(" qrupuna tələbə əlavə et") for label in parts[1:]):
            flags.add("faq_manage_academic_groups")
        # An observer too can open a Midterm tab. Only the two recorded
        # instructor views show the editable cells of the instructor's own group.
        if section == "external-journal" and (
            "Midterm qiyməti" in parts[1:] or parts[-2:] == ["Öz jurnalını aç", "Midterm"]
        ):
            flags.add("faq_write_own_journal")
    return flags
