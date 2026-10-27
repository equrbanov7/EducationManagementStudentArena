"""Tələbənin fənn üzrə «ev» jurnalı — eyni fənn+dövrün bir neçə legacy jurnalı arasında seçim (RİM 2026-10-27).

Problem (MR-11/15): delta qeydiyyatı ``(tələbə, fənn, dövr)`` üzrə BİR sətir açır və «ilk emal olunan» legacy jurnal
qalib gəlirdi — passivləşdirilmiş (``active=0``) köhnə jurnal və ya tələbənin yalnız qalıq xanaları olan BAŞQA qrupun
jurnalı da. Sonrakı (əsl) jurnalın xanaları həmin açılışa 1–3 xanalı «fantom dərs» kimi yazılırdı; yalnız «qb» olan
fantom dərslər atılırdı → real qayıblar itirdi.

Qayda (deterministik, emal sırasından ASILI DEYİL):

* namizəd = AKTİV (``active != 0``) jurnal, tələbə onun siyahısındadır və ya xanası var; passiv jurnal SEÇİLMİR;
* sıra: siyahıda olan → xanası çox olan → tarixi çox olan → jurnal id kiçik olan;
* qalib jurnalın tələbə üçün seçilən açılışı (``JournalSlices.pick``) «ev»dir. Ev açılışı ilə eyni AİLƏDƏN olan
  açılışlar (eyni açılış, ana ↔ alt qrup — məs. mühazirə jurnalı + laboratoriya alt qrupu jurnalı) TAMAMLAYICIDIR:
  onların xanaları əvvəlki kimi ev qeydiyyatına yazılır (dərs yaradıla bilər). Başqa ailədən (paralel qrupun
  jurnalı — «əkiz») olan xana yalnız ev açılışında EYNİ tarix + saatda MÖVCUD dərsə düşür, yeni dərs açmır.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .extract import parse_id_list

CALENDAR = {f"{month:02d}" for month in range(1, 13)}


def journal_is_active(journal: dict) -> bool:
    """Legacy ``journals.active`` — boş/NULL aktiv sayılır (köhnə paketlərdə sütun olmaya bilər)."""

    value = journal.get("active")
    if value is None or value == "":
        return True
    try:
        return int(value) != 0
    except (TypeError, ValueError):
        return True


def units_related(catalog, left_id, right_id) -> bool:
    """Eyni qrup və ya ana ↔ alt qrup (ad şablonu və ya ``settings.parent_group`` izi)."""

    from apps.registrar.public import subgroup_rollup

    if left_id is None or right_id is None:
        return False
    if left_id == right_id:
        return True
    left, right = catalog.units.get(left_id), catalog.units.get(right_id)
    if left is None or right is None:
        return False
    for one, other in ((left, right), (right, left)):
        trail = (one.settings or {}).get("parent_group") if isinstance(one.settings, dict) else None
        if trail and str(trail) == str(other.pk):
            return True
    return subgroup_rollup.is_subgroup_of(left.name, right.name) or subgroup_rollup.is_subgroup_of(
        right.name, left.name
    )


def offerings_related(catalog, left, right) -> bool:
    if left is None or right is None:
        return False
    if left.pk == right.pk:
        return True
    return units_related(catalog, left.group_id, right.group_id)


@dataclass
class Candidate:
    journal_id: int
    offering: object
    listed: bool
    cells: int = 0
    dates: set = field(default_factory=set)

    def rank(self) -> tuple:
        return (self.listed, self.cells, len(self.dates), -int(self.journal_id))


def cell_counts(points) -> dict:
    """``(uniqid, legacy tələbə) → (dolu xana sayı, {(ay, gün)})`` — yalnız təqvim ayları, boş xana sayılmır."""

    out: dict = {}
    for row in points:
        if row.get("month_id") not in CALENDAR or not str(row.get("point") or "").strip():
            continue
        key = (row["journal_uniqid"], row["student_id"])
        count, dates = out.get(key, (0, set()))
        dates.add((row["month_id"], str(row.get("day_number"))))
        out[key] = (count + 1, dates)
    return out


class HomeIndex:
    """``(hesab, fənn, dövr) → ev açılışı`` — bütün jurnallar bir dəfə gəzilir, sonra seçim."""

    def __init__(self, catalog):
        self.catalog = catalog
        self._candidates: dict = {}

    def observe(self, key, journal_id, offering, *, listed: bool, cells: int, dates) -> None:
        bucket = self._candidates.setdefault(key, {})
        current = bucket.get(journal_id)
        if current is None:
            bucket[journal_id] = Candidate(journal_id, offering, listed, cells, set(dates))
        else:
            current.listed = current.listed or listed
            current.cells += cells
            current.dates |= set(dates)

    def home(self, key):
        bucket = self._candidates.get(key)
        if not bucket:
            return None
        return max(bucket.values(), key=Candidate.rank).offering

    def is_twin(self, key, offering) -> bool:
        """Bu açılış ev açılışının ailəsindən DEYİL (paralel qrupun «əkiz» jurnalı)."""

        home = self.home(key)
        return home is not None and offering is not None and not offerings_related(self.catalog, home, offering)

    def keys(self):
        return self._candidates.keys()


def build_home_index(run, slices: dict, cells: dict | None = None) -> HomeIndex:
    """Aktiv jurnalların namizədlərini yığ. ``slices`` — ``uniqid → JournalSlices``."""

    if cells is None:
        from .lessons import winning_cells

        cells = cell_counts(winning_cells(run.bundle["points"]))
    by_journal: dict = {}
    for (uniqid, legacy_id), value in cells.items():
        by_journal.setdefault(uniqid, {})[legacy_id] = value
    index = HomeIndex(run.catalog)
    for uniqid, entry in slices.items():
        if not entry.offerings or not journal_is_active(entry.journal):
            continue
        listed = list(dict.fromkeys(parse_id_list(entry.journal["students_id"])))
        own = by_journal.get(uniqid, {})
        for legacy_id in list(dict.fromkeys(listed + sorted(own))):
            user_id, _outcome = run.students.resolve(legacy_id, create=False)
            if user_id is None:
                continue
            offering = entry.pick(run.students.group_of.get(user_id), run.catalog, legacy_unit_id(run, legacy_id))
            if offering is None:
                continue
            count, dates = own.get(legacy_id, (0, set()))
            key = (user_id, offering.subject_id, offering.period_id)
            index.observe(key, entry.journal["id"], offering, listed=legacy_id in listed, cells=count, dates=dates)
    return index


def legacy_unit_id(run, legacy_id):
    """Tələbənin legacy qrupunun hədəf vahidi (yalnız tapılırsa; yaradılmır)."""

    row = run.students.students.get(legacy_id) if hasattr(run.students, "students") else None
    legacy_group = run.legacy_groups.get((row or {}).get("group_id")) if row else None
    if not legacy_group:
        return None
    unit, _how = run.catalog.group_for(legacy_group)
    return unit.pk if unit is not None else None


__all__ = [
    "Candidate",
    "HomeIndex",
    "build_home_index",
    "cell_counts",
    "journal_is_active",
    "legacy_unit_id",
    "offerings_related",
    "units_related",
]
