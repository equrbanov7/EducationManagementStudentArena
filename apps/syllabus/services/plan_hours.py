"""Plan saatı yazıları — ``set_plan_hours`` və ``seed_week_hours``.

``drafts.py``-dan ayrılıb (modul ölçüsü büdcəsi).  Audit 2026-09-28 SYL-3:
hər iki yazı versiyanı ``select_for_update()`` ilə YENİDƏN oxuyur və statusu
KİLİDLİ sətirdə yoxlayır — göndərmə ilə yarışan köhnə (stale) obyekt artıq
SUBMITTED/APPROVED versiyaya yaza bilmir.
"""

from __future__ import annotations

from django.db import transaction

from ..constants import EDITABLE_STATUSES, LESSON_HOUR_KINDS, SectionKey
from ..models import SyllabusSection, SyllabusVersion
from ..week_plan import seed_missing_hours
from .drafts import recompute_completion


def lock_editable_version(version):
    """Versiyanı kilidləyib YENİDƏN oxuyur; redaktəyə açıq deyilsə ``None``.

    Çağıran tərəf tranzaksiya daxilində olmalıdır.
    """
    locked = SyllabusVersion.objects.select_for_update(of=("self",)).filter(pk=version.pk).first()
    if locked is None or locked.status not in EDITABLE_STATUSES:
        return None
    return locked


def _sync_caller(version, locked) -> None:
    """Çağıranın obyektini kilidli sətirlə uzlaşdırır (context yenidən qurulmasın)."""
    version.plan_hours = locked.plan_hours
    version.completion_percent = locked.completion_percent
    version.status = locked.status


@transaction.atomic
def set_plan_hours(version, hours: dict | None):
    """Tədris planından gələn auditoriya saatı bölgüsünü versiyaya yazır.

    README §8/11: «Auditoriya saatlarının cəmi tədris planındakı saatla üst-üstə
    düşməlidir; uyğunsuzluq təsdiqə göndərməni bloklayır.»  Bölgünün MƏNBƏYİ
    ``registrar.CurriculumSubject``-in TƏSDİQLƏNMİŞ plan sətridir; onu bu modula
    gətirən glue accounts/registrar qatındadır (sillabus registrar-ı import
    etmir).

    Yalnız REDAKTƏYƏ AÇIQ versiyaya yazılır — təsdiqlənmiş versiya immutable-dır
    (README §8/1), plan sonradan dəyişsə belə tarixi qeyd toxunulmaz qalır.
    """
    if version.status not in EDITABLE_STATUSES:
        return version
    cleaned = {}
    for kind in LESSON_HOUR_KINDS:
        try:
            value = int((hours or {}).get(kind) or 0)
        except (TypeError, ValueError):
            value = 0
        if value > 0:
            cleaned[kind] = value
    locked = lock_editable_version(version)
    if locked is None:
        return version
    if (locked.plan_hours or {}) == cleaned:
        _sync_caller(version, locked)
        return version
    SyllabusVersion.objects.filter(pk=locked.pk).update(plan_hours=cleaned)
    locked.plan_hours = cleaned
    recompute_completion(locked)
    _sync_caller(version, locked)
    return version


@transaction.atomic
def seed_week_hours(version, plan_hours=None) -> bool:
    """Həftəlik cədvəlin saatını PLANDAN standart bölgü ilə doldurur (bir dəfə).

    Sahib 2026-09-21: sətir sayı və saat özü tənzimlənsin.  Yalnız cəmi 0 olan
    dərs növünə yazılır (təzə qaralama); müəllimin yazdığı bölgüyə toxunulmur.
    Redaktəyə açıq olmayan versiya dəyişmir.  Qayıdış: nəsə yazıldısa ``True``.
    """
    if version.status not in EDITABLE_STATUSES:
        return False
    locked = lock_editable_version(version)
    if locked is None:
        return False
    hours = plan_hours if plan_hours is not None else (locked.plan_hours or {})
    if not hours:
        return False
    row = SyllabusSection.objects.select_for_update().filter(version=locked, section_id=SectionKey.WEEK.value).first()
    if row is None:
        return False
    data = dict(row.data or {})
    rows, changed = seed_missing_hours(data.get("rows") or [], hours)
    if not changed:
        return False
    data["rows"] = rows
    row.data = data
    row.revision += 1
    row.save(update_fields=["data", "revision", "updated_at"])
    recompute_completion(locked)
    _sync_caller(version, locked)
    return True


__all__ = ["lock_editable_version", "seed_week_hours", "set_plan_hours"]
