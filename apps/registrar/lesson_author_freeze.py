"""Jurnal sahibi dəyişəndə keçilmiş dərslər KÖHNƏ müəllimdə qalır (sahib 2026-11-13).

``Lesson.instructor`` boşdursa dərs «açılışın cari sahibi» kimi oxunur (``lessons_log.scoped_lessons``). Ona görə
fənn təhvili / dərs yükü bölgüsü / cədvəl redaktoru sahibi dəyişəndə köhnə müəllimin keçdiyi dərslər YENİ sahibə
«sürüşür» — köhnə müəllim «Keçilmiş dərslər»də görmür, ödənişi saat üzrə hesablanır. Sahiblik dəyişməzdən ƏVVƏL
həmin açılışın boş-müəllimli (bu günə qədərki) dərsləri çıxan sahibə yazılır. Gələcək tarixli dərs toxunulmur.

Çağırılır: ``journal_transfer._move_owner`` (``update()`` siqnal işlətmir) və ``CourseOffering`` ``pre_save``
siqnalı (``save()`` ilə sahib dəyişən bütün yollar: yük sinxronu, vakant doldurma, cədvəl redaktoru …).
"""

from __future__ import annotations

from django.utils import timezone


def freeze(offering_id, owner_id) -> int:
    """Açılışın boş-müəllimli keçilmiş dərsləri ``owner_id``-yə; yazılan dərs sayı."""
    if not offering_id or not owner_id:
        return 0
    from .models import Lesson

    return Lesson.objects.filter(
        offering_id=offering_id, instructor__isnull=True, date__lte=timezone.localdate()
    ).update(instructor_id=owner_id, updated_at=timezone.now())


def offering_pre_save(sender, instance, raw=False, update_fields=None, **kwargs) -> None:
    """``save()`` sahibi dəyişirsə köhnə sahibin dərsləri dondurulur (yeni açılış / sahibsiz → heç nə)."""
    if raw or instance._state.adding or not instance.pk:
        return
    if update_fields is not None and not ({"instructor", "instructor_id"} & set(update_fields)):
        return
    old_id = sender.objects.filter(pk=instance.pk).values_list("instructor_id", flat=True).first()
    if old_id is not None and old_id != instance.instructor_id:
        freeze(instance.pk, old_id)


__all__ = ["freeze", "offering_pre_save"]
