"""«Praktiki məşğələ» — seminar növünün YALNIZ GÖRÜNÜŞ adı (sahib 2026-10-28, minimal variant).

Dizayn məktəbi: praktiki fənlər jurnalda «Seminar» görünür. Köhnə sistemdə dərs kodu ``3`` «praktiki məşğələ» idi;
köçürmə onu qəsdən ``seminar`` yazıb (``legacy_import.rehearsal_journal_lesson_kinds``) — hədəf enumunda ayrıca növ
yoxdur və OLMAYACAQ: saxlanan növ ``seminar`` qalır, bal / pay / slot / yük / DB CHECK-ləri dəyişmir.

Bayraq AÇILIŞDADIR (``CourseOffering.seminar_is_practical``), fənndə yox:

* köhnə sistemdə kod jurnalın (= açılışın) xassəsi idi — 2026/2027 payızında 62 «praktiki» köhnə fəndən 5-i eyni
  semestrdə həm praktiki, həm adi seminar jurnalı ilə keçib; fənn kartı isə ixtisaslar arasında ortaqdır;
* növ etiketi onsuz da açılışın dərs / slot sətrindən oxunur — əlavə JOIN yoxdur.

Bayraq ``True`` olan açılışda insana göstərilən hər «Seminar» etiketi «Praktiki məşğələ» olur: jurnal sütun başlığı,
tip pillələri və dərs modalının növ seçicisi, cədvəl hüceyrəsi, «Keçilmiş dərslər», tələbənin jurnal / davamiyyət
tarixçəsi. ``Lesson.get_kind_display`` / ``ScheduleSlot.get_kind_display`` buradakı :func:`kind_display`-i çağırır —
şablonlar dəyişmir. Açılış obyektdə keşlənibsə (``select_related`` / ``offering.lessons``) sorğu yoxdur; deyilsə
seminar sətri üçün bir ``EXISTS`` (nəticə nüsxədə saxlanılır).
"""

from __future__ import annotations

from django.utils.translation import pgettext_lazy

SEMINAR = "seminar"
PRACTICAL_LABEL = pgettext_lazy("registrar.lesson_kind", "Practical session")
_MEMO = "_seminar_is_practical_memo"


def _base_labels() -> dict:
    from .models.grading_choices import LessonKind

    return dict(LessonKind.choices)


def kind_label(kind, *, practical: bool = False, labels: dict | None = None) -> str:
    """Növün görünüş adı; ``practical`` yalnız seminarı dəyişir. ``labels`` — sahənin öz seçimləri (slot üçün)."""

    if practical and kind == SEMINAR:
        return str(PRACTICAL_LABEL)
    return str((labels if labels is not None else _base_labels()).get(kind, kind or ""))


def offering_is_practical(offering) -> bool:
    return bool(getattr(offering, "seminar_is_practical", False))


def kind_choices(offering=None, labels: dict | None = None) -> list:
    """Dərs modalı / tip pillələri üçün ``[(dəyər, ad), …]`` — açılışın bayrağı ilə."""

    labels = labels if labels is not None else _base_labels()
    practical = offering_is_practical(offering)
    return [(value, kind_label(value, practical=practical, labels=labels)) for value in labels]


def row_is_practical(row) -> bool:
    """Dərs / cədvəl slotu sətrinin açılışı «praktiki»dirmi (keşlənmiş açılış → sorğusuz)."""

    if getattr(row, "kind", None) != SEMINAR:
        return False
    if type(row).offering.is_cached(row):  # açılış keşdədir — sorğu yoxdur (``offering_id`` deferred ola bilər)
        return offering_is_practical(row.offering)
    memo = row.__dict__.get(_MEMO)
    if memo is None and not row.offering_id:
        return False
    if memo is None:
        from .models import CourseOffering

        memo = CourseOffering.objects.filter(pk=row.offering_id, seminar_is_practical=True).exists()
        row.__dict__[_MEMO] = memo
    return memo


def kind_display(row) -> str:
    """``get_kind_display`` gövdəsi (``Lesson`` və ``ScheduleSlot``)."""

    labels = dict(type(row)._meta.get_field("kind").flatchoices)
    return kind_label(row.kind, practical=row_is_practical(row), labels=labels)


__all__ = [
    "PRACTICAL_LABEL",
    "kind_choices",
    "kind_display",
    "kind_label",
    "offering_is_practical",
    "row_is_practical",
]
