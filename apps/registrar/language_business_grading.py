"""«Xarici dildə işgüzar kommunikasiya» profili — registrar tərəfi (sahib 2026-11-22).

Qayda, ad şablonu və tavanlar :mod:`core.language_business_rule`-dadır. Profil xarici dil SƏVİYYƏ fənlərinin alt
dəstidir (:mod:`apps.registrar.language_level_grading` — midterm 10, imtahan 70, 11-ci q/b), ona görə buradakı
funksiyalar yalnız fərqi verir:

* :func:`is_business` — açılış profilə düşürmü (səviyyə dövr qapısı + ad + RİM açarı);
* :func:`entry_parts` — giriş balı = davamiyyət + midterm + (praktiki məşğələ ortası + sərbəst iş, ≤ 10);
* :func:`teacher_cell_open` / :func:`teacher_entries` — İmtahan Mərkəzinin pəncərəsi açıq olmayanda müəllimin
  midterm xanası: boş xana həmişə, yazılmış xana jurnal balının redaktə müddəti ərzində
  (``gradebook.mark_edit_window``); imtahandan avtomatik yazılmış xana heç vaxt (əvvəlki qayda).
"""

from __future__ import annotations

from decimal import Decimal

from django.utils import timezone

from core import language_business_rule as rule

ZERO = Decimal("0")


def is_business(offering) -> bool:
    """Açılış «işgüzar kommunikasiya» profilindədirmi (səviyyə qaydası qüvvədədir + ad + RİM açarı)."""
    from .language_level_grading import is_level

    if offering is None or not is_level(offering):
        return False
    return rule.applies_to_name(rule.offering_subject_name(offering))


def selfwork_points_for(enrollment, selfwork_points=None) -> Decimal:
    """Sərbəst iş cəmi (≤ 10) — toplu dəst verməyibsə kanonik tək-sətir oxu (:mod:`selfwork_points`)."""
    if selfwork_points is None:
        from .selfwork_points import selfwork_total_for

        selfwork_points = selfwork_total_for(enrollment)
    value = Decimal(str(selfwork_points or 0))
    return max(ZERO, min(value, Decimal(rule.SELFWORK_MAX)))


def entry_parts(*, attendance, practical, midterm, selfwork, barred):
    """Profilin :class:`entry_standard.EntryParts`-ı (sahib 2026-11-22 «Praktiki məşğələ balını hesabla seminar kimi»):
    üçüncü hissə = praktiki məşğələ ortası (səviyyə qaydası kimi, /10) + sərbəst iş, cəmi 10-la kəsilir — bir sütun
    («Praktiki / sərbəst iş», ``practical_selfwork``); ``activity_parts`` = (praktiki, sərbəst iş) yalnız görünüşdür."""
    from . import entry_standard
    from .gradebook_components import round_score

    practical = max(ZERO, practical)
    combined = min(practical + selfwork, Decimal(rule.PRACTICAL_SELFWORK_MAX))
    return entry_standard.EntryParts(
        attendance=attendance,
        activity=combined,
        midterm=midterm,
        selfwork=ZERO,
        total=round_score(attendance + combined + midterm),
        attendance_barred=barred,
        midterm_max=Decimal(rule.MIDTERM_MAX),
        selfwork_active=False,
        practical=True,
        practical_selfwork=True,
        activity_parts=(practical, selfwork),
    )


def teacher_cell_open(score_row, now=None) -> bool:
    """Pəncərəsiz müəllim xanası: boş → açıq; imtahandan avtomatik → bağlı; yazılmış → redaktə müddəti ərzində."""
    if score_row is None:
        return True
    if getattr(score_row, "exam_source", None):
        return False
    from .journal_edit_windows import mark_edit_window

    created = getattr(score_row, "created_at", None)
    return created is None or ((now or timezone.now()) - created) <= mark_edit_window()


def teacher_entries(offering, component, entries):
    """``kollokvium_save``-in pəncərəsiz yolu: redaktə müddəti bitmiş / avtomatik xanalar atılır.

    Qaytarır ``(qəbul olunan sətirlər, atılan var?)``. Yazı ``save_component_scores(bypass_edit_window=True)`` ilə
    gedir (KOLLOKVIUM növü yalnız o yolla yazılır), ona görə müddət qaydası burada tətbiq olunur."""
    from .models import ComponentScore

    rows = {
        str(cs.enrollment_id): cs
        for cs in ComponentScore.objects.filter(component=component, enrollment__offering=offering).only(
            "enrollment_id", "created_at", "exam_source", "score"
        )
    }
    now = timezone.now()
    kept = [entry for entry in entries if teacher_cell_open(rows.get(str(entry["enrollment_id"])), now)]
    return kept, len(kept) != len(entries)


def merge_midterm_entries(offering, components, entries, closed):
    """``kollokvium_save``: pəncərəsi açıq sütunların sətirləri (``entries``) + pəncərəsi bağlı sütunların sətirləri
    (``closed``). Profildə bağlı pəncərəli ƏSAS Midterm sütunu müəllimə açıqdır (:func:`teacher_entries`); qalanı
    əvvəlki kimi yazılmır. Qaytarır ``(yazılacaq sətirlər, nəsə yazılmadı?)``."""
    if not closed:
        return entries, False
    if not components or not is_business(offering):
        return entries, True
    primary = str(components[0].id)
    own = [entry for entry in closed if str(entry["component_id"]) == primary]
    kept, dropped = teacher_entries(offering, components[0], own) if own else ([], False)
    return [*entries, *kept], dropped or len(own) != len(closed)


__all__ = [
    "entry_parts",
    "merge_midterm_entries",
    "is_business",
    "selfwork_points_for",
    "teacher_cell_open",
    "teacher_entries",
]
