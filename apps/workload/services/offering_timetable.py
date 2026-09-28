"""Açılışın müəllimi dəyişəndə cədvəl toqquşmasının yenidən yoxlanması (Audit 2026-09-28 W4).

Tədris yükü sinxronu (``offering_sync._Sync._update``) açılışın ``instructor``-unu
dəyişir.  Açılışın cədvəl slotlarında öz müəllimi YOXDURSA (``ScheduleSlot.instructor``
boşdur), slotu faktiki aparan şəxs jurnal sahibidir — yəni yeni müəllim həmin
saatlara avtomatik düşür.  Yeni müəllimin o saatda başqa dərsi varsa bu, SƏSSİZ
ikiqat yüklənmə idi.

Burada registrar-ın cədvəl konflikt mühərriki (``apps.registrar.public.schedule_conflicts``)
açılışın canlı slotları üçün yeni müəllimlə yenidən işlədilir.  Toqquşmalar
PARKLANMIR (tələbə cədvəlindən dərs silinməsin) — sinxron hesabatına, audit
jurnalına və loga yazılır, bölgü səthi isə istifadəçiyə xəbərdarlıq göstərir.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def instructor_change_conflicts(offering, new_instructor_id) -> list[dict]:
    """Yeni müəllimin bu açılışın slotlarında yaratdığı MÜƏLLİM toqquşmaları.

    Yalnız slotu açılışın müəllimi aparanda (slotun öz müəllimi boşdur) yoxlanılır;
    qrup/otaq toqquşmaları müəllim dəyişikliyindən asılı deyil, ona görə sayılmır.
    """
    if not new_instructor_id or offering is None or not offering.pk:
        return []
    from apps.registrar.public import schedule_conflicts

    own_slots = schedule_conflicts.live_slots(offering.organization).filter(
        offering_id=offering.pk, instructor__isnull=True
    )
    found: list[dict] = []
    for slot in own_slots:
        conflicts = schedule_conflicts.detect(
            organization=offering.organization,
            weekday=slot.weekday,
            start_time=slot.start_time,
            end_time=slot.end_time,
            week_type=slot.week_type,
            instructor_id=new_instructor_id,
            exclude_ids=(slot.pk,),
            period_id=offering.period_id,
            subject_id=offering.subject_id,
            kind=slot.kind,
        )
        for conflict in conflicts:
            if conflict.get("kind") != schedule_conflicts.KIND_TEACHER:
                continue
            found.append({**conflict, "offering_id": str(offering.pk), "own_slot_id": str(slot.pk)})
    if found:
        logger.warning(
            "workload: instructor change on offering %s double-books teacher %s (%d slot(s))",
            offering.pk,
            new_instructor_id,
            len(found),
        )
    return found


__all__ = ["instructor_change_conflicts"]
