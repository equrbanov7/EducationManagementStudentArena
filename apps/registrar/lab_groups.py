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

Qrupların yaradılması / adı / tərkibi (jurnaldakı «Lab qrupları» ekranı, sahib 2026-11-06):
:mod:`apps.registrar.lab_groups_manage`. Jurnalın qrupları = ``LabGroup`` sətirləri ∪ aktiv siyahının
``lab_group`` dəyərləri — sətirsiz köhnə Lab-1 / Lab-2 də qrupdur və «Lab-N» adlanır (:func:`label`).
"""

from __future__ import annotations

from django.utils.translation import pgettext

from .models import Enrollment, LabGroup, LessonKind

#: Qrup nömrəsinin tavanı (praktikada 2; 9 — yazı səhvinə qarşı sərhəd).
MAX_LAB_GROUP = 9
_MEMO_ATTR = "_lab_groups_memo"
_NAMES_ATTR = "_lab_group_names_memo"


class LabGroupError(ValueError):
    """Yanlış lab qrupu (növ lab deyil, qrup jurnalda yoxdur, qrup seçilməyib)."""


def default_label(number) -> str:
    return pgettext("registrar.lab_groups", "Lab-%(n)s") % {"n": number}


def label(number, offering=None) -> str:
    """Qrupun görünən adı: ``offering`` verilib və qrupun adı varsa ad, yoxsa «Lab-N»."""
    name = names(offering).get(number, "") if offering is not None else ""
    return name or default_label(number)


def names(offering) -> dict:
    """``{nömrə: ad}`` — yalnız adı olan qruplar; offering obyektində memo (bir sorğu)."""
    memo = getattr(offering, _NAMES_ATTR, None)
    if memo is None:
        _load_rows(offering)
        memo = getattr(offering, _NAMES_ATTR)
    return memo


def _load_rows(offering) -> set:
    """``LabGroup`` sətirləri (nömrə dəsti) — adlar memo-ya yazılır."""
    rows = list(LabGroup.objects.filter(offering_id=offering.pk).values_list("number", "name"))
    setattr(offering, _NAMES_ATTR, {number: name for number, name in rows if name})
    return {number for number, _name in rows}


def offering_groups(offering) -> list:
    """Jurnalın lab qrupları (artan sıra): ``LabGroup`` sətirləri ∪ aktiv siyahı — iki sorğu, offering-də memo."""
    memo = getattr(offering, _MEMO_ATTR, None)
    if memo is None:
        roster = Enrollment.objects.filter(
            offering_id=offering.pk, status=Enrollment.Status.ENROLLED, lab_group__isnull=False
        ).values_list("lab_group", flat=True)
        memo = sorted(_load_rows(offering) | set(roster))
        setattr(offering, _MEMO_ATTR, memo)
    return memo


def prime(offering, enrollments) -> None:
    """Hazır aktiv siyahıdan memo (jurnal qridi siyahını onsuz da oxuyur — yalnız ``LabGroup`` sorğusu)."""
    setattr(
        offering, _MEMO_ATTR, sorted(_load_rows(offering) | {row.lab_group for row in enrollments if row.lab_group})
    )


def forget(offering) -> None:
    """Memo-nu at (qruplar dəyişəndən sonra eyni obyektlə yenidən oxumaq üçün)."""
    for attr in (_MEMO_ATTR, _NAMES_ATTR):
        if hasattr(offering, attr):
            delattr(offering, attr)


def choices(offering) -> list:
    """Dərs modalının seçimi: ``[(nömrə, ad və ya «Lab-N»), …]``; qrup yoxdursa boş."""
    return [(number, label(number, offering)) for number in offering_groups(offering)]


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
    """Dərs bu tələbəyə aiddirmi: qrupsuz dərs hamınındır; qruplu lab dərsi yalnız öz lab qrupunun, alt qruplu
    seminar dərsi yalnız öz seminar alt qrupunun (:mod:`apps.registrar.seminar_groups`, sahib 2026-11-07)."""
    group = getattr(lesson, "lab_group", None)
    if group is not None and group != getattr(enrollment, "lab_group", None):
        return False
    seminar = getattr(lesson, "seminar_group", None)
    return seminar is None or seminar == getattr(enrollment, "seminar_group", None)


def is_split(lesson) -> bool:
    """Dərs qrupun yalnız bir hissəsinindir (lab qrupu və ya seminar alt qrupu)."""
    return bool(getattr(lesson, "lab_group", None) or getattr(lesson, "seminar_group", None))


def per_student_hours(lessons, *, extra_hours=0, extra_group=None, extra_seminar_group=None) -> int:
    """Bir tələbənin saatı: qrupsuz dərslər + ən çox saatlı lab qrupu + ən çox saatlı seminar alt qrupu
    (``extra_*`` — yaradılmaqda olan dərs)."""
    shared = 0
    by_group: dict = {}
    by_seminar: dict = {}
    for lesson in lessons:
        hours = int(getattr(lesson, "hours", 0) or 0)
        group = getattr(lesson, "lab_group", None)
        seminar = getattr(lesson, "seminar_group", None)
        if group is not None:
            by_group[group] = by_group.get(group, 0) + hours
        elif seminar is not None:
            by_seminar[seminar] = by_seminar.get(seminar, 0) + hours
        else:
            shared += hours
    extra = int(extra_hours or 0)
    if extra_group is not None:
        by_group[extra_group] = by_group.get(extra_group, 0) + extra
    elif extra_seminar_group is not None:
        by_seminar[extra_seminar_group] = by_seminar.get(extra_seminar_group, 0) + extra
    else:
        shared += extra
    return shared + max(by_group.values(), default=0) + max(by_seminar.values(), default=0)


__all__ = [
    "MAX_LAB_GROUP",
    "LabGroupError",
    "applies",
    "choices",
    "default_label",
    "forget",
    "is_split",
    "label",
    "names",
    "offering_groups",
    "parse",
    "per_student_hours",
    "prime",
    "require_for_new",
    "validate",
]
