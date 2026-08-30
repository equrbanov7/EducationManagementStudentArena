"""Profil bölmələrinin başlıqları və birbaşa-render şablon xəritəsi.

`user_profile` (main.py) daxilindən çıxarılıb ki, fayl şişməsin və yeni bölmə
gələndə buraya əlavə olunsun (main.py-a yox).

DİQQƏT: ``build_section_titles()`` qəsdən funksiyadır — bəzi başlıqlar **eager**
``gettext`` (``_``) istifadə edir, yəni cari dilə görə per-request hesablanmalıdır.
Modul-səviyyə sabit etsək, import vaxtı (yanlış dildə) tərcümə olunardı.
"""

from django.utils.translation import gettext as _
from django.utils.translation import pgettext_lazy

# Birbaşa-render şablonları sırf statikdir (tərcümə yoxdur) → modul sabiti.
DIRECT_PROFILE_SECTION_TEMPLATES = {
    "pending-answers": "accounts/profile/sections/_pending_answers.html",
    "pending-review": "accounts/profile/sections/_pending_review.html",
    "review-results": "accounts/profile/sections/_review_results.html",
    "student-organization-management": "accounts/profile/sections/_student_org_management.html",
    "student-organization-request": "accounts/profile/sections/_student_org_request.html",
    "manage-roles": "accounts/profile/sections/_manage_roles.html",
    "permission-editor": "accounts/profile/sections/_permission_editor.html",
    "superadmin-organizations": "accounts/profile/sections/superadmin/_superadmin_organizations.html",
    "superadmin-ai": "accounts/profile/sections/superadmin/_superadmin_ai_settings.html",
    "superadmin-exam-rooms": "accounts/profile/sections/superadmin/_superadmin_exam_rooms.html",
    "exam-center-pins": "accounts/profile/sections/_exam_center_pins.html",
    "exam-center-stats": "accounts/profile/sections/_exam_center_stats.html",
    "academic-records": "accounts/profile/sections/_academic_records.html",
    "appeal-stats": "accounts/profile/sections/_appeal_stats.html",
    "kollokvium-windows": "accounts/profile/sections/_kollokvium_windows.html",
    "exam-score-entry": "accounts/profile/sections/_exam_score_entry.html",
    "exam-chance": "accounts/profile/sections/_exam_chance.html",
    "org-structure": "accounts/profile/sections/_org_structure.html",
    "org-faculties": "accounts/profile/sections/_org_faculties.html",
    "org-kafedras": "accounts/profile/sections/_org_kafedras.html",
    "org-members": "accounts/profile/sections/_org_members.html",
    "org-roles": "accounts/profile/sections/_org_roles.html",
    "audit-log": "accounts/profile/sections/_audit_log.html",
    "rim-center": "accounts/profile/sections/_rim_center.html",
    "people-teachers": "accounts/profile/sections/_people_teachers.html",
    "people-students": "accounts/profile/sections/_people_students.html",
    "syllabus-list": "accounts/profile/sections/_syllabus_list.html",
    "syllabus-editor": "accounts/profile/sections/_syllabus_editor.html",
}


def build_section_titles() -> dict:
    """Bölmə başlıqları xəritəsi (per-request — eager ``_()`` tərcümələri üçün)."""
    return {
        "profile-info": pgettext_lazy("profile.section", "profile_info"),
        "notifications": pgettext_lazy("profile.section", "notifications"),
        "publish-notification": pgettext_lazy("profile.publish_notification", "title"),
        "posts": pgettext_lazy("profile.section", "posts"),
        "create-post": pgettext_lazy("profile.section", "create_post"),
        "create-category": _("Create category"),
        "category-management": _("Categories"),
        "courses": pgettext_lazy("profile.section", "my_courses"),
        "my-exams": pgettext_lazy("profile.section", "my_exams"),
        "my-courses": pgettext_lazy("profile.section", "my_created_courses"),
        "assigned-exams": pgettext_lazy("profile.section", "assigned_tasks"),
        "assigned-courses": pgettext_lazy("profile.section", "assigned_courses"),
        "my-results": pgettext_lazy("profile.section", "my_results"),
        "my-subjects": pgettext_lazy("profile.section", "my_subjects"),
        "my-transcript": pgettext_lazy("profile.section", "my_transcript"),
        "overall-academic": pgettext_lazy("profile.section", "overall_academic"),
        # U12 — registrar kabinet bölmələri
        "my-schedule": pgettext_lazy("profile.sidebar", "Dərs cədvəli"),
        "academic-calendar": pgettext_lazy("profile.sidebar", "Akademik təqvim"),
        "my-journal": pgettext_lazy("profile.sidebar", "Elektron jurnal"),
        "journal-close": pgettext_lazy("profile.sidebar", "Jurnal bağlama"),
        "analytics": pgettext_lazy("profile.sidebar", "Akademik analitika"),
        "academic-records": pgettext_lazy("profile.sidebar", "Akademik qeydlər"),
        "pending-answers": pgettext_lazy("accounts.pending_answers", "section_title"),
        "groups": pgettext_lazy("profile.section", "groups"),
        "pending-post-approvals": "Postların idarəetməsi",
        "pending-review": pgettext_lazy("profile.section", "pending_review"),
        "review-results": "Dəyərləndirilmiş nəticələr",
        "role-assignment": pgettext_lazy("profile.section", "role_assignment"),
        "student-organization-request": pgettext_lazy("profile.section", "join_organization"),
        "student-organization-management": pgettext_lazy("profile.section", "staff_management"),
        "permission-editor": pgettext_lazy("profile.section", "permissions"),
        "manage-roles": pgettext_lazy("profile.section", "manage_roles"),
        "superadmin-org-features": "Təşkilat özəllikləri",
        "superadmin-organizations": pgettext_lazy("profile.section", "superadmin_control"),
        "superadmin-users": pgettext_lazy("superadmin.users", "user_management_title"),
        "rim-center": pgettext_lazy("profile.section", "rim_center"),
        "superadmin-ai": pgettext_lazy("superadmin.ai_settings", "title"),
        "superadmin-exam-rooms": pgettext_lazy("profile.section", "İmtahan zalları"),
        "exam-center-pins": pgettext_lazy("profile.section", "PIN axtarışı"),
        "exam-center-stats": pgettext_lazy("profile.section", "İmtahan statistikaları"),
        "kollokvium-windows": pgettext_lazy("profile.section", "Kollokvium pəncərələri"),
        "exam-score-entry": pgettext_lazy("profile.section", "İmtahan balının daxil edilməsi"),
        "exam-chance": pgettext_lazy("profile.section", "İmtahan şansı ver"),
        "appeal-stats": pgettext_lazy("profile.section", "Apellyasiya statistikası"),
        "superadmin-contact-messages": _("Contact Messages"),
        "blog": pgettext_lazy("nav", "home"),
        "edit-profile": pgettext_lazy("profile.section", "edit_profile"),
        "change-password": pgettext_lazy("profile.section", "change_password"),
        "statistics": pgettext_lazy("profile.section", "statistics"),
        "question-bank": "Sual Bankı",
        "my-appeals": pgettext_lazy("appeals.template", "Apellyasiyalarım"),
        "manage-appeals": pgettext_lazy("appeals.template", "Apellyasiyalar"),
        "unit-exams": "Bölmə imtahanları",
        "org-structure": "Fakültə və kafedralar",
        "org-faculties": "Fakültələr",
        "org-kafedras": "Kafedralar",
        "org-members": "Struktur üzvləri",
        "org-roles": "Təşkilat rolları",
        "audit-log": "Audit jurnalı",
        "superadmin-org-inspector": "Təşkilat məlumatları",
        "people-teachers": pgettext_lazy("profile.sidebar", "Müəllimlər"),
        "people-students": pgettext_lazy("profile.sidebar", "Tələbələr"),
        "syllabus-list": pgettext_lazy("profile.sidebar", "Sillabuslar"),
        "syllabus-editor": pgettext_lazy("profile.sidebar", "Sillabus redaktoru"),
    }
