"""Vakant saatın sahibi — JURNAL DATASINDAN (sahib 2026-10-25: «payızda vakantda olanlar olmamalıdır …
köhnə sistemdən dəqiqləşdirməyə çalış, datadan ki bunu kim keçir. Boş olmasın»).

Bu modul YALNIZ OXUYUR: hər vakant ``(sətir, fəaliyyət)`` üçün sübut toplayır və qərar verir; yazı
:mod:`.vacant_fill_apply`-dadır.

VAKANT — müəllimsiz bölgü (``TeacherAssignment.teacher IS NULL``) — kafedra tapşırığının (ləğv olunmamış)
həmin tədris ili + fəsil üzrə dərs sətrində (``row_kind=teaching``).

SÜBUT (fəaliyyət növü üzrə AYRICA — mühazirə və seminar fərqli müəllimlərdə ola bilər), prioritetlə:

1. Yeni sistemin jurnalı: sətrin (fənn × semestr × qrup) açılışlarında KEÇİRİLMİŞ (tarixi bu gün və ya əvvəl),
   MÜƏLLİMİ YAZILMIŞ (``Lesson.instructor``) həmin növ dərslər.
2. Köhnə sistemin cari semestr jurnalı (``legacy_journal_teachers_extract`` faylı): fənn + qrup üzrə jurnallar,
   hər birinin müəllimi və elan etdiyi növlər (``sem_muh``); yalnız dərs tarixi OLAN jurnallar, çəki — tarix sayı.
   Niyə 1-dən sonra: köhnə jurnaldan köçən dərslərdə müəllim BOŞDUR (yeni sistemdə dərsləri bir açılışa toplanıb,
   açılışın sahibi isə yalnız birinci jurnalın müəllimidir) — kimin keçdiyini yalnız köhnə jurnal deyir.
3. Praktiki hovuz: laboratoriya sübutu yoxdursa və sətirdə seminar saatı YOXDURSA, seminar sübutu sayılır (və
   əksinə) — Forma 1-in seminar↔laboratoriya qaydası.
4. ÇOXLUQ: bir müəllim sübutun (dərs / jurnal tarixi) ≥ 75 %-ni təşkil edirsə — o (``fill``); yoxsa ``conflict``.

Qalan hallar (yazılmır, kafedra müdirinə siyahı): ``kind_missing`` (fənn+qrupun jurnalı var, bu növ yoxdur),
``no_journal`` (heç bir sistemdə jurnal yoxdur), ``no_subject`` (sətrin fənni yoxdur), ``teacher_unresolved``
(köhnə jurnalın müəllimi hesabla tutuşmadı), ``teacher_blocked`` (hesab aktiv deyil / bloklanıb / arxivdədir /
tələbədir). Kafedra üzvü olmayan müəllim — ``outside`` (yazıda kafedraya ƏLAVƏ üzvlük + saathesabı).
"""

from __future__ import annotations

import json
import os
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from django.apps import apps as django_apps
from django.utils import timezone

from ..constants import ACTIVITY_TOTAL_FIELD, TEACHING_ACTIVITIES, RowKind, TaskStatus
from ..models import TeacherAssignment, TeachingTaskRow
from .people import home_chairs, is_assignable_teacher

#: Çoxluq həddi — bir müəllim sübutun ən azı bu payını təşkil etməlidir.
MAJORITY_SHARE = 0.75
#: ``legacy_journal_teachers_extract`` faylının formatı (müqavilə — legacy_import-u import etmirik).
LEGACY_FORMAT = "legacy-journal-teachers/1"

FILL = "fill"
CONFLICT = "conflict"
KIND_MISSING = "kind_missing"
NO_JOURNAL = "no_journal"
NO_SUBJECT = "no_subject"
TEACHER_UNRESOLVED = "teacher_unresolved"
TEACHER_BLOCKED = "teacher_blocked"
DECISIONS = (FILL, CONFLICT, KIND_MISSING, NO_JOURNAL, NO_SUBJECT, TEACHER_UNRESOLVED, TEACHER_BLOCKED)

SOURCE_LESSONS = "journal_lessons"
SOURCE_LEGACY = "legacy_journal"

_ACTIVITIES = tuple(str(activity) for activity in TEACHING_ACTIVITIES)
_PRACTICAL_PAIR = {"seminar": "lab", "lab": "seminar"}
_STUDENT_ROLES = ("student", "lead_student", "alumni")


class LegacyFileError(ValueError):
    """Köhnə sistem sübut faylı oxunmur / formatı tanınmır (fail-closed)."""


@dataclass
class Vacancy:
    """Bir vakant ``(sətir, fəaliyyət)`` və onun sübutu / qərarı."""

    row: object
    activity: str
    assignment_ids: list
    hours: int
    evidence: Counter = field(default_factory=Counter)  # müəllim_id|None → çəki (dərs / jurnal tarixi)
    source: str = ""  # journal_lessons | legacy_journal
    pooled: bool = False  # seminar↔lab hovuzundan
    legacy: list = field(default_factory=list)  # fənn + qrup üzrə köhnə jurnallar (hamısı)
    hints: Counter = field(default_factory=Counter)  # eyni fənn, BAŞQA qruplar: müəllim → tarix
    owners: set = field(default_factory=set)
    offering_ids: list = field(default_factory=list)
    students: int = 0
    decision: str = ""
    teacher_id: int | None = None
    share: float = 0.0
    outside: bool = False
    result: str = ""

    @property
    def chair(self):
        return self.row.task.chair

    @property
    def weight(self) -> int:
        return sum(self.evidence.values())


def load_legacy(path: str) -> dict:
    """Fayl → ``{fənn_id: [jurnal, …]}`` (qrup id-ləri ``set``)."""
    if not path:
        return {}
    try:
        with open(os.path.expanduser(path), encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError) as exc:
        raise LegacyFileError(f"legacy_journals_unreadable: {type(exc).__name__}") from None
    if not isinstance(data, dict) or data.get("format") != LEGACY_FORMAT:
        raise LegacyFileError("legacy_journals_format_unknown")
    index: dict = defaultdict(list)
    for journal in data.get("journals") or []:
        index[str(journal["subject_id"])].append({**journal, "group_ids": set(journal.get("group_ids") or [])})
    return index


def vacant_rows(organization, year: str, season: str):
    """Həmin il + fəslin vakant bölgüsü olan dərs sətirləri (ləğv olunmamış tapşırıqlar)."""
    return (
        TeachingTaskRow.objects.filter(
            organization=organization,
            task__academic_year=year,
            season=season,
            row_kind=RowKind.TEACHING,
            assignments__teacher__isnull=True,
            assignments__activity__in=_ACTIVITIES,
        )
        .exclude(task__status=TaskStatus.CANCELLED)
        .select_related("task", "task__chair", "subject", "period")
        .prefetch_related("groups")
        .distinct()
        .order_by("task__chair__name", "order", "pk")
    )


def collect(organization, year: str, season: str, legacy: dict | None = None) -> list[Vacancy]:
    """Bütün vakant cütlər + sübut + qərar (baza yazılmır)."""
    rows = list(vacant_rows(organization, year, season))
    vacancies: dict = {}
    for assignment in TeacherAssignment.objects.filter(
        row__in=rows, teacher__isnull=True, activity__in=_ACTIVITIES
    ).order_by("created_at"):
        key = (assignment.row_id, str(assignment.activity))
        if key not in vacancies:
            vacancies[key] = Vacancy(row=None, activity=key[1], assignment_ids=[], hours=0)
        vacancies[key].assignment_ids.append(assignment.pk)
        vacancies[key].hours += int(assignment.hours or 0)
    by_pk = {row.pk: row for row in rows}
    for (row_id, _), vacancy in vacancies.items():
        vacancy.row = by_pk[row_id]
    items = sorted(vacancies.values(), key=lambda v: (v.chair.name, v.row.order, str(v.row.pk), v.activity))
    _attach_new_system(organization, items)
    _attach_legacy(items, legacy or {})
    _decide(organization, items)
    return items


def _total(row, activity: str) -> int:
    return int(getattr(row, ACTIVITY_TOTAL_FIELD[activity], 0) or 0)


def _pooled(row, activity: str, get) -> tuple[Counter, bool]:
    """Növün sübutu; yoxdursa və sətirdə cüt praktiki növün saatı yoxdursa — onun sübutu (hovuz)."""
    found = get(activity)
    other = _PRACTICAL_PAIR.get(activity)
    if not found and other and not _total(row, other):
        return get(other), True
    return found, False


# ── 1. yeni sistem ────────────────────────────────────────────────────────
def _attach_new_system(organization, items: list[Vacancy]) -> None:
    CourseOffering = django_apps.get_model("registrar", "CourseOffering")
    Lesson = django_apps.get_model("registrar", "Lesson")
    Enrollment = django_apps.get_model("registrar", "Enrollment")
    rows = {item.row.pk: item.row for item in items if item.row.subject_id and item.row.period_id}
    keys = {(row.subject_id, row.period_id) for row in rows.values()}
    offerings: dict = defaultdict(list)
    if keys:
        for offering in CourseOffering.objects.filter(
            organization=organization,
            subject_id__in={key[0] for key in keys},
            period_id__in={key[1] for key in keys},
            group__isnull=False,
            is_active=True,
        ):
            offerings[(offering.subject_id, offering.period_id, offering.group_id)].append(offering)
    row_offerings = {
        pk: [o for group in row.groups.all() for o in offerings.get((row.subject_id, row.period_id, group.pk), [])]
        for pk, row in rows.items()
    }
    offering_ids = {o.pk for found in row_offerings.values() for o in found}
    lessons: dict = defaultdict(Counter)  # (açılış, növ) → {müəllim: say} — yalnız müəllimi YAZILMIŞ dərslər
    for offering_id, kind, instructor_id in Lesson.objects.filter(
        offering_id__in=offering_ids, date__lte=timezone.localdate(), instructor__isnull=False
    ).values_list("offering_id", "kind", "instructor_id"):
        lessons[(offering_id, kind)][instructor_id] += 1
    students = Counter(Enrollment.objects.filter(offering_id__in=offering_ids).values_list("offering_id", flat=True))
    for item in items:
        found = row_offerings.get(item.row.pk, [])
        item.offering_ids = [o.pk for o in found]
        item.owners = {o.instructor_id for o in found if o.instructor_id}
        item.students = sum(students.get(o.pk, 0) for o in found)

        def get(kind, found=found):
            total: Counter = Counter()
            for offering in found:
                total.update(lessons.get((offering.pk, kind), Counter()))
            return total

        evidence, pooled = _pooled(item.row, item.activity, get)
        if evidence:
            item.evidence, item.pooled, item.source = evidence, pooled, SOURCE_LESSONS


# ── 2. köhnə sistem ───────────────────────────────────────────────────────
def _attach_legacy(items: list[Vacancy], legacy: dict) -> None:
    for item in items:
        if not item.row.subject_id:
            continue
        groups = {str(group.pk) for group in item.row.groups.all()}
        same_subject = legacy.get(str(item.row.subject_id), [])
        item.legacy = [j for j in same_subject if j["group_ids"] & groups]
        for journal in same_subject:
            if journal not in item.legacy and journal["dates"] and journal["teacher_id"]:
                item.hints[journal["teacher_id"]] += journal["dates"]
        if item.source:
            continue  # yeni sistemin müəllimli dərsləri üstündür

        def get(kind, journals=item.legacy):
            total: Counter = Counter()
            for journal in journals:
                if journal["dates"] and kind in journal["kinds"]:
                    total[journal["teacher_id"]] += journal["dates"]
            return total

        evidence, pooled = _pooled(item.row, item.activity, get)
        if evidence:
            item.evidence, item.pooled, item.source = evidence, pooled, SOURCE_LEGACY


# ── qərar ─────────────────────────────────────────────────────────────────
def _decide(organization, items: list[Vacancy]) -> None:
    for item in items:
        if not item.row.subject_id:
            item.decision = NO_SUBJECT
        elif item.evidence:
            teacher_id, weight = item.evidence.most_common(1)[0]
            item.share = weight / item.weight
            ties = [pk for pk, value in item.evidence.items() if value == weight]
            if item.share < MAJORITY_SHARE or len(ties) > 1:
                item.decision = CONFLICT
            elif teacher_id is None:
                item.decision = TEACHER_UNRESOLVED
            else:
                item.decision, item.teacher_id = FILL, teacher_id
        elif item.legacy or item.owners:
            item.decision = KIND_MISSING
        else:
            item.decision = NO_JOURNAL
    candidates = {item.teacher_id for item in items if item.decision == FILL}
    blocked = _blocked_teachers(organization, candidates)
    homes = home_chairs(organization, list(candidates))
    users = {user.pk: user for user in django_apps.get_model("auth", "User").objects.filter(pk__in=candidates)}
    for item in items:
        if item.decision != FILL:
            continue
        if item.teacher_id in blocked:
            item.decision = TEACHER_BLOCKED
            continue
        home = (homes.get(item.teacher_id) or {}).get("id")
        member = is_assignable_teacher(organization, item.chair, users[item.teacher_id])
        item.outside = home != str(item.chair.pk) or not member


def _blocked_teachers(organization, ids) -> set:
    """Yük ala bilməyən hesablar: yoxdur, aktiv deyil, bloklanıb / silinib / arxivdədir və ya TƏLƏBƏDİR."""
    ids = {pk for pk in ids if pk}
    if not ids:
        return set()
    User = django_apps.get_model("auth", "User")
    Membership = django_apps.get_model("organizations", "Membership")
    blocked = set(ids)
    for user in User.objects.filter(pk__in=ids).select_related("profile"):
        profile = getattr(user, "profile", None)
        if user.is_active and not (
            profile is not None and (profile.blocked_at or profile.deleted_at or profile.access_state == "archived")
        ):
            blocked.discard(user.pk)
    blocked |= set(
        Membership.objects.filter(
            organization=organization, user_id__in=ids, is_active=True, role__name__in=_STUDENT_ROLES
        ).values_list("user_id", flat=True)
    )
    return blocked


def summary_by_chair(items: list[Vacancy]) -> dict:
    """Kafedra adı → {"rows": vakant sətir sayı, "hours": vakant saat}."""
    result: dict = defaultdict(lambda: {"rows": set(), "hours": 0})
    for item in items:
        bucket = result[item.chair.name]
        bucket["rows"].add(item.row.pk)
        bucket["hours"] += item.hours
    return {name: {"rows": len(value["rows"]), "hours": value["hours"]} for name, value in sorted(result.items())}


__all__ = [
    "CONFLICT",
    "DECISIONS",
    "FILL",
    "KIND_MISSING",
    "LEGACY_FORMAT",
    "MAJORITY_SHARE",
    "NO_JOURNAL",
    "NO_SUBJECT",
    "SOURCE_LEGACY",
    "SOURCE_LESSONS",
    "TEACHER_BLOCKED",
    "TEACHER_UNRESOLVED",
    "LegacyFileError",
    "Vacancy",
    "collect",
    "load_legacy",
    "summary_by_chair",
    "vacant_rows",
]
