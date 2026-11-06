"""Laboratoriya qrupları BİR jurnal daxilində (sahib 2026-11-06, Ekologiya kafedrası).

Sahib: «Köhnə sistemdə laboratoriya jurnalları Lab-1 / Lab-2 siyahılarına bölünmüşdü — eyni cür bölün.» Köçürmə
hər fənn üçün BİR jurnal yaratdı; mühazirə və seminar bütün qrupla keçir, yalnız lab dərsləri yarım qrupladır.

Model (ən kiçik dəyişiklik): ``Enrollment.lab_group`` (tələbənin bu jurnaldakı lab qrupu) + ``Lesson.lab_group``
(yalnız LAB dərsində; boş = bütün qrup, köhnə davranış). Qaydalar:

* qrupu olan lab dərsi yalnız həmin qrupun tələbələrinindir — başqa qrupun xanası yazılmır, jurnalda boş/bağlı
  göstərilir (:func:`applies`);
* qayıb saatı və bal onsuz da tələbənin ÖZ xanalarından yığılır — qrup dərsinə xanası olmayan tələbə üçün heç nə
  dəyişmir; məxrəc (``CourseOffering.lesson_hours``) tələbə başınadır (mühazirə + seminar + BİR lab qrupu);
* fənnin saat həddi tələbə başına yoxlanır (:func:`per_student_hours`): qrupsuz dərslər + ən çox saatlı lab
  qrupunun dərsləri — Lab-1 və Lab-2-nin saatları toplanmır;
* jurnalın lab qrupları varsa («Yeni dərs»də) lab dərsi üçün qrup seçmək məcburidir (:func:`require_for_new`).
"""

from __future__ import annotations

from django.utils.translation import pgettext

from .models import Enrollment, LessonKind

#: Qrup nömrəsinin tavanı (praktikada 2; 9 — yazı səhvinə qarşı sərhəd).
MAX_LAB_GROUP = 9
_MEMO_ATTR = "_lab_groups_memo"


class LabGroupError(ValueError):
    """Yanlış lab qrupu (növ lab deyil, qrup jurnalda yoxdur, qrup seçilməyib)."""


def label(number) -> str:
    return pgettext("registrar.lab_groups", "Lab-%(n)s") % {"n": number}


def offering_groups(offering) -> list:
    """Jurnalın lab qrupları (artan sıra) — aktiv siyahıdan BİR sorğu, offering obyektində memo."""
    memo = getattr(offering, _MEMO_ATTR, None)
    if memo is None:
        memo = sorted(
            set(
                Enrollment.objects.filter(
                    offering_id=offering.pk, status=Enrollment.Status.ENROLLED, lab_group__isnull=False
                ).values_list("lab_group", flat=True)
            )
        )
        setattr(offering, _MEMO_ATTR, memo)
    return memo


def prime(offering, enrollments) -> None:
    """Hazır aktiv siyahıdan memo (jurnal qridi siyahını onsuz da oxuyur — əlavə sorğu yoxdur)."""
    setattr(offering, _MEMO_ATTR, sorted({row.lab_group for row in enrollments if row.lab_group}))


def choices(offering) -> list:
    """Dərs modalının seçimi: ``[(nömrə, «Lab-N»), …]``; qrup yoxdursa boş."""
    return [(number, label(number)) for number in offering_groups(offering)]


def parse(raw):
    """POST dəyəri → ``int`` | ``None`` (boş). Yararsız dəyər ``LabGroupError``."""
    text = str(raw or "").strip()
    if not text:
        return None
    if not text.isdigit() or not 1 <= int(text) <= MAX_LAB_GROUP:
        raise LabGroupError(pgettext("registrar.lab_groups", "Laboratoriya qrupu düzgün seçilməyib."))
    return int(text)


def validate(offering, *, kind, lab_group) -> None:
    """Dərsin qrupu yalnız lab dərsində və yalnız jurnalda mövcud qrup ola bilər."""
    if lab_group is None:
        return
    if kind != LessonKind.LAB:
        raise LabGroupError(pgettext("registrar.lab_groups", "Laboratoriya qrupu yalnız laboratoriya dərsinə aiddir."))
    if lab_group not in offering_groups(offering):
        raise LabGroupError(pgettext("registrar.lab_groups", "Bu jurnalda belə laboratoriya qrupu yoxdur."))


def require_for_new(offering, *, kind, lab_group) -> None:
    """«Yeni dərs»: jurnal lab qruplarına bölünübsə lab dərsinin qrupu MƏCBURİDİR."""
    validate(offering, kind=kind, lab_group=lab_group)
    if kind == LessonKind.LAB and lab_group is None and offering_groups(offering):
        raise LabGroupError(
            pgettext("registrar.lab_groups", "Bu jurnal laboratoriya qruplarına bölünüb — dərsin qrupunu seçin.")
        )


def applies(lesson, enrollment) -> bool:
    """Dərs bu tələbəyə aiddirmi: qrupsuz dərs hamınındır; qruplu lab dərsi yalnız öz qrupunun."""
    group = getattr(lesson, "lab_group", None)
    return group is None or group == getattr(enrollment, "lab_group", None)


def per_student_hours(lessons, *, extra_hours=0, extra_group=None) -> int:
    """Bir tələbənin saatı: qrupsuz dərslər + ən çox saatlı lab qrupu (``extra_*`` — yaradılmaqda olan dərs)."""
    shared = 0
    by_group: dict = {}
    for lesson in lessons:
        hours = int(getattr(lesson, "hours", 0) or 0)
        group = getattr(lesson, "lab_group", None)
        if group is None:
            shared += hours
        else:
            by_group[group] = by_group.get(group, 0) + hours
    if extra_group is None:
        shared += int(extra_hours or 0)
    else:
        by_group[extra_group] = by_group.get(extra_group, 0) + int(extra_hours or 0)
    return shared + max(by_group.values(), default=0)


__all__ = [
    "MAX_LAB_GROUP",
    "LabGroupError",
    "applies",
    "choices",
    "label",
    "offering_groups",
    "parse",
    "per_student_hours",
    "prime",
    "require_for_new",
    "validate",
]
