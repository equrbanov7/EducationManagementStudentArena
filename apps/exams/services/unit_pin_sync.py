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

from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.exams.models import Exam
from apps.exams.services.student_pins import SECURE_PIN_CATEGORIES, provision_exam_student_pins
from apps.registrar.models import StudentAcademicRecord
from apps.registrar.public import student_group_changed
from core.rls_pooling import rls_worker_atomic

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


@receiver(student_group_changed, dispatch_uid="exams.unit_pin_sync.student_group_changed")
def _on_student_group_changed(sender, record=None, new_group=None, **kwargs):
    _schedule_unit_sync(getattr(new_group, "pk", None) or getattr(record, "group_id", None))


@receiver(post_save, sender=StudentAcademicRecord, dispatch_uid="exams.unit_pin_sync.record_saved")
def _on_student_record_saved(sender, instance, created, update_fields=None, **kwargs):
    if not getattr(instance, "group_id", None):
        return
    if not created and update_fields is not None and not (_MEMBERSHIP_FIELDS & set(update_fields)):
        return
    _schedule_unit_sync(instance.group_id)


__all__ = ["sync_student_pins_for_unit"]
