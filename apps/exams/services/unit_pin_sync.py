"""Reyestr qrupu üzvlüyü dəyişəndə final/midterm PIN-lərinin sinxronu.

2026-09-14 (W5 `w5left`, tapşırıq 3; W4 hesabatı «qalanlar» 4). İmtahan
reyestr qrupuna (`Exam.allowed_units`) təyin olunanda PIN-lər həmin andakı
tələbələrə verilir; sonradan qrupa köçürülən / yeni qeydlə qrupa düşən
tələbənin PIN-i imtahan yenidən saxlananadək YOX idi (tələbə kabinetdə PIN
görmür, imtahana girə bilmir). İki qapı:

* `registrar.student_group_changed` — köçürmə xidməti (PostgreSQL-də qrup
  yazısı DB funksiyası ilə gedir, `post_save` işə düşmür);
* `post_save(StudentAcademicRecord)` — yeni qeyd, ORM ilə qrup/status/is_active
  dəyişikliyi (xaric edilən tələbənin PIN-i də eyni tam sinxronla silinir —
  `provision_exam_student_pins` idempotent tam sinxrondur).

Yalnız YENİ qrupun imtahanları işlənir (brief: «provision only»); köhnə
qrupun imtahanlarında PIN ləğvi tələb olunmur. İş `transaction.on_commit`-də
gedir ki, köçürmənin atomik bloku uğursuz olsa PIN yazılmasın.
"""

import logging

from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.exams.models import Exam
from apps.exams.services.student_pins import SECURE_PIN_CATEGORIES, provision_exam_student_pins
from apps.registrar.models import StudentAcademicRecord
from apps.registrar.public import student_group_changed
from core.rls_pooling import rls_worker_atomic

logger = logging.getLogger("exams.unit_pin_sync")

#: `post_save`-də `update_fields` verilibsə, üzvlüyə təsir edən sahələr.
_MEMBERSHIP_FIELDS = frozenset({"group", "group_id", "status", "is_active"})


def sync_student_pins_for_unit(unit_id) -> int:
    """Reyestr qrupuna təyin olunmuş aktiv final/midterm imtahanların PIN-lərini sinxronlaşdırır.

    Silinmiş imtahanlar keçilir; `exam_type_extended` filtri boş yerə işi
    (və qeyri-təhlükəsiz imtahanlarda PIN silmə sorğusunu) kəsir. Qaytarır:
    işlənən imtahan sayı.
    """
    if not unit_id:
        return 0
    exams = Exam.objects.filter(
        allowed_units__id=unit_id,
        is_deleted=False,
        exam_type_extended__in=sorted(SECURE_PIN_CATEGORIES),
    ).distinct()
    count = 0
    with rls_worker_atomic():
        for exam in exams:
            provision_exam_student_pins(exam)
            count += 1
    return count


def _schedule_unit_sync(unit_id) -> None:
    if not unit_id:
        return
    transaction.on_commit(lambda: sync_student_pins_for_unit(unit_id))


def _parent_unit_ids(organization, unit) -> list:
    """Alt qrupun ANA qrup(lar)ı — ana qrupa təyin olunmuş imtahan alt qrupun tələbəsinə də açıqdır.

    2026-10-26: köçürmə yalnız ``allowed_units = yeni qrup`` imtahanlarını sinxronlaşdırırdı; tələbə
    alt qrupa («234 K-1») köçəndə ana qrupa («234 K az») təyin olunmuş final/midterm-də PIN-i
    yaranmırdı (kabinet açılana qədər; PIN axtarışında da görünmürdü). Xəta köçürməni sındırmır.
    """
    if organization is None or unit is None:
        return []
    try:
        from apps.registrar.public import subgroup_rollup

        return [parent.pk for parent in subgroup_rollup.parent_group_candidates(organization, unit)]
    except Exception:  # noqa: BLE001 — ana qrup həlli köməkçidir; köçürmə və əsas sinx davam edir
        logger.warning("unit_pin_sync: ana qrup həll olunmadı unit=%s", getattr(unit, "pk", None), exc_info=True)
        return []


def _sync_unit_and_parents(unit_id, organization, unit) -> None:
    """Commit-dən SONRA: yeni qrup + onun ana qrup(lar)ının imtahanları (ana qrup sorğusu köçürmə
    tranzaksiyasından kənardadır — onun xətası köçürməni geri qaytara bilməz)."""
    sync_student_pins_for_unit(unit_id)
    for parent_id in _parent_unit_ids(organization, unit):
        if parent_id != unit_id:
            sync_student_pins_for_unit(parent_id)


@receiver(student_group_changed, dispatch_uid="exams.unit_pin_sync.student_group_changed")
def _on_student_group_changed(sender, record=None, new_group=None, **kwargs):
    unit_id = getattr(new_group, "pk", None) or getattr(record, "group_id", None)
    if not unit_id:
        return
    if new_group is None:
        _schedule_unit_sync(unit_id)
        return
    organization = getattr(record, "organization", None)
    transaction.on_commit(lambda: _sync_unit_and_parents(unit_id, organization, new_group))


@receiver(post_save, sender=StudentAcademicRecord, dispatch_uid="exams.unit_pin_sync.record_saved")
def _on_student_record_saved(sender, instance, created, update_fields=None, **kwargs):
    if not getattr(instance, "group_id", None):
        return
    if not created and update_fields is not None and not (_MEMBERSHIP_FIELDS & set(update_fields)):
        return
    _schedule_unit_sync(instance.group_id)


__all__ = ["sync_student_pins_for_unit"]
