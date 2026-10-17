"""«Dəyərləndirilmiş nəticələr» bölməsinin təqdimat qatı (yenidən dizayn 2026-10-17).

``build_review_results_context`` siyahını kollektordan alır; burada yalnız ekranın
özü qurulur: KPI kartları, filtr paneli sahələri, boş vəziyyət mətni və görünən
səhifənin sətir bəzəkləri (baş hərflər, növ nişanı, apellyasiya statusu).

SORĞU QAYDASI: KPI-lər artıq yaddaşdakı siyahıdan sayılır (0 sorğu); apellyasiya
statusu bütün süzülmüş imtahan cəhdləri üçün TƏK sorğu ilə gəlir
(``appeal_status_by_attempt``). Orta bal / keçid faizi QƏSDƏN yoxdur: test balı
yalnız görünən 15 sətir üçün hesablanır (2026-10-07 perf qərarı) — bütün tarixçə
üzrə orta bal hər açılışda bütün cavab sətirlərini yükləmək deməkdir.
"""

from __future__ import annotations

from datetime import timedelta

from django.utils import timezone
from django.utils.translation import pgettext

from apps.accounts.views._dashboard_helpers.evaluated_review import PERIOD_FILTERS
from apps.accounts.views._helpers.task_kind_visibility import hidden_task_filters

CTX = "accounts.review_results"
RECENT_DAYS = 7

#: Sətir nişanı: açar → (CSS modifikatoru, Font Awesome ikonu).
TYPE_META = {
    "test": ("test", "fa-list-ul"),
    "written": ("written", "fa-pen-fancy"),
    "coding": ("coding", "fa-code"),
    "assignment": ("assignment", "fa-file-signature"),
    "project": ("project", "fa-diagram-project"),
    "lab": ("lab", "fa-flask"),
}

_OPEN_APPEAL_TONE = "warning"


def _type_label(item):
    if item["type"] == "exam":
        return item.get("exam_kind_label") or pgettext("profile.pending_review", "type_exam")
    return {
        "assignment": pgettext("profile.pending_review", "type_assignment"),
        "project": pgettext("profile.pending_review", "type_project"),
    }.get(item["type"], pgettext("profile.pending_review", "type_lab"))


def _initials(user):
    first = (getattr(user, "first_name", "") or "").strip()
    last = (getattr(user, "last_name", "") or "").strip()
    letters = (first[:1] + last[:1]) or (getattr(user, "username", "") or "?")[:2]
    return letters.upper()


def _item_date(item):
    return item.get("reviewed_at") or item.get("submitted_at")


def decorate_rows(page_items, appeal_map):
    """Görünən səhifənin sətirlərinə ekran sahələri əlavə edir (sorğusuz)."""
    for item in page_items:
        student = item["student"]
        key = item.get("exam_kind") if item["type"] == "exam" else item["type"]
        modifier, icon = TYPE_META.get(key or "", ("exam", "fa-file-alt"))
        item["student_display"] = student.get_full_name() or student.username
        item["initials"] = _initials(student)
        item["type_modifier"] = modifier
        item["type_icon"] = icon
        item["type_label"] = _type_label(item)
        item["is_exam"] = item["type"] == "exam"
        item["row_date"] = _item_date(item)
        appeal = appeal_map.get(item.get("attempt_id")) if item["type"] == "exam" else None
        if appeal:
            appeal = {**appeal, "tone": "neutral" if appeal["is_final"] else _OPEN_APPEAL_TONE}
        item["appeal"] = appeal
    return page_items


def build_kpi_tiles(items, appeal_map):
    since = timezone.now() - timedelta(days=RECENT_DAYS)
    exam_count = sum(1 for item in items if item["type"] == "exam")
    recent = sum(1 for item in items if _item_date(item) and _item_date(item) >= since)
    students = {item["student"].pk for item in items}
    groups = {item.get("group_name") for item in items if item.get("group_name")}
    open_appeals = sum(1 for row in appeal_map.values() if not row["is_final"])
    return [
        {
            "label": pgettext(CTX, "Dəyərləndirilib"),
            "value": len(items),
            "note": pgettext(CTX, "İmtahan: %(exams)s · digər iş: %(other)s")
            % {"exams": exam_count, "other": len(items) - exam_count},
            "tone": "accent-primary",
        },
        {
            "label": pgettext(CTX, "Son 7 gün"),
            "value": recent,
            "note": pgettext(CTX, "bu həftə qiymətləndirilən"),
            "tone": "accent-success",
        },
        {
            "label": pgettext(CTX, "Tələbə"),
            "value": len(students),
            "note": pgettext(CTX, "Qrup: %(n)s") % {"n": len(groups)},
        },
        {
            "label": pgettext(CTX, "Apellyasiya"),
            "value": len(appeal_map),
            "note": pgettext(CTX, "Açıq: %(n)s") % {"n": open_appeals},
            "tone": "accent-warning" if open_appeals else "",
        },
    ]


def _type_options():
    hidden = hidden_task_filters("review-results")
    options = [
        {"value": "all", "label": pgettext("profile.pending_review", "type_all")},
        {"value": "exams", "label": pgettext(CTX, "İmtahanlar (hamısı)")},
        {"value": "exam_test", "label": pgettext(CTX, "İmtahan — test")},
        {"value": "exam_written", "label": pgettext(CTX, "İmtahan — yazılı")},
    ]
    if "assignments" not in hidden:
        options.append({"value": "assignments", "label": pgettext("profile.pending_review", "type_assignment")})
    if "projects" not in hidden:
        options.append({"value": "projects", "label": pgettext("profile.pending_review", "type_project")})
    options.append({"value": "labs", "label": pgettext("profile.pending_review", "type_lab")})
    return options


def build_filter_fields(*, search, filter_type, group, groups, period, order):
    period_labels = {
        "7": pgettext(CTX, "Son 7 gün"),
        "30": pgettext(CTX, "Son 30 gün"),
        "90": pgettext(CTX, "Son 90 gün"),
    }
    return [
        {
            "name": "evaluated_search",
            "label": pgettext(CTX, "Axtarış"),
            "kind": "search",
            "wide": True,
            "value": search,
            "placeholder": pgettext(CTX, "Tələbə, imtahan və ya fənn"),
        },
        {
            "name": "evaluated_type",
            "label": pgettext(CTX, "Növ"),
            "kind": "select",
            "value": filter_type,
            "default": "all",
            "options": _type_options(),
        },
        {
            "name": "evaluated_group",
            "label": pgettext(CTX, "Qrup"),
            "kind": "select",
            "value": group,
            "searchable": len(groups) > 8,
            "options": [{"value": "", "label": pgettext(CTX, "Bütün qruplar")}]
            + [{"value": name, "label": name} for name in groups],
        },
        {
            "name": "evaluated_period",
            "label": pgettext(CTX, "Dövr"),
            "kind": "select",
            "value": period,
            "options": [{"value": "", "label": pgettext(CTX, "Bütün vaxtlar")}]
            + [{"value": key, "label": period_labels[key]} for key in PERIOD_FILTERS],
        },
        {
            "name": "evaluated_submitted_order",
            "label": pgettext(CTX, "Sıralama"),
            "kind": "select",
            "value": order,
            "default": "newest",
            "options": [
                {"value": "newest", "label": pgettext(CTX, "Ən yenisi əvvəl")},
                {"value": "oldest", "label": pgettext(CTX, "Ən köhnəsi əvvəl")},
            ],
        },
    ]


def empty_state(*, filtered):
    if filtered:
        return {
            "icon": "fa-filter-circle-xmark",
            "title": pgettext(CTX, "Filtrə uyğun nəticə tapılmadı"),
            "body": pgettext(CTX, "Axtarışı qısaldın və ya «Sıfırla» ilə bütün nəticələrə qayıdın."),
        }
    return {
        "icon": "fa-clipboard-check",
        "title": pgettext(CTX, "Hələ dəyərləndirilmiş nəticə yoxdur"),
        "body": pgettext(
            CTX,
            "Yoxlanılan işlər redaktə pəncərəsi bağlandıqdan sonra burada görünür; test imtahanları — təhvil verilən kimi.",
        ),
    }
