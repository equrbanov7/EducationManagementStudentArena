"""«Müəllimlər» / «Tələbələr» bölmələrinin CONTEXT MÜQAVİLƏSİ.

Bölmələr SPA panelidir: server yalnız ÇƏRÇİVƏNİ verir (icazə xəritəsi, endpoint
URL-ləri, seçim siyahılarının etiketləri); cədvəl, filtr açılışları və detal
kartı JSON endpoint-lərindən AJAX-la gəlir. Ona görə burada ağır sorğu YOXDUR —
yalnız aktorun icazələri oxunur.

──────────────────────────────────────────────────────────────────────────────
CONTEXT MÜQAVİLƏSİ (UI agenti buna söykənir — açar adları dəyişməz)
──────────────────────────────────────────────────────────────────────────────
``people_section`` (dict):

    kind                    "teachers" | "students"
    has_access              bool  — bölmə ümumiyyətlə açılırmı
    access_denied_message   str   — has_access False olanda göstərilən mətn
    organization            Organization | None

    can_view_contacts       bool  — email/telefon/FİN sütunları
    can_view_demographics   bool  — cins/yaş sütunu VƏ filtrləri
    can_manage_status       bool  — «hesabı dayandır / bərpa et» düymələri
    can_manage_teacher_role bool  — «müəllim statusu ver / çıxar» düymələri
    can_manage_academic     bool  — «Tələbəni idarə et» düyməsi + idarə paneli
                                    (yalnız tələbə kataloqunda mənalıdır)
    granted_permissions     [{"key": str, "label": str}]  — aktorun açarları

    list_url                str   — GET  cədvəl datası
    analytics_url           str   — GET  filtrdən SONRA göstəricilər + qrafiklər
    analytics_ai_url        str   — GET  AI analizi (aqreqat yük, PII yoxdur)
    options_url             str   — GET  filtr açılışları + səbət sayları
    action_url              str   — POST əməllər
    detail_url_template     str   — GET  detal (içindəki "0" hədəf id ilə əvəzlənir)
    card_url_template       str   — GET  tələbə idarəetmə kartı ("0" → user id)
    groups_url              str   — GET  hədəf qrup axtarışı (type-ahead, səhifəli)
    preview_url_template    str   — GET  köçürmə ön baxışı (UUID «0» → record id)
    academic_status_options [{"key": str, "label": str}] — status seçimləri

    default_page_size       int
    max_page_size           int
    min_reason_length       int
    max_reason_length       int

    sort_options            [{"key": str, "label": str}]
    status_options          [{"key": str, "label": str}]
    gender_options          [{"key": str, "label": str}]
    age_unknown_key         str   — «doğum tarixi yoxdur» səbətinin GET dəyəri

    columns                 [str] — bu rol üçün göstərilməli sütun açarları

⚠️ DEMOQRAFİYA SEYRƏKDİR (mənbədə cins ~21 %, doğum tarixi ~28 % dolu).
``gender_options`` və yaş filtri «təyin edilməyib» səbətini HƏMİŞƏ daşıyır;
UI onu gizlətməməlidir, əks halda istifadəçilərin böyük hissəsi ünvansız qalır.

──────────────────────────────────────────────────────────────────────────────
JSON MÜQAVİLƏSİ (endpoint cavabları — açar adları dəyişməz)
──────────────────────────────────────────────────────────────────────────────
``GET list_url?<filtrlər>&page=N`` →

    has_access, results[], page, num_pages, total, has_next, has_previous,
    filters {…tətbiq olunmuş normallaşdırılmış filtrlər…}, capabilities {…}

``results[]`` sətri — ORTAQ sahələr (hər iki kataloq):

    id, username, full_name, first_name, last_name, patronymic,
    initials      — şəkil yoxdursa göstəriləcək baş hərflər (məs. «ƏE»)
    avatar_url    — BOŞ ola bilər (köhnə sistemin şəkil FAYLLARI köçmür)
    status        — active | blocked | archived | deleted
    email, phone, fin      — `people.view_contacts` yoxdursa BOŞ SƏTİR
    gender, birth_date, age — `people.view_demographics` yoxdursa boş/None
    kind          — "teacher" | "student"

müəllim sətrinin ƏLAVƏ sahələri:  role_name, role_label, title, unit_name,
                                  faculty_name, kafedra_name
tələbə sətrinin ƏLAVƏ sahələri:   group_name, program_name, program_label,
                                  admission_year, academic_status,
                                  faculty_name, kafedra_name

``GET analytics_url?<eyni filtrlər>`` → has_access, kind, total,
can_view_demographics, status[], gender[], age{}, breakdowns[], workload[],
filters{} — bax ``apps/accounts/views/people/analytics.py``.

``GET analytics_ai_url?<eyni filtrlər>`` → ``{ok, summary, cached, limit,
remaining, window}``; uğursuzluqda ``{ok: false, error}`` (200 ilə — bölmə
səssizcə gizlənir).

``GET options_url`` → has_access, faculties[], kafedras[], groups[], programs[],
subjects[], years[], seasons[] (hamısı ``{"id", "text"}``), gender_facets{},
status_facets{}, demographics_coverage{total, gender_known, birth_date_known},
can_filter_demographics.

``GET detail_url`` → has_access, person{…sətir sahələri…, profile_url, last_login,
date_joined, memberships[], is_teacher, teaching[], academic[], units[],
actions{block, unblock, grant_teacher, revoke_teacher}}.

``POST action_url`` (JSON) → {action, user_id, reason, unit_id?}; action ∈
{block, unblock, grant_teacher, revoke_teacher}. Cavab: ``{ok, action, result}``
və ya ``{ok: false, error, message}`` (403/404/409/400). ``block`` və
``revoke_teacher`` üçün ``reason`` MƏCBURİDİR (≥ ``min_reason_length``).

``POST action_url`` — AKADEMİK əməllər (hədəf ``record_id``, ``user_id`` DEYİL):

* ``{action: "transfer_group", record_id, group_id, reason}`` — ``reason``
  HƏMİŞƏ məcburidir; cavab ``{moved, created, from_group, to_group}``.
* ``{action: "set_academic_status", record_id, status, reason}`` — ``status`` ∈
  {enrolled, academic_leave, expelled, graduated}; ``expelled`` və
  ``academic_leave`` üçün ``reason`` məcburidir.

``GET card_url`` → ``{has_access, can_manage, person{…}, records[…], period,
status_options[]}``; ``records[]`` sətri: id, program_label, program_code,
group_name, faculty_name, kafedra_name, admission_year, course_label, status,
status_label, status_tone, enrollments[].

``GET preview_url?group=<uuid>`` → ``{ok, from_group, to_group, rows[], totals{},
warnings[], blocking[]}`` — bax ``apps/accounts/services/people/academic.py``.
"""

from __future__ import annotations

from django.urls import reverse
from django.utils.translation import pgettext_lazy

from apps.accounts.services import people
from apps.accounts.services.people.academic import STATUS_LABELS as ACADEMIC_STATUS_LABELS
from apps.accounts.services.people.actions import MAX_REASON_LENGTH, MIN_REASON_LENGTH
from apps.accounts.services.people.constants import AGE_UNKNOWN, DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from apps.organizations.permissions import get_permission_label as permission_label

_CTX = "accounts.people"

_SORT_LABELS = {
    "name": pgettext_lazy(_CTX, "Ad üzrə (A→Z)"),
    "-name": pgettext_lazy(_CTX, "Ad üzrə (Z→A)"),
    "unit": pgettext_lazy(_CTX, "Struktur üzrə"),
    "group": pgettext_lazy(_CTX, "Qrup üzrə"),
    "year": pgettext_lazy(_CTX, "Qəbul ili üzrə"),
    "newest": pgettext_lazy(_CTX, "Ən yeni"),
    "oldest": pgettext_lazy(_CTX, "Ən köhnə"),
}

_STATUS_LABELS = {
    "all": pgettext_lazy(_CTX, "Bütün statuslar"),
    "active": pgettext_lazy(_CTX, "Aktiv"),
    "blocked": pgettext_lazy(_CTX, "Dayandırılıb"),
    "archived": pgettext_lazy(_CTX, "Arxiv (məzun/xaric)"),
    "deleted": pgettext_lazy(_CTX, "Silinib"),
}

_GENDER_LABELS = {
    "male": pgettext_lazy(_CTX, "Kişi"),
    "female": pgettext_lazy(_CTX, "Qadın"),
    "unspecified": pgettext_lazy(_CTX, "Cinsi göstərilməyib"),
}

_AGE_UNKNOWN_LABEL = pgettext_lazy(_CTX, "Doğum tarixi göstərilməyib")

ACCESS_DENIED = pgettext_lazy(_CTX, "Bu bölmə üçün icazəniz yoxdur.")

#: Rola görə deyil, KATALOQA görə sütun dəsti; icazə süzgəci aşağıda tətbiq olunur.
_TEACHER_COLUMNS = ("person", "role", "faculty", "kafedra", "status", "contact", "demographics", "actions")
_STUDENT_COLUMNS = ("person", "group", "program", "faculty", "status", "contact", "demographics", "actions")

_SORT_KEYS = {
    "teachers": ("name", "-name", "unit", "newest", "oldest"),
    "students": ("name", "-name", "group", "year", "newest", "oldest"),
}


def _options(keys, labels):
    return [{"key": key, "label": labels[key]} for key in keys if key in labels]


def _columns_for(kind, actor):
    columns = _TEACHER_COLUMNS if kind == "teachers" else _STUDENT_COLUMNS
    visible = []
    for column in columns:
        if column == "contact" and not actor.can_view_contacts:
            continue
        if column == "demographics" and not actor.can_view_demographics:
            continue
        if column == "actions" and not (
            actor.can_manage_status or actor.can_manage_teacher_role or actor.can_manage_academic
        ):
            continue
        visible.append(column)
    return visible


def build_people_section(request, kind: str) -> dict:
    """``people-teachers`` / ``people-students`` bölməsinin context-i."""
    actor = people.resolve_actor(request)
    has_access = actor.can_view_teachers if kind == "teachers" else actor.can_view_students

    return {
        "people_section": {
            "kind": kind,
            "has_access": has_access,
            "access_denied_message": "" if has_access else ACCESS_DENIED,
            "organization": actor.organization,
            "can_view_contacts": actor.can_view_contacts,
            "can_view_demographics": actor.can_view_demographics,
            "can_manage_status": actor.can_manage_status,
            "can_manage_teacher_role": actor.can_manage_teacher_role,
            # İdarəetmə paneli YALNIZ tələbə kataloqunda mənalıdır: müəllimin
            # akademik qeydi yoxdur, ona görə müəllim kataloqunda bayraq həmişə
            # False-dur (düymə render edilmir, endpoint onsuz da 404 verir).
            "can_manage_academic": actor.can_manage_academic and kind == "students",
            "granted_permissions": [{"key": key, "label": permission_label(key)} for key in actor.granted_permissions],
            "list_url": reverse("accounts:people_list", kwargs={"kind": kind}),
            "analytics_url": reverse("accounts:people_analytics", kwargs={"kind": kind}),
            "analytics_ai_url": reverse("accounts:people_analytics_ai", kwargs={"kind": kind}),
            "options_url": reverse("accounts:people_options", kwargs={"kind": kind}),
            "action_url": reverse("accounts:people_action"),
            "detail_url_template": reverse("accounts:people_detail", kwargs={"user_id": 0}),
            "card_url_template": reverse("accounts:people_student_card", kwargs={"user_id": 0}),
            "groups_url": reverse("accounts:people_academic_groups"),
            "preview_url_template": reverse(
                "accounts:people_transfer_preview",
                kwargs={"record_id": "00000000-0000-0000-0000-000000000000"},
            ),
            "default_page_size": DEFAULT_PAGE_SIZE,
            "max_page_size": MAX_PAGE_SIZE,
            "min_reason_length": MIN_REASON_LENGTH,
            "max_reason_length": MAX_REASON_LENGTH,
            "sort_options": _options(_SORT_KEYS[kind], _SORT_LABELS),
            "status_options": _options(("all", "active", "blocked", "archived", "deleted"), _STATUS_LABELS),
            "gender_options": _options(("male", "female", "unspecified"), _GENDER_LABELS),
            "age_unknown_key": AGE_UNKNOWN,
            "age_unknown_label": _AGE_UNKNOWN_LABEL,
            "academic_status_options": [{"key": key, "label": label} for key, label in ACADEMIC_STATUS_LABELS.items()],
            "columns": _columns_for(kind, actor),
        }
    }


def build_people_teachers_section(request) -> dict:
    return build_people_section(request, "teachers")


def build_people_students_section(request) -> dict:
    return build_people_section(request, "students")


__all__ = [
    "ACCESS_DENIED",
    "build_people_section",
    "build_people_students_section",
    "build_people_teachers_section",
]
