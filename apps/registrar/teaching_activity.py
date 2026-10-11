"""Müəllim başına tədris fəaliyyəti aqreqatı — «Kadr analitikası» üçün (sahib 2026-10-11).

``apps.accounts`` jurnal modellərinə birbaşa toxunmur (kontekst qapısı, ``scripts/context_map.py``):
bu funksiya ``registrar.public`` müqaviləsi ilə çağırılır və yalnız hazır rəqəmlər qaytarır.

* jurnal — seçilmiş tədris ilinin AKTİV açılışı (``CourseOffering.instructor``);
* plan saat — açılışın semestr kontakt saatı (``lesson_hours``);
* keçirilmiş dərs / saat — jurnala yazılmış dərslər; dərsin öz müəllimi (``Lesson.instructor``,
  bölünmüş fənn) varsa ona, yoxsa açılışın müəlliminə yazılır.

Sorğu sayı: 2 (GROUP BY), müəllim sayından asılı deyil.
"""

from __future__ import annotations

from django.db.models import Count, Sum
from django.db.models.functions import Coalesce

from .models import CourseOffering, Lesson


def instructor_activity(*, organization, academic_year: str, teacher_ids) -> dict:
    """{müəllim id: {journals, planned_hours, lessons, held_hours}} — yalnız fəaliyyəti olanlar."""
    ids = [pk for pk in teacher_ids if pk]
    out: dict = {}
    if not ids or not academic_year:
        return out

    def item(pk):
        return out.setdefault(pk, {"journals": 0, "planned_hours": 0, "lessons": 0, "held_hours": 0})

    offerings = (
        CourseOffering.objects.filter(
            organization=organization, is_active=True, period__academic_year=academic_year, instructor_id__in=ids
        )
        .values("instructor_id")
        .annotate(journals=Count("pk"), planned=Sum("lesson_hours"))
        .order_by()
    )
    for row in offerings:
        entry = item(row["instructor_id"])
        entry["journals"] = row["journals"] or 0
        entry["planned_hours"] = int(row["planned"] or 0)
    lessons = (
        Lesson.objects.filter(
            organization=organization, offering__is_active=True, offering__period__academic_year=academic_year
        )
        .annotate(teacher=Coalesce("instructor_id", "offering__instructor_id"))
        .filter(teacher__in=ids)
        .values("teacher")
        .annotate(lessons=Count("pk"), hours=Sum("hours"))
        .order_by()
    )
    for row in lessons:
        entry = item(row["teacher"])
        entry["lessons"] = row["lessons"] or 0
        entry["held_hours"] = int(row["hours"] or 0)
    return out


__all__ = ["instructor_activity"]
