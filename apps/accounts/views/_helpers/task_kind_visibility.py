"""Kurs sistemi tapşırıq növlərinin kabinetdə görünüşü — 2026-10-13 (rol auditi B12).

Sahib qaydası 2026-10-10: «sərbəst iş ləğv olur — kodu saxla, lazım olsa yenidən yazmadan əlavə edək».
Jurnal/sillabus tərəfi ``core.academic_rules`` ilə artıq qapılıdır, amma kurs sisteminin bölmələri
(müəllim ``pending-review`` / ``review-results``, tələbə ``my-results`` / ``pending-answers``) kurs
tapşırığını («Sərbəst iş» — ``assignments.Submission``) və layihəni («Kurs işi» — ``projects.ProjectSubmission``)
göstərməyə davam edirdi. Bu modul həmin iki növün sətir/tab/badge-lərini RİM tənzimləməsi ilə gizlədir
(``academic.selfwork_enabled`` / ``academic.coursework_enabled``) — data silinmir, bayraq yandırılanda geri gəlir.

İmtahanlar və lab işləri sərbəst iş DEYİL — onlar həmişə qalır; ona görə heç bir bölmə bütövlükdə boşalmır,
yalnız içindəki sətirlər/tablar süzülür. Kurs kartları (``assigned-courses``) konteynerdir (lab, imtahan da
ola bilər) — o bölmə toxunulmur.

Kurs sistemi semestrə bağlı deyil (``courses.Course``-da dövr yoxdur), ona görə dövr-asılı
``selfwork_active_for_period`` yox, CARİ qayda oxunur.
"""

from __future__ import annotations

from core import academic_rules

#: Bölmə → həmin bölmədə «Sərbəst iş» və «Kurs işi» tab/kateqoriya açarı (tarixən fərqli adlanır:
#: tələbə tərəfində tapşırıq ``courses``, layihə ``independent`` kateqoriyasıdır).
_SECTION_TASK_KEYS = {
    "pending-review": {"selfwork": "assignments", "coursework": "projects"},
    "review-results": {"selfwork": "assignments", "coursework": "projects"},
    "my-results": {"selfwork": "courses", "coursework": "independent"},
    "pending-answers": {"selfwork": "courses", "coursework": "independent"},
}


def selfwork_tasks_visible() -> bool:
    """Kurs sisteminin «Sərbəst iş» (kurs tapşırığı) sətirləri kabinetdə görünürmü."""
    return academic_rules.selfwork_enabled()


def coursework_tasks_visible() -> bool:
    """Kurs sisteminin «Kurs işi» (layihə) sətirləri kabinetdə görünürmü."""
    return academic_rules.coursework_enabled()


def task_kind_visibility() -> dict[str, bool]:
    """Şablonlar üçün: ``{"selfwork": bool, "coursework": bool}``."""
    return {"selfwork": selfwork_tasks_visible(), "coursework": coursework_tasks_visible()}


def hidden_task_filters(section: str) -> frozenset[str]:
    """Bu bölmədə GİZLƏDİLMİŞ tab/kateqoriya açarları (bayraq söndürülübsə)."""
    keys = _SECTION_TASK_KEYS.get(section)
    if not keys:
        return frozenset()
    hidden = set()
    if not selfwork_tasks_visible():
        hidden.add(keys["selfwork"])
    if not coursework_tasks_visible():
        hidden.add(keys["coursework"])
    return frozenset(hidden)


def visible_task_filter(section: str, value: str, *, default: str = "all") -> str:
    """Gizli tab URL-də qalıbsa (köhnə link, əl ilə yazılmış ``?type=``) → defolt tab.

    Əks halda boş, amma «Sərbəst iş» adlı aktiv tab görünərdi."""
    return default if value in hidden_task_filters(section) else value


__all__ = [
    "coursework_tasks_visible",
    "hidden_task_filters",
    "selfwork_tasks_visible",
    "task_kind_visibility",
    "visible_task_filter",
]
