"""Dərs yükündə ARTIQ SAYILAN saatların aşkarlanması — YALNIZ OXU (sahib 2026-10-25).

Sahib («Yük bölgüsü», Proqramlaşdırma və informasiya təhlükəsizliyi kafedrası): «lazımından artıq çıxmasın
ortaya. Patok dərsi olanda 30 saat 2-yə vurulmur, mühazirə tək formada hesablanır». Müəllimin yükü
``Σ TeacherAssignment.hours``-dur (``queries.teacher_load_panel``) — hesab düzgündür, ARTIQ saat datadadır:

(a) ``duplicate`` — eyni fənn + eyni semestr + kəsişən qrup + eyni fəaliyyət bir neçə sətirdə (eyni və ya
    fərqli kafedrada). Mənbə: köhnə sistem deltasının yük fazası / «Dərs yükü faylı» fənni başqa adla
    («… (Digital Forensics …)», «… (Malware analysis)») yazılmış sətri tanımayıb YENİ sətir açıb.
(b) ``joint`` — birgə dərs (patok) hər qrup sətrində ayrıca saat ilə: eyni müəllim + fənn + NÖV, ayrı qrup
    sətirləri, SÜBUT — dərs cədvəlində eyni gün/saat/həftə + eyni növ slotu (``registrar.schedule.is_joint_lecture``
    qaydası) və ya — ƏSAS mənbə — jurnalda eyni tarix + başlama saatında eyni növ dərs (çoxluq qaydası: kiçik
    tərəfin tarixlərinin ≥ 75 %-i ortaq → birgə; qismən → «qeyri-müəyyən»; cədvəl yalnız jurnal datası azdırsa).
    Mühazirə axını əsas haldır; sahib 2026-10-25 əlavə: seminar/lab da birgə keçirilə bilər — onda o növ də
    BİR dəfə sayılır («60 saatlıq fənn — bir qrup kimi 60 saat»). Sübut yoxdursa seminar/lab qrup üzrə qalır.
    Birləşmə yalnız EYNİ növ + EYNİ müəllim bölgüləri arasındadır (sahib: «mühazirə bir müəllimdə, seminar
    digərində» — fərqli müəllimlərin eyni növ saatı iki ayrı yükdür); sübut da müəllim + növ üzrə yoxlanır
    (dərsin öz müəllimi, boşdursa açılışın müəllimi).
(c) ``plan_overrun`` — sətrin cəmi planı (``*_plan × çarpan``) və ya fənnin kurikulum saatını aşır (yalnız hesabat).
(d) ``source`` — (a)-nın intensiv / «Dərs yükü faylı» (legacy delta) sətirləri ilə mövcud sətrin üst-üstə düşməsi.

Model AXINI TANIYIR: çox qruplu sətir = bir axın (``union_count`` mühazirə çarpanı, ``subgroup_count`` seminar/lab
çarpanı; ``offering_rules.per_group_hours``). Problem eyni axının qrup başına AYRI sətirlərdə yazılmasıdır.
"""

from __future__ import annotations

import difflib
import re
from collections import defaultdict
from dataclasses import dataclass, field

from django.apps import apps as django_apps
from django.db.models import Q

from ..constants import RowKind, Season, TaskStatus
from ..models import TeacherAssignment, TeachingTaskRow
from .task_form1_import import SUBJECT_THRESHOLD, subject_key

TEACHING_ACTIVITIES = ("lecture", "seminar", "lab")
TOTAL_FIELD = {"lecture": "lecture_total", "seminar": "seminar_total", "lab": "lab_total"}
PLAN_FIELD = {"lecture": "lecture_plan", "seminar": "seminar_plan", "lab": "lab_plan"}
MULTIPLIER_FIELD = {"lecture": "union_count", "seminar": "subgroup_count", "lab": "subgroup_count"}

#: «Dərs yükü faylı» (``load_upload`` — həm Tədris şöbəsinin yüklədiyi fayl, həm köhnə sistem deltasının
#: yük fazası) sətrə bu qeydi yazır.
LOAD_FILE_NOTE = "Dərs yükü faylından əlavə olundu"
TIMETABLE_NOTE = "saat bölgüsü cədvəldən"

#: Jurnal sübutu: ən az bu qədər ortaq tarix və kiçik tərəfin ən az bu payı.
JOINT_MIN_DATES = 2
_LEVEL_RE = re.compile(r"elementar|interm|beginn|advanc|upper")
JOINT_MIN_SHARE = 0.75


def row_source(row) -> str:
    if row.row_kind == RowKind.INTENSIVE:
        return "intensive"
    note = row.note or ""
    if note.startswith(LOAD_FILE_NOTE):
        return "load_file"
    if note.startswith(TIMETABLE_NOTE):
        return "timetable"
    return "task"


@dataclass
class RowInfo:
    row: object
    chair_id: str
    chair_name: str
    task_status: str
    subject: str
    key: str
    groups: frozenset
    group_names: dict
    source: str
    hours: dict  # activity → sətir cəmi
    assignments: list  # (teacher_id | None, activity, hours, is_hourly_paid, assignment_id)
    has_objection: bool = False  # müəllim etirazı (append-only) — sətir avtomatik silinmir/dəyişmir

    @property
    def pk(self):
        return self.row.pk

    def teachers(self, activity: str) -> set:
        return {a[0] for a in self.assignments if a[1] == activity}

    def single_teacher(self, activity: str):
        """Fəaliyyətin YEGANƏ (vakant olmayan) müəllimi — bütün saatı tam onundursa."""
        items = [a for a in self.assignments if a[1] == activity]
        if len(items) != 1 or items[0][0] is None or items[0][2] != self.hours.get(activity, 0):
            return None
        return items[0][0]

    def signature(self) -> tuple:
        return tuple(sorted((str(a[0] or ""), a[1], a[2]) for a in self.assignments if a[1] in TEACHING_ACTIVITIES))

    def has_named(self) -> bool:
        return any(a[0] is not None for a in self.assignments if a[1] in TEACHING_ACTIVITIES)

    def per_group(self, activity: str) -> int:
        plan = int(getattr(self.row, PLAN_FIELD[activity]) or 0)
        if plan:
            return plan
        multiplier = max(int(getattr(self.row, MULTIPLIER_FIELD[activity]) or 1), 1)
        return int(self.hours.get(activity, 0)) // multiplier


@dataclass
class Detection:
    year: str
    rows: list = field(default_factory=list)
    by_pk: dict = field(default_factory=dict)
    duplicates: list = field(default_factory=list)  # [{"rows": [RowInfo], "exact": bool, ...}]
    joint: list = field(default_factory=list)  # [{"activity", "rows": [RowInfo], "anchor", "others", ...}]
    joint_unproven: list = field(default_factory=list)  # «uncertain»: jurnalda qismən birgə (< 75 %)
    journal_stats: list = field(default_factory=list)
    plan_overrun: list = field(default_factory=list)
    skipped_no_groups: int = 0


def load_rows(organization, year: str) -> list[RowInfo]:
    rows = (
        TeachingTaskRow.objects.filter(organization=organization, task__academic_year=year)
        .exclude(task__status=TaskStatus.CANCELLED)
        .select_related("task__chair", "subject")
        .prefetch_related("groups")
        .order_by("created_at", "pk")
    )
    assignments = defaultdict(list)
    for item in TeacherAssignment.objects.filter(row__in=rows).values_list(
        "row_id", "teacher_id", "activity", "hours", "is_hourly_paid", "pk"
    ):
        assignments[item[0]].append((item[1], item[2], int(item[3] or 0), bool(item[4]), item[5]))
    LoadObjection = django_apps.get_model("workload", "LoadObjection")
    objected = set(LoadObjection.objects.filter(row__in=rows).values_list("row_id", flat=True))
    aliases = split_group_aliases(organization, {group for row in rows for group in row.groups.all()})
    result = []
    for row in rows:
        name = row.subject.name if row.subject_id else row.subject_text
        groups = list(row.groups.all())
        expanded = set()
        for group in groups:
            expanded |= aliases.get(group.pk, {group.pk})
        result.append(
            RowInfo(
                row=row,
                chair_id=str(row.task.chair_id),
                chair_name=row.task.chair.name,
                task_status=row.task.status,
                subject=name or "—",
                key=subject_key(name),
                groups=frozenset(expanded),
                group_names={group.pk: group.name for group in groups},
                source=row_source(row),
                hours={activity: int(getattr(row, TOTAL_FIELD[activity]) or 0) for activity in TEACHING_ACTIVITIES},
                assignments=assignments.get(row.pk, []),
                has_objection=row.pk in objected,
            )
        )
    return result


def split_group_aliases(organization, groups) -> dict:
    """Boş «köhnə» qrup → onun bölündüyü qruplar: «234 K az» (0 tələbə) ≡ «234 K-1» + «234 K-2» (eyni ixtisas).

    Tapşırıq kitabçası qrupu bölünmədən əvvəlki adla yazır, köhnə sistemin jurnalları isə bölünmüş qruplardadır —
    eyni tələbələr üçün iki sətir dublikat sayılmalıdır. Yalnız tələbəsi OLMAYAN qrup açılır.
    """
    from .task_form1_parsing import group_key

    OrgUnit = django_apps.get_model("organizations", "OrgUnit")
    Record = django_apps.get_model("registrar", "StudentAcademicRecord")
    group_ids = {group.pk for group in groups}
    populated = set(Record.objects.filter(group_id__in=group_ids).values_list("group_id", flat=True).distinct())
    empty = [group for group in groups if group.pk not in populated and group.parent_id]
    if not empty:
        return {}
    siblings = defaultdict(list)
    for unit in OrgUnit.objects.filter(
        organization=organization, parent_id__in={group.parent_id for group in empty}, unit_type="group"
    ).values("pk", "name", "parent_id"):
        siblings[unit["parent_id"]].append(unit)
    sibling_ids = {unit["pk"] for units in siblings.values() for unit in units}
    filled = set(Record.objects.filter(group_id__in=sibling_ids).values_list("group_id", flat=True).distinct())
    result = {}
    for group in empty:
        base = group_key(group.name)
        parts = {
            unit["pk"]
            for unit in siblings[group.parent_id]
            if unit["pk"] in filled and re.fullmatch(re.escape(base) + r"\d{1,2}", group_key(unit["name"]))
        }
        if len(parts) >= 2:
            result[group.pk] = parts
    return result


def _components(nodes, edges) -> list[list]:
    parent = {node: node for node in nodes}

    def find(node):
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    for left, right in edges:
        parent[find(left)] = find(right)
    groups = defaultdict(list)
    for node in nodes:
        groups[find(node)].append(node)
    return [members for members in groups.values() if len(members) > 1]


def _shares_activity(left: RowInfo, right: RowInfo) -> bool:
    return any(left.hours[a] and right.hours[a] for a in TEACHING_ACTIVITIES)


def same_subject(left: str, right: str) -> bool:
    """Fənn açarları eyni fənndirmi: bərabər, və ya oxşarlıq ≥ 0.88 + rəqəmlər eyni («Verilənlər bazası
    sistemləri» = «Verilənlərin bazası sistemləri»; «… əsasları -1» ≠ «… əsasları -2»)."""
    if left == right:
        return True
    if _LEVEL_RE.search(left) or _LEVEL_RE.search(right):
        return False  # səviyyə qrupları («(elementary)» / «(intermediate)») paraleldir — yalnız dəqiq bərabərlik
    if not left or not right or re.findall(r"\d+", left) != re.findall(r"\d+", right):
        return False
    return difflib.SequenceMatcher(None, left, right).ratio() >= SUBJECT_THRESHOLD


def find_duplicates(infos: list[RowInfo]) -> list[dict]:
    """(a) eyni fənn (oxşar ad) + semestr + kəsişən qrup + ortaq fəaliyyət → klaster."""
    by_group = defaultdict(list)
    for index, info in enumerate(infos):
        if info.key:
            for group in info.groups:
                by_group[(info.row.season, group)].append(index)
    edges = set()
    for members in by_group.values():
        for i, left in enumerate(members):
            for right in members[i + 1 :]:
                pair = (min(left, right), max(left, right))
                if pair in edges:
                    continue
                a, b = infos[left], infos[right]
                if _shares_activity(a, b) and same_subject(a.key, b.key):
                    edges.add(pair)
    clusters = []
    for members in _components(range(len(infos)), edges):
        rows = [infos[index] for index in sorted(members)]
        clusters.append(
            {
                "rows": rows,
                "exact": len({info.groups for info in rows}) == 1,
                "cross_chair": len({info.chair_id for info in rows}) > 1,
                "sources": sorted({info.source for info in rows}),
                "excess": _cluster_excess(rows),
            }
        )
    return clusters


def _cluster_excess(rows) -> int:
    """Yuxarı hədd: fəaliyyət üzrə Σ − ən böyük sətir (qalan sətir bütün qrupları əhatə edirsə — dəqiq)."""
    excess = 0
    for activity in TEACHING_ACTIVITIES:
        values = [info.hours[activity] for info in rows]
        excess += sum(values) - max(values)
    return excess


# ── (b) birgə mühazirə sübutu ───────────────────────────────────────────────


def _periods(organization, year: str) -> dict:
    AcademicPeriod = django_apps.get_model("organizations", "AcademicPeriod")
    from .plan_calendar import season_from_period

    result = {}
    for period in AcademicPeriod.objects.filter(organization=organization, academic_year=year):
        result.setdefault(season_from_period(period), period.pk)
    return result


class JointEvidence:
    """Müəllim × fənn açarı × semestr × NÖV → qrup → «anlar» (jurnal tarixi+saat, cədvəl slotu).

    Sahib 2026-10-25 (əlavə): axın yalnız mühazirə deyil — seminar/lab da birgə keçirilə bilər («60 saatlıq
    fənn — bir qrup kimi 60 saat»). Sübut hər növ üçün AYRICA yoxlanır (eyni növ, eyni vaxt).
    """

    def __init__(self, organization, year: str):
        self.periods = _periods(organization, year)
        season_of = {pk: season for season, pk in self.periods.items()}
        CourseOffering = django_apps.get_model("registrar", "CourseOffering")
        Lesson = django_apps.get_model("registrar", "Lesson")
        ScheduleSlot = django_apps.get_model("registrar", "ScheduleSlot")
        offerings = {
            row["pk"]: row
            for row in CourseOffering.objects.filter(
                organization=organization, period_id__in=list(season_of), group__isnull=False
            ).values("pk", "group_id", "period_id", "instructor_id", "subject__name")
        }
        self.lessons: dict = defaultdict(lambda: defaultdict(set))
        self.slots: dict = defaultdict(lambda: defaultdict(set))
        for lesson in Lesson.objects.filter(offering_id__in=list(offerings), kind__in=TEACHING_ACTIVITIES).values(
            "offering_id", "date", "start_time", "instructor_id", "kind"
        ):
            offering = offerings[lesson["offering_id"]]
            teacher = lesson["instructor_id"] or offering["instructor_id"]
            if not teacher or not lesson["start_time"]:
                continue
            key = (teacher, subject_key(offering["subject__name"]), season_of[offering["period_id"]], lesson["kind"])
            self.lessons[key][offering["group_id"]].add((lesson["date"], lesson["start_time"]))
        slot_q = Q(offering_id__in=list(offerings), kind__in=TEACHING_ACTIVITIES, is_parked=False)
        for slot in ScheduleSlot.objects.filter(slot_q).values(
            "offering_id", "weekday", "start_time", "week_type", "instructor_id", "kind"
        ):
            offering = offerings[slot["offering_id"]]
            teacher = slot["instructor_id"] or offering["instructor_id"]
            if not teacher:
                continue
            key = (teacher, subject_key(offering["subject__name"]), season_of[offering["period_id"]], slot["kind"])
            self.slots[key][offering["group_id"]].add((slot["weekday"], slot["start_time"], slot["week_type"]))

    def joint(self, teacher_id, key: str, season: str, activity: str, left, right) -> str:
        """İki qrup bu növdə birgə keçirilirmi: «journal» / «schedule» / «uncertain» / boş (ayrı və ya data yox).

        Sahib 2026-10-25: əsas sübut JURNALDIR — eyni müəllim + fənn + növ + tarix + başlama saatı bir neçə qrupun
        açılışında → birgə. Çoxluq qaydası: kiçik tərəfin tarixlərinin ≥ 75 %-i ortaqdırsa birgə, bəziləri ortaqdırsa
        «qeyri-müəyyən», heç biri — ayrı. Jurnalda hər iki qrupun ən az 2 dərsi yoxdursa, dərs cədvəlinin birgə slotu.
        """
        lessons = self.lessons.get((teacher_id, key, season, activity), {})
        a, b = lessons.get(left, set()), lessons.get(right, set())
        if len(a) >= JOINT_MIN_DATES and len(b) >= JOINT_MIN_DATES:
            shared = len(a & b)
            if shared >= JOINT_MIN_DATES and shared >= JOINT_MIN_SHARE * min(len(a), len(b)):
                return "journal"
            return "uncertain" if shared else ""
        slots = self.slots.get((teacher_id, key, season, activity), {})
        if slots.get(left, set()) & slots.get(right, set()):
            return "schedule"
        return ""

    def stream_stats(self) -> list[dict]:
        """Jurnala görə müəllim × fənn × növ: neçə qrup, neçə axın (birgə komponent), neçə qeyri-müəyyən cüt."""
        stats = []
        for (teacher, key, season, kind), by_group in self.lessons.items():
            groups = [group for group, moments in by_group.items() if len(moments) >= JOINT_MIN_DATES]
            if len(groups) < 2:
                continue
            edges, uncertain = [], 0
            for i in range(len(groups)):
                for j in range(i + 1, len(groups)):
                    verdict = self.joint(teacher, key, season, kind, groups[i], groups[j])
                    if verdict == "journal":
                        edges.append((i, j))
                    elif verdict == "uncertain":
                        uncertain += 1
            joined = _components(range(len(groups)), edges)
            streams = len(groups) - sum(len(members) - 1 for members in joined)
            stats.append(
                {"teacher_id": teacher, "key": key, "season": season, "activity": kind, "groups": len(groups),
                 "streams": streams, "uncertain_pairs": uncertain}
            )  # fmt: skip
        return stats


def find_joint(infos: list[RowInfo], evidence: JointEvidence, busy: set, activity: str) -> tuple[list, list]:
    """(b) eyni müəllimin eyni fənn × NÖV saatı AYRI qrup sətirlərində — sübutlu axınlar və sübutsuz namizədlər.

    ``busy`` — (a) klasterindəki sətirlər (əvvəlcə dublikat həll olunmalıdır, burada sayılmır).
    """
    buckets = defaultdict(list)
    for info in infos:
        if info.pk in busy or not info.groups or not info.hours[activity]:
            continue
        teacher = info.single_teacher(activity)
        if teacher is not None:
            buckets[(teacher, info.key, info.row.season)].append(info)
    proven, unproven = [], []
    for (teacher, key, season), rows in buckets.items():
        if len(rows) < 2:
            continue
        edges, kinds, doubtful = [], {}, set()
        for i in range(len(rows)):
            for j in range(i + 1, len(rows)):
                if rows[i].groups & rows[j].groups:
                    continue
                verdicts = {
                    evidence.joint(teacher, key, season, activity, left, right)
                    for left in rows[i].groups
                    for right in rows[j].groups
                }
                kind = next((v for v in ("journal", "schedule") if v in verdicts), "")
                if kind:
                    edges.append((i, j))
                    kinds[(i, j)] = kind
                elif "uncertain" in verdicts:
                    doubtful.update((i, j))
        linked = set()
        for members in _components(range(len(rows)), edges):
            linked.update(members)
            stream = [rows[index] for index in members]
            found_kinds = sorted({kinds[e] for e in edges if e[0] in members and e[1] in members})
            proven.append(_stream(stream, teacher, found_kinds, activity))
        rest = [rows[index] for index in range(len(rows)) if index not in linked]
        if len(rest) > 1:
            unproven.append(
                {
                    "rows": rest,
                    "teacher_id": teacher,
                    "activity": activity,
                    "hours": sum(r.hours[activity] for r in rest),
                    # jurnalda bəzi tarixlər ortaq, amma < 75 % — çoxluq qaydası ilə «qeyri-müəyyən»
                    "uncertain": bool(doubtful - linked),
                }
            )
    return proven, unproven


def _stream(rows: list[RowInfo], teacher, evidence_kinds, activity: str) -> dict:
    """Axın: lövbər (ən çox qrup, sonra rəsmi tapşırıq, sonra ən köhnə) + digərlərinin bu növ saatı artıqdır."""
    ordered = sorted(rows, key=lambda r: (-len(r.groups), r.source != "task", r.row.created_at, str(r.pk)))
    anchor, others = ordered[0], ordered[1:]
    return {
        "activity": activity,
        "rows": ordered,
        "anchor": anchor,
        "others": others,
        "teacher_id": teacher,
        "evidence": evidence_kinds,
        "equal_hours": len({info.per_group(activity) for info in rows}) == 1,
        "excess": sum(info.hours[activity] for info in others),
        "cross_chair": len({info.chair_id for info in rows}) > 1,
    }


# ── (c) plandan artıq ───────────────────────────────────────────────────────


def find_plan_overrun(organization, infos: list[RowInfo]) -> list[dict]:
    """Sətrin cəmi > plan × çarpan, və ya qrup başına saat > fənnin kurikulumdakı ən böyük saatı."""
    CurriculumSubject = django_apps.get_model("registrar", "CurriculumSubject")
    subject_ids = {info.row.subject_id for info in infos if info.row.subject_id}
    curriculum = defaultdict(lambda: {"lecture": 0, "seminar": 0, "lab": 0})
    for item in CurriculumSubject.objects.filter(organization=organization, subject_id__in=subject_ids).values(
        "subject_id", "lecture_hours", "seminar_hours", "lab_hours"
    ):
        bucket = curriculum[item["subject_id"]]
        bucket["lecture"] = max(bucket["lecture"], int(item["lecture_hours"] or 0))
        bucket["seminar"] = max(bucket["seminar"], int(item["seminar_hours"] or 0))
        bucket["lab"] = max(bucket["lab"], int(item["lab_hours"] or 0))
    found = []
    for info in infos:
        row = info.row
        for activity in TEACHING_ACTIVITIES:
            total = info.hours[activity]
            if not total:
                continue
            plan = int(getattr(row, PLAN_FIELD[activity]) or 0)
            multiplier = int(getattr(row, MULTIPLIER_FIELD[activity]) or 0)
            limit = plan * max(multiplier, 1) if plan else 0
            if limit and total > limit:
                found.append({"info": info, "activity": activity, "total": total, "limit": limit, "basis": "row_plan"})
                continue
            cap = curriculum.get(row.subject_id, {}).get(activity, 0) if row.subject_id else 0
            divisor = max(multiplier, 1) if activity == "lecture" else max(len(info.groups), multiplier, 1)
            if cap and total // divisor > cap:
                found.append({"info": info, "activity": activity, "total": total, "limit": cap, "basis": "curriculum"})
    return found


def detect(organization, year: str) -> Detection:
    infos = load_rows(organization, year)
    result = Detection(year=year, rows=infos, by_pk={info.pk: info for info in infos})
    result.skipped_no_groups = sum(1 for info in infos if not info.groups and any(info.hours.values()))
    result.duplicates = find_duplicates(infos)
    busy = {info.pk for cluster in result.duplicates for info in cluster["rows"]}
    evidence = JointEvidence(organization, year)
    for activity in TEACHING_ACTIVITIES:
        proven, unproven = find_joint(infos, evidence, busy, activity)
        result.joint += proven
        result.joint_unproven += unproven
    result.journal_stats = evidence.stream_stats()
    result.plan_overrun = find_plan_overrun(organization, infos)
    return result


SEASON_LABELS = {Season.FALL: "payız", Season.SPRING: "yaz", Season.SUMMER: "yay"}

__all__ = [
    "Detection",
    "JointEvidence",
    "RowInfo",
    "detect",
    "find_duplicates",
    "find_joint",
    "find_plan_overrun",
    "load_rows",
    "row_source",
    "subject_key",
]
