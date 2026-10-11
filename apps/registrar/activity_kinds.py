"""Aktivlik hissəsinin (0–10) seminar / laboratoriya bölgüsü — TƏK qayda (sahib 2026-10-10).

Sahib: «10 bal seminar … fəndə laboratoriya da varsa 5 + 5».  Midterm rejimli (2026/2027+) dövrdə:

* yalnız seminar olan fənn → aktivlik = seminar ballarının ədədi ortası (≤ 10);
* yalnız laboratoriya       → aktivlik = laboratoriya ortası (≤ 10);
* seminar VƏ laboratoriya   → aktivlik = ``round2(min(seminar ortası, 10) / 2) + round2(min(lab ortası, 10) / 2)``;
  balı olmayan növ 0 verir (məs. hələ lab balı yoxdursa yalnız seminarın yarısı sayılır).

RİM «Sistem tənzimləmələri»ndə ``academic.activity_split`` söndürülsə köhnə qayda qayıdır: bütün balı olan dərs
işarələrinin BİRGƏ ortası (``entry_standard.activity_part`` — bayt-bayt əvvəlki kimi).

FƏNNİN NÖVLƏRİ — açılış səviyyəsində, bütün yollarda EYNİ: **planlı növlər ∪ balı olan növlər**.  Planlı növlər:
təsdiqlənmiş tədris planının sətri (ixtisasın planı üstün, ``plan_hours.plan_hours_for_offering`` qaydası) → sətir
yoxdursa / saatı yoxdursa dərs yükü (``workload.TeachingTaskRow``) → orada da seminar/lab yoxdursa cədvəl slotlarının
növləri.  Balı olan növlər — açılışın HƏR HANSI yazılışının balı olan seminar/lab işarəsi.  Nəticə bit maskasıdır
(1 = seminar, 2 = lab) və bir SQL ifadəsidir (:func:`bits_expression`): toplu yollar onu MÖVCUD sorğularına qatır
(komponent sorğusu, açılış sətirləri, tək-sətir bal sorğusu) — sətir başına sorğu yoxdur; qalan hallarda bütün
lazım olan açılışlar üçün TƏK sorğu (:func:`bits_map`, :class:`PendingBits`).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from django.apps import apps as django_apps
from django.db.models import Case, Exists, F, IntegerField, OuterRef, Q, Subquery, Value, When
from django.db.models.functions import Coalesce, NullIf

ZERO = Decimal("0")
_TWO_PLACES = Decimal("0.01")
_HALF = Decimal("2")
#: Aktivlik hissəsinin tavanı = dərs balının tavanı (``gradebook.LESSON_SCORE_MAX``).
ACTIVITY_MAX = Decimal("10")

SEMINAR = "seminar"
LAB = "lab"
SEMINAR_BIT = 1
LAB_BIT = 2
LECTURE_BIT = 4
BOTH = SEMINAR_BIT | LAB_BIT

#: Bal sorğularının dərs növü annotasiyası (``LessonMark`` sətrində).
KIND_ATTR = "ems_lesson_kind"
#: Açılışın növ maskası annotasiyası (açılış / komponent / bal sətrində).
BITS_ATTR = "ems_activity_bits"
#: Tək-sətir yolunda açılış nümunəsinə yazılan memo.
_MEMO_ATTR = "_ems_activity_bits"
_INT = IntegerField()


# ── Hesab (saf funksiyalar) ──────────────────────────────────────────────────


class LessonTotals:
    """Bir yazılışın balı olan dərs işarələri: hamısı (birgə orta) + seminar və laboratoriya ayrıca."""

    __slots__ = ("total", "count", "seminar", "seminar_count", "lab", "lab_count")

    def __init__(self, total=ZERO, count=0):
        self.total = Decimal(total or 0)
        self.count = int(count or 0)
        self.seminar = ZERO
        self.seminar_count = 0
        self.lab = ZERO
        self.lab_count = 0

    def add(self, kind, score_sum, count=1) -> None:
        score_sum = Decimal(score_sum or 0)
        self.total += score_sum
        self.count += int(count)
        if kind == SEMINAR:
            self.seminar += score_sum
            self.seminar_count += int(count)
        elif kind == LAB:
            self.lab += score_sum
            self.lab_count += int(count)

    @property
    def own_bits(self) -> int:
        return (SEMINAR_BIT if self.seminar_count else 0) | (LAB_BIT if self.lab_count else 0)


@dataclass(frozen=True)
class ActivityDetail:
    """Aktivlik hissəsi + görünüş üçün bölgü (``split`` — 5 + 5 qaydası tətbiq olunub)."""

    value: Decimal
    split: bool = False
    seminar_mean: Decimal | None = None
    lab_mean: Decimal | None = None
    seminar_part: Decimal | None = None
    lab_part: Decimal | None = None


def pooled_mean(score_sum, score_count) -> Decimal:
    """Birgə orta (köhnə qayda): 2 onluğa yarım-yuxarı, sonra 10 ilə kəsilir; bal yoxdursa 0."""
    count = int(score_count or 0)
    if count <= 0:
        return ZERO
    mean = (Decimal(score_sum or 0) / Decimal(count)).quantize(_TWO_PLACES, rounding=ROUND_HALF_UP)
    return min(mean, ACTIVITY_MAX)


def _mean(score_sum, count):
    return (Decimal(score_sum) / Decimal(count)).quantize(_TWO_PLACES, rounding=ROUND_HALF_UP) if count else None


def half_part(score_sum, count) -> Decimal:
    """Bir növün 5 + 5 payı: ``round2(min(orta, 10) / 2)``; balı yoxdursa 0."""
    if not count:
        return ZERO
    mean = min(Decimal(score_sum) / Decimal(count), ACTIVITY_MAX)
    return (mean / _HALF).quantize(_TWO_PLACES, rounding=ROUND_HALF_UP)


def resolve(bits) -> int:
    """Maska dəyəri: hazır ədəd, tənbəl çağırış (toplu dəst / tək açılış) və ya ``None`` (0)."""
    if callable(bits):
        bits = bits()
    return int(bits or 0)


def activity(totals: LessonTotals, bits=None, *, split_enabled: bool) -> ActivityDetail:
    """Aktivlik hissəsi — qayda TƏK yerdə.  ``bits`` yalnız tələbənin ÖZ balları bir növdə olanda oxunur
    (ikisində də varsa fənn onsuz da hər iki növlüdür; heç balı yoxdursa hissə hər halda 0-dır)."""
    sem_mean = _mean(totals.seminar, totals.seminar_count)
    lab_mean = _mean(totals.lab, totals.lab_count)
    own = totals.own_bits
    if split_enabled and own:
        kinds = own if own == BOTH else own | resolve(bits)
        if kinds & BOTH == BOTH:
            sem_part = half_part(totals.seminar, totals.seminar_count)
            lab_part = half_part(totals.lab, totals.lab_count)
            return ActivityDetail(sem_part + lab_part, True, sem_mean, lab_mean, sem_part, lab_part)
    return ActivityDetail(pooled_mean(totals.total, totals.count), False, sem_mean, lab_mean)


# ── Bal işarələri → cəmlər ───────────────────────────────────────────────────


def annotate_kind(queryset):
    """``LessonMark`` sorğusuna dərs növü (eyni sorğu, JOIN; əlavə sorğu yoxdur)."""
    return queryset.annotate(**{KIND_ATTR: F("lesson__kind")})


def mark_kind(mark):
    """İşarənin dərs növü — annotasiyadan və ya keşlənmiş ``lesson``-dan (sorğusuz); bilinmirsə ``None``."""
    kind = getattr(mark, KIND_ATTR, None)
    if kind is None:
        state = getattr(mark, "_state", None)
        lesson = state.fields_cache.get("lesson") if state is not None else None
        kind = getattr(lesson, "kind", None)
    return kind


def totals_from_marks(marks, *, need_kinds=True) -> LessonTotals:
    """Balı olan işarələrin cəmləri.  Növü bilinməyən işarə (çağıran nə annotasiya, nə ``lesson`` vermişdir)
    yalnız ``need_kinds`` olanda TƏK sorğu ilə həll olunur — daxili yolların hamısı növü verir."""
    totals = LessonTotals()
    unknown = []
    for mark in marks:
        if mark.score is None:
            continue
        kind = mark_kind(mark)
        if kind is None and need_kinds:
            unknown.append(mark)
            continue
        totals.add(kind, mark.score)
    if unknown:
        from apps.registrar.models import Lesson

        kinds = dict(Lesson.objects.filter(id__in={m.lesson_id for m in unknown}).values_list("id", "kind"))
        for mark in unknown:
            totals.add(kinds.get(mark.lesson_id), mark.score)
    return totals


def totals_by_key(rows) -> dict:
    """SQL güzgüləri: ``(açar, növ, cəm, say)`` sətirləri → ``{açar: LessonTotals}``."""
    result: dict = {}
    for key, kind, total, count in rows:
        totals = result.get(key)
        if totals is None:
            totals = result[key] = LessonTotals()
        totals.add(kind, total or ZERO, count or 0)
    return result


# ── Açılışın növ maskası (SQL ifadəsi) ───────────────────────────────────────


def _flag(condition, bit):
    return Case(When(condition, then=Value(bit)), default=Value(0), output_field=_INT)


def _hour_bits(seminar, lab, lecture):
    return _flag(seminar, SEMINAR_BIT) + _flag(lab, LAB_BIT) + _flag(lecture, LECTURE_BIT)


def _curriculum_bits(ref):
    """Təsdiqlənmiş plan sətri — ixtisasın (qrupun valideyn bölməsi) planı üstün, sonra ən yeni qəbul ili/versiya."""
    from apps.registrar.models import CurriculumSubject, PlanStatus, Program

    program = (
        Program.objects.filter(
            organization_id=OuterRef("organization_id"),
            specialty_unit_id=OuterRef(OuterRef(ref("group__parent_id"))),
        )
        .order_by("name", "pk")
        .values("pk")[:1]
    )
    rows = (
        CurriculumSubject.objects.filter(
            organization_id=OuterRef(ref("organization_id")),
            subject_id=OuterRef(ref("subject_id")),
            curriculum__status=PlanStatus.APPROVED,
        )
        .annotate(
            ems_pref=Case(When(curriculum__program_id=Subquery(program), then=Value(0)), default=Value(1)),
            ems_bits=_hour_bits(Q(seminar_hours__gt=0), Q(lab_hours__gt=0), Q(lecture_hours__gt=0)),
        )
        .order_by("ems_pref", "-curriculum__admission_year", "-curriculum__version", "pk")
        .values("ems_bits")[:1]
    )
    return Subquery(rows, output_field=_INT)


def _workload_bits(ref):
    """Dərs yükü sətri (eyni fənn + dövr; qrupu olan açılışda həmin qrup) — ən son yenilənən sətir."""
    try:
        task_row = django_apps.get_model("workload", "TeachingTaskRow")
    except LookupError:  # workload tətbiqi yoxdur
        return Value(None, output_field=_INT)
    bits = _hour_bits(
        Q(seminar_plan__gt=0) | Q(seminar_total__gt=0),
        Q(lab_plan__gt=0) | Q(lab_total__gt=0),
        Q(lecture_plan__gt=0) | Q(lecture_total__gt=0),
    )
    base = task_row.objects.filter(
        organization_id=OuterRef(ref("organization_id")),
        subject_id=OuterRef(ref("subject_id")),
        period_id=OuterRef(ref("period_id")),
    )

    def _first(rows):
        return Subquery(
            rows.annotate(ems_bits=bits).order_by("-updated_at", "pk").values("ems_bits")[:1], output_field=_INT
        )

    return Case(
        When(**{ref("group_id") + "__isnull": True}, then=_first(base)),
        default=_first(base.filter(groups=OuterRef(ref("group_id")))),
        output_field=_INT,
    )


def bits_expression(prefix: str = ""):
    """Açılışın növ maskası (0–3) — ``prefix`` sorğu modelindən açılışa gedən yoldur
    (``""`` — ``CourseOffering``, ``"offering__"`` — komponent, ``"lesson__offering__"`` — bal işarəsi)."""
    from apps.registrar.models import LessonMark, ScheduleSlot

    def ref(name):
        return prefix + name

    offering_id = OuterRef(ref("id"))
    planned = Coalesce(NullIf(_curriculum_bits(ref), Value(0)), _workload_bits(ref), Value(0), output_field=_INT)
    slots = _flag(Exists(ScheduleSlot.objects.filter(offering_id=offering_id, kind=SEMINAR)), SEMINAR_BIT) + _flag(
        Exists(ScheduleSlot.objects.filter(offering_id=offering_id, kind=LAB)), LAB_BIT
    )
    scored = LessonMark.objects.filter(lesson__offering_id=offering_id, score__isnull=False)
    marked = _flag(Exists(scored.filter(lesson__kind=SEMINAR)), SEMINAR_BIT) + _flag(
        Exists(scored.filter(lesson__kind=LAB)), LAB_BIT
    )
    plan_kinds = Coalesce(NullIf(planned.bitand(BOTH), Value(0)), slots, output_field=_INT)
    return plan_kinds.bitor(marked)


def bits_map(offering_ids) -> dict:
    """``{offering_id: maska}`` — verilmiş açılışlar üçün TƏK sorğu."""
    from apps.registrar.models import CourseOffering

    ids = [oid for oid in dict.fromkeys(offering_ids) if oid is not None]
    if not ids:
        return {}
    rows = (
        CourseOffering.objects.filter(id__in=ids)
        .annotate(**{BITS_ATTR: bits_expression()})
        .values_list("id", BITS_ATTR)
    )
    return {offering_id: int(bits or 0) for offering_id, bits in rows}


def remember(offering, bits) -> int:
    """Tək açılış nümunəsinə maskanı memo kimi yaz (eyni nümunədə təkrar sorğu olmasın)."""
    bits = int(bits or 0)
    if offering is not None:
        setattr(offering, _MEMO_ATTR, bits)
    return bits


def known_bits(offering, marks=()):
    """Sorğusuz bilinən maska: nümunənin memo-su, yoxdursa bal sətirlərinin annotasiyası; bilinmirsə ``None``."""
    memo = getattr(offering, _MEMO_ATTR, None) if offering is not None else None
    if memo is not None:
        return memo
    for mark in marks:
        bits = getattr(mark, BITS_ATTR, None)
        return None if bits is None else remember(offering, bits)
    return None


def bits_for_offering(offering) -> int:
    """Tək açılış — memo varsa sorğusuz, yoxdursa BİR sorğu (nəticə nümunəyə yazılır)."""
    memo = known_bits(offering)
    if memo is not None:
        return memo
    return remember(offering, bits_map([offering.id]).get(offering.id, 0))


class PendingBits:
    """Toplu dəstdə maskası hələ oxunmamış açılışlar — İLK ehtiyacda HAMISI bir sorğu ilə oxunur."""

    __slots__ = ("_ids", "_bits")

    def __init__(self, offering_ids):
        self._ids = list(dict.fromkeys(offering_ids))
        self._bits = None

    def get(self, offering_id) -> int:
        if self._bits is None:
            self._bits = bits_map(self._ids)
        return self._bits.get(offering_id, 0)

    def lazy(self, offering_id):
        """``EntryRule.activity_bits`` üçün tənbəl dəyər (yalnız lazım olanda sorğu)."""
        return lambda: self.get(offering_id)


def splits(bits) -> bool:
    """Fənn həm seminar, həm laboratoriya növlüdür (5 + 5 qaydası tətbiq olunur)."""
    return resolve(bits) & BOTH == BOTH


__all__ = [
    "ACTIVITY_MAX",
    "BITS_ATTR",
    "BOTH",
    "KIND_ATTR",
    "LAB",
    "LAB_BIT",
    "SEMINAR",
    "SEMINAR_BIT",
    "ActivityDetail",
    "LessonTotals",
    "PendingBits",
    "activity",
    "annotate_kind",
    "bits_expression",
    "bits_for_offering",
    "bits_map",
    "half_part",
    "known_bits",
    "mark_kind",
    "pooled_mean",
    "remember",
    "resolve",
    "splits",
    "totals_by_key",
    "totals_from_marks",
]
