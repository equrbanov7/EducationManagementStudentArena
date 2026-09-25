"""«Sorğu nəticələri» — qısa sual adları, Likert etiketləri, tab/sıralama sabitləri.

Sual mətnləri uzundur (qrafik oxuna sığmır) — qrafiklər və cədvəl başlıqları
bu qısa adları işlədir, tam mətn cədvəldə/tooltip-də qalır. Tenantın öz
yazdığı (defolt dəstdə olmayan) sualın qısa adı mətninin qısaldılmasıdır.
"""

from __future__ import annotations

from django.utils.translation import pgettext, pgettext_lazy

from ..defaults import LIKERT_LABELS

CTX = "surveys.results"

SHORT_LABELS = {
    "organization": pgettext_lazy(CTX, "Hazırlıq və plan"),
    "clarity": pgettext_lazy(CTX, "Aydın izah"),
    "syllabus": pgettext_lazy(CTX, "Sillabusa əməl"),
    "punctuality": pgettext_lazy(CTX, "Vaxtında başlama"),
    "engagement": pgettext_lazy(CTX, "Fəal iştirak"),
    "respect": pgettext_lazy(CTX, "Hörmət və ədalət"),
    "fair_assessment": pgettext_lazy(CTX, "Ədalətli qiymətləndirmə"),
    "feedback": pgettext_lazy(CTX, "Vaxtında rəy"),
    "availability": pgettext_lazy(CTX, "Əlçatanlıq"),
    "relevance": pgettext_lazy(CTX, "Praktika ilə əlaqə"),
    "materials": pgettext_lazy(CTX, "Dərs materialları"),
    "learning": pgettext_lazy(CTX, "Öyrənmə nəticəsi"),
    "workload": pgettext_lazy(CTX, "İş yükü"),
    "overall": pgettext_lazy(CTX, "Ümumi bal (1–10)"),
    "recommend": pgettext_lazy(CTX, "Tövsiyə"),
    "satisfaction": pgettext_lazy(CTX, "Ümumi məmnunluq"),
    "facilities": pgettext_lazy(CTX, "Tədris şəraiti"),
    "strengths": pgettext_lazy(CTX, "Güclü cəhətlər"),
    "improve": pgettext_lazy(CTX, "Təkliflər"),
    "suggestions": pgettext_lazy(CTX, "Universitet üçün təkliflər"),
}

TAB_OVERVIEW = "overview"
TAB_TEACHERS = "teachers"
TAB_GENERAL = "general"
TABS = (TAB_OVERVIEW, TAB_TEACHERS, TAB_GENERAL)

TAB_LABELS = {
    TAB_OVERVIEW: pgettext_lazy(CTX, "Ümumi baxış"),
    TAB_TEACHERS: pgettext_lazy(CTX, "Müəllimlər"),
    TAB_GENERAL: pgettext_lazy(CTX, "Ümumi təkliflər"),
}

#: Müəllim cədvəlinin sıralama açarları (server ilkin sıranı bu açarla verir).
SORT_KEYS = (
    "avg_overall",
    "likert_index",
    "recommend_top2",
    "n",
    "rate",
    "delta_department_overall",
    "question_avg",
    "teacher_name",
)
DEFAULT_SORT = "-avg_overall"

#: «Minimum cavab» süzgəcinin seçimləri (0 — hamısı).
MIN_N_CHOICES = (0, 5, 10, 20, 50, 100)

#: Müəllim cədvəlinin səhifə ölçüsü (kliyent səhifələməsi).
PAGE_SIZE = 25


def short_label(code, text="") -> str:
    """Qısa sual adı; tenantın öz sualı üçün mətnin ilk ~32 simvolu."""
    label = SHORT_LABELS.get(code)
    if label is not None:
        return str(label)
    text = str(text or code or "")
    return text if len(text) <= 32 else text[:31].rstrip() + "…"


def likert_labels() -> list:
    """``[(1, "Tamamilə razı deyiləm"), …]`` — F1-in ``surveys.scale`` tərcümələri ilə."""
    return [(score, pgettext("surveys.scale", label)) for score, label in LIKERT_LABELS]
