"""«Transkript və arayış vermək» icazəsi — ``transcript.issue`` (sahib 2026-10-19).

Açar əməkdaşın tələbəyə RƏSMİ, QR ilə möhürlənmiş sənəd verməsini açır:

* akademik transkript PDF-i (``registrar:student_transcript_pdf``);
* «Təhsil aldığı yer haqqında arayış» PDF-i (``registrar:student_enrollment_certificate_pdf``) və
  «Müraciətlər»-də «Arayış sorğusu»-na arayışın hazırlanıb əlavə edilməsi.

Əvvəl transkripti yalnız təşkilat üzrə ``course.edit`` daşıyan (rektor, prorektor, RİM) verə bilirdi — o
yol QORUNUR (``registrar.document_access``). Əhatə ``get_permission_scope`` ilə: ORGANIZATION rolu → bütün
təşkilat; UNIT rolu (dekan, dekan müavini) → yalnız öz fakültəsinin alt-ağacındakı tələbələr (kənarı 404).

Sənəd buraxılışı möhür sətri YAZIR — «başqasının adından» (view-as) rejimində bağlıdır.

NİYƏ AYRI MODUL? ``permissions.py`` ölçü büdcəsinə (600) yaxındır — ``permissions_document_seal.py`` ilə eyni
naxış. Rol şablonuna verilmə ``default_roles_university.py``-da; mövcud tenantlar —
``verification/0004_seed_transcript_issue_permission``.
"""

from django.utils.translation import pgettext_lazy

_PERM_CTX = "organizations.permission.label"

PERM_TRANSCRIPT_ISSUE = "transcript.issue"

TRANSCRIPT_PERMISSION_CATEGORIES = {"transcript": [PERM_TRANSCRIPT_ISSUE]}
TRANSCRIPT_CATEGORY_LABELS = {"transcript": "Rəsmi sənədlər"}
TRANSCRIPT_PERMISSION_LABELS = {
    PERM_TRANSCRIPT_ISSUE: pgettext_lazy(_PERM_CTX, "Transkript və arayış vermək"),
}

#: Şablonda açarı alan rollar: Tədris şöbəsinin müdiri, Tələbə xidmətləri (arayış/transkript sorğularını icra
#: edən bölmə), RİM rəhbəri (``*`` daraldılıbsa da qalsın), dekan və dekan müavini (öz fakültəsi üzrə).
TRANSCRIPT_GRANT_ROLES = ("teaching_office_head", "student_services", "ikt_rehber", "dean", "vice_dean")


def merge_transcript_permissions(categories: dict, category_labels: dict, permission_labels: dict) -> None:
    """Kataloqu YERİNDƏ genişləndirir (idempotent — təkrar çağırış təsirsizdir)."""
    for name, keys in TRANSCRIPT_PERMISSION_CATEGORIES.items():
        bucket = categories.setdefault(name, [])
        for key in keys:
            if key not in bucket:
                bucket.append(key)
    category_labels.update(TRANSCRIPT_CATEGORY_LABELS)
    permission_labels.update(TRANSCRIPT_PERMISSION_LABELS)


def apply_transcript_grants(roles):
    """Rol şablonlarına açarı idempotent əlavə edir (``*`` / ``transcript.*`` daşıyana toxunmur)."""
    for role in roles:
        if role.get("name") not in TRANSCRIPT_GRANT_ROLES:
            continue
        permissions = role.setdefault("permissions", [])
        if "*" in permissions or "transcript.*" in permissions or PERM_TRANSCRIPT_ISSUE in permissions:
            continue
        permissions.append(PERM_TRANSCRIPT_ISSUE)
    return roles


__all__ = [
    "PERM_TRANSCRIPT_ISSUE",
    "TRANSCRIPT_CATEGORY_LABELS",
    "TRANSCRIPT_GRANT_ROLES",
    "TRANSCRIPT_PERMISSION_CATEGORIES",
    "TRANSCRIPT_PERMISSION_LABELS",
    "apply_transcript_grants",
    "merge_transcript_permissions",
]
