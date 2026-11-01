"""Two full-name source proofs: fill only own syllabi; never repair course/journal FKs."""

import hashlib
import html
import json
import re
import unicodedata
from collections import Counter
from pathlib import Path
from uuid import uuid4

from django.db import transaction
from django.utils import timezone

from . import exact_syllabus_recovery as core
from .delta.syllabi import document_for
from .mr46_syllabus import ORG
from .named_syllabus_spec import ROWS
from .rehearsal_syllabus_targets import TEXT_TRUNCATED, build_section_data
from .syllabus_migration_contracts import SYLLABUS_SECTION_CONTRACTS

RestoreError = core.RestoreError
RESOURCE = "legacy_import.named_workload_syllabi"
FORMAT = "named-own-syllabus-evidence/1"


def _active_scope(org, actor):
    if (
        str(org.pk) != ORG
        or not org.is_active
        or org.status != "active"
        or not actor.is_active
        or not actor.is_superuser
    ):
        raise RestoreError("actor_or_tenant_scope")


def normalized(value):
    text = unicodedata.normalize("NFKC", html.unescape(str(value)))
    return re.sub(r"\s+", " ", text.translate(str.maketrans({"I": "ı", "İ": "i"})).casefold()).strip()


def spec_for(row):
    units = row["source_plan_units"]
    return core.RecoverySpec(
        organization=ORG,
        period=row["period_id"],
        offering=row["offering_id"],
        author=row["author_id"],
        uniqid=row["uniqid"],
        resource=RESOURCE + "." + row["offering_id"],
        journal=row["journal_id"],
        source_author=row["source_author"],
        journal_lesson=row["journal_lesson"],
        source_syllabus=row["source_syllabus_id"],
        source_lesson=row["source_lesson"],
        hours=row["hours"],
        topics=row["topics"],
        selfwork=row["selfwork_rows"],
        selfwork_topics=row["selfwork_topics"],
        format=FORMAT,
        subject_code=row["subject_code"],
        subject_id=row["subject_id"],
        allowed_owners=(row["author_id"],),
        batch_prefix="namesrc-",
        label="Pinned full-name own syllabus",
        authority="User-authorized current migration approval; legacy approval is not asserted. Only the two pinned raw journal catalogue mismatches are accepted: explicit full custom course name, own source subject/author, exact group/term, direct source pointer and official contact hours/credit agree. No journal or course metadata is changed.",
        note="Müəllifin tam jurnal adı, birbaşa mənbə sillabusu və rəsmi yükü ilə təsdiqlənmiş öz sillabusu bərpa olunub.",
        group_id=row["group_id"],
        contact_hours=(units["lecture"], units["seminar"], 0, units["lab"]),
    )


def _source(entry, row):
    source, journal, lesson = entry["source"], entry["source_journal"], entry["source_lesson"]
    suffix = " - (2026/2027 payız)"
    title = normalized(journal["name"])
    if not title.endswith(suffix) or title[: -len(suffix)].strip() != normalized(row["source_course_title"]):
        raise RestoreError("source_full_custom_course_name_scope")
    if normalized(lesson["name"]) != normalized(row["source_course_title"]):
        raise RestoreError("source_lesson_full_name_scope")
    if (
        journal["id"],
        journal["teacher_id"],
        journal["lesson_id"],
        journal["sillabus_id"],
        journal["semestr"],
        journal["active"],
        journal["fake"],
        journal["sonra_sil"],
        str(journal["fenn_saati"]),
        str(journal["kredit"]),
    ) != (
        row["journal_id"],
        row["source_author"],
        row["journal_lesson"],
        row["source_syllabus_id"],
        14,
        1,
        0,
        0,
        str(row["hours"]),
        row["credits"],
    ) or sorted(
        map(str, json.loads(journal["groups_id"]))
    ) != row[
        "source_group_ids"
    ]:
        raise RestoreError("journal_source_scope")
    for value, key in ((source, "source_digest"), (journal, "journal_digest"), (lesson, "source_lesson_digest")):
        if core.digest(value) != row[key]:
            raise RestoreError("pinned_" + key + "_changed")
    if set(source["sections"]) != set(SYLLABUS_SECTION_CONTRACTS):
        raise RestoreError("complete_twelve_table_source_required")
    if (
        source["id"],
        source["teacher_id"],
        source["lesson_id"],
        source["uniqid"],
        source["ders_saati"],
        source["active"],
    ) != (
        row["source_syllabus_id"],
        row["source_author"],
        row["source_lesson"],
        row["uniqid"],
        row["hours"],
        1,
    ) or lesson[
        "id"
    ] != row[
        "source_lesson"
    ]:
        raise RestoreError("syllabus_source_scope")
    if (
        len(source["week"]) != row["topics"]
        or len({r["id"] for r in source["week"]}) != row["topics"]
        or any(r["uniqid"] != row["uniqid"] for r in source["week"])
        or len(source["sections"]["sillabus_serbest_is"]) != row["selfwork_rows"]
    ):
        raise RestoreError("complete_week_and_selfwork_source_required")
    sections, codes = build_section_data(document_for(source))
    if TEXT_TRUNCATED in codes or core.digest(sections) != row["converted_content_digest"]:
        raise RestoreError("source_content_conversion_changed")
    spec = spec_for(row)
    units = tuple(
        sum(r.get(k, 0) for r in sections["week"]["rows"]) for k in ("lecture", "seminar", "practical", "lab")
    )
    if units != spec.contact_hours or len(sections["self"]["topics"]) != spec.selfwork_topics:
        raise RestoreError("source_hours_or_selfwork_changed")
    return spec, sections, codes


def load(path, expected):
    raw = Path(path).read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    if len(raw) > 2000000 or sha != expected:
        raise RestoreError("plan_digest_mismatch")
    try:
        package = json.loads(raw)
        if package["format"] != FORMAT or set(package["entries"]) != {row["offering_id"] for row in ROWS}:
            raise RestoreError("fixed_source_target_set_required")
        loaded = []
        for row in ROWS:
            entry = package["entries"][row["offering_id"]]
            spec, sections, codes = _source(entry, row)
            loaded.append((spec, (entry, sections, codes, sha)))
        return loaded
    except RestoreError:
        raise
    except (KeyError, TypeError, ValueError, AttributeError):
        raise RestoreError("plan_shape") from None


def check_workload(org, spec):
    pinned = next(row for row in ROWS if row["offering_id"] == spec.offering)
    row = (
        core.model("workload.TeachingTaskRow")
        .objects.select_for_update()
        .select_related("task")
        .get(
            pk=pinned["row_id"],
            organization=org,
            task_id=pinned["task_id"],
            task__organization=org,
            subject_id=spec.subject_id,
            period_id=spec.period,
        )
    )
    checks = {
        "season": "fall",
        "row_kind": "teaching",
        "credits": pinned["credits"],
        "degree_level": pinned["degree_level"],
        "education_form": pinned["education_form"],
        "total_hours": pinned["row_total_hours"],
        "union_count": pinned["union_count"],
        "subgroup_count": pinned["subgroup_count"],
    }
    checks.update({k + "_plan": v for k, v in pinned["source_plan_units"].items()})
    checks.update({k + "_total": v for k, v in pinned["row_totals"].items()})
    if (
        any(getattr(row, key) != value for key, value in checks.items())
        or (row.task.academic_year != "2026/2027" or row.task.status not in ("approved", "distributed", "amended"))
        or sorted(map(str, row.groups.values_list("pk", flat=True))) != pinned["row_group_ids"]
    ):
        raise RestoreError("live_official_workload_scope_changed")
    assignments = list(
        core.model("workload.TeacherAssignment").objects.select_for_update().filter(row=row, organization=org)
    )
    projection = [
        {k: getattr(a, k) for k in ("teacher_id", "activity", "hours", "is_hourly_paid")} for a in assignments
    ]

    def order(a):
        return str(a["teacher_id"]), a["activity"], a["hours"]

    if sorted(projection, key=order) != sorted(pinned["assignments"], key=order):
        raise RestoreError("live_workload_assignment_changed")
    return core.digest(
        {
            "row": core.metadata_digest(row),
            "groups": pinned["row_group_ids"],
            "assignments": [core.metadata_digest(a) for a in sorted(assignments, key=lambda a: str(a.pk))],
        }
    )


@transaction.atomic
def apply(org, actor, loaded):
    _active_scope(org, actor)
    if [spec.offering for spec, _ in loaded] != [row["offering_id"] for row in ROWS]:
        raise RestoreError("fixed_target_set_required")
    counts, children = Counter(), []
    for spec, entry in loaded:
        offering = core.scope(org, actor, spec)
        fingerprint = core.metadata_digest(offering)
        workload = check_workload(org, spec)
        if (
            offering.period.locked_at
            or not offering.period.start_date <= timezone.localdate() <= offering.period.end_date
        ):
            raise RestoreError("live_period_locked_or_outside_dates")
        if offering.lesson_hours != spec.hours or normalized(offering.subject.name) != normalized(
            next(r["source_course_title"] for r in ROWS if r["offering_id"] == spec.offering)
        ):
            raise RestoreError("live_course_title_or_contact_hours_changed")
        result, batch = core.apply(org, actor, entry, spec)
        offering.refresh_from_db()
        if core.metadata_digest(offering) != fingerprint or check_workload(org, spec) != workload:
            raise RestoreError("course_or_workload_metadata_changed")
        counts.update(result)
        children.append({"offering": spec.offering, "batch": batch, "created": bool(result.get("syllabi_created"))})
    batch = f"namesyl-{timezone.now():%Y%m%d-%H%M%S}-{uuid4().hex[:4]}"
    if counts.get("syllabi_created"):
        core.log_action(
            action=core.AuditAction.UPDATE,
            user=actor,
            organization=org,
            resource_type=RESOURCE,
            resource_id=batch,
            resource_repr=batch,
            reason="Named own syllabus restore",
            new_values={
                "children": children,
                "source_journal_hashes": {r["offering_id"]: r["journal_digest"] for r in ROWS},
            },
        )
    return dict(counts), batch


@transaction.atomic
def undo(org, actor, batch):
    _active_scope(org, actor)
    logs = core.model("audit.AuditLog").objects.filter(organization=org, resource_type=RESOURCE, resource_id=batch)
    if logs.filter(reason="Named own syllabus undo").exists():
        return {"already_undone": 1}
    receipt = logs.filter(reason="Named own syllabus restore").first()
    if not receipt:
        raise RestoreError("undo_batch_missing")
    children = receipt.new_values["children"]
    rows = {row["offering_id"]: row for row in ROWS}
    if len(children) != len(ROWS) or {child["offering"] for child in children} != set(rows):
        raise RestoreError("undo_target_set_changed")
    counts = Counter()
    for child in children:
        if child["created"]:
            spec = spec_for(rows[child["offering"]])
            check_workload(org, spec)
            counts.update(core.undo(org, actor, child["batch"], spec))
    core.log_action(
        action=core.AuditAction.UPDATE,
        user=actor,
        organization=org,
        resource_type=RESOURCE,
        resource_id=batch,
        resource_repr=batch,
        reason="Named own syllabus undo",
        new_values={"receipt": str(receipt.pk)},
    )
    return dict(counts)
