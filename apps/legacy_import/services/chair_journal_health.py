"""Kafedra jurnal sağlamlığı — hər müəllim üçün bir sətir (YALNIZ OXU; sahib 2026-10-27: «kafedra-kafedra davam et»).

Sütunlar (cari dövr, kafedra :func:`apps.registrar.offering_chairs.offering_chairs` tərifi ilə):

* ``journals`` — müəllimin sahibi olduğu aktiv açılışlar; ``shared_journals`` — sahibi olmadığı, aktiv payı olanlar;
* ``enrolled`` — sahib olduğu jurnallardakı ``enrolled`` sətirlər;
* ``wrong_level`` / ``unlisted`` — səviyyə jurnallarında: tələbə bu səviyyənin köhnə jurnalında yox, eyni ailənin başqa
  səviyyəsində var / heç bir səviyyə siyahısında yoxdur (köhnə paket lazımdır);
* ``foreign_journals`` / ``foreign_rows`` — müəllimin jurnalı açanda gördüyü BAŞQA müəllimin tələbələri (payların
  görünüş qaydası :mod:`apps.registrar.journal_shares` ilə); paket yoxdursa — başqa payların açıq siyahısındakı sətirlər;
* ``split_level_journals`` — müəllimin köhnə səviyyə jurnalı ≥2 açılışa bölünüb (``merge_level_journals``-in işi);
* ``no_lesson_journals`` — sahib olduğu, dərsi olmayan jurnallar;
* ``legacy_unmapped`` — müəllimin köhnə jurnalında xanası olan, yeni sistemdə həmin fənn üzrə heç bir xanası olmayan
  tələbələr (jurnal × tələbə cütləri);
* ``teacher="-"`` sətri: kafedranın müəllimsiz açılışları (``no_instructor_offerings``).

Müəllim yalnız istifadəçi id-si ilə (ad yoxdur); adlı Excel yalnız :func:`write_xlsx` ilə repodan KƏNAR lokal fayla.
"""

from __future__ import annotations

import os
from collections import Counter, defaultdict

from django.apps import apps as django_apps

COLUMNS = (
    "chair",
    "teacher",
    "journals",
    "shared_journals",
    "enrolled",
    "wrong_level",
    "unlisted",
    "foreign_journals",
    "foreign_rows",
    "split_level_journals",
    "no_lesson_journals",
    "no_instructor_offerings",
    "legacy_unmapped",
)
LEGACY_COLUMNS = ("wrong_level", "unlisted", "split_level_journals", "legacy_unmapped")


def _model(app, name):
    return django_apps.get_model(app, name)


def resolve_chairs(organization, keys) -> list:
    """``--chair`` dəyərləri (uuid və ya slug) → ``OrgUnit``; tapılmayan açar ``LookupError``."""
    from core.http_ids import parse_uuid

    OrgUnit = _model("organizations", "OrgUnit")
    units = []
    for key in keys:
        key = str(key).strip()
        parsed = parse_uuid(key)
        query = OrgUnit.objects.filter(organization=organization)
        unit = (query.filter(pk=parsed) if parsed else query.filter(slug=key)).first()
        if unit is None:
            raise LookupError(key)
        units.append(unit)
    return units


def _visible(user_id, owner_id, shares: dict, enrolled: set) -> set:
    """İstifadəçinin bu açılışda gördüyü sətirlər (dərs növləri nəzərə alınmır)."""
    if user_id == owner_id:
        if user_id not in shares:
            return set(enrolled)
        others = [rows for teacher, rows in shares.items() if teacher != user_id]
        if any(not rows for rows in others):
            covered = set(enrolled)
        else:
            covered = set().union(*others) if others else set()
        return ((shares[user_id] or enrolled) | (enrolled - covered)) & enrolled
    if user_id in shares:
        return (shares[user_id] or enrolled) & enrolled
    return set()


class ChairHealth:
    def __init__(self, organization, period, *, index=None):
        self.organization = organization
        self.period = period
        self.index = index
        self.counts: Counter = Counter()

    def rows(self, units=None) -> list:
        from apps.registrar.public import offering_chairs

        CourseOffering = _model("registrar", "CourseOffering")
        base = CourseOffering.objects.filter(organization=self.organization, period=self.period, is_active=True)
        if units:
            scopes = [(str(unit.pk), set(offering_chairs.offering_ids_in_unit(unit, base))) for unit in units]
        else:
            by_chair = defaultdict(set)
            for offering_id, chairs in offering_chairs.offering_chairs(base, self.organization.pk).items():
                for chair_id in chairs:
                    by_chair[chair_id].add(offering_id)
            scopes = sorted(by_chair.items())
        self._load({pk for _chair, ids in scopes for pk in ids})
        out = []
        for chair_id, offering_ids in scopes:
            out.extend(self._chair_rows(chair_id, offering_ids))
        self.counts["chairs"] = len(scopes)
        self.counts["rows"] = len(out)
        return out

    # ── oxu ──────────────────────────────────────────────────────────────
    def _load(self, offering_ids) -> None:
        Enrollment = _model("registrar", "Enrollment")
        JournalShare = _model("registrar", "JournalShare")
        Lesson = _model("registrar", "Lesson")
        CourseOffering = _model("registrar", "CourseOffering")
        ids = list(offering_ids)
        self.offerings = {
            row["id"]: row
            for row in CourseOffering.objects.filter(pk__in=ids).values("id", "instructor_id", "subject__name")
        }
        self.enrolled = defaultdict(set)
        for offering_id, pk in Enrollment.objects.filter(offering_id__in=ids, status="enrolled").values_list(
            "offering_id", "pk"
        ):
            self.enrolled[offering_id].add(pk)
        self.shares = defaultdict(dict)
        through = JournalShare.enrollments.through.objects.filter(
            journalshare__offering_id__in=ids, journalshare__is_active=True
        ).values_list("journalshare_id", "enrollment_id")
        listed = defaultdict(set)
        for share_id, enrollment_id in through:
            listed[share_id].add(enrollment_id)
        for share_id, offering_id, teacher_id in JournalShare.objects.filter(
            offering_id__in=ids, is_active=True
        ).values_list("pk", "offering_id", "teacher_id"):
            self.shares[offering_id][teacher_id] = listed.get(share_id, set())
        self.lessons = Counter(Lesson.objects.filter(offering_id__in=ids).values_list("offering_id", flat=True))
        self.classes, self.owners_of, self.unmapped = {}, {}, Counter()
        if self.index is not None:
            self._load_legacy()

    def _load_legacy(self) -> None:
        from apps.registrar.public import language_levels as levels

        from .journal_share_plan import level_classes

        LessonMark = _model("registrar", "LessonMark")
        self.classes = level_classes(self.index)
        self.owners_of = {
            pk: {entry.teacher_id for entry in entries} for pk, entries in self.index.journals_by_enrollment().items()
        }
        marked = set(
            LessonMark.objects.filter(organization=self.organization, lesson__offering__period=self.period)
            .values_list("enrollment_id", flat=True)
            .distinct()
        )
        self.split = defaultdict(list)
        for entry in self.index.resolved_journals():
            if levels.level_of(entry.subject_name) and len(entry.hits) >= 2:
                self.split[entry.teacher_id].append(set(entry.hits))
            for legacy_id, user_id in entry.students:
                if not entry.points.get(legacy_id):
                    continue
                rows = self.index.by_student_subject.get((user_id, entry.subject_id), ()) if user_id else ()
                if not any(row["id"] in marked for row in rows):
                    places = {row["offering_id"] for row in rows} or set(entry.hits)
                    for offering_id in places:
                        self.unmapped[(entry.teacher_id, offering_id)] += 1
                    if not places:
                        self.counts["legacy_unmapped_no_offering"] += 1

    # ── sətirlər ─────────────────────────────────────────────────────────
    def _chair_rows(self, chair_id, offering_ids) -> list:
        stats = defaultdict(Counter)
        no_instructor = 0
        for offering_id in offering_ids:
            offering = self.offerings.get(offering_id)
            if offering is None:
                continue
            owner = offering["instructor_id"]
            if owner is None:
                no_instructor += 1
            shares = self.shares.get(offering_id, {})
            for teacher_id in {owner, *shares} - {None}:
                self._teacher_offering(stats[teacher_id], teacher_id, owner, offering_id, shares)
        legacy = self.index is not None
        for teacher_id, row in stats.items():
            if legacy:
                row["split_level_journals"] = sum(1 for hits in self.split.get(teacher_id, ()) if hits & offering_ids)
                row["legacy_unmapped"] = sum(self.unmapped.get((teacher_id, pk), 0) for pk in offering_ids)
        rows = [self._render(chair_id, teacher_id, row, legacy) for teacher_id, row in sorted(stats.items())]
        if no_instructor:
            rows.append(self._render(chair_id, "-", Counter(no_instructor_offerings=no_instructor), legacy))
        return rows

    def _teacher_offering(self, row: Counter, teacher_id, owner, offering_id, shares) -> None:
        enrolled = self.enrolled.get(offering_id, set())
        if teacher_id == owner:
            row["journals"] += 1
            row["enrolled"] += len(enrolled)
            row["no_lesson_journals"] += 0 if self.lessons.get(offering_id) else 1
            for pk in enrolled:
                verdict = self.classes.get(pk)
                if verdict in ("wrong_level", "unlisted"):
                    row[verdict] += 1
        else:
            row["shared_journals"] += 1
        visible = _visible(teacher_id, owner, shares, enrolled)
        if self.index is not None:
            foreign = {pk for pk in visible if self.owners_of.get(pk) and teacher_id not in self.owners_of[pk]}
        else:
            listed = set().union(*[rows for teacher, rows in shares.items() if teacher != teacher_id] or [set()])
            foreign = visible & listed
        if foreign:
            row["foreign_journals"] += 1
            row["foreign_rows"] += len(foreign)

    @staticmethod
    def _render(chair_id, teacher_id, row: Counter, legacy: bool) -> dict:
        out = {"chair": str(chair_id), "teacher": str(teacher_id)}
        for column in COLUMNS[2:]:
            out[column] = "" if (column in LEGACY_COLUMNS and not legacy) else int(row.get(column, 0))
        return out


def totals(rows) -> Counter:
    out: Counter = Counter()
    for row in rows:
        for column in COLUMNS[2:]:
            if isinstance(row[column], int):
                out[column] += row[column]
    return out


def write_table(handle, rows, fmt: str) -> None:
    if fmt == "md":
        lines = ["| " + " | ".join(COLUMNS) + " |", "|" + "---|" * len(COLUMNS)]
        lines += ["| " + " | ".join(str(row[column]) for column in COLUMNS) + " |" for row in rows]
        handle.write("\n".join(lines) + "\n")
        return
    from core.export_safety import safe_csv_writer

    writer = safe_csv_writer(handle, lineterminator="\n")
    writer.writerow(COLUMNS)
    for row in rows:
        writer.writerow([row[column] for column in COLUMNS])


def outside_repo(path: str) -> bool:
    from django.conf import settings

    target = os.path.realpath(os.path.expanduser(path))
    root = os.path.realpath(str(settings.BASE_DIR))
    return os.path.commonpath([target, root]) != root


def write_xlsx(path: str, rows) -> None:
    """Sahib üçün ADLI Excel (kafedra və müəllim adları) — yalnız repodan kənar lokal fayla, 0600."""
    from openpyxl import Workbook

    from core.export_safety import sheet_append

    OrgUnit = _model("organizations", "OrgUnit")
    User = _model("auth", "User")
    chairs = dict(OrgUnit.objects.filter(pk__in={row["chair"] for row in rows}).values_list("pk", "name"))
    chairs = {str(key): value for key, value in chairs.items()}
    teacher_ids = {int(row["teacher"]) for row in rows if row["teacher"].isdigit()}
    names = {user.pk: user.get_full_name() or user.username for user in User.objects.filter(pk__in=teacher_ids)}
    book = Workbook()
    sheet = book.active
    sheet.title = "Kafedra jurnalları"
    sheet_append(sheet, ["chair_name", "teacher_name", *COLUMNS])
    for row in rows:
        teacher = names.get(int(row["teacher"])) if row["teacher"].isdigit() else "—"
        sheet_append(sheet, [chairs.get(row["chair"], ""), teacher, *(row[column] for column in COLUMNS)])
    target = os.path.realpath(os.path.expanduser(path))
    descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        book.save(handle)


__all__ = ["COLUMNS", "ChairHealth", "outside_repo", "resolve_chairs", "totals", "write_table", "write_xlsx"]
