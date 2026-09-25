"""HAZIRDA OXUYAN tələbələr üçün ATILMIŞ jurnal yazılışlarının seçimi (2026-09-25).

Sahibin göstərişi: «ballar çox vacibdir, yenidən görünməlidir — əsas diqqət indi
oxuyanlaradır».  Bu modul iki kateqoriyanı deterministik qaydalarla seçir, heç
nə yazmır (plan qatı ``repair_enrollments_replay`` onu klonda icra edir).

«Hazırda oxuyan» — dəqiq tərif (mənbə + hədəf sübutu)
----------------------------------------------------
Mənbədə ``students.azadedildi = 0`` VƏ aşağıdakılardan biri:

* **E1** — hədəfdə 2026/2027 açılışına yazılışı var (tədris tapşırığı idxalı);
* **E2** — mənbə qrupunun kohortu 2026/2027-də hələ oxuyur (bakalavr
  ``start_year`` 2023…2026, magistr 2025…2026) VƏ 2025/2026-da jurnalda var;
* **E3** — qrupun ``start_year``-i bilinmir (``0000``) VƏ 2025/2026 Yaz
  jurnalında var (son tam semestrdə dərs alıb — uzadılmış təhsil ola bilər).

«Jurnalda var» = jurnalın ``students_id`` siyahısında və ya bal cədvəlində xanası var.

Kateqoriyalar
-------------
* **K9** — çoxqruplu jurnalda tələbənin qrupu dilimlərə uyğun gəlmədiyi üçün
  J2 yazılışı atıb (``legacy_journal_student_group_mismatch``).
* **fake** — jurnal ``fake=1`` (J-V6 atıb), amma tələbənin həmin fənn+semestr
  üzrə NƏTİCƏSİNİ YALNIZ bu jurnal daşıyır: imtahan xanası (``im``/``im2``
  rəqəm) və ya ``yekun`` sətri.  ⚠️ ``yekun`` cədvəli mənbədə yalnız 2022/2023
  Payız üçün doludur — qalan semestrlərdə köhnə nəticənin daşıyıcısı jurnalın
  imtahan xanasıdır.
* **deleted** — real jurnal (``fake=0``, ``sonra_sil=0``), amma ONUN BÜTÜN qrupları
  mənbənin ``groups`` cədvəlində yoxdur (J1: ``legacy_journal_group_unresolved``,
  heç bir dilim qurulmayıb).  Qrup yalnız SÜBUTLA seçilir: tələbənin HƏMİN dövrdəki
  köçmüş yazılışlarının hamısı TƏK qrupdadırsa, jurnal o qrupun dilimi kimi
  qurulur (J1, C6 birləşməsi ilə); sübut yoxdursa və ya bir neçə qrupdursa cüt
  bərpa olunmur (hesabata düşür).  Xanası olmayan cüt bərpa olunmur.

Dilim qaydası (hər iki kateqoriya)
----------------------------------
1. tələbənin CARİ qrupu (SAR) dilimlərdən biridirsə — o dilim (J2 qaydası);
2. yoxdursa: tələbənin HƏMİN dövrdəki digər yazılışlarının qrupu dilimlərdən
   birinə düşürsə — o dilim (çoxdursa jurnal sırasında birincisi);
3. yoxdursa: jurnalın ilk dilimi (``primary_offering`` ilə eyni qayda).
Cari qrupdan fərqli dilimə yazılış **qonaq** (``source_group`` = tələbənin öz
qrupu) kimi yaradılır — ``guest_roster`` ilə eyni təmsil, jurnalda «alt qrup» çipi.

Təhlükəsizlik: həmin fənn+semestr üzrə tələbənin hədəfdə ARTIQ yazılışı varsa
(«əkiz») cüt BƏRPA OLUNMUR — fənn transkriptdə/ÜOMG-də iki dəfə sayılmasın; cüt
hesabata düşür.  Heç bir xanası olmayan K9 siyahı cütü də bərpa olunmur (boş
fənn sətri yaradardı, bərpa ediləsi bal yoxdur).
"""

from __future__ import annotations

import datetime
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from django.apps import apps as django_apps

from apps.legacy_import.models import LegacyEntityMap, LegacyMigrationIssue

from .field_contracts import GROUP_STRUCTURE_FIELDS, STUDENT_IDENTITY_FIELDS, STUDENT_STATUS_FIELDS
from .rehearsal_journal_offerings_source import journal_rows, legacy_int, parse_group_ids, validated_uniqid
from .rehearsal_journal_points_source import (
    ARCHIVE_CUTOFF,
    added_on,
    archive_rows,
    attested_rows,
    legacy_text,
    point_rows,
    yekun_rows,
)
from .source_extraction import open_audited_identity_stream

LAST_LEGACY_YEAR = "2025/2026"
LAST_LEGACY_SPRING = "2025/2026 Yaz"
CURRENT_YEAR_START = datetime.date(2026, 9, 1)
BACHELOR_CURRENT = range(2023, 2027)
MASTER_CURRENT = range(2025, 2027)
EXAM_MONTHS = frozenset({"im", "im2"})
K9_RULE = "legacy_journal_student_group_mismatch"
_MIGRATED = LegacyEntityMap.State.MIGRATED


@dataclass(frozen=True)
class RestorePair:
    """Bərpa olunacaq bir (jurnal, tələbə) cütü — qərar bitib."""

    category: str  # k9 | fake
    uniqid: str
    legacy_student: int
    user_id: int
    group_ref: str
    group_unit: str
    offering_pk: str  # K9: mövcud dilim; fake: "" (J1 qurur/birləşdirir)
    guest_unit: str  # "" = öz qrupu; əks halda tələbənin cari qrupu (source_group)
    slice_rule: str
    period_pk: str
    subject_pk: str

    @property
    def ledger_key(self) -> str:
        return f"{self.uniqid}:{self.legacy_student}"


@dataclass
class Selection:
    current: dict = field(default_factory=dict)  # legacy id → (user_id, sübut kodu)
    pairs: list = field(default_factory=list)
    skipped: Counter = field(default_factory=Counter)
    skipped_rows: list = field(default_factory=list)  # (kateqoriya, legacy tələbə, uniqid, səbəb)


def _year(value) -> int:
    if type(value) is int:
        return value
    text = str(value or "").strip()
    return int(text) if text.isdigit() else 0


def _maps(organization, run, entity_type, *, states=(_MIGRATED,)):
    rows = LegacyEntityMap.objects.filter(
        organization=organization, created_run=run, entity_type=entity_type, state__in=states
    ).values_list("legacy_pk", "target_pk", "state")
    return {str(legacy_pk): (str(target_pk), str(state)) for legacy_pk, target_pk, state in rows.iterator(10_000)}


def _source_journals(context):
    journals = {}
    for legacy_pk, row in journal_rows(context):
        groups = parse_group_ids(row["groups_id"]) or ()
        roster = parse_group_ids(row["students_id"]) or ()
        journals[validated_uniqid(row["uniqid"])] = {
            "id": legacy_pk,
            "lesson": legacy_int(row["lesson_id"]),
            "semestr": legacy_int(row["semestr"]),
            "groups": tuple(str(member) for member in groups),
            "roster": frozenset(int(member) for member in roster),
            "fake": legacy_int(row["fake"]) == 1,
            "deleted_later": legacy_int(row["sonra_sil"]) == 1,
        }
    return journals


def _source_cells(context):
    """``(uniqid, tələbə)`` → (xana varmı, imtahan xanası varmı) — əsas + kəsimdən əvvəlki arxiv."""

    cells: dict[tuple[str, int], list] = {}
    for from_archive, stream in ((False, point_rows(context)), (True, archive_rows(context))):
        for _legacy_pk, row in stream:
            if from_archive:
                stamped = added_on(row)
                if stamped is None or stamped >= ARCHIVE_CUTOFF:
                    continue
            point = legacy_text(row["point"])
            if not point:
                continue
            student = row["student_id"]
            if type(student) is not int:
                continue
            key = (validated_uniqid(row["journal_uniqid"]), student)
            flags = cells.setdefault(key, [True, False])
            if legacy_text(row["month_id"]) in EXAM_MONTHS and point.isdigit():
                flags[1] = True
    return cells


def _source_students(context):
    status = {
        pk: legacy_int(row["azadedildi"])
        for pk, row in attested_rows(
            context, contract=STUDENT_STATUS_FIELDS, source_table=STUDENT_STATUS_FIELDS.source_table
        )
    }
    groups = {
        pk: (_year(row["start_year"]), str(row["bak_or_mag"] or "").strip())
        for pk, row in attested_rows(
            context, contract=GROUP_STRUCTURE_FIELDS, source_table=GROUP_STRUCTURE_FIELDS.source_table
        )
    }
    cohort = {}
    with open_audited_identity_stream(
        connection_factory=context.source_connection_factory, contract=STUDENT_IDENTITY_FIELDS
    ) as stream:
        for row in stream:
            group_id = row["group_id"] if type(row["group_id"]) is int else 0
            cohort[int(row["id"])] = groups.get(group_id, (0, ""))
    return status, cohort


def _target_state(organization):
    enrollment_model = django_apps.get_model("registrar", "Enrollment")
    by_user: dict[int, set] = defaultdict(set)
    period_groups: dict[tuple[int, str], set] = defaultdict(set)
    enrolled_offering: set[tuple[int, str]] = set()
    placed: set[int] = set()
    rows = enrollment_model.objects.filter(organization=organization).values_list(
        "student_id",
        "offering_id",
        "offering__subject_id",
        "offering__period_id",
        "offering__group_id",
        "offering__period__start_date",
    )
    for user_id, offering_id, subject_id, period_id, group_id, start in rows.iterator(10_000):
        by_user[user_id].add((str(subject_id), str(period_id)))
        enrolled_offering.add((user_id, str(offering_id)))
        if group_id is not None:
            period_groups[(user_id, str(period_id))].add(str(group_id))
        if start is not None and start >= CURRENT_YEAR_START:
            placed.add(user_id)
    record_model = django_apps.get_model("registrar", "StudentAcademicRecord")
    sar = {
        user_id: "" if group_id is None else str(group_id)
        for user_id, group_id in record_model.objects.filter(organization=organization).values_list(
            "student_id", "group_id"
        )
    }
    periods = {
        str(pk): f"{year} {name}"
        for pk, year, name in django_apps.get_model("organizations", "AcademicPeriod")
        .objects.filter(organization=organization)
        .values_list("pk", "academic_year", "name")
    }
    return by_user, period_groups, enrolled_offering, placed, sar, periods


def _current_students(*, students, status, cohort, activity, placed):
    current = {}
    for legacy_id, (user_id, _state) in students.items():
        legacy = int(legacy_id)
        if status.get(legacy, 1) != 0:
            continue
        start_year, level = cohort.get(legacy, (0, ""))
        years = activity.get(legacy, set())
        in_last_year = any(label.startswith(LAST_LEGACY_YEAR) for label in years)
        evidence = ""
        if int(user_id) in placed:
            evidence = "E1_placed_2026_27"
        elif level == "bak" and start_year in BACHELOR_CURRENT and in_last_year:
            evidence = "E2_cohort_bak"
        elif level == "mag" and start_year in MASTER_CURRENT and in_last_year:
            evidence = "E2_cohort_mag"
        elif start_year == 0 and LAST_LEGACY_SPRING in years:
            evidence = "E3_unknown_cohort_active_spring"
        if evidence:
            current[legacy] = (int(user_id), evidence)
    return current


def _choose_slice(slices, *, sar_unit, same_period_units):
    """``(group_ref, unit, qayda)`` — modul qeydindəki üç pilləli qayda."""

    for group_ref, unit in slices:
        if unit and unit == sar_unit:
            return group_ref, unit, "own_group"
    evidence = [(group_ref, unit) for group_ref, unit in slices if unit in same_period_units]
    if evidence:
        return (*evidence[0], "same_period_group" if len(evidence) == 1 else "same_period_group_first")
    group_ref, unit = slices[0]
    return group_ref, unit, "primary_slice"


def _evidence_slice(evidence, unit_refs):
    """Qrupu silinmiş jurnal üçün dilim: tələbənin HƏMİN dövrdəki yazılışlarının TƏK qrupu.

    ``(dilimlər, səbəb)`` — səbəb boşdursa bir dilim var; sübutsuz / çoxqruplu hal
    TƏXMİN EDİLMİR.
    """

    if not evidence:
        return [], "no_group_evidence"
    if len(evidence) > 1:
        return [], "ambiguous_group"
    unit = next(iter(evidence))
    if unit not in unit_refs:
        return [], "no_slice"
    return [(unit_refs[unit], unit, "")], ""


def select_pairs(context, *, source_run) -> Selection:
    """Hazırda oxuyanlar üçün K9 və «yeganə nəticə daşıyıcısı» fake cütlərini seç."""

    organization = context.organization
    journals = _source_journals(context)
    cells = _source_cells(context)
    status, cohort = _source_students(context)
    yekun = {(legacy_int(row["journal_id"]), legacy_int(row["student_id"])) for _pk, row in yekun_rows(context)}
    students = _maps(organization, source_run, "student")
    subjects = _maps(organization, source_run, "lesson_subject")
    period_map = _maps(organization, source_run, "academic_period")
    units = _maps(organization, source_run, "group_unit")
    offerings = _maps(organization, source_run, "course_offering")
    by_user, period_groups, enrolled_offering, placed, sar, period_labels = _target_state(organization)

    cell_students: dict[str, set] = defaultdict(set)
    for uniqid, student in cells:
        cell_students[uniqid].add(student)
    activity: dict[int, set] = defaultdict(set)
    for uniqid, info in journals.items():
        label = period_labels.get(period_map.get(str(info["semestr"]), ("", ""))[0], "")
        for student in set(info["roster"]) | cell_students.get(uniqid, set()):
            activity[student].add(label)
    selection = Selection(
        current=_current_students(students=students, status=status, cohort=cohort, activity=activity, placed=placed)
    )

    k9_keys = {
        str(legacy_pk)
        for legacy_pk in LegacyMigrationIssue.objects.filter(
            organization=organization, run=source_run, entity_type="journal_enrollment", rule_code=K9_RULE
        ).values_list("legacy_pk", flat=True)
    }
    candidates = []
    for key in sorted(k9_keys):
        uniqid, _sep, student = key.rpartition(":")
        if not (student.isdigit() and int(student) in selection.current and uniqid in journals):
            continue
        if (uniqid, int(student)) not in cells:
            # Siyahıda var, amma HEÇ BİR xanası yoxdur → bərpa boş fənn sətri olardı.
            selection.skipped["k9:no_cells"] += 1
            selection.skipped_rows.append(("k9", int(student), uniqid, "no_cells"))
            continue
        candidates.append(("k9", uniqid, int(student)))
    for uniqid, info in sorted(journals.items()):
        if not info["fake"]:
            continue
        for student in sorted(set(info["roster"]) | cell_students.get(uniqid, set())):
            if student not in selection.current:
                continue
            carries = cells.get((uniqid, student), [False, False])[1] or (info["id"], student) in yekun
            if carries:
                candidates.append(("fake", uniqid, student))
            else:
                selection.skipped["fake:no_legacy_result"] += 1
                selection.skipped_rows.append(("fake", student, uniqid, "no_legacy_result"))

    for uniqid, info in sorted(journals.items()):
        # «deleted»: real jurnal, heç bir qrupu həll olunmur → J1 bir dilim də qurmayıb.
        if info["fake"] or info["deleted_later"] or not info["groups"]:
            continue
        if any(group_ref in units or f"{uniqid}:{group_ref}" in offerings for group_ref in info["groups"]):
            continue
        for student in sorted(set(info["roster"]) | cell_students.get(uniqid, set())):
            if student not in selection.current:
                continue
            if (uniqid, student) not in cells:
                selection.skipped["deleted:no_cells"] += 1
                selection.skipped_rows.append(("deleted", student, uniqid, "no_cells"))
                continue
            candidates.append(("deleted", uniqid, student))

    unit_refs = {unit: group_ref for group_ref, (unit, _state) in units.items()}
    for category, uniqid, student in candidates:
        user_id, _evidence = selection.current[student]
        info = journals[uniqid]
        subject_pk = subjects.get(str(info["lesson"]), ("", ""))[0]
        period_pk = period_map.get(str(info["semestr"]), ("", ""))[0]
        reason = ""
        if not subject_pk or not period_pk:
            reason = "reference_unresolved"
        elif (subject_pk, period_pk) in by_user.get(user_id, set()):
            reason = "twin_enrollment"
        if category == "k9":
            slices = [
                (group_ref, units.get(group_ref, ("", ""))[0], offerings.get(f"{uniqid}:{group_ref}", ("", ""))[0])
                for group_ref in info["groups"]
                if f"{uniqid}:{group_ref}" in offerings
            ]
        elif category == "deleted":
            slices, why = _evidence_slice(period_groups.get((user_id, period_pk), set()), unit_refs)
            reason = reason or why
        else:
            slices = [(group_ref, units[group_ref][0], "") for group_ref in info["groups"] if group_ref in units]
        if not reason and not slices:
            reason = "no_slice"
        if reason:
            selection.skipped[f"{category}:{reason}"] += 1
            selection.skipped_rows.append((category, student, uniqid, reason))
            continue
        group_ref, unit, rule = _choose_slice(
            [(ref, slice_unit) for ref, slice_unit, _pk in slices],
            sar_unit=sar.get(user_id, ""),
            same_period_units=period_groups.get((user_id, period_pk), set()),
        )
        offering_pk = next(pk for ref, _unit, pk in slices if ref == group_ref)
        if offering_pk and (user_id, offering_pk) in enrolled_offering:
            selection.skipped[f"{category}:already_enrolled"] += 1
            selection.skipped_rows.append((category, student, uniqid, "already_enrolled"))
            continue
        own = sar.get(user_id, "")
        selection.pairs.append(
            RestorePair(
                category=category,
                uniqid=uniqid,
                legacy_student=student,
                user_id=user_id,
                group_ref=group_ref,
                group_unit=unit,
                offering_pk=offering_pk,
                guest_unit=own if own and own != unit else "",
                slice_rule=rule,
                period_pk=period_pk,
                subject_pk=subject_pk,
            )
        )
    return selection


__all__ = [
    "BACHELOR_CURRENT",
    "CURRENT_YEAR_START",
    "LAST_LEGACY_SPRING",
    "LAST_LEGACY_YEAR",
    "MASTER_CURRENT",
    "RestorePair",
    "Selection",
    "select_pairs",
]
