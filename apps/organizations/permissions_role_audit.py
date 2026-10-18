"""Rol auditi 2026-10-13 — yeni açarlar (bax ``default_roles_role_audit.py`` sənədinə).

NİYƏ AYRI MODUL? ``permissions.py`` modul ölçüsü büdcəsinə (600) yaxındır — ``permissions_account.py`` ilə
eyni naxış: burada YALNIZ data, birləşmə ``permissions.py``-ın sonunda bir sətirlə.
"""

from django.utils.translation import pgettext_lazy

_PERM_CTX = "organizations.permission.label"

PERM_EXAM_CENTER_DECIDE = "exam_center.decide"
PERM_STUDENT_RECORDS_VIEW = "student.records_view"
PERM_USER_IMPORT_STAFF = "user.import_staff"
#: B14 — «Bildiriş göndər» (əvvəl rol bayraqları ilə açılırdı, redaktordan idarə olunmurdu).
PERM_NOTIFICATION_PUBLISH = "notification.publish"

ROLE_AUDIT_PERMISSION_CATEGORIES = {
    "exams": [PERM_EXAM_CENTER_DECIDE],
    "grading": [PERM_STUDENT_RECORDS_VIEW],
    "users": [PERM_USER_IMPORT_STAFF],
    # «Elanlar» kateqoriyası (`permissions_announcements.py`) — kütləvi bildiriş də auditoriyaya müraciətdir.
    "announcement": [PERM_NOTIFICATION_PUBLISH],
}

ROLE_AUDIT_PERMISSION_LABELS = {
    PERM_EXAM_CENTER_DECIDE: pgettext_lazy(
        _PERM_CTX, "İmtahan mərkəzinin qərarları (yenidən imtahan cəhdi, kollokvium pəncərəsi, sual göndərişi)"
    ),
    PERM_STUDENT_RECORDS_VIEW: pgettext_lazy(_PERM_CTX, "Akademik qeydlərə baxış (ÜOMG, transkript)"),
    PERM_USER_IMPORT_STAFF: pgettext_lazy(_PERM_CTX, "Müəllim/heyət hesablarının toplu idxalı"),
    PERM_NOTIFICATION_PUBLISH: pgettext_lazy(_PERM_CTX, "Bildiriş göndərmək (alıcılar öz əhatəsində)"),
}


def merge_role_audit_permissions(categories: dict, category_labels: dict, permission_labels: dict) -> None:
    """Kataloqu YERİNDƏ genişləndirir (idempotent)."""
    for name, keys in ROLE_AUDIT_PERMISSION_CATEGORIES.items():
        bucket = categories.setdefault(name, [])
        for key in keys:
            if key not in bucket:
                bucket.append(key)
    permission_labels.update(ROLE_AUDIT_PERMISSION_LABELS)


__all__ = [
    "PERM_EXAM_CENTER_DECIDE",
    "PERM_NOTIFICATION_PUBLISH",
    "PERM_STUDENT_RECORDS_VIEW",
    "PERM_USER_IMPORT_STAFF",
    "ROLE_AUDIT_PERMISSION_CATEGORIES",
    "ROLE_AUDIT_PERMISSION_LABELS",
    "merge_role_audit_permissions",
]
