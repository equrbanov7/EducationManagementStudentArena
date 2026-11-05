"""Slotun KÖHNƏLMİŞ müəllimi — jurnalı da, dərs yükü də olmayan müəllimin cədvəlində qalan dərs (2026-11-05).

Sahib (2026-11-05): «bəzi müəllimlərdə elektron jurnalında və dərs yükündə o fənn olmasa da dərs cədvəlində
qalıb. Bunu fix elə, olmasın o orda. O tip problemin qarşısını al.»

KÖK SƏBƏB
---------
Müəllim cədvəli EFFEKTİV müəllimə görə qurulur (:func:`apps.registrar.schedule.taught_by_q`): slotun öz
müəllimi (``ScheduleSlot.instructor``, bölünmüş tədris), boşdursa jurnal sahibi. Jurnal sahibi dəyişəndə
(dərs yükü sinxronu, fənn təhvili) NULL slotlar yeni sahibi avtomatik izləyir, amma slota YAZILMIŞ müəllim
heç vaxt yenidən yoxlanmırdı: bölgüdən çıxarılmış / səhv adla idxal olunmuş müəllim jurnalı (sahib/pay) və
yükü itirsə də dərs onun cədvəlində qalırdı.

QAYDA (TƏK — oxu, qarşısının alınması və təmizləmə əmri bunu işlədir)
-------------------------------------------------------------------
Slotun öz müəllimi ``T`` ``O`` açılışında HƏLƏ DƏ CARİDİR, əgər:

1. ``T`` jurnalın sahibidir (``O.instructor``), və ya
2. ``T``-nin bu jurnalda AKTİV payı var (``JournalShare``, bölünmüş jurnal), və ya
3. ``T`` bu jurnalda dərs aparıb (``Lesson.instructor`` — jurnal onun siyahısında tarixçə kimi qalır), və ya
4. ``T``-nin bu fənn + semestr + qrup üzrə dərs yükü bölgüsü var (ləğv olunmamış tapşırıq; mühazirə /
   məşğələ / laboratoriya).

3–4 slot redaktorunun seçicisi ilə EYNİ mənbələrdir (:mod:`apps.registrar.schedule_slot_teachers`;
əlavə olaraq pay). Heç biri yoxdursa slot köhnəlmişdir: müəllim cədvəlində göstərilmir, qarşısının alınması
və təmizləmə isə slotun müəllimini BOŞALDIR (NULL) — dərs qrupun cədvəlində qalır və jurnal sahibini izləyir
(``stored_instructor_id`` konvensiyası). Slot silinmir. Hər boşaltma audit jurnalına köhnə müəllimlə düşür.

Qayda TƏK SQL ifadəsidir (:func:`current_q`, ``EXISTS`` alt-sorğuları) — müəllim cədvəli yenə BİR sorğudur.

Dərs yükü modeli ``get_model`` ilə oxunur — registrar → workload Python import kənarı yaranmır.
"""

from __future__ import annotations

from django.apps import apps as django_apps
from django.db.models import Exists, F, OuterRef, Q
from django.utils import timezone

from core.audit import log_actions
from core.constants import AuditAction

from .models import JournalShare, Lesson, ScheduleSlot
from .schedule_slot_teachers import _CANCELLED_TASK, _TEACHING_ACTIVITIES

#: Audit səbəbi (qarşısının alınması və təmizləmə əmri eyni mətni yazır).
RELEASE_REASON = (
    "Slotun müəllimi bu jurnalın sahibi/pay sahibi deyil və dərs yükündə yoxdur — slot jurnal sahibinə qaytarıldı"
)


def current_q() -> Q:
    """``ScheduleSlot`` Q — slotun öz müəllimi YOXDUR və ya modul şərhindəki qayda ilə HƏLƏ DƏ CARİDİR.

    NULL-təhlükəsizdir: sahib boş olanda bərabərlik termini FALSE-dur (NULL deyil), ona görə ``exclude`` da düzgündür.
    """
    teacher = OuterRef("instructor_id")
    shared = JournalShare.objects.filter(offering_id=OuterRef("offering_id"), teacher_id=teacher, is_active=True)
    taught = Lesson.objects.filter(offering_id=OuterRef("offering_id"), instructor_id=teacher)
    load = (
        django_apps.get_model("workload", "TeacherAssignment")
        .objects.filter(
            teacher_id=teacher,
            row__subject_id=OuterRef("offering__subject_id"),
            row__period_id=OuterRef("offering__period_id"),
            row__groups=OuterRef("offering__group_id"),
            activity__in=_TEACHING_ACTIVITIES,
        )
        .exclude(row__task__status=_CANCELLED_TASK)
    )
    return (
        Q(instructor__isnull=True)
        | Q(offering__instructor__isnull=False, instructor_id=F("offering__instructor_id"))
        | Exists(shared)
        | Exists(taught)
        | Exists(load)
    )


def stale(queryset):
    """``queryset``-in köhnəlmiş slotları (öz müəllimi var, amma artıq cari deyil)."""
    return queryset.filter(instructor__isnull=False).exclude(current_q())


def release(*, offering_ids, by_user=None, request=None, reason=RELEASE_REASON) -> int:
    """Aktiv açılışların köhnəlmiş slot müəllimlərini BOŞALT (NULL → jurnal sahibi); boşaldılan slot sayı.

    Parklanmış slotlar da daxildir (yenidən yerləşdiriləndə köhnə müəllimlə qayıtmasın); qeyri-aktiv açılışın
    slotlarına toxunulmur — onlar təmir paketlərinin geri qaytarma sübutudur. Çağıran tranzaksiyanı saxlayır."""
    ids = [offering_id for offering_id in (offering_ids or ()) if offering_id]
    if not ids:
        return 0
    candidates = ScheduleSlot.objects.filter(offering_id__in=ids, offering__is_active=True, instructor__isnull=False)
    # Ucuz ön-yoxlama: sahibdən FƏRQLİ slot müəllimi yoxdursa (adi hal) dərs yükü alt-sorğusu işləmir —
    # sinxronun sorğu büdcəsi (təyinat cədvəli bir dəfə oxunur) dəyişmir.
    if not candidates.exclude(offering__instructor__isnull=False, instructor_id=F("offering__instructor_id")).exists():
        return 0
    found = list(stale(candidates).select_related("offering__organization").order_by("pk"))
    if not found:
        return 0
    ScheduleSlot.objects.filter(pk__in=[slot.pk for slot in found], instructor__isnull=False).update(
        instructor=None, updated_at=timezone.now()
    )
    actor = by_user if getattr(by_user, "pk", None) else None
    log_actions(
        {
            "action": AuditAction.UPDATE,
            "user": actor,
            "organization": slot.offering.organization,
            "old_values": {"instructor": str(slot.instructor_id)},
            "new_values": {"instructor": "", "offering": str(slot.offering_id)},
            "reason": reason,
            "request": request,
            "resource_type": "registrar.ScheduleSlot",
            "resource_id": str(slot.pk),
            "resource_repr": f"{slot.offering_id} · {slot.weekday} {slot.start_time:%H:%M}",
        }
        for slot in found
    )
    return len(found)


__all__ = ["RELEASE_REASON", "current_q", "release", "stale"]
