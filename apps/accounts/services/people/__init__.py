"""«Müəllimlər» / «Tələbələr» kataloqu — servis fasadı.

Modul bölgüsü (SOFT_CAP=600 büdcəsi):

* ``permissions`` — icazə açarları + aktor + scope həlli (fail-closed qapı)
* ``constants``   — rol adları, unit tipləri, sıralama allowlist-i
* ``filters``     — GET normallaşdırma + Q qurucuları (axtarış/status/cins/yaş)
* ``scoping``     — istifadəçinin seçdiyi fakültə/kafedra daralması
* ``rows``        — sətir serializasiyası (avatar/baş hərf, yaş, struktur adları)
* ``teachers`` / ``students`` — səhifələnmiş siyahı sorğuları
* ``lookups``     — filtr açılışları + səbət sayları (AYRICA endpoint)
* ``analytics``   — ORTAQ analitika primitivləri (başlıq aqreqatı, bölgü qurucu)
* ``analytics_teachers`` / ``analytics_students`` — kataloq-xüsusi göstəricilər
* ``analytics_ai``— PII-siz AI yükü + xülasə çağırışı
* ``detail``      — bir şəxsin kartı
* ``actions``     — hesabı dayandır/bərpa et, müəllim statusu (RİM-i çağırır)
"""

from .actions import load_target, set_account_status, set_teacher_role
from .analytics_ai import build_ai_payload, generate_analytics_summary
from .analytics_students import build_student_analytics
from .analytics_teachers import build_teacher_analytics
from .constants import DEFAULT_PAGE_SIZE, STUDENT_SORT_OPTIONS, TEACHER_ROLE_NAMES, TEACHER_SORT_OPTIONS
from .detail import build_detail
from .filters import PeopleFilters, parse_filters
from .lookups import build_filter_options
from .permissions import (
    PEOPLE_PERMISSIONS,
    PERM_MANAGE_STATUS,
    PERM_MANAGE_TEACHER_ROLE,
    PERM_VIEW_CONTACTS,
    PERM_VIEW_DEMOGRAPHICS,
    PERM_VIEW_STUDENTS,
    PERM_VIEW_TEACHERS,
    SECTION_VIEW_PERMISSION,
    PeopleActor,
    resolve_actor,
)
from .students import build_students_page, visible_students_qs
from .teachers import build_teachers_page, visible_teachers_qs

__all__ = [
    "DEFAULT_PAGE_SIZE",
    "PEOPLE_PERMISSIONS",
    "PERM_MANAGE_STATUS",
    "PERM_MANAGE_TEACHER_ROLE",
    "PERM_VIEW_CONTACTS",
    "PERM_VIEW_DEMOGRAPHICS",
    "PERM_VIEW_STUDENTS",
    "PERM_VIEW_TEACHERS",
    "SECTION_VIEW_PERMISSION",
    "STUDENT_SORT_OPTIONS",
    "TEACHER_ROLE_NAMES",
    "TEACHER_SORT_OPTIONS",
    "PeopleActor",
    "PeopleFilters",
    "build_ai_payload",
    "build_detail",
    "build_filter_options",
    "build_student_analytics",
    "build_students_page",
    "build_teacher_analytics",
    "build_teachers_page",
    "generate_analytics_summary",
    "load_target",
    "parse_filters",
    "resolve_actor",
    "set_account_status",
    "set_teacher_role",
    "visible_students_qs",
    "visible_teachers_qs",
]
