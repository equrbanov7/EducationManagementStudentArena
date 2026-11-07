"""Seminar alt qrupları BİR jurnal daxilində (sahib 2026-11-07).

Sahib: «mühazirədə 234 K bir göstərsin; seminarda 234 K1 və 234 K2-ni ayrı göstərsin, dərs əlavə edəndə onu seçsin,
ad olaraq görsün … lab-1, lab-2 də … aydın görünsün deyə». Tələbə yenidən yaranmır: ana qrupun jurnalında hər iki alt
qrupun tələbələri var; seminar dərsi istəyə görə bir alt qrupa bağlanır.

Model (laboratoriya qrupları ilə eyni naxış — :mod:`apps.registrar.lab_groups`): ``Enrollment.seminar_group`` +
``Lesson.seminar_group`` (yalnız SEMİNAR dərsində; boş = bütün qrup, köhnə davranış) + ``SeminarGroup`` (ad, mənbə
reyestr alt qrupu). Qaydalar:

* alt qrupu olan seminar dərsi yalnız həmin alt qrupun tələbələrinindir (:func:`apps.registrar.lab_groups.applies`
  hər iki bölgünü yoxlayır) — başqa alt qrupun xanası bağlıdır, yazılmır;
* saat həddi tələbə başına: ümumi dərslər + BİR seminar alt qrupu + BİR lab qrupu
  (:func:`apps.registrar.lab_groups.per_student_hours`);
* lab-dan FƏRQLİ: alt qrup seçimi MƏCBURİ DEYİL — birgə keçən seminar «Bütün qrup» kimi yazılır.
"""

from __future__ import annotations

from django.utils.translation import pgettext

from .models import Enrollment, LessonKind, SeminarGroup

MAX_SEMINAR_GROUP = 9
_MEMO_ATTR = "_seminar_groups_memo"
_NAMES_ATTR = "_seminar_group_names_memo"
_CTX = "registrar.seminar_groups"


class SeminarGroupError(ValueError):
    """Yanlış seminar alt qrupu (növ seminar deyil, alt qrup jurnalda yoxdur)."""


def default_label(number) -> str:
    return pgettext(_CTX, "Seminar-%(n)s") % {"n": number}


def label(number, offering=None) -> str:
    """Alt qrupun görünən adı («234 K1»); adı yoxdursa «Seminar-N»."""
    name = names(offering).get(number, "") if offering is not None else ""
    return name or default_label(number)


def names(offering) -> dict:
    memo = getattr(offering, _NAMES_ATTR, None)
    if memo is None:
        _load_rows(offering)
        memo = getattr(offering, _NAMES_ATTR)
    return memo


def _load_rows(offering) -> set:
    rows = list(SeminarGroup.objects.filter(offering_id=offering.pk).values_list("number", "name"))
    setattr(offering, _NAMES_ATTR, {number: name for number, name in rows if name})
    return {number for number, _name in rows}


def offering_groups(offering) -> list:
    """Jurnalın seminar alt qrupları (artan sıra): ``SeminarGroup`` sətirləri ∪ aktiv siyahı — offering-də memo."""
    memo = getattr(offering, _MEMO_ATTR, None)
    if memo is None:
        roster = Enrollment.objects.filter(
            offering_id=offering.pk, status=Enrollment.Status.ENROLLED, seminar_group__isnull=False
        ).values_list("seminar_group", flat=True)
        memo = sorted(_load_rows(offering) | set(roster))
        setattr(offering, _MEMO_ATTR, memo)
    return memo


def prime(offering, enrollments) -> None:
    """Hazır aktiv siyahıdan memo. Siyahıda alt qruplu tələbə yoxdursa ``SeminarGroup`` sorğusu da getmir — bölünməmiş
    jurnalın qrid sorğu büdcəsi dəyişmir (tələbəsiz alt qrupun qriddə yeri yoxdur)."""
    roster = {row.seminar_group for row in enrollments if row.seminar_group}
    if not roster:
        setattr(offering, _MEMO_ATTR, [])
        setattr(offering, _NAMES_ATTR, {})
        return
    setattr(offering, _MEMO_ATTR, sorted(_load_rows(offering) | roster))


def forget(offering) -> None:
    for attr in (_MEMO_ATTR, _NAMES_ATTR):
        if hasattr(offering, attr):
            delattr(offering, attr)


def lesson_label(row, offering) -> str:
    """Dərsin və ya qeydiyyatın (``seminar_group`` sahəsi olan sətir) alt qrup adı; bölünməyibsə boş."""
    number = getattr(row, "seminar_group", None)
    return label(number, offering) if number else ""


def choices(offering) -> list:
    """Dərs modalının seçimi: ``[(nömrə, «234 K1»), …]``; alt qrup yoxdursa boş."""
    return [(number, label(number, offering)) for number in offering_groups(offering)]


def parse(raw):
    """POST dəyəri → ``int`` | ``None`` (boş = bütün qrup). Yararsız dəyər ``SeminarGroupError``."""
    text = str(raw or "").strip()
    if not text:
        return None
    if not text.isdigit() or not 1 <= int(text) <= MAX_SEMINAR_GROUP:
        raise SeminarGroupError(pgettext(_CTX, "Seminar alt qrupu düzgün seçilməyib."))
    return int(text)


def validate(offering, *, kind, seminar_group) -> None:
    """Dərsin alt qrupu yalnız seminar dərsində və yalnız jurnalda mövcud alt qrup ola bilər."""
    if seminar_group is None:
        return
    if kind != LessonKind.SEMINAR:
        raise SeminarGroupError(pgettext(_CTX, "Seminar alt qrupu yalnız seminar dərsinə aiddir."))
    if seminar_group not in offering_groups(offering):
        raise SeminarGroupError(pgettext(_CTX, "Bu jurnalda belə seminar alt qrupu yoxdur."))


__all__ = [
    "MAX_SEMINAR_GROUP",
    "SeminarGroupError",
    "choices",
    "default_label",
    "forget",
    "label",
    "lesson_label",
    "names",
    "offering_groups",
    "parse",
    "prime",
    "validate",
]
