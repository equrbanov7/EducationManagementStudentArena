"""Jurnal dərslərindən həftəlik cədvəlin çıxarılması — analiz qatı (sahib 2026-10-24).

Sahib: «hər müəllimin faktiki keçdiyi dərs saatlarını nəzərə alaraq dərs cədvəlini rəsmiləşdir — dəqiq
bilək ki, bu müəllim bu saatda dərs deyir; üst/alt həftə, mühazirə və seminar; patok bir slot qalsın».
``backfill_teacher_lessons``-in TƏRSİ: orada slot → dərs, burada keçirilmiş dərs (``Lesson``) → slot.
Yazı / toqquşma / hesabat qatı: :mod:`apps.registrar.timetable_inference_plan`.

QAYDALAR
--------
* FAKT: semestrin [from, to] aralığındakı dərs sətri (``Lesson``) — tarix, başlama/bitmə saatı, növ,
  EFFEKTİV müəllim (``Lesson.instructor``, boşdursa jurnal sahibi — ``schedule.effective_instructor_id`` ilə
  eyni qayda), otaq. Saatı olmayan, cədvəldən KƏNAR işarəli (``off_schedule_reason`` — əvəzetmə /
  kompensasiya), müəllimsiz və passiv açılışın dərsləri sayılır, amma slot üçün işlənmir.
* AÇAR: müəllim × həftə günü × başlama saatı × dərs növü. Açar daxilində açılışlar EYNİ TARİXDƏ birlikdə
  keçirilibsə birləşdirilir (union-find) — bu, AXINDIR (patok: bir mühazirə, bir neçə qrup). Hər komponent
  bir VAHİDDİR; fərqli tarixlərdə eyni saatı paylaşan açılışlar (məs. A qrupu üst, B qrupu alt həftə)
  ayrı vahidlərdir.
* AXIN bölünmür: vahidin bütün qrupları EYNİ gün/saat/həftə növü/otaqla yazılır (canlı modeldə axın =
  eyni müəllim + fənn + mühazirə + otaq olan qrup-slotları, ``schedule.is_joint_lecture``). Fərqli fənlərdən
  yığılmış «axın» (``stream_mixed_subjects``) və bir müəllimin eyni anda iki qrupla seminar/laboratoriyası
  (``shared_non_lecture``) cədvəl modelində ifadə oluna bilmir — qeyri-müəyyən, yazılmır.
* HƏDD: vahidin fərqli tarixləri ``min_occurrences``-dən (defolt 2) azdırsa — birdəfəlik dərs
  (``below_threshold``); axında qrupun öz tarixləri həddən azdırsa yalnız o qrup düşür.
* HƏFTƏ: hər tarixin üst/alt pariteti ``schedule.week_parity`` ilə (dövrün ilk həftəsi = üst/odd — jurnalın
  «Aktivləşdir»i və ``backfill_teacher_lessons`` ilə EYNİ). Yalnız üst → ``odd``, yalnız alt → ``even``,
  ikisi də → ``all``; azlıq paritet təkdirsə və çoxluğun yarısından azdırsa (məs. 1 alt + 3 üst) —
  ``parity_mixed`` (təsadüfi dərs, yoxsa buraxılmış həftələr — bilinmir), yazılmır.
* BİTMƏ SAATI: ən çox rast gələn; yoxdursa universitetin standart zəngi; o da yoxdursa ``no_end_time``.
* OTAQ: dərslərin yarıdan çoxunda eyni otaqdırsa o, əks halda boş (sonra redaktorda doldurulur).
"""

from __future__ import annotations

import datetime as dt
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from django.db.models import Q

from apps.registrar import schedule
from apps.registrar.models import Lesson, SlotKind, WeekType

DEFAULT_MIN_OCCURRENCES = 2

# Vahid / sətir statusları
READY = "ready"
BELOW_THRESHOLD = "below_threshold"
AMBIGUOUS = "ambiguous"

#: Fakt sayğacının açarları (stdout sırası).
FACT_KEYS = ("lessons", "used", "no_time", "off_schedule", "no_teacher", "inactive_offering", "unknown_kind", "legacy")


@dataclass(frozen=True)
class LessonFact:
    offering_id: object
    subject_id: object
    date: dt.date
    start: dt.time
    end: dt.time | None
    kind: str
    teacher_id: int
    room: str


@dataclass
class Unit:
    """Bir müəllimin bir həftəlik saatı: tək qrup və ya axın (eyni tarixlərdə birlikdə keçən qruplar)."""

    teacher_id: int
    weekday: int
    start: dt.time
    kind: str
    members: dict = field(default_factory=dict)  # offering_id → {tarix}
    facts: list = field(default_factory=list)
    subject_ids: set = field(default_factory=set)
    status: str = READY
    reason: str = ""
    dropped: dict = field(default_factory=dict)  # offering_id → səbəb (axından düşən qrup)
    end: dt.time | None = None
    week_type: str = ""
    room: str = ""
    odd: int = 0
    even: int = 0

    @property
    def offering_ids(self) -> list:
        return sorted(self.members, key=str)

    @property
    def active_ids(self) -> list:
        return [pk for pk in self.offering_ids if pk not in self.dropped]

    @property
    def dates(self) -> set:
        out = set()
        for pk in self.active_ids:
            out |= self.members[pk]
        return out

    @property
    def is_stream(self) -> bool:
        return len(self.members) > 1

    def sort_key(self) -> tuple:
        """Güclü sübut əvvəl: çox tarixli, sonra böyük axın — toqquşmada zəif olan düşsün."""
        return (-len(self.dates), -len(self.members), str(self.teacher_id), self.weekday, self.start, self.kind)


# ── Faktlar ─────────────────────────────────────────────────────────────────


def _room_label(name, code) -> str:
    """Canlı slotun otaq mətni — ``schedule_suggest.load_rooms`` ilə eyni (ad, yoxdursa kod)."""
    return ((name or "").strip() or (code or "").strip())[:64]


def load_facts(*, organization, period, date_from, date_to, teacher=None) -> tuple[list[LessonFact], Counter]:
    """Aralığın dərsləri → slot üçün yararlı faktlar + sayğac (``FACT_KEYS``)."""
    queryset = Lesson.objects.filter(
        organization=organization, offering__period=period, date__range=(date_from, date_to)
    )
    if teacher is not None:
        queryset = queryset.filter(Q(instructor=teacher) | Q(instructor__isnull=True, offering__instructor=teacher))
    fields = (
        "offering_id",
        "offering__subject_id",
        "offering__is_active",
        "date",
        "start_time",
        "end_time",
        "kind",
        "instructor_id",
        "offering__instructor_id",
        "room__name",
        "room__code",
        "off_schedule_reason",
        "is_legacy_synthesised",
    )
    stats: Counter = Counter({key: 0 for key in FACT_KEYS})
    facts = []
    for row in queryset.values_list(*fields).iterator(chunk_size=5000):
        offering_id, subject_id, active, day, start, end, kind, own, owner, room_name, room_code, off, legacy = row
        stats["lessons"] += 1
        if legacy:
            stats["legacy"] += 1
        teacher_id = own or owner
        if start is None:
            stats["no_time"] += 1
        elif (off or "").strip():
            stats["off_schedule"] += 1
        elif not teacher_id:
            stats["no_teacher"] += 1
        elif not active:
            stats["inactive_offering"] += 1
        elif kind not in SlotKind.values:
            stats["unknown_kind"] += 1
        else:
            stats["used"] += 1
            end = end if end and end > start else None
            facts.append(
                LessonFact(
                    offering_id, subject_id, day, start, end, kind, teacher_id, _room_label(room_name, room_code)
                )
            )
    return facts, stats


# ── Vahidlər ────────────────────────────────────────────────────────────────


def _components(by_offering: dict) -> list[list]:
    """Eyni tarixi paylaşan açılışları birləşdir (union-find) → komponentlər."""
    parent = {pk: pk for pk in by_offering}

    def find(key):
        while parent[key] != key:
            parent[key] = parent[parent[key]]
            key = parent[key]
        return key

    first_on_day: dict = {}
    for pk in sorted(by_offering, key=str):
        for day in by_offering[pk]:
            other = first_on_day.setdefault(day, pk)
            if other != pk:
                parent[find(pk)] = find(other)
    groups = defaultdict(list)
    for pk in sorted(by_offering, key=str):
        groups[find(pk)].append(pk)
    return list(groups.values())


def parity_counts(period, days) -> tuple[int, int]:
    odd = even = 0
    for day in days:
        monday = day - dt.timedelta(days=day.weekday())
        if schedule.week_parity(period, monday) == WeekType.ODD:
            odd += 1
        else:
            even += 1
    return odd, even


def decide_week_type(odd: int, even: int) -> str:
    """Tarixlərin paritetindən həftə növü; ``""`` = qərar verilmir (``parity_mixed``)."""
    if odd and not even:
        return WeekType.ODD
    if even and not odd:
        return WeekType.EVEN
    minority, majority = min(odd, even), max(odd, even)
    if minority >= 2 or minority * 2 >= majority:
        return WeekType.ALL
    return ""


def _standard_end(start: dt.time):
    for start_text, end_text in schedule.STANDARD_LESSON_TIMES:
        if dt.time.fromisoformat(start_text) == start:
            return dt.time.fromisoformat(end_text)
    return None


def _decide_end(unit: Unit):
    ends = Counter(fact.end for fact in unit.facts if fact.end is not None)
    if ends:
        return sorted(ends.items(), key=lambda item: (-item[1], item[0]))[0][0]
    return _standard_end(unit.start)


def _decide_room(unit: Unit) -> str:
    rooms = Counter(fact.room.lower() for fact in unit.facts)
    labels = {}
    for fact in unit.facts:
        labels.setdefault(fact.room.lower(), fact.room)
    for key, count in sorted(rooms.items(), key=lambda item: (-item[1], item[0])):
        if key and count * 2 > len(unit.facts):
            return labels[key]
    return ""


def _classify(unit: Unit, *, period, min_occurrences: int) -> None:
    if len(unit.subject_ids) > 1:
        unit.status, unit.reason = AMBIGUOUS, "stream_mixed_subjects"
        return
    if unit.is_stream and unit.kind != SlotKind.LECTURE:
        unit.status, unit.reason = AMBIGUOUS, "shared_non_lecture"
        return
    if len(unit.dates) < min_occurrences:
        unit.status, unit.reason = BELOW_THRESHOLD, "below_threshold"
        return
    for pk in unit.offering_ids:
        if len(unit.members[pk]) < min_occurrences:
            unit.dropped[pk] = "member_below_threshold"
    if len(unit.dates) < min_occurrences:
        unit.status, unit.reason = BELOW_THRESHOLD, "below_threshold"
        return
    unit.odd, unit.even = parity_counts(period, unit.dates)
    unit.week_type = decide_week_type(unit.odd, unit.even)
    if not unit.week_type:
        unit.status, unit.reason = AMBIGUOUS, "parity_mixed"
        return
    active = set(unit.active_ids)
    unit.facts = [fact for fact in unit.facts if fact.offering_id in active]
    unit.end = _decide_end(unit)
    if unit.end is None or unit.end <= unit.start:
        unit.status, unit.reason = AMBIGUOUS, "no_end_time"
        return
    unit.room = _decide_room(unit)


def build_units(facts, *, period, min_occurrences: int = DEFAULT_MIN_OCCURRENCES) -> list[Unit]:
    """Faktlar → vahidlər (statusları ilə), güclü sübut birinci."""
    by_key: dict = defaultdict(list)
    for fact in facts:
        by_key[(fact.teacher_id, fact.date.isoweekday(), fact.start, fact.kind)].append(fact)
    units = []
    for (teacher_id, weekday, start, kind), rows in by_key.items():
        by_offering: dict = defaultdict(set)
        for fact in rows:
            by_offering[fact.offering_id].add(fact.date)
        for component in _components(by_offering):
            members = set(component)
            unit = Unit(teacher_id=teacher_id, weekday=weekday, start=start, kind=kind)
            unit.members = {pk: by_offering[pk] for pk in component}
            unit.facts = [fact for fact in rows if fact.offering_id in members]
            unit.subject_ids = {fact.subject_id for fact in unit.facts}
            _classify(unit, period=period, min_occurrences=max(1, int(min_occurrences)))
            units.append(unit)
    units.sort(key=Unit.sort_key)
    return units


__all__ = [
    "AMBIGUOUS",
    "BELOW_THRESHOLD",
    "DEFAULT_MIN_OCCURRENCES",
    "FACT_KEYS",
    "READY",
    "LessonFact",
    "Unit",
    "build_units",
    "decide_week_type",
    "load_facts",
    "parity_counts",
]
