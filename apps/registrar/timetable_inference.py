"""Jurnal dərslərindən həftəlik cədvəlin çıxarılması — analiz qatı (sahib 2026-10-24, qaydalar 2026-10-25).

Sahib: «hər müəllimin faktiki keçdiyi dərs saatlarını nəzərə alaraq dərs cədvəlini rəsmiləşdir — dəqiq
bilək ki, bu müəllim bu saatda dərs deyir; üst/alt həftə, mühazirə və seminar; patok bir slot qalsın».
2026-10-25: «jurnalı ÇOXLUQ olaraq yazdığı dərs saatlarına əsasən, alt-üst həftə və s. hər şey nəzərə alınaraq».
``backfill_teacher_lessons``-in TƏRSİ: orada slot → dərs, burada keçirilmiş dərs (``Lesson``) → slot.
Yazı / toqquşma / hesabat qatı: :mod:`apps.registrar.timetable_inference_plan`.

QAYDALAR
--------
* FAKT: semestrin [from, to] aralığındakı dərs sətri (``Lesson``) — tarix, başlama/bitmə saatı, növ,
  EFFEKTİV müəllim (``Lesson.instructor``, boşdursa jurnal sahibi — ``schedule.effective_instructor_id`` ilə
  eyni qayda), otaq. Saatı olmayan, cədvəldən KƏNAR işarəli (``off_schedule_reason`` — əvəzetmə /
  kompensasiya), müəllimsiz və passiv açılışın dərsləri sayılır, amma slot üçün işlənmir.
* ZƏNG (2026-10-25): redaktor yalnız universitetin standart zənglərini qəbul edir
  (``schedule.STANDARD_LESSON_TIMES``). Standartdan kənar başlama (11:30, 10:00, 13:30 …) ən yaxın standart
  zəngə ``snap_minutes`` (defolt 25 dəq) daxilindədirsə ona çəkilir (``snapped``) — eyni dərsin 11:30 / 11:50
  yazılışları bir vahiddə toplanır; uzaqdırsa olduğu kimi qalır.
* AÇAR: müəllim × həftə günü × başlama saatı × dərs növü. Açar daxilində ``min_occurrences``-dən (defolt 2)
  AZ tarixli açılış birdəfəlik / kompensasiya dərsidir (``below_threshold``) — o, axına QOŞULMUR (əvvəl bir
  təsadüfi dərs başqa fənnin axınına yapışıb bütün axını «qarışıq fənn» edirdi). Qalan açılışlar tarixlərinin
  ƏKSƏRİYYƏTİNDƏ birlikdədirsə (ortaq tarix × 2 ≥ kiçik dəstin tarixi) birləşdirilir — bu, AXINDIR (patok:
  bir dərs, bir neçə qrup). Hər komponent bir VAHİDDİR; fərqli tarixlərdə eyni saatı paylaşan açılışlar
  (məs. A qrupu üst, B qrupu alt həftə) ayrı vahidlərdir.
* AXIN bölünmür: vahidin bütün qrupları EYNİ gün/saat/həftə növü/otaqla yazılır. 2026-10-25-dən birgə
  MƏŞĞƏLƏ də axındır (``schedule.is_joint_lecture`` — eyni müəllim + fənn + EYNİ növ). Fərqli fənlərdən
  yığılmış axın (``stream_mixed_subjects``) cədvəl modelində ifadə oluna bilmir — qeyri-müəyyən, yazılmır.
* HƏFTƏ (çoxluq qaydası): hər tarixin üst/alt pariteti ``schedule.week_parity`` ilə (dövrün ilk həftəsi =
  üst/odd — jurnalın «Aktivləşdir»i və ``backfill_teacher_lessons`` ilə EYNİ). Azlıq paritetin payı
  ``parity_tolerance``-dən (defolt 0.25) çox deyilsə çoxluq qalib — azlıq kompensasiya sayılır (3 üst + 1 alt →
  üst); əks halda hər həftə (``all``).
* BİTMƏ SAATI: ən çox rast gələn; yoxdursa standart zəngin sonu; standartdan kənar başlamada ən yaxın zəngin
  müddəti.
* KÖÇÜRÜLMÜŞ DƏRS («sonuncu qalib»): eyni qrup dəsti (qrup / axın) × eyni növ üçün iki yararlı vahidin tarix
  aralıqları KƏSİŞMİRSƏ köhnəsi yazılmır — eyni müəllimdə ``moved_later`` (saat dəyişib), fərqli müəllimdə
  ``teacher_changed`` (fənn başqa müəllimə verilib). Aralıqları kəsişən vahidlər (həftədə iki mühazirə,
  paralel alt qrup) hər ikisi qalır.
* AZLIQ / HƏFTƏLİK SAAT (çoxluq qaydası, 2026-10-25): eyni açılış × növ üzrə ən güclü vahid qalır; plan / yük
  saatı (``budgets``: ``{(açılış, növ): həftəlik slot}``; ``all`` = 1, üst/alt = 0.5) dolubsa ondan xeyli zəif
  vahid kompensasiyadır (``over_weekly_hours``), saat məlum deyilsə yarısından zəif vahid (``minority_slot``).
  Müntəzəm (güclü) vahid plan saatından artıq olsa da qalır — jurnal faktdır. Bax :func:`apply_weekly_budget`.
* YENİ BAŞLAMIŞ AÇILIŞ: ilk dərsi aralığın son ``recent_days`` (defolt 14) günündədirsə və heç bir yararlı
  vahidi yoxdursa son dərsinin günü / saatı hər həftə slotu olur (``recent_start``) — :func:`promote_recent`.
* OTAQ (2026-10-25): vahidin dərslərində ən çox yazılan otaq (bərabərlikdə ən son istifadə olunan); yoxdursa
  müəllimin həmin gün/saatdakı, sonra ümumən ən çox yazdığı otaq — :func:`assign_rooms`. Toqquşursa otaqsız.
"""

from __future__ import annotations

import datetime as dt
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from django.db.models import Q

from apps.registrar import schedule
from apps.registrar.models import Lesson, SlotKind, WeekType

DEFAULT_MIN_OCCURRENCES = 2
DEFAULT_PARITY_TOLERANCE = 0.25
DEFAULT_SNAP_MINUTES = 25
DEFAULT_RECENT_DAYS = 14
MAX_ROOM_CANDIDATES = 8  # əsas + 7 növbəti otaq (tutulubsa)
#: Cədvəl şəbəkəsinin günləri (B.e. … Şənbə — ``schedule_grid.TEACHING_WEEKDAYS``); bazar günü çəkilmir.
GRID_WEEKDAYS = frozenset(range(1, 7))

# Otağın mənbəyi (hesabat)
ROOM_FROM_LESSONS = "lessons"
ROOM_FROM_TEACHER_SLOT = "teacher_slot"
ROOM_FROM_TEACHER = "teacher"

# Vahid / sətir statusları
READY = "ready"
BELOW_THRESHOLD = "below_threshold"
AMBIGUOUS = "ambiguous"
SUPERSEDED = "superseded"

#: Fakt sayğacının açarları (stdout sırası).
FACT_KEYS = (
    "lessons",
    "used",
    "snapped",
    "no_time",
    "off_schedule",
    "no_teacher",
    "inactive_offering",
    "unknown_kind",
    "legacy",
)


@dataclass(frozen=True)
class Rules:
    """Çıxarışın parametrləri (komanda bayraqları): hədd, paritet tolerantlığı, zəng çəkmə, həftəlik saat."""

    min_occurrences: int = DEFAULT_MIN_OCCURRENCES
    parity_tolerance: float = DEFAULT_PARITY_TOLERANCE
    snap_minutes: int = DEFAULT_SNAP_MINUTES
    hours_cap: bool = True
    fill_rooms: bool = True
    recent_days: int = DEFAULT_RECENT_DAYS


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
    room_source: str = ""
    # Əsas otaq eyni vaxt başqa dərsdə tutulubsa sınanan növbəti otaqlar: [(otaq, mənbə)], ən çox yazılandan.
    room_alternatives: list = field(default_factory=list)
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

    @property
    def weight(self) -> float:
        """Həftəlik yük: hər həftə = 1, üst / alt = 0.5."""
        return 1.0 if self.week_type == WeekType.ALL else 0.5

    def sort_key(self) -> tuple:
        """Güclü sübut əvvəl: çox tarixli, sonra böyük axın — toqquşmada zəif olan düşsün."""
        return (-len(self.dates), -len(self.members), str(self.teacher_id), self.weekday, self.start, self.kind)


# ── Zəng ────────────────────────────────────────────────────────────────────


def _minutes(value: dt.time) -> int:
    return value.hour * 60 + value.minute


def _bells() -> list[tuple[dt.time, dt.time]]:
    return [(dt.time.fromisoformat(start), dt.time.fromisoformat(end)) for start, end in schedule.STANDARD_LESSON_TIMES]


def snap_to_bell(start: dt.time, end, max_minutes: int) -> tuple[dt.time, dt.time | None]:
    """Standartdan kənar başlamanı ``max_minutes`` daxilindəki ən yaxın standart zəngə çək (bitmə = zəngin sonu)."""
    bells = _bells()
    if max_minutes <= 0 or any(bell_start == start for bell_start, _end in bells):
        return start, end
    distance, bell = min((abs(_minutes(bell[0]) - _minutes(start)), bell) for bell in bells)
    if distance <= max_minutes:
        return bell
    return start, end


def fallback_end(start: dt.time):
    """Bitmə saatı yazılmayıbsa: standart zəngin sonu; kənar başlamada ən yaxın zəngin müddəti."""
    bells = _bells()
    for bell_start, bell_end in bells:
        if bell_start == start:
            return bell_end
    _distance, (bell_start, bell_end) = min((abs(_minutes(bell[0]) - _minutes(start)), bell) for bell in bells)
    total = _minutes(start) + _minutes(bell_end) - _minutes(bell_start)
    if total >= 24 * 60:
        return None
    return dt.time(total // 60, total % 60)


# ── Faktlar ─────────────────────────────────────────────────────────────────


def _room_label(name, code) -> str:
    """Canlı slotun otaq mətni — ``schedule_suggest.load_rooms`` ilə eyni (ad, yoxdursa kod)."""
    return ((name or "").strip() or (code or "").strip())[:64]


def load_facts(
    *, organization, period, date_from, date_to, teacher=None, snap_minutes: int = DEFAULT_SNAP_MINUTES
) -> tuple[list[LessonFact], Counter]:
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
            snapped_start, end = snap_to_bell(start, end, snap_minutes)
            if snapped_start != start:
                stats["snapped"] += 1
            facts.append(
                LessonFact(
                    offering_id,
                    subject_id,
                    day,
                    snapped_start,
                    end,
                    kind,
                    teacher_id,
                    _room_label(room_name, room_code),
                )
            )
    return facts, stats


# ── Vahidlər ────────────────────────────────────────────────────────────────


def _components(by_offering: dict) -> list[list]:
    """Tarixlərinin ƏKSƏRİYYƏTİNİ paylaşan açılışları birləşdir (union-find) → komponentlər."""
    keys = sorted(by_offering, key=str)
    parent = {pk: pk for pk in keys}

    def find(key):
        while parent[key] != key:
            parent[key] = parent[parent[key]]
            key = parent[key]
        return key

    for index, left in enumerate(keys):
        for right in keys[index + 1 :]:
            shared = len(by_offering[left] & by_offering[right])
            if shared and shared * 2 >= min(len(by_offering[left]), len(by_offering[right])):
                parent[find(right)] = find(left)
    groups = defaultdict(list)
    for pk in keys:
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


def decide_week_type(odd: int, even: int, tolerance: float = DEFAULT_PARITY_TOLERANCE) -> str:
    """Çoxluq qaydası: azlıq paritetin payı ``tolerance``-dən çox deyilsə çoxluq qalib, əks halda hər həftə."""
    total = odd + even
    if not total:
        return ""
    if min(odd, even) <= total * tolerance:
        return WeekType.ODD if odd > even else WeekType.EVEN
    return WeekType.ALL


def _decide_end(unit: Unit):
    ends = Counter(fact.end for fact in unit.facts if fact.end is not None)
    if ends:
        return sorted(ends.items(), key=lambda item: (-item[1], item[0]))[0][0]
    return fallback_end(unit.start)


def most_used_room(facts) -> str:
    """Ən çox yazılan otaq (böyük/kiçik hərf fərqi yox); bərabərlikdə ƏN SON istifadə olunan; otaq yoxdursa ``""``."""
    ranked = ranked_rooms(facts)
    return ranked[0] if ranked else ""


def ranked_rooms(facts) -> list:
    """Otaqlar ən çox yazılandan azına (bərabərlikdə ƏN SON istifadə olunan əvvəl); boş otaqlar sayılmır."""
    counts: Counter = Counter()
    last: dict = {}
    labels: dict = {}
    for fact in facts:
        key = fact.room.strip().lower()
        if not key:
            continue
        counts[key] += 1
        if fact.date >= last.get(key, dt.date.min):
            last[key], labels[key] = fact.date, fact.room.strip()
    order = sorted(counts, key=lambda key: (counts[key], last[key], key), reverse=True)
    return [labels[key] for key in order]


def assign_rooms(units, facts) -> None:
    """Yararlı vahidin otağı (sahib 2026-10-25: «müəllimin ən çox yazdığı otağı çıxardaq ki, harada dərs keçir»).

    1. vahidin ÖZ dərslərində ən çox yazılan otaq (``room_source = "lessons"``);
    2. yoxdursa — müəllimin HƏMİN gün + başlama saatındakı bütün dərslərində ən çox otaq (``teacher_slot``);
    3. o da yoxdursa — müəllimin bu aralıqdakı bütün dərslərində ən çox otaq (``teacher``).
    Otaq toqquşması (eyni otaq, eyni vaxt) plan qatında ``schedule_conflicts.detect`` ilə yoxlanır; əsas otaq tutulubsa
    plan eyni sıra ilə növbəti otaqları sınayır (``room_alternatives``, sahib 2026-10-25: «bəzi müəllimlərin otaqları
    düşməyib»)."""
    by_slot: dict = defaultdict(list)
    by_teacher: dict = defaultdict(list)
    for fact in facts:
        if fact.room.strip():
            by_slot[(fact.teacher_id, fact.date.isoweekday(), fact.start)].append(fact)
            by_teacher[fact.teacher_id].append(fact)
    for unit in units:
        if unit.status != READY:
            continue
        candidates, seen = [], set()
        for source, pool in (
            (ROOM_FROM_LESSONS, unit.facts),
            (ROOM_FROM_TEACHER_SLOT, by_slot.get((unit.teacher_id, unit.weekday, unit.start), ())),
            (ROOM_FROM_TEACHER, by_teacher.get(unit.teacher_id, ())),
        ):
            for room in ranked_rooms(pool):
                key = room.strip().lower()
                if key not in seen:
                    seen.add(key)
                    candidates.append((room[:64], source))
        if candidates:
            (unit.room, unit.room_source), unit.room_alternatives = candidates[0], candidates[1:MAX_ROOM_CANDIDATES]


def _classify(unit: Unit, *, period, min_occurrences: int, parity_tolerance: float) -> None:
    if len(unit.dates) < min_occurrences:
        unit.status, unit.reason = BELOW_THRESHOLD, "below_threshold"
        return
    if unit.weekday not in GRID_WEEKDAYS:
        unit.status, unit.reason = AMBIGUOUS, "weekday_outside_grid"
        return
    if len(unit.subject_ids) > 1:
        unit.status, unit.reason = AMBIGUOUS, "stream_mixed_subjects"
        return
    unit.odd, unit.even = parity_counts(period, unit.dates)
    unit.week_type = decide_week_type(unit.odd, unit.even, parity_tolerance)
    unit.end = _decide_end(unit)
    if unit.end is None or unit.end <= unit.start:
        unit.status, unit.reason = AMBIGUOUS, "no_end_time"
        return


def build_units(
    facts,
    *,
    period,
    min_occurrences: int = DEFAULT_MIN_OCCURRENCES,
    parity_tolerance: float = DEFAULT_PARITY_TOLERANCE,
    budgets=None,
    recent_since=None,
) -> list[Unit]:
    """Faktlar → vahidlər (statusları ilə), güclü sübut birinci."""
    min_occurrences = max(1, int(min_occurrences))
    by_key: dict = defaultdict(list)
    for fact in facts:
        by_key[(fact.teacher_id, fact.date.isoweekday(), fact.start, fact.kind)].append(fact)
    units = []
    for (teacher_id, weekday, start, kind), rows in by_key.items():
        by_offering: dict = defaultdict(set)
        for fact in rows:
            by_offering[fact.offering_id].add(fact.date)
        strong = {pk: days for pk, days in by_offering.items() if len(days) >= min_occurrences}
        components = _components(strong) + [[pk] for pk in sorted(by_offering, key=str) if pk not in strong]
        for component in components:
            members = set(component)
            unit = Unit(teacher_id=teacher_id, weekday=weekday, start=start, kind=kind)
            unit.members = {pk: by_offering[pk] for pk in component}
            unit.facts = [fact for fact in rows if fact.offering_id in members]
            unit.subject_ids = {fact.subject_id for fact in unit.facts}
            _classify(unit, period=period, min_occurrences=min_occurrences, parity_tolerance=parity_tolerance)
            units.append(unit)
    mark_superseded(units)
    if budgets is not None:
        apply_weekly_budget(units, budgets)
    if recent_since is not None:
        promote_recent(units, period=period, since=recent_since)
    assign_rooms(units, facts)
    units.sort(key=Unit.sort_key)
    return units


def promote_recent(units, *, period, since) -> None:
    """Yeni başlamış açılış (sahib: «hər aktiv açılışın real həftəlik cədvəli»): açılış × növün İLK dərsi
    ``since``-dən (defolt: aralığın son 14 günü) gec deyilsə və onun heç bir yararlı vahidi yoxdursa, ən SON
    dərsinin günü / saatı hər həftə slotu kimi qəbul olunur (``recent_start``) — həddə çatmağa hələ vaxt olmayıb.
    Köhnədən gedən, amma nizamsız (hər dəfə başqa saat) açılışa bu qayda tətbiq OLUNMUR."""
    covered = {(str(pk), unit.kind) for unit in units if unit.status == READY for pk in unit.active_ids}
    first_seen: dict = {}
    for unit in units:
        for pk, days in unit.members.items():
            key = (str(pk), unit.kind)
            first_seen[key] = min(first_seen.get(key, dt.date.max), min(days))
    chosen: dict = {}
    for unit in units:
        if unit.status != BELOW_THRESHOLD or len(unit.members) != 1 or len(unit.subject_ids) != 1:
            continue
        key = (str(unit.offering_ids[0]), unit.kind)
        if key in covered or first_seen[key] < since or unit.weekday not in GRID_WEEKDAYS:
            continue
        current = chosen.get(key)
        if current is None or (max(unit.dates), current.start) > (max(current.dates), unit.start):
            chosen[key] = unit
    for unit in chosen.values():
        unit.odd, unit.even = parity_counts(period, unit.dates)
        unit.week_type = WeekType.ALL
        unit.end = _decide_end(unit)
        if unit.end is None or unit.end <= unit.start:
            unit.status, unit.reason = AMBIGUOUS, "no_end_time"
            continue
        unit.status, unit.reason = READY, "recent_start"


def mark_superseded(units) -> None:
    """«Sonuncu qalib»: eyni qrup dəsti × növ üzrə SONRA başlayan vahiddən tam əvvəl bitən yararlı vahid
    köçürülmüşdür — eyni müəllimdə ``moved_later``, fərqli müəllimdə ``teacher_changed``; aralıqları
    kəsişənlər toxunulmaz qalır."""
    families: dict = defaultdict(list)
    for unit in units:
        if unit.status == READY:
            families[(frozenset(str(pk) for pk in unit.active_ids), unit.kind)].append(unit)
    for family in families.values():
        if len(family) < 2:
            continue
        spans = [(min(unit.dates), max(unit.dates)) for unit in family]
        for unit, (_first, last) in zip(family, spans):
            later = [other for other, (first, _end) in zip(family, spans) if first > last]
            if later:
                same_teacher = any(str(other.teacher_id) == str(unit.teacher_id) for other in later)
                unit.status = SUPERSEDED
                unit.reason = "moved_later" if same_teacher else "teacher_changed"


def _strength(unit: Unit) -> float:
    """Həftə növünə görə normallaşdırılmış sübut: üst/alt vahidin ÖZ paritetindəki 3 tarixi = hər həftə vahidinin
    6 tarixi (azlıq paritetin kompensasiya tarixləri sayılmır)."""
    if unit.week_type == WeekType.ODD:
        return unit.odd * 2.0
    if unit.week_type == WeekType.EVEN:
        return unit.even * 2.0
    return float(len(unit.dates))


def apply_weekly_budget(units, budgets: dict) -> None:
    """Çoxluq qaydası — eyni açılış × növ üzrə AZLIQ vahid kompensasiya / köçürmədir.

    ``budgets`` — ``{(açılış id, növ): həftəlik slot}`` (plan / yük saatından; ``all`` = 1, üst/alt = 0.5).
    Vahidlər güclüdən zəifə (normallaşdırılmış tarix sayı, sonra son tarix gec) yerləşir; ən güclü vahid
    həmişə qalır. Sonrakı vahid:

    * büdcə məlumdur və hələ dolmayıb → qalır (plan həftədə bir neçə dərs nəzərdə tutur);
    * büdcə dolub → ən güclünün 2/3-dən zəifdirsə ``over_weekly_hours`` (kompensasiya); güclüdürsə QALIR —
      müntəzəm jurnal sübutu (məs. xarici dil həftədə 4 dəfə) plandakı səhv saatdan üstündür;
    * büdcə məlum deyil → ən güclünün yarısından zəifdirsə ``minority_slot``.

    Axın (bir neçə qrup) yalnız BÜTÜN qrupları üçün artıqdırsa düşür."""
    used: dict = defaultdict(float)
    best: dict = {}
    ready = [unit for unit in units if unit.status == READY]
    ready.sort(key=lambda unit: (-_strength(unit), -max(unit.dates).toordinal(), unit.sort_key()))
    for unit in ready:
        strength = _strength(unit)
        keys = [(str(pk), unit.kind) for pk in unit.active_ids]
        verdicts = []
        for key in keys:
            top, limit = best.get(key), budgets.get(key)
            if top is None:
                verdicts.append("")
            elif limit is None:
                verdicts.append("minority_slot" if strength * 2 < top else "")
            elif used[key] + 1e-9 < limit:
                verdicts.append("")
            else:
                verdicts.append("over_weekly_hours" if strength * 3 < top * 2 else "")
        if verdicts and all(verdicts):
            unit.status, unit.reason = SUPERSEDED, sorted(verdicts)[-1]
            continue
        for key in keys:
            used[key] += unit.weight
            best[key] = max(best.get(key, 0.0), strength)


__all__ = [
    "AMBIGUOUS",
    "BELOW_THRESHOLD",
    "DEFAULT_MIN_OCCURRENCES",
    "DEFAULT_PARITY_TOLERANCE",
    "DEFAULT_RECENT_DAYS",
    "DEFAULT_SNAP_MINUTES",
    "FACT_KEYS",
    "GRID_WEEKDAYS",
    "READY",
    "ROOM_FROM_LESSONS",
    "ROOM_FROM_TEACHER",
    "ROOM_FROM_TEACHER_SLOT",
    "SUPERSEDED",
    "LessonFact",
    "Rules",
    "Unit",
    "apply_weekly_budget",
    "assign_rooms",
    "build_units",
    "decide_week_type",
    "fallback_end",
    "load_facts",
    "mark_superseded",
    "most_used_room",
    "parity_counts",
    "promote_recent",
    "snap_to_bell",
]
