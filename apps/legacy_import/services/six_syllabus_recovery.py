"""Six pinned workload openings: atomic fill-only recovery of four own sources."""

import hashlib
import json
from collections import Counter
from pathlib import Path
from uuid import uuid4

from django.utils import timezone

from . import exact_syllabus_recovery as core
from .delta.syllabi import document_for
from .mr46_syllabus import ORG
from .rehearsal_syllabus_targets import TEXT_TRUNCATED, build_section_data
from .six_syllabus_spec import ROWS

RestoreError = core.RestoreError
RESOURCE = "legacy_import.six_workload_syllabi"


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
        format="six-own-syllabus-evidence/1",
        subject_code=row["subject_code"],
        allowed_owners=(row["author_id"],),
        batch_prefix="wksyl-",
        label="Pinned workload syllabus",
        authority="Own author, exact subject and official workload kind-hours; journal ID 0 means no journal link asserted.",
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
        if package["format"] != "six-own-syllabus-evidence/1":
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


def apply(org, actor, loaded):
    if len(loaded) != len(ROWS) or [s.offering for s, _ in loaded] != [r["offering_id"] for r in ROWS]:
        raise RestoreError("fixed_target_set_required")
    counts, children = Counter(), []
    for spec, source in loaded:
        # Current metadata must still match official total; never amend a workload here.
        offering = core.scope(org, actor, spec)
        if offering.lesson_hours != spec.hours:
            raise RestoreError("live_workload_hours_changed")
        result, child = core.apply(org, actor, source, spec)
        counts.update(result)
        children.append({"offering": spec.offering, "batch": child, "created": bool(result.get("syllabi_created"))})
    batch = f"sixsyl-{timezone.now():%Y%m%d-%H%M%S}-{uuid4().hex[:4]}"
    if counts.get("syllabi_created"):
        core.log_action(
            action=core.AuditAction.UPDATE,
            user=actor,
            organization=org,
            resource_type=RESOURCE,
            resource_id=batch,
            resource_repr=batch,
            reason="Six workload syllabus restore",
            new_values={"children": children},
        )
    return dict(counts), batch


def undo(org, actor, batch):
    logs = core.model("audit.AuditLog").objects.filter(organization=org, resource_type=RESOURCE, resource_id=batch)
    if logs.filter(reason="Six workload syllabus undo").exists():
        return {"already_undone": 1}
    receipt = logs.filter(reason="Six workload syllabus restore").first()
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
        reason="Six workload syllabus undo",
        new_values={"receipt": str(receipt.pk)},
    )
    return dict(counts)
