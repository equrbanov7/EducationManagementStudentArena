"""Mühərrikin verilənlər tipləri — SAF Python (Django-dan asılı DEYİL).

Model (ITC-2019 / UniTime ruhunda, universitet cədvəli üçün sadələşdirilmiş):

* **Vaxt şəbəkəsi** — ``days × pairs`` xana; xana indeksi ``t = gün * pairs + cüt``
  (hər ikisi 0-dan). Həftə pariteti ayrıca ölçüdür: ``wk = 0`` üst (odd),
  ``wk = 1`` alt (even) həftə.
* **Hadisə (Event)** — bir dərs cütü: mühazirə/məşğələ/laboratoriya. Həftəlik hadisə
  hər iki həftəni tutur (``WEEK_BOTH``); iki həftədən bir keçirilən hadisə üçün
  mühərrik özü üst VƏ YA alt həftəni seçir (``WEEK_ODD`` / ``WEEK_EVEN``).
* **Resurslar** — müəllimlər və **kohortlar** (tələbə axınları: alt qrup və ya
  birbaşa tələbəsi olan qrup). Ana qrupun hadisəsi bütün alt qruplarının
  kohortunu tutur — beləcə «alt qrup ↔ ana qrup» toqquşması da görünür.
* **Korpus (Building)** — eyni anda keçirilə bilən dərs sayına üst hədd
  (otaq sayı); otaqların özü vaxtdan SONRA təyin olunur (``rooms.py``).

Dəyər (value) = ``(t, week)`` və ya ``None`` (yerləşdirilməyib).
"""

from __future__ import annotations

from dataclasses import dataclass, field

WEEK_BOTH = 0  # hər həftə (üst + alt)
WEEK_ODD = 1  # yalnız üst həftə
WEEK_EVEN = 2  # yalnız alt həftə

#: Dəyərin həftə kodu → tutduğu həftə indeksləri (0 = üst, 1 = alt).
WEEKS_OF = {WEEK_BOTH: (0, 1), WEEK_ODD: (0,), WEEK_EVEN: (1,)}

#: Mühərrik kodu → ``ScheduleSlot.week_type`` dəyəri.
WEEK_CODES = {WEEK_BOTH: "all", WEEK_ODD: "odd", WEEK_EVEN: "even"}
WEEK_FROM_CODE = {code: week for week, code in WEEK_CODES.items()}

#: Müəllimin xana səviyyələri (``TeacherAvailability.grid`` simvolları ilə eyni).
LEVEL_UNAVAILABLE = "u"
LEVEL_DISCOURAGED = "d"
LEVEL_NEUTRAL = "n"
LEVEL_PREFERRED = "p"


def priority_factor(priority: int) -> float:
    """Prioritet (1..5) → çəki əmsalı: 1, 1.5, 2, 2.5, 3."""
    value = max(1, min(5, int(priority or 1)))
    return 1.0 + (value - 1) * 0.5


@dataclass
class Weights:
    """Cərimə çəkiləri. ``hard`` > hər hansı yumşaq cəmdən; ``unplaced`` < ``hard``.

    Beləcə mühərrik sərt qaydanı pozmaqdansa dərsi yerləşdirilməmiş saxlamağı
    üstün tutur, amma yerləşdirmə hər yumşaq cərimədən vacibdir.
    """

    hard: int = 1_000_000
    unplaced: int = 150_000
    teacher_idle: int = 40
    teacher_day: int = 3
    teacher_overload: int = 60
    teacher_days_over: int = 80
    discouraged: int = 14
    neutral: int = 2
    group_overload: int = 40
    group_single_day: int = 8
    group_balance: int = 1
    same_subject_day: int = 4
    same_kind_day: int = 20
    late_pair: int = 3
    move: int = 25

    @classmethod
    def from_dict(cls, raw: dict | None) -> "Weights":
        weights = cls()
        for key, value in (raw or {}).items():
            if hasattr(weights, key) and key not in ("hard", "unplaced"):
                try:
                    setattr(weights, key, max(0, int(value)))
                except (TypeError, ValueError):
                    continue
        return weights

    def as_dict(self) -> dict:
        return dict(self.__dict__)


@dataclass
class Teacher:
    key: str
    label: str = ""
    priority: int = 1
    max_per_day: int = 0  # 0 = limitsiz
    max_days: int = 0  # 0 = limitsiz
    #: Hər xana üçün səviyyə simvolu (uzunluq = days * pairs); boşdursa hamısı neytral.
    levels: str = ""


@dataclass
class Cohort:
    key: str
    label: str = ""
    max_per_day: int = 0
    is_master: bool = False
    #: İcazəli xanalar (qrupun növbə siyasəti) — yoxlayıcı üçün.
    allowed: frozenset = frozenset()


@dataclass
class Building:
    key: str
    label: str = ""
    capacity: int = 0  # eyni anda dərs sayı (otaq sayı); 0 = məhdudiyyət yoxdur


@dataclass
class Room:
    key: str
    label: str = ""
    building: int | None = None
    capacity: int = 0  # 0 = naməlum tutum


@dataclass
class Event:
    key: str
    kind: str
    teacher: int | None
    cohorts: tuple
    course: int
    biweekly: bool
    domain: tuple
    pref: dict = field(default_factory=dict)
    priority: int = 1
    fixed: tuple | None = None
    hint: tuple | None = None
    building: int | None = None
    size: int = 0
    domain_reason: str = ""
    meta: dict = field(default_factory=dict)

    def values(self) -> list:
        """Hadisənin mümkün dəyərləri (sabit sıra — determinizm üçün)."""
        if self.biweekly:
            out = []
            for t in self.domain:
                out.append((t, WEEK_ODD))
                out.append((t, WEEK_EVEN))
            return out
        return [(t, WEEK_BOTH) for t in self.domain]


@dataclass
class Instance:
    days: int
    pairs: int
    teachers: list
    cohorts: list
    events: list
    buildings: list = field(default_factory=list)
    rooms: list = field(default_factory=list)
    #: Kənar (sabit) məşğulluq: [(teacher_index, week, t)] — başqa fakültənin dərc
    #: olunmuş dərsləri. Müəllimin boşluq hesabına daxildir, toqquşma sərtdir.
    teacher_busy: list = field(default_factory=list)
    #: Korpusda kənar dərslərin tutduğu otaq sayı: [(building, week, t, count)].
    building_busy: list = field(default_factory=list)
    #: Kənar dərslərin tutduğu otaqlar: [(room_index, week, t)].
    room_busy: list = field(default_factory=list)
    #: Axşam bandından əvvəlki son «gec olmayan» cüt (bakalavr üçün gec saat cəriməsi).
    late_after: int = 5

    @property
    def slots(self) -> int:
        return self.days * self.pairs


@dataclass
class Params:
    seed: int = 1
    time_limit: float = 30.0
    #: 0 → yalnız vaxtla məhdud; >0 → iterasiya büdcəsi (deterministik nəticə).
    max_iterations: int = 0
    weights: Weights = field(default_factory=Weights)
    t_start: float = 30.0
    t_end: float = 0.4


@dataclass
class Result:
    values: list
    rooms: list
    unplaced: list
    kpis: dict
    log: list
    stats: dict


__all__ = [
    "LEVEL_DISCOURAGED",
    "LEVEL_NEUTRAL",
    "LEVEL_PREFERRED",
    "LEVEL_UNAVAILABLE",
    "WEEKS_OF",
    "WEEK_BOTH",
    "WEEK_CODES",
    "WEEK_EVEN",
    "WEEK_FROM_CODE",
    "WEEK_ODD",
    "Building",
    "Cohort",
    "Event",
    "Instance",
    "Params",
    "Result",
    "Room",
    "Teacher",
    "Weights",
    "priority_factor",
]
