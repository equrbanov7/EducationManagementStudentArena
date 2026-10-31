"""One pinned Human Genetics opening: fill-only own-author syllabus recovery."""

import hashlib
import json
from collections import Counter
from pathlib import Path
from uuid import uuid4

from django.utils import timezone

from . import exact_syllabus_recovery as core
from .delta.syllabi import document_for
from .genetics_syllabus_spec import ROWS
from .mr46_syllabus import ORG
from .rehearsal_syllabus_targets import TEXT_TRUNCATED, build_section_data

RestoreError = core.RestoreError
RESOURCE = "legacy_import.genetics_workload_syllabus"


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
        journal_lesson=row["source_lesson"],
        source_syllabus=row["source_syllabus_id"],
        source_lesson=row["source_lesson"],
        hours=row["hours"],
        topics=row["topics"],
        selfwork=0,
        format="genetics-own-syllabus-evidence/1",
        subject_code=row["subject_code"],
        allowed_owners=(row["author_id"],),
        batch_prefix="gensrc-",
        label="Pinned Human Genetics workload syllabus",
        authority="User-authorized reviewed current migration approval; legacy approval is not asserted. Exact own author, subject, official workload kind-hours; journal ID 0 asserts no journal link.",
        note="Müəllimin öz köhnə sillabusu fənn və dərs növlərinin saatları üzrə rəsmi yüklə uyğunlaşdırılaraq bərpa olunub.",
        group_id=row["group_id"],
        contact_hours=(units["lecture"], units["seminar"], 0, units["lab"]),
        subject_id=row["subject_id"],
        require_current_period=row["season"] != "spring",
    )


def load(path, expected):
    raw = Path(path).read_bytes()
    if len(raw) > 2000000 or hashlib.sha256(raw).hexdigest() != expected:
        raise RestoreError("plan_digest_mismatch")
    try:
        package = json.loads(raw)
        if package["format"] != "genetics-own-syllabus-evidence/1":
            raise RestoreError("plan_format")
        loaded = []
        for row in ROWS:
            source = package["unique_sources"][str(row["source_syllabus_id"])]
            if core.digest(source) != row["source_digest"]:
                raise RestoreError("pinned_source_changed")
            sections, codes = build_section_data(document_for(source))
            spec = spec_for(row)
            totals = tuple(
                sum(r.get(k, 0) for r in sections["week"]["rows"]) for k in ("lecture", "seminar", "practical", "lab")
            )
            if TEXT_TRUNCATED in codes or totals != spec.contact_hours or len(sections["week"]["rows"]) != spec.topics:
                raise RestoreError("source_content_or_hours_changed")
            loaded.append((spec, ({"source": source}, sections, codes, row["source_digest"])))
        return loaded
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, RestoreError):
            raise
        raise RestoreError("plan_shape") from None


def check_workload(org, spec):
    row_spec = next(row for row in ROWS if row["offering_id"] == spec.offering)
    row = (
        core.model("workload.TeachingTaskRow")
        .objects.select_for_update()
        .filter(
            pk=row_spec["row_id"],
            organization=org,
            subject_id=spec.subject_id,
            period_id=spec.period,
            season="fall",
            task__organization=org,
            task__academic_year="2026/2027",
            groups__id=spec.group_id,
        )
        .first()
    )
    units = row_spec["source_plan_units"]
    if row is None or any(getattr(row, key + "_plan") != units[key] for key in units):
        raise RestoreError("live_official_kind_hours_changed")
    if (
        not core.model("workload.TeacherAssignment")
        .objects.filter(
            organization=org,
            row=row,
            teacher_id=spec.author,
            hours__gt=0,
            activity__in=("lecture", "seminar", "lab"),
        )
        .exists()
    ):
        raise RestoreError("live_workload_assignment_missing")


def apply(org, actor, loaded):
    if len(loaded) != len(ROWS) or [s.offering for s, _ in loaded] != [r["offering_id"] for r in ROWS]:
        raise RestoreError("fixed_target_set_required")
    counts, children = Counter(), []
    for spec, source in loaded:
        # Current metadata must still match official total; never amend a workload here.
        offering = core.scope(org, actor, spec)
        check_workload(org, spec)
        if offering.period.locked_at is not None or not (
            offering.period.start_date <= timezone.localdate() <= offering.period.end_date
        ):
            raise RestoreError("live_period_locked_or_outside_dates")
        if offering.lesson_hours != spec.hours:
            raise RestoreError("live_workload_hours_changed")
        result, child = core.apply(org, actor, source, spec)
        counts.update(result)
        children.append({"offering": spec.offering, "batch": child, "created": bool(result.get("syllabi_created"))})
    batch = f"gensyl-{timezone.now():%Y%m%d-%H%M%S}-{uuid4().hex[:4]}"
    if counts.get("syllabi_created"):
        core.log_action(
            action=core.AuditAction.UPDATE,
            user=actor,
            organization=org,
            resource_type=RESOURCE,
            resource_id=batch,
            resource_repr=batch,
            reason="Human Genetics workload syllabus restore",
            new_values={"children": children},
        )
    return dict(counts), batch


def undo(org, actor, batch):
    logs = core.model("audit.AuditLog").objects.filter(organization=org, resource_type=RESOURCE, resource_id=batch)
    if logs.filter(reason="Human Genetics workload syllabus undo").exists():
        return {"already_undone": 1}
    receipt = logs.filter(reason="Human Genetics workload syllabus restore").first()
    if not receipt:
        raise RestoreError("undo_batch_missing")
    rows = {r["offering_id"]: r for r in ROWS}
    counts = Counter()
    children = receipt.new_values["children"]
    if len(children) != len(ROWS) or {c["offering"] for c in children} != set(rows):
        raise RestoreError("undo_target_set_changed")
    for child in children:
        if not child.get("created"):
            continue
        counts.update(core.undo(org, actor, child["batch"], spec_for(rows[child["offering"]])))
    core.log_action(
        action=core.AuditAction.UPDATE,
        user=actor,
        organization=org,
        resource_type=RESOURCE,
        resource_id=batch,
        resource_repr=batch,
        reason="Human Genetics workload syllabus undo",
        new_values={"receipt": str(receipt.pk)},
    )
    return dict(counts)
