"""``journal-shares/1`` planı — köhnə sistemin müəllim jurnallarından bölünmüş jurnal payları + səviyyə artığı çıxarışları
(``apply_journal_shares`` faylı; sahib 2026-10-26/27). Əvvəl sessiya skripti idi (``shares/build2.py`` + ``drops.py``),
indi :class:`SharePlan` + ``build_journal_share_plans`` əmri.

PAYLAR (``build2`` ilə eyni qayda):

* hər həll olunmuş jurnal × onun tələbələrinin oturduğu açılış → (açılış, müəllim) payı: həmin tələbələrin
  qeydiyyatları + dərs növləri. Növ legacy dərsin TARİXİ üzrə: həmin açılışda eyni tarix + saatdakı yeni sistem dərsinin
  növü; dərs yoxdursa ``journals_dates_rooms.sem_muh``; heç biri yoxdursa ay cədvəlinin növləri (son ehtiyat);
* açılışda yalnız sahibin öz jurnalı varsa pay YAZILMIR (sahib payı olmadan hamısını görür — düzgündür);
* SAHİB köhnə sistemdə həmin açılışda heç kimə dərs deməyibsə, amma başqa müəllimlərin payı varsa (səviyyə
  jurnalında sahib başqasının tələbələrini görürdü): sahibə yalnız heç bir köhnə jurnala düşməyən tələbələrdən ibarət
  pay (``owner_unlisted``); belə tələbə yoxdursa — pay yazıla bilmir (boş siyahı = hamısı), sayılır
  (``owner_not_legacy_full``) — açılışı birləşmə (``merge_level_journals``) və ya kafedra həll edir;
* ``deactivate`` cütləri (açılış:müəllim) → ``"active": false`` sətri (RİM MR-000017 naxışı).

ÇIXARIŞLAR (``drops.py`` + 2026-10-27 «(pre-intermadiate)» düzəlişi, :mod:`apps.registrar.language_levels`):
səviyyə fənninin cari ``enrolled`` qeydiyyatı heç bir köhnə jurnala düşmürsə, AMMA tələbənin eyni ailənin (məs.
«…-1») BAŞQA səviyyəsində köhnə jurnala düşən qeydiyyatı varsa — «yanlış səviyyə». Datası olmayanlar
(``absence_hours=0`` + «Jurnal təmizliyi» sübutu yox) ``drop_enrollments``-ə; datası olanlar yalnız sayılır.
Heç bir səviyyə siyahısında olmayan tələbələrə (``unlisted``) toxunulmur — kafedra qərarıdır.
"""

from __future__ import annotations

from collections import Counter, defaultdict

from django.apps import apps as django_apps

from .level_journal_index import parse_time

FORMAT = "journal-shares/1"


def _levels():
    from apps.registrar.public import language_levels

    return language_levels


def level_classes(index) -> dict:
    """Səviyyə fənlərinin ``enrolled`` qeydiyyatları → ``"covered" | "wrong_level" | "unlisted"``.

    ``wrong_level`` — tələbə bu səviyyənin köhnə jurnalında yoxdur, eyni ailənin başqa səviyyəsində isə (yeni sistemdə
    həmin səviyyənin köhnə jurnala düşən qeydiyyatı ilə) var."""
    levels = _levels()
    covered = index.covered_enrollments()
    family_covered = defaultdict(set)
    for pk in covered:
        row = index.enrolled.get(pk)
        if row and levels.level_of(row["offering__subject__name"]):
            family_covered[(row["student_id"], levels.level_family(row["offering__subject__name"]))].add(pk)
    out = {}
    for pk, row in index.enrolled.items():
        name = row["offering__subject__name"]
        if not levels.level_of(name):
            continue
        if pk in covered:
            out[pk] = "covered"
        elif family_covered.get((row["student_id"], levels.level_family(name))):
            out[pk] = "wrong_level"
        else:
            out[pk] = "unlisted"
    return out


def data_free(enrollment_ids) -> set:
    """Datası olmayan qeydiyyatlar (``apply_drops``-un özü ilə eyni süzgəc)."""
    from apps.registrar.public import journal_hygiene

    Enrollment = django_apps.get_model("registrar", "Enrollment")
    ids = list(enrollment_ids)
    found = set()
    for start in range(0, len(ids), 2000):
        found |= set(
            Enrollment.objects.filter(pk__in=ids[start : start + 2000], absence_hours=0)
            .filter(*journal_hygiene.no_evidence_filters())
            .values_list("pk", flat=True)
        )
    return found


class SharePlan:
    def __init__(self, index, *, deactivate=()):
        self.index = index
        self.deactivate = {(str(offering), int(teacher)) for offering, teacher in deactivate}
        self.counts: Counter = Counter()

    def build(self) -> dict:
        shares = self._collect()
        classes = level_classes(self.index)
        drops = self._drops(classes)
        dropped = set(drops)
        rows = self._rows(shares, {pk for pk in self.index.enrolled if str(pk) in dropped})
        for offering, teacher in sorted(self.deactivate):
            rows.append({"offering": offering, "teacher": teacher, "active": False})
        self.counts["share_rows"] = len(rows)
        self.counts["drop_enrollments"] = len(drops)
        return {"format": FORMAT, "period": str(self.index.period.pk), "shares": rows, "drop_enrollments": drops}

    # ── paylar ───────────────────────────────────────────────────────────
    def _collect(self) -> dict:
        lesson_kind = self.index.lesson_kinds()
        shares = defaultdict(lambda: defaultdict(lambda: {"kinds": set(), "enrollments": set(), "old": set()}))
        for entry in self.index.resolved_journals():
            for offering_id, enrollment_ids in entry.hits.items():
                share = shares[offering_id][entry.teacher_id]
                share["enrollments"] |= enrollment_ids
                for (day, hhmm), room_kind in entry.slots.items():
                    kind = lesson_kind.get((offering_id, day, parse_time(hhmm)))
                    if kind:
                        self.counts["kind_from_lesson"] += 1
                    elif room_kind:
                        kind = room_kind
                        self.counts["kind_from_room_row"] += 1
                    else:
                        self.counts["kind_unknown_date"] += 1
                        share["old"] |= entry.month_kinds
                        continue
                    share["kinds"].add(kind)
        return shares

    def _rows(self, shares: dict, dropped: set) -> list:
        rows = []
        covered = self.index.covered_enrollments()
        enrolled_by_offering = defaultdict(set)
        for pk, row in self.index.enrolled.items():
            if pk not in dropped:
                enrolled_by_offering[row["offering_id"]].add(pk)
        for offering_id in sorted(shares, key=str):
            per = shares[offering_id]
            offering = self.index.offerings.get(offering_id) or {}
            owner = offering.get("instructor_id")
            if set(per) == {owner}:
                self.counts["single_owner_only"] += 1
                continue
            for teacher_id in sorted(per):
                if (str(offering_id), teacher_id) in self.deactivate:
                    continue
                share = per[teacher_id]
                rows.append(
                    {
                        "offering": str(offering_id),
                        "teacher": teacher_id,
                        "kinds": sorted(share["kinds"] or share["old"]),
                        "enrollments": sorted(str(pk) for pk in share["enrollments"]),
                        "is_owner": teacher_id == owner,
                    }
                )
            if owner and owner not in per and (str(offering_id), owner) not in self.deactivate:
                rows.extend(self._owner_unlisted(offering_id, owner, enrolled_by_offering[offering_id] - covered))
        return rows

    def _owner_unlisted(self, offering_id, owner, unlisted: set) -> list:
        if not unlisted:
            self.counts["owner_not_legacy_full"] += 1
            return []
        self.counts["owner_unlisted"] += 1
        return [
            {
                "offering": str(offering_id),
                "teacher": owner,
                "kinds": [],
                "enrollments": sorted(str(pk) for pk in unlisted),
                "is_owner": True,
            }
        ]

    # ── çıxarışlar ───────────────────────────────────────────────────────
    def _drops(self, classes: dict) -> list:
        wrong = sorted((pk for pk, verdict in classes.items() if verdict == "wrong_level"), key=str)
        free = data_free(wrong)
        self.counts["level_enrollments"] = len(classes)
        self.counts["level_covered"] = sum(1 for verdict in classes.values() if verdict == "covered")
        self.counts["level_unlisted"] = sum(1 for verdict in classes.values() if verdict == "unlisted")
        self.counts["wrong_level"] = len(wrong)
        self.counts["wrong_level_with_data"] = len(wrong) - len(free)
        return [str(pk) for pk in wrong if pk in free]


__all__ = ["FORMAT", "SharePlan", "data_free", "level_classes"]
