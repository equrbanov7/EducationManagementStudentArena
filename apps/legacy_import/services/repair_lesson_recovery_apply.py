"""J12 təmiri — plan faylının CANLI bazaya tətbiqi (server addımı, mənbəsiz).

Plan lokalda, production-un atılabilən nüsxəsində J12-nin öz kodu ilə qurulur
(``repair_lesson_recovery``).  Bu modul onu canlı bazada TƏKRAR yoxlayır, çünki
nüsxə alınandan sonra canlı data dəyişmiş ola bilər:

* başlıq: təşkilat, snapshot sha256 və hədəfi quran import run-u CANLI bazada
  eyni olmalıdır — başqa bazanın planı fail-closed rədd edilir;
* açılış: ledger-də ``course_offering`` MIGRATED möhürü olmalı və dövrü
  ``LEGACY_CUTOFF``-dan (2026-09-01) ƏVVƏL bitməlidir — 2026/2027 datasına
  TOXUNULMUR; dərs tarixi də kəsimdən əvvəl olmalıdır;
* dərs: eyni pk artıq varsa ``already_present``; eyni təbii açarda
  ``(açılış, tarix, saat)`` başqa dərs varsa ``reuse_existing`` (yeni sətir
  YARADILMIR, xanalar ona bağlanır); qalanı ``create``;
* xana: qeydiyyat yoxdursa / başqa açılışdadırsa atlanır; ``(dərs, qeydiyyat)``
  xanası artıq varsa — eyni dəyər ``already_present``, fərqli dəyər
  ``live_conflict`` (ÜSTÜNDƏN YAZILMIR);
* sübut faktı (``LegacyGradeFact``): eyni ``(cədvəl, pk)`` varsa sübut eyni
  olmalıdır (``already_present``), fərqlidirsə ``live_conflict``.

Müəllim: J12 dərsin müəllimini açılışın CARİ müəllimindən götürür — burada da
eyni qayda canlı açılışla tətbiq olunur; müəllimin ``grade.input`` icazəli aktiv
üzvlüyü yoxdursa (PG ``registrar_guard_active_member`` onu rədd edərdi) sahə
BOŞ qalır və ``instructor_dropped`` kimi sayılır — heç kim uydurulmur.

Yazı: vahid (dərs + onun xanaları / mövcud dərsə xanalar / fakt) dəstələrlə, hər
dəstə öz tranzaksiyasında və RLS kontekstində.  Hər yaradılan dərs, mövcud dərsə
əlavə olunan xanalar və hər fakt üçün ``core.audit.log_action`` yazılır (xana
siyahısı dərsin audit sətrindədir).  Sonda plana düşən bütün qeydiyyatların
``absence_hours``-u J4/J12-nin öz toplu funksiyası ilə yenidən hesablanır və
dəyişən hər qeydiyyat üçün audit yazılır.  İkinci icra: 0 dəyişiklik.
"""

from __future__ import annotations

import datetime
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from decimal import Decimal

from django.apps import apps as django_apps

from apps.legacy_import.models import LegacyEntityMap, LegacyMigrationRun

from . import repair_lesson_recovery as planner
from .rehearsal_journal_marks_targets import recompute_absence_hours
from .rehearsal_journal_offerings_targets import COURSE_OFFERING_ENTITY_TYPE
from .repair_lesson_recovery import AUDIT_REASON, REPAIR_KEY
from .repair_plan_file import RepairPlanError
from .repair_support import scoped_atomic
from .table_plan import SOURCE_SNAPSHOT_SHA256

#: 2026/2027 tədris ilinin başlanğıcı: bu tarixdən sonra bitən dövrə/dərsə yazı YOXDUR.
LEGACY_CUTOFF = datetime.date(2026, 9, 1)
GRADE_INPUT_PERMISSIONS = frozenset({"grade.input", "grading.input", "grade.*", "grading.*", "*"})
UNIT_BATCH = 200
TABLE_HEADERS = ("vahid", "açılış", "tarix", "saat", "xana", "qərar")
_CHUNK = 2_000


@dataclass
class Unit:
    """Bir yazı vahidi: bərpa dərsi (+xanaları), mövcud dərsə xanalar, və ya fakt."""

    kind: str  # lesson | existing_lesson | fact
    record: dict
    action: str = ""
    live_lesson_pk: str = ""
    instructor_id: int | None = None
    marks: list = field(default_factory=list)  # [(mark record, action)]

    def as_row(self):
        if self.kind == "fact":
            return (
                "fakt",
                self.record.get("source_journal_ref", ""),
                "",
                "",
                self.record.get("source_pk"),
                self.action,
            )
        created = sum(1 for _mark, action in self.marks if action == "create")
        return (
            "dərs" if self.kind == "lesson" else "mövcud dərs",
            str(self.record.get("offering_id", ""))[:8],
            self.record.get("date", ""),
            self.record.get("start_time") or "—",
            f"{created}/{len(self.marks)}",
            self.action,
        )


@dataclass
class Decided:
    units: list
    counters: Counter
    enrollment_ids: set


def _chunks(values, size=_CHUNK):
    values = list(values)
    for start in range(0, len(values), size):
        yield values[start : start + size]


def _time(value):
    return None if not value else datetime.time.fromisoformat(value)


def _lesson_key(offering_id, date, start_time):
    return (
        str(offering_id),
        date if isinstance(date, datetime.date) else datetime.date.fromisoformat(date),
        start_time,
    )


def validate_header(organization, header: dict) -> LegacyMigrationRun:
    """Plan MƏHZ bu bazanın (bu tenant + bu import run-u) nüsxəsindən qurulubmu?"""

    if header.get("repair") != REPAIR_KEY:
        raise RepairPlanError("legacy_repair_plan_repair_mismatch")
    if str(header.get("organization_id")) != str(organization.pk):
        raise RepairPlanError("legacy_repair_plan_organization_mismatch")
    if header.get("source_snapshot_sha256") != SOURCE_SNAPSHOT_SHA256:
        raise RepairPlanError("legacy_repair_plan_snapshot_mismatch")
    run = LegacyMigrationRun.objects.filter(
        pk=header.get("source_run_id"),
        organization=organization,
        status__in=planner.SOURCE_RUN_STATUSES,
        snapshot_sha256=SOURCE_SNAPSHOT_SHA256,
    ).first()
    if run is None:
        raise RepairPlanError("legacy_repair_plan_source_run_unknown")
    return run


def _legacy_offerings(organization, offering_ids) -> dict[str, int | None]:
    """Canlı LEGACY açılışlar: ledger MIGRATED + dövr kəsimdən ƏVVƏL bitir → müəllim."""

    offering_model = django_apps.get_model("registrar", "CourseOffering")
    wanted = sorted({str(pk) for pk in offering_ids})
    migrated: set[str] = set()
    live: dict[str, int | None] = {}
    for chunk in _chunks(wanted):
        migrated.update(
            LegacyEntityMap.objects.filter(
                organization=organization,
                entity_type=COURSE_OFFERING_ENTITY_TYPE,
                state=LegacyEntityMap.State.MIGRATED,
                target_pk__in=chunk,
            ).values_list("target_pk", flat=True)
        )
        for pk, instructor_id, period_end in offering_model.objects.filter(
            organization=organization, pk__in=chunk
        ).values_list("pk", "instructor_id", "period__end_date"):
            if str(pk) in migrated and period_end is not None and period_end < LEGACY_CUTOFF:
                live[str(pk)] = instructor_id
    return live


def grade_input_users(organization, user_ids) -> set[int]:
    """``registrar_member_has_permission(org, user, 'grade.input')``-in Python güzgüsü."""

    membership_model = django_apps.get_model("organizations", "Membership")
    allowed: set[int] = set()
    rows = membership_model.objects.filter(
        organization=organization,
        user_id__in=sorted({pk for pk in user_ids if pk is not None}),
        is_active=True,
        role__is_active=True,
        role__organization=organization,
        user__is_active=True,
    ).values_list("user_id", "role__permissions")
    for user_id, permissions in rows:
        if GRADE_INPUT_PERMISSIONS & set(permissions or ()):
            allowed.add(user_id)
    return allowed


def _existing_lessons(organization, offering_ids):
    lesson_model = django_apps.get_model("registrar", "Lesson")
    by_pk: dict[str, tuple] = {}
    by_key: dict[tuple, str] = {}
    for chunk in _chunks(sorted(offering_ids)):
        rows = lesson_model.objects.filter(organization=organization, offering_id__in=chunk).values_list(
            "pk", "offering_id", "date", "start_time"
        )
        for pk, offering_id, date, start_time in rows.iterator(chunk_size=10_000):
            key = _lesson_key(offering_id, date, start_time)
            by_pk[str(pk)] = key
            by_key.setdefault(key, str(pk))
    return by_pk, by_key


def _existing_marks(organization, lesson_pks) -> dict[tuple[str, str], tuple[str, object]]:
    mark_model = django_apps.get_model("registrar", "LessonMark")
    found: dict[tuple[str, str], tuple[str, object]] = {}
    for chunk in _chunks(sorted(lesson_pks)):
        rows = mark_model.objects.filter(organization=organization, lesson_id__in=chunk).values_list(
            "lesson_id", "enrollment_id", "status", "score"
        )
        for lesson_id, enrollment_id, status, score in rows.iterator(chunk_size=10_000):
            found[(str(lesson_id), str(enrollment_id))] = (status, score)
    return found


def _enrollment_offerings(organization, enrollment_ids) -> dict[str, str]:
    enrollment_model = django_apps.get_model("registrar", "Enrollment")
    found: dict[str, str] = {}
    for chunk in _chunks(sorted(enrollment_ids)):
        for pk, offering_id in enrollment_model.objects.filter(organization=organization, pk__in=chunk).values_list(
            "pk", "offering_id"
        ):
            found[str(pk)] = str(offering_id)
    return found


def _same_score(stored, incoming) -> bool:
    if stored is None or incoming is None:
        return stored is None and incoming is None
    return Decimal(stored) == Decimal(incoming)


def _decide_lesson(unit, *, legacy, by_pk, by_key, permitted, counters):
    record = unit.record
    offering_id = record["offering_id"]
    if offering_id not in legacy:
        return "skip_offering_not_legacy"
    if datetime.date.fromisoformat(record["date"]) >= LEGACY_CUTOFF:
        return "skip_date_after_cutoff"
    key = _lesson_key(offering_id, record["date"], _time(record["start_time"]))
    if record["pk"] in by_pk:
        if by_pk[record["pk"]] != key:
            raise RepairPlanError("legacy_repair_plan_lesson_pk_collision")
        unit.live_lesson_pk = record["pk"]
        return "already_present"
    if key in by_key:
        unit.live_lesson_pk = by_key[key]
        return "reuse_existing"
    unit.live_lesson_pk = record["pk"]
    live_instructor = legacy[offering_id]
    if live_instructor != record.get("instructor_id"):
        counters["  müəllim canlı açılışdan götürüldü"] += 1
    if live_instructor is not None and live_instructor not in permitted:
        counters["  instructor_dropped (icazəsiz müəllim → boş)"] += 1
        live_instructor = None
    unit.instructor_id = live_instructor
    return "create"


def _decide_mark(mark, *, live_lesson_pk, lesson_offering, enrollments, existing):
    offering_id = enrollments.get(mark["enrollment_id"])
    if offering_id is None:
        return "skip_enrollment_missing"
    if offering_id != lesson_offering:
        return "skip_offering_mismatch"
    stored = existing.get((live_lesson_pk, mark["enrollment_id"]))
    if stored is None:
        return "create"
    same = stored[0] == mark["status"] and _same_score(stored[1], mark["score"])
    return "already_present" if same else "live_conflict"


def _decide_facts(organization, facts, enrollments, legacy) -> list[Unit]:
    fact_model = django_apps.get_model("registrar", "LegacyGradeFact")
    existing: dict[tuple[str, int], object] = {}
    keys = {(fact["source_table"], fact["source_pk"]) for fact in facts}
    systems = {fact["source_system"] for fact in facts}
    for source_table in sorted({table for table, _pk in keys}):
        pks = sorted(pk for table, pk in keys if table == source_table)
        for chunk in _chunks(pks):
            for row in fact_model.objects.filter(
                organization=organization,
                source_system__in=systems,
                source_table=source_table,
                source_pk__in=chunk,
            ).only("source_table", "source_pk", "source_row_hash", "raw_score_text", "materialization_digest"):
                existing[(row.source_table, row.source_pk)] = row
    units = []
    for fact in facts:
        unit = Unit(kind="fact", record=fact)
        row = existing.get((fact["source_table"], fact["source_pk"]))
        if row is not None:
            same = (
                row.source_row_hash == fact["source_row_hash"]
                and row.raw_score_text == fact["raw_score_text"]
                and row.materialization_digest == fact["materialization_digest"]
            )
            unit.action = "already_present" if same else "live_conflict"
        elif fact.get("enrollment_id") and fact["enrollment_id"] not in enrollments:
            unit.action = "skip_enrollment_missing"
        elif fact.get("enrollment_id") and enrollments[fact["enrollment_id"]] not in legacy:
            unit.action = "skip_offering_not_legacy"
        else:
            unit.action = "create"
        units.append(unit)
    return units


def decide(organization, plan, *, limit: int = 0) -> Decided:
    """Canlı bazaya qarşı TAM qərar (yazısız) — dry-run və apply eyni yolu gedir."""

    validate_header(organization, plan.header)
    lessons = plan.of("lesson")
    marks_by_lesson: dict[str, list] = defaultdict(list)
    for mark in plan.of("mark"):
        marks_by_lesson[mark["lesson_id"]].append(mark)
    planned = {record["pk"] for record in lessons}
    if len(planned) != len(lessons):
        raise RepairPlanError("legacy_repair_plan_lesson_duplicate")
    units = [Unit(kind="lesson", record=record, marks=marks_by_lesson.get(record["pk"], [])) for record in lessons]
    units += [
        Unit(kind="existing_lesson", record={"pk": lesson_pk}, marks=marks)
        for lesson_pk, marks in sorted(marks_by_lesson.items())
        if lesson_pk not in planned
    ]
    enrollment_ids = {mark["enrollment_id"] for mark in plan.of("mark")}
    enrollment_ids |= {fact["enrollment_id"] for fact in plan.of("fact") if fact.get("enrollment_id")}
    enrollments = _enrollment_offerings(organization, enrollment_ids)
    offering_ids = {record["offering_id"] for record in lessons} | set(enrollments.values())
    legacy = _legacy_offerings(organization, offering_ids)
    by_pk, by_key = _existing_lessons(organization, legacy.keys())
    permitted = grade_input_users(organization, legacy.values())
    counters: Counter = Counter()
    for unit in units:
        if unit.kind == "lesson":
            unit.action = _decide_lesson(
                unit, legacy=legacy, by_pk=by_pk, by_key=by_key, permitted=permitted, counters=counters
            )
        else:
            key = by_pk.get(unit.record["pk"])
            unit.live_lesson_pk = unit.record["pk"] if key is not None else ""
            unit.record.update({"offering_id": key[0], "date": key[1].isoformat()} if key else {})
            unit.action = "attach" if key is not None and key[0] in legacy else "skip_lesson_missing"
    existing = _existing_marks(
        organization, {unit.live_lesson_pk for unit in units if unit.live_lesson_pk and unit.action != "create"}
    )
    for unit in units:
        lesson_offering = by_pk.get(unit.live_lesson_pk, (unit.record.get("offering_id"),))[0]
        writable = unit.action in ("create", "already_present", "reuse_existing", "attach")
        unit.marks = [
            (
                mark,
                (
                    _decide_mark(
                        mark,
                        live_lesson_pk=unit.live_lesson_pk,
                        lesson_offering=lesson_offering,
                        enrollments=enrollments,
                        existing=existing,
                    )
                    if writable
                    else "skip_lesson_" + unit.action
                ),
            )
            for mark in unit.marks
        ]
    units += _decide_facts(organization, plan.of("fact"), enrollments, legacy)
    if limit:
        units = units[:limit]
    for unit in units:
        counters[f"{unit.kind}:{unit.action}"] += 1
        for mark, action in unit.marks:
            counters[f"mark:{action}"] += 1
            if action == "create":
                counters[f"  yeni xana · {mark['status']}{' (bal)' if mark['score'] is not None else ''}"] += 1
    touched = {mark["enrollment_id"] for unit in units for mark, action in unit.marks if action == "create"}
    return Decided(units=units, counters=counters, enrollment_ids=touched)


def _lesson_row(organization, unit):
    record = unit.record
    return django_apps.get_model("registrar", "Lesson")(
        pk=record["pk"],
        organization=organization,
        offering_id=record["offering_id"],
        date=datetime.date.fromisoformat(record["date"]),
        start_time=_time(record["start_time"]),
        end_time=_time(record.get("end_time")),
        kind=record["lesson_kind"],
        hours=int(record["hours"]),
        topic=record.get("topic") or "",
        room_id=record.get("room_id"),
        instructor_id=unit.instructor_id,
        created_by=None,
        is_legacy_synthesised=True,
    )


def _fact_row(organization, record):
    values = {key: value for key, value in record.items() if key != "kind"}
    for key in ("entry_score", "exam_score", "resit_score", "final_score"):
        if values.get(key) is not None:
            values[key] = Decimal(values[key])
    return django_apps.get_model("registrar", "LegacyGradeFact")(organization=organization, **values)


def _write_units(context, units, *, plan_sha256) -> Counter:
    from core.audit import log_action
    from core.constants import AuditAction

    organization, actor = context.organization, context.actor
    mark_model = django_apps.get_model("registrar", "LessonMark")
    fact_model = django_apps.get_model("registrar", "LegacyGradeFact")
    written: Counter = Counter()
    lessons = [
        (_lesson_row(organization, unit), unit) for unit in units if unit.kind == "lesson" and unit.action == "create"
    ]
    facts = [
        (_fact_row(organization, unit.record), unit)
        for unit in units
        if unit.kind == "fact" and unit.action == "create"
    ]
    marks, audited = [], []
    for unit in units:
        created = [(mark, action) for mark, action in unit.marks if action == "create"]
        for mark, _action in created:
            marks.append(
                mark_model(
                    organization=organization,
                    lesson_id=unit.live_lesson_pk,
                    enrollment_id=mark["enrollment_id"],
                    status=mark["status"],
                    score=None if mark["score"] is None else Decimal(mark["score"]),
                    entered_by=None,
                )
            )
        if created:
            audited.append((unit, created))
    if lessons:
        django_apps.get_model("registrar", "Lesson").objects.bulk_create([row for row, _unit in lessons])
    if marks:
        mark_model.objects.bulk_create(marks)
    if facts:
        fact_model.objects.bulk_create([row for row, _unit in facts])
    lesson_rows = {str(row.pk): row for row, _unit in lessons}
    for unit, created in audited:
        new_lesson = lesson_rows.get(unit.live_lesson_pk)
        log_action(
            action=AuditAction.CREATE if new_lesson is not None else AuditAction.UPDATE,
            user=actor,
            organization=organization,
            obj=new_lesson,
            resource_type="registrar.Lesson",
            resource_id=unit.live_lesson_pk,
            reason=f"{AUDIT_REASON}: {'bərpa dərsi' if new_lesson is not None else 'mövcud dərsə xana'}",
            new_values={
                "plan_sha256": plan_sha256,
                "offering_id": unit.record.get("offering_id"),
                "date": unit.record.get("date"),
                "start_time": unit.record.get("start_time"),
                "seal_key": unit.record.get("seal_key", ""),
                "is_legacy_synthesised": new_lesson is not None,
                "marks": [[mark["enrollment_id"], mark["status"], mark["score"]] for mark, _action in created],
            },
        )
    for row, _unit in facts:
        log_action(
            action=AuditAction.CREATE,
            user=actor,
            organization=organization,
            obj=row,
            reason=f"{AUDIT_REASON}: sübut faktı ({row.mapping_status})",
            new_values={
                "plan_sha256": plan_sha256,
                "source": f"{row.source_table}#{row.source_pk}",
                "enrollment_id": None if row.enrollment_id is None else str(row.enrollment_id),
                "raw_score_text": row.raw_score_text,
            },
        )
    written["dərs yaradıldı"] += len(lessons)
    written["xana yaradıldı"] += len(marks)
    written["fakt yaradıldı"] += len(facts)
    return written


def recompute_and_audit_absence(context, enrollment_ids, *, plan_sha256) -> int:
    """Plana düşən qeydiyyatların ``absence_hours``-u — J4/J12-nin öz toplu funksiyası."""

    from core.audit import log_action
    from core.constants import AuditAction

    enrollment_model = django_apps.get_model("registrar", "Enrollment")
    changed = 0
    for chunk in _chunks(sorted(enrollment_ids), 1_000):
        with scoped_atomic(context):
            before = dict(enrollment_model.objects.filter(pk__in=chunk).values_list("pk", "absence_hours"))
            recompute_absence_hours(context, chunk)
            after = dict(enrollment_model.objects.filter(pk__in=chunk).values_list("pk", "absence_hours"))
            for pk, hours in sorted(after.items(), key=lambda item: str(item[0])):
                if before.get(pk) == hours:
                    continue
                changed += 1
                log_action(
                    action=AuditAction.UPDATE,
                    user=context.actor,
                    organization=context.organization,
                    resource_type="registrar.Enrollment",
                    resource_id=str(pk),
                    reason=f"{AUDIT_REASON}: absence_hours yenidən hesablandı",
                    old_values={"absence_hours": before.get(pk)},
                    new_values={"absence_hours": hours, "plan_sha256": plan_sha256},
                )
    return changed


def apply_decided(context, decided: Decided, *, plan, plan_sha256: str) -> Counter:
    """Qərarları dəstə-dəstə yaz; sonra qayıb saatı; sonda xülasə audit sətri."""

    from core.audit import log_action
    from core.constants import AuditAction

    written: Counter = Counter()
    for start in range(0, len(decided.units), UNIT_BATCH):
        with scoped_atomic(context):
            written.update(_write_units(context, decided.units[start : start + UNIT_BATCH], plan_sha256=plan_sha256))
    every_enrollment = {mark["enrollment_id"] for mark in plan.of("mark")}
    written["absence_hours dəyişdi"] = recompute_and_audit_absence(context, every_enrollment, plan_sha256=plan_sha256)
    if not any(written.values()):
        return written  # təkrar icra: heç nə dəyişmədi → audit izi də yoxdur (idempotent)
    with scoped_atomic(context):
        log_action(
            action=AuditAction.UPDATE,
            user=context.actor,
            organization=context.organization,
            resource_type="legacy_import.repair",
            resource_id=plan_sha256,
            reason=f"{AUDIT_REASON}: xülasə",
            new_values={
                "plan_sha256": plan_sha256,
                "source_run_id": plan.header.get("source_run_id"),
                "planning_run_id": plan.header.get("planning_run_id"),
                "code_revision": plan.header.get("code_revision"),
                "written": dict(sorted(written.items())),
                "decisions": dict(sorted(decided.counters.items())),
            },
        )
    return written


__all__ = [
    "GRADE_INPUT_PERMISSIONS",
    "LEGACY_CUTOFF",
    "TABLE_HEADERS",
    "Decided",
    "Unit",
    "apply_decided",
    "decide",
    "grade_input_users",
    "recompute_and_audit_absence",
    "validate_header",
]
