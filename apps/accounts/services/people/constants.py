"""Kataloq sabitləri — rol adları, səhifə ölçüləri, sıralama açarları."""

from __future__ import annotations

from core.constants import OrgUnitType

#: Kataloqun «müəllim» saydığı rol adları.
#:
#: MƏNBƏ SEÇİMİ (bax MEMORY «Müəllim siyahısı 2 mənbə»): kataloq ROL-əsaslıdır,
#: offering-instructor əsaslı DEYİL. Səbəb: «Müəllimlər» bölməsi kadr
#: kataloqudur — cari semestrdə dərsi olmayan müəllim də siyahıda qalmalıdır
#: (əks halda məzuniyyətdəki müəllim yoxa çıxardı). «Dərs dediyi fənn» filtri
#: isə offering üzərindən İSTƏYƏ görə daraldır.
TEACHER_ROLE_NAMES = (
    "teacher",
    "assistant",
    "assistant_teacher",
    "instructor",
    "collaborator",
    "lab_assistant",
)

#: Müəllim statusunu VERƏRKƏN istifadə olunan kanonik rol adı.
DEFAULT_TEACHER_ROLE_NAME = "teacher"

FACULTY_UNIT_TYPES = (OrgUnitType.FACULTY, OrgUnitType.DEANERY)
KAFEDRA_UNIT_TYPES = (OrgUnitType.CHAIR, OrgUnitType.DEPARTMENT)
GROUP_UNIT_TYPES = (OrgUnitType.GROUP,)

DEFAULT_PAGE_SIZE = 25
MAX_PAGE_SIZE = 100

MAX_QUERY_TOKENS = 6
MAX_QUERY_LENGTH = 120

#: `sort` açarı → ORDER BY sahələri. Allowlist-dir: ixtiyari sətir qəbul edilmir.
#:
#: Hər iki kataloq ``User`` üzərində qurulur (bax `teachers.py` şərhi), ona görə
#: sahə adları prefikssizdir; struktur/qrup sıralaması annotasiya adına baxır.
TEACHER_SORT_OPTIONS = {
    "name": ("last_name", "first_name", "username"),
    "-name": ("-last_name", "-first_name", "-username"),
    "unit": ("unit_name", "last_name", "first_name"),
    "newest": ("-date_joined", "last_name", "username"),
    "oldest": ("date_joined", "last_name", "username"),
}

STUDENT_SORT_OPTIONS = {
    "name": ("last_name", "first_name", "username"),
    "-name": ("-last_name", "-first_name", "-username"),
    "group": ("group_name", "last_name", "first_name"),
    "year": ("-admission_year", "last_name", "username"),
    "newest": ("-date_joined", "last_name", "username"),
    "oldest": ("date_joined", "last_name", "username"),
}

#: Cins səbətləri — «təyin edilməyib» QƏSDƏN görünən səbətdir.
#: Mənbədə cins yalnız ~21 % tələbədə doludur; onu gizlətmək 79 % tələbəni
#: siyahıdan yox etmək demək olardı.
GENDER_BUCKETS = ("male", "female", "unspecified")

#: Yaş səbətləri — `unknown` doğum tarixi olmayanları AÇIQ göstərir.
AGE_UNKNOWN = "unknown"

__all__ = [
    "AGE_UNKNOWN",
    "DEFAULT_PAGE_SIZE",
    "DEFAULT_TEACHER_ROLE_NAME",
    "FACULTY_UNIT_TYPES",
    "GENDER_BUCKETS",
    "GROUP_UNIT_TYPES",
    "KAFEDRA_UNIT_TYPES",
    "MAX_PAGE_SIZE",
    "MAX_QUERY_LENGTH",
    "MAX_QUERY_TOKENS",
    "STUDENT_SORT_OPTIONS",
    "TEACHER_ROLE_NAMES",
    "TEACHER_SORT_OPTIONS",
]
