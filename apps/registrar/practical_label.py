"""«Praktiki məşğələ» — seminar növünün YALNIZ GÖRÜNÜŞ adı (sahib 2026-10-28, minimal variant).

Dizayn məktəbi: praktiki fənlər jurnalda «Seminar» görünür. Köhnə sistemdə dərs kodu ``3`` «praktiki məşğələ» idi;
köçürmə onu qəsdən ``seminar`` yazıb (``legacy_import.rehearsal_journal_lesson_kinds``) — hədəf enumunda ayrıca növ
yoxdur və OLMAYACAQ: saxlanan növ ``seminar`` qalır, bal / pay / slot / yük / DB CHECK-ləri dəyişmir.

Bayraq AÇILIŞDADIR (``CourseOffering.seminar_is_practical``), fənndə yox:

* köhnə sistemdə kod jurnalın (= açılışın) xassəsi idi — 2026/2027 payızında 62 «praktiki» köhnə fəndən 5-i eyni
  semestrdə həm praktiki, həm adi seminar jurnalı ilə keçib; fənn kartı isə ixtisaslar arasında ortaqdır;
* növ etiketi onsuz da açılışın dərs / slot sətrindən oxunur — əlavə JOIN yoxdur.

Yalnız fənnin açıq şəkildə Dizayn kafedrasına aid olduğu və bayraq ``True`` olan açılışda insana göstərilən hər «Seminar» etiketi «Praktiki məşğələ» olur: jurnal sütun başlığı,
tip pillələri və dərs modalının növ seçicisi, cədvəl hüceyrəsi, «Keçilmiş dərslər», tələbənin jurnal / davamiyyət
tarixçəsi.

Sahib 2026-11-08: xarici dil SƏVİYYƏ fənləri («Xarici dildə işgüzar və akademik kommunikasiya-1(elementary)» …,
reyestr :mod:`core.language_level_rule`) bayraqdan və kafedradan asılı olmayaraq HƏMİŞƏ «Praktiki məşğələ»dir —
qayda fənn adındandır, prod-da məlumat əməliyyatı tələb etmir (yazın «-2 …» açılışları da avtomatik düşür).

``Lesson.get_kind_display`` / ``ScheduleSlot.get_kind_display`` buradakı :func:`kind_display`-i çağırır —
şablonlar dəyişmir. Açılış obyektdə keşlənibsə (``select_related`` / ``offering.lessons``) sorğu yoxdur; deyilsə
seminar sətri üçün bir ``EXISTS`` (nəticə nüsxədə saxlanılır).
"""

from __future__ import annotations

from django.utils.translation import pgettext_lazy

SEMINAR = "seminar"
PRACTICAL_LABEL = pgettext_lazy("registrar.lesson_kind", "Practical session")
_MEMO = "_seminar_is_practical_memo"
_LEVEL_MEMO = "_level_subject_practical_memo"


def _base_labels() -> dict:
    from .models.grading_choices import LessonKind

    return dict(LessonKind.choices)


def kind_label(kind, *, practical: bool = False, labels: dict | None = None) -> str:
    """Növün görünüş adı; ``practical`` yalnız seminarı dəyişir. ``labels`` — sahənin öz seçimləri (slot üçün)."""

    if practical and kind == SEMINAR:
        return str(PRACTICAL_LABEL)
    return str((labels if labels is not None else _base_labels()).get(kind, kind or ""))


def subject_forces_practical(offering) -> bool:
    """Açılışın fənni səviyyə fənnidirmi (seminarı həmişə «Praktiki məşğələ»). Nəticə nüsxədə saxlanılır;
    fənn keşdədirsə (``select_related``) sorğu yoxdur, deyilsə Django onu bir dəfə oxuyub keşləyir."""
    if offering is None or not getattr(offering, "subject_id", None):
        return False
    memo = offering.__dict__.get(_LEVEL_MEMO)
    if memo is None:
        from core.language_level_rule import is_practical_name

        if type(offering).subject.is_cached(offering):
            memo = is_practical_name(getattr(offering.subject, "name", ""))
        else:
            memo = _subject_is_practical(offering.subject_id)
        offering.__dict__[_LEVEL_MEMO] = memo
    return memo


def _subject_is_practical(subject_id) -> bool:
    """Fənn keşdə deyilsə: request-in oxu memo-su (``read_memo``) fənn başına BİR sorğu — eyni açılışın bir neçə
    nüsxəsi (dərs sətirləri) sorğunu təkrarlamır."""
    from core.language_level_rule import is_practical_name

    from . import read_memo
    from .models import Subject

    memo = read_memo.bucket("level_practical_subjects")
    if memo is not None and subject_id in memo:
        return memo[subject_id]
    value = is_practical_name(Subject.objects.filter(pk=subject_id).values_list("name", flat=True).first())
    if memo is not None:
        memo[subject_id] = value
    return value


def offering_is_practical(offering) -> bool:
    from .design_practical_scope import is_design_offering

    if subject_forces_practical(offering):
        return True
    return bool(getattr(offering, "seminar_is_practical", False)) and is_design_offering(offering)


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

        # Bayraqsız da ola bilər: səviyyə fənni adından praktikidir (sahib 2026-11-08). Eyni BİR sorğu; bayraqsız
        # adi açılışda ``offering_is_practical`` bayraqda dayanır — kafedra yoxlaması işə düşmür.
        offering = CourseOffering.objects.select_related("subject__chair_unit").filter(pk=row.offering_id).first()
        memo = offering is not None and offering_is_practical(offering)
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
    "subject_forces_practical",
]
