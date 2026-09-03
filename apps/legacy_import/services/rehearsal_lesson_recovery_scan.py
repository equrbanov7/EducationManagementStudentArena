"""J12-nin saf hesablama qatı: xana → bərpa slotu (heç bir yazı yoxdur).

Faza modulunu 600-sətir büdcəsi altında saxlamaq üçün ayrılıb; burada yalnız
MƏNBƏ üzərində işləyən saf funksiyalar və data formaları yaşayır — hədəf
yazısı, ledger möhürü və qərar nərdivanı ``rehearsal_lesson_recovery_phase``-dədir.

Hər funksiya J3/J4-ün ÖZ köməkçilərini çağırır (``parse_lesson_schedule``,
``classify_mark_cell``, ``distill_mark_cell``), yəni bərpa yolu ilə əsas yol
bir-birindən sürüşə bilmir: eyni giriş həmişə eyni slotu verir.
"""

from __future__ import annotations

import dataclasses
import datetime
from dataclasses import dataclass

from django.apps import apps as django_apps

from .field_contracts import JOURNAL_POINT_ARCHIVE_FIELDS, JOURNAL_POINT_FIELDS
from .rehearsal_contracts import RehearsalContext, source_row_hash
from .rehearsal_journal_components_phase import ComponentCell, distill_component_cell
from .rehearsal_journal_lessons_phase import journal_index, parse_lesson_schedule, semester_year_index
from .rehearsal_journal_marks_phase import MarkCell, classify_mark_cell, distill_mark_cell


@dataclass(frozen=True)
class RecoveryMarkCell(MarkCell):
    """J4-ün xanası + mənbə sətrinin öz hash-i (toqquşma sübutu üçün lazımdır)."""

    row_hash: str = ""


@dataclass(frozen=True)
class RecoveryComponentCell(ComponentCell):
    """J5 xanası + tam field-contract source hash-i.

    Konflikt faktının immutable hash-i məhz xam source sətrinin hash-i olmalıdır;
    distillə olunmuş alt-dəstdən ayrıca digest düzəltmək exact gate-i pozur.
    """

    row_hash: str = ""


def distill_recovery_cell(legacy_pk: int, row, from_archive: bool) -> RecoveryMarkCell:
    """J4-ün distilləsi + ``source_row_hash`` (sübut sətrinin provenansı)."""

    base = distill_mark_cell(legacy_pk, row, from_archive)
    contract = JOURNAL_POINT_ARCHIVE_FIELDS if from_archive else JOURNAL_POINT_FIELDS
    return RecoveryMarkCell(
        **dataclasses.asdict(base),
        row_hash=source_row_hash(contract=contract, legacy_pk=legacy_pk, projected_row=row),
    )


def distill_recovery_component_cell(legacy_pk: int, row, from_archive: bool) -> RecoveryComponentCell:
    """J5 distilləsi + importer-in tam source-row hash müqaviləsi."""

    base = distill_component_cell(legacy_pk, row, from_archive)
    contract = JOURNAL_POINT_ARCHIVE_FIELDS if from_archive else JOURNAL_POINT_FIELDS
    return RecoveryComponentCell(
        **dataclasses.asdict(base),
        row_hash=source_row_hash(contract=contract, legacy_pk=legacy_pk, projected_row=row),
    )


@dataclass
class SlotPlan:
    """Bir bərpa slotunun planı — A keçidində yığılır, sonra dərsə çevrilir."""

    uniqid: str
    group_ref: str
    offering_pk: str
    date: datetime.date
    start_time: datetime.time | None
    #: Slotu AÇAN ilk xana — ``(arxivdənmi, legacy pk)``.  Cütün özü müqayisə
    #: olunur: axın ƏVVƏL əsas cədvəli, SONRA arxivi yeriyir, ona görə
    #: ``False < True`` sıralaması sürücünün öz sırasını güzgüləyir.
    first_cell: tuple[bool, int]
    cell_count: int = 1

    @property
    def time_text(self) -> str:
        return "" if self.start_time is None else self.start_time.isoformat(timespec="minutes")

    @property
    def first_cell_pk(self) -> int:
        return self.first_cell[1]

    @property
    def from_archive(self) -> bool:
        return self.first_cell[0]

    @property
    def metadata_key(self) -> tuple[str, int, int, str]:
        return (self.uniqid, self.date.month, self.date.day, self.time_text)


def recovered_schedule(*, first_year: int, month: int, day: int, time_text: str):
    """``(tarix, saat|None)`` — tarix J3-ün ÖZ törəməsi ilə, saat opsional.

    Saat oxunmayan xana (legacy ``TIME`` 24 saatı aşır və ya pozuqdur) dərsi
    ÖLDÜRMÜR: dərs yaradılır, ``start_time`` NULL qalır və sətir
    ``legacy_lesson_synth_time_unknown`` ilə işarələnir — saat TƏXMİN EDİLMİR.
    ``"00:00"`` yalnız TARİXİ almaq üçün sentineldir: akademik il bölgüsü iki
    fazada sürüşə bilməsin deyə J3-ün öz funksiyası çağırılır.
    """

    schedule = parse_lesson_schedule(
        first_year=first_year, month=month, day=day, time_value=time_text if time_text else "00:00"
    )
    if schedule is None:
        return None
    lesson_date, lesson_time = schedule
    return lesson_date, (lesson_time if time_text else None)


def journal_year_index(context: RehearsalContext) -> dict[str, int]:
    """``uniqid`` → akademik ilin BİRİNCİ ili (J3-ün öz iki indeksindən)."""

    semesters = semester_year_index(context)
    index: dict[str, int] = {}
    for _legacy_pk, (uniqid, semester_ref) in journal_index(context).items():
        year = semesters.get(semester_ref)
        if year is not None:
            index[uniqid] = year
    return index


def resolve_cell_target(cell, *, resolution):
    """``(offering_pk, slot|None)`` və ya ``None`` (xana ümumiyyətlə yazıla bilmir).

    J4 nərdivanının eyni pillələri, eyni sırada — heç bir dəyər burada təhrif
    olunmur, yalnız təsnif edilir.
    """

    if not resolution.slices.has_offering(cell.uniqid):
        return None
    outcome, _status, _score = classify_mark_cell(cell.point)
    if outcome in ("empty", "unknown", "range"):
        return None
    enrollment_pk = resolution.enrollments.get(f"{cell.uniqid}:{cell.student_id}", "")
    if not enrollment_pk:
        return None
    offering_pk = resolution.offerings.get(enrollment_pk, "")
    if not offering_pk:
        return None
    return offering_pk, resolution.lessons.get((offering_pk, cell.month, cell.day, cell.time_text))


def slice_group_ref(resolution, uniqid: str, offering_pk: str) -> str:
    """Açılışın legacy qrup ref-i — bərpa dərsinin möhür açarının ikinci hissəsi."""

    for group_ref, pk in resolution.slices.slice_pairs(uniqid):
        if pk == offering_pk:
            return group_ref
    return ""


def offering_instructors(context, offering_pks) -> dict[str, str]:
    """Açılış → müəllim; J3-ün ``offering_instructor_index`` güzgüsü."""

    model = django_apps.get_model("registrar", "CourseOffering")
    rows = model.objects.filter(organization=context.organization, pk__in=offering_pks).values_list(
        "pk", "instructor_id"
    )
    return {str(pk): "" if instructor_id is None else str(instructor_id) for pk, instructor_id in rows}


__all__ = [
    "RecoveryComponentCell",
    "RecoveryMarkCell",
    "SlotPlan",
    "distill_recovery_cell",
    "distill_recovery_component_cell",
    "journal_year_index",
    "offering_instructors",
    "recovered_schedule",
    "resolve_cell_target",
    "slice_group_ref",
]
