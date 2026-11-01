"""Four fixed own-source proofs: fill only syllabi; never repair course/journal FKs."""

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
        authority="User-authorized current migration approval; legacy approval is not asserted. Only four pinned raw journal catalogue mismatches are accepted: exact full custom title or the pinned official DOCX full-course option with independently verified aggregate/per-group hours, own source subject/author, exact group/term and direct source pointer agree. No journal or course metadata is changed.",
        note="Müəllifin tam jurnal adı, birbaşa mənbə sillabusu və rəsmi yükü ilə təsdiqlənmiş öz sillabusu bərpa olunub.",
        group_id=row["group_id"],
        contact_hours=(units["lecture"], units["seminar"], 0, units["lab"]),
    )


def _official_title(entry, row):
    proof = entry["proof"]
    items = proof["official_row"]["nonpersonal_cells"]
    cells = {str(item["column"]): item["text"] for item in items}
    if (
        proof["official_docx_sha256"] != row["official_docx_sha256"]
        or proof["official_row"]["table_0based"] != 0
        or proof["official_row"]["row_1based"] != 17
        or normalized(proof["official_full_course_title"]) != normalized(row["source_course_title"])
        or proof["raw_subject_options"] != row["official_subject_options"]
        or cells.get("2") != row["official_subject_options"]
    ):
        raise RestoreError("official_source_course_title_scope")
    # The source's printed45 minus lecture15 and zero unrelated hours uniquely
    # verifies seminar30 = two15h contacts; it does not amend the live workload.
    arithmetic = proof["arithmetic"]
    if (
        cells.get("4") != "15"
        or cells.get("5") != "15+2"
        or cells.get("10") != "45"
        or any(cells.get(str(index), "") not in ("", "0") for index in (*range(6, 10), *range(11, 23)))
        or tuple(
            arithmetic[key]
            for key in (
                "lecture_total",
                "printed_fall_total",
                "other_fall_hours",
                "seminar_total",
                "seminar_contact_unit",
                "seminar_contact_multiplier",
            )
        )
        != (15, 45, 0, 30, 15, 2)
        or (row["source_plan_units"], row["row_totals"], row["subgroup_count"], row["hours"], row["credits"])
        != ({"lecture": 15, "seminar": 15, "lab": 0}, {"lecture": 15, "seminar": 30, "lab": 0}, 2, 30, "3")
    ):
        raise RestoreError("official_source_aggregate_per_group_hours_scope")
    if (
        len(cells) != len(items)
        or any(cells.get(key) != value for key, value in row["official_columns"].items())
        or core.digest(proof) != row["official_proof_digest"]
    ):
        raise RestoreError("pinned_official_source_proof_changed")


def _source(entry, row):
    source, journal, lesson = entry["source"], entry["source_journal"], entry["source_lesson"]
    suffix = " - (2026/2027 payız)"
    title = normalized(journal["name"])
    authority = row.get("title_authority", "explicit_full_custom_journal_name")
    if authority == "official_docx_full_course_with_verified_aggregate_hours":
        if journal["name"] != row["source_journal_name"] or not title.endswith(suffix):
            raise RestoreError("source_group_journal_name_scope")
        _official_title(entry, row)
    elif (
        authority != "explicit_full_custom_journal_name"
        or not title.endswith(suffix)
        or title[: -len(suffix)].strip() != normalized(row["source_course_title"])
    ):
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
