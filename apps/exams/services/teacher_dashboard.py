"""
Müəllim paneli ("İmtahanlarım") üçün view-model qurucusu.

Verilmiş (artıq filtrlənmiş, annotate + prefetch edilmiş) imtahan siyahısını
status üzrə qruplaşdırır və KPI / kateqoriya sayğaclarını hazırlayır. Status
məntiqi tək mənbədəndir — `Exam.lifecycle_status`.

Niyə servisdə? `accounts/views/profile/main.py` onsuz da nəhəngdir; qruplaşdırma
domeninə (exams) aid olduğu üçün burada saxlanır, şablon yalnız render edir
(SOLID — view-model qurmaq ≠ render).
"""

from __future__ import annotations

from django.utils.translation import pgettext_lazy

from apps.exams.constants import (
    EXAM_CATEGORY_FILTER_ORDER,
    EXAM_CATEGORY_META,
    EXAM_STATUS_META,
    EXAM_STATUS_ORDER,
)
from apps.exams.models import Exam

# Status etiketləri + ipucu mətnləri (hesablanmış status üçün model choice yoxdur).
_STATUS_LABELS = {
    "active": pgettext_lazy("exams.dashboard.status", "label_active"),
    "scheduled": pgettext_lazy("exams.dashboard.status", "label_scheduled"),
    "draft": pgettext_lazy("exams.dashboard.status", "label_draft"),
    "archived": pgettext_lazy("exams.dashboard.status", "label_archived"),
}
_STATUS_HINTS = {
    "active": pgettext_lazy("exams.dashboard.status", "hint_active"),
    "scheduled": pgettext_lazy("exams.dashboard.status", "hint_scheduled"),
    "draft": pgettext_lazy("exams.dashboard.status", "hint_draft"),
    "archived": pgettext_lazy("exams.dashboard.status", "hint_archived"),
}


def build_teacher_exam_dashboard(
    exams,
    *,
    include_empty_categories: bool = True,
    status_counts: dict | None = None,
    category_counts_override: dict | None = None,
    total: int | None = None,
) -> dict:
    """
    `exams`: göstəriləcək Exam iterable (annotate/prefetch artıq tətbiq olunub).

    SƏHİFƏLƏMƏ İLƏ İSTİFADƏ: `exams` yalnız CARİ SƏHİFƏ olduqda KPI kartları və
    kateqoriya çipləri səhifə üzrə deyil, BÜTÜN filtrlənmiş dəst üzrə
    göstərilməlidir — əks halda «Aktiv: 12» yazılar, halbuki 150-dir. Ona görə
    çağıran tərəf `status_counts` / `category_counts` / `total` dəyərlərini
    SQL aqreqatı ilə hesablayıb ötürür; verilmədikdə köhnə davranış (siyahıdan
    hesablama) qalır.

    Qaytarır::

        {
          "status_groups": [ {key,label,hint,color,soft,deep,icon,count,exams}, ... ],
          "status_counts": {status_key: int, "all": int},
          "category_filters": [ {key,label,color,soft,deep,count}, ... ],
          "total": int,
        }
    """
    exam_list = list(exams)
    category_label_map = dict(Exam.EXAM_TYPE_EXTENDED_CHOICES)

    grouped: dict[str, list] = {key: [] for key in EXAM_STATUS_ORDER}
    category_counts: dict[str, int] = {key: 0 for key in EXAM_CATEGORY_FILTER_ORDER}

    for exam in exam_list:
        status_key = exam.lifecycle_status
        grouped.setdefault(status_key, []).append(exam)
        if exam.exam_type_extended in category_counts:
            category_counts[exam.exam_type_extended] += 1

    if status_counts is None:
        status_counts = {key: len(grouped.get(key, [])) for key in EXAM_STATUS_ORDER}
        status_counts["all"] = len(exam_list)
    else:
        status_counts = {key: status_counts.get(key, 0) for key in EXAM_STATUS_ORDER} | {
            "all": status_counts.get("all", sum(status_counts.get(k, 0) for k in EXAM_STATUS_ORDER))
        }
    if category_counts_override is not None:
        category_counts = {key: category_counts_override.get(key, 0) for key in EXAM_CATEGORY_FILTER_ORDER}

    def _descriptor(key):
        meta = EXAM_STATUS_META.get(key, {})
        return {
            "key": key,
            "label": _STATUS_LABELS.get(key, key),
            "hint": _STATUS_HINTS.get(key, ""),
            "color": meta.get("color", "#64748B"),
            "soft": meta.get("soft", "#F1F4F9"),
            "deep": meta.get("deep", "#475569"),
            "icon": meta.get("icon", "fa-file-alt"),
            "count": status_counts[key],
        }

    # KPI zolağı — bütün 4 status (boş olsa belə, say 0 göstərilir).
    status_kpis = [_descriptor(key) for key in EXAM_STATUS_ORDER]

    # Bölmələr — yalnız doludan olanlar (boş status bölməsi göstərilmir).
    status_groups = []
    for key in EXAM_STATUS_ORDER:
        items = grouped.get(key, [])
        if not items:
            continue
        descriptor = _descriptor(key)
        descriptor["exams"] = items
        status_groups.append(descriptor)

    category_filters = []
    for key in EXAM_CATEGORY_FILTER_ORDER:
        # Müəllim final/midterm YARADA bilmədiyi üçün boş kateqoriya çipi ona
        # göstərilmir (köhnə imtahanı olan müəllimdə çip sayı ilə birgə qalır).
        if not include_empty_categories and category_counts.get(key, 0) == 0:
            continue
        meta = EXAM_CATEGORY_META.get(key, {})
        category_filters.append(
            {
                "key": key,
                "label": category_label_map.get(key, key),
                "color": meta.get("color", "#64748B"),
                "soft": meta.get("soft", "#F1F4F9"),
                "deep": meta.get("deep", "#475569"),
                "count": category_counts.get(key, 0),
            }
        )

    return {
        "status_kpis": status_kpis,
        "status_groups": status_groups,
        "status_counts": status_counts,
        "category_filters": category_filters,
        "total": len(exam_list) if total is None else total,
    }
