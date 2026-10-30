"""MR112: Nuray's exact QKU-1150 draft, official row69 30M/15S correction."""

import copy
import hashlib
import json

from django.apps import apps
from django.db import transaction

from core.audit import log_action
from core.constants import AuditAction

from ..models import Syllabus, SyllabusVersion
from .drafts import save_section, section_data_map
from .scoping import resolve_actor
from .workflow import submit

VERSION = "acc523da-1758-458e-87fa-79f93df45efa"
SYLLABUS = "1aef04a2-67cc-4957-8a14-592751843b36"
AUTHOR = "nuray.ismayilzade3"
SOURCE_SHA = "99f45965b5bf00579e0a84e9845131393452666a2ecb0f2e6723baafb6d1418c"


class RepairError(ValueError):
    pass


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


def corrected_week(data):
    result = copy.deepcopy(data)
    rows = result.get("rows")
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise RepairError("expected_15_topics")
    filled = [row for row in rows if str(row.get("topic", "")).strip()]
    empty = [row for row in rows if not str(row.get("topic", "")).strip()]
    if len(filled) != 15 or any(
        any(row.get(k, 0) for k in ("lecture", "seminar", "lab", "practical")) for row in empty
    ):
        raise RepairError("expected_15_topics")
    if any(
        not str(row.get("topic", "")).strip()
        or row.get("lecture") != 2
        or row.get("seminar") != 2
        or any(row.get(key, 0) for key in ("lab", "practical"))
        for row in filled
    ):
        raise RepairError("topic_hour_shape_changed")
    for row in filled:
        row["seminar"] = 1
    return result


def _state(version):
    syllabus = version.syllabus
    return {
        "version": {field.attname: getattr(version, field.attname) for field in version._meta.concrete_fields},
        "syllabus": {field.attname: getattr(syllabus, field.attname) for field in syllabus._meta.concrete_fields},
        "sections": list(version.sections.order_by("pk").values()),
    }


def _academic_state(syllabus):
    offering_id = syllabus.offering_id
    if not offering_id:
        raise RepairError("offering_missing")
    result = {}
    for label, scope in (
        ("registrar.Lesson", {"offering_id": offering_id}),
        ("registrar.Enrollment", {"offering_id": offering_id}),
        ("registrar.LessonMark", {"lesson__offering_id": offering_id}),
    ):
        query = apps.get_model(label).objects.filter(organization_id=syllabus.organization_id, **scope)
        result[label] = list(query.select_for_update(of=("self",)).order_by("pk").values())
    return result


@transaction.atomic
def run(*, organization, user, apply=False, expected_baseline=""):
    if not user.is_active or not user.is_superuser:
        raise RepairError("active_superadmin_required")
    version = (
        SyllabusVersion.objects.select_for_update(of=("self",))
        .select_related("syllabus", "syllabus__author", "syllabus__subject", "organization")
        .get(pk=VERSION, organization=organization, syllabus_id=SYLLABUS)
    )
    syllabus = version.syllabus
    Syllabus.objects.select_for_update().get(pk=syllabus.pk, organization=organization)
    if syllabus.author.username != AUTHOR or syllabus.subject.code != "QKU-1150" or not syllabus.is_active:
        raise RepairError("identity_changed")
    list(version.sections.select_for_update().order_by("pk"))
    data = section_data_map(version)
    week = data.get("week", {})
    if version.status == "approved" and syllabus.approved_version_id == version.pk:
        if len([r for r in week.get("rows", []) if str(r.get("topic", "")).strip()]) == 15 and all(
            row.get("lecture") == 2 and row.get("seminar") == 1
            for row in week["rows"]
            if str(row.get("topic", "")).strip()
        ):
            return {"already_present": 1}
        raise RepairError("approved_content_changed")
    if version.status != "draft" or version.plan_hours.get("lecture") != 30 or version.plan_hours.get("seminar") != 15:
        raise RepairError("draft_or_official_plan_changed")
    changed = corrected_week(week)
    academic = _academic_state(syllabus)
    baseline = digest({"syllabus": _state(version), "academic": academic})
    result = {"baseline": baseline, "topics": 15, "before": [30, 30], "after": [30, 15], "source_sha": SOURCE_SHA}
    if not apply:
        return result
    if not expected_baseline or expected_baseline != baseline:
        raise RepairError("baseline_changed")
    actor = resolve_actor(syllabus.author, organization)
    section = version.sections.get(section_id="week")
    _, report = save_section(
        version=version, section_id="week", data=changed, actor=actor, expected_revision=section.revision
    )
    version.refresh_from_db()
    if version.completion_percent != 100:
        raise RepairError("remaining_completion_errors:" + ",".join(issue.code for issue in report.issues))
    version = submit(version=version, actor=actor)
    version.refresh_from_db()
    if version.status != "approved":
        raise RepairError("automatic_approval_not_enabled")
    after = section_data_map(version)
    expected = copy.deepcopy(data)
    expected["week"] = changed
    if _academic_state(syllabus) != academic:
        raise RepairError("academic_content_changed")
    if after != expected:
        raise RepairError("unexpected_section_change")
    log_action(
        AuditAction.UPDATE,
        user=user,
        organization=organization,
        resource_type="syllabus.mr112_repair",
        resource_id=str(version.pk),
        reason="MR112 official row69 30M15S; teacher-requested draft correction",
        old_values={"baseline": baseline},
        new_values={"source_sha": SOURCE_SHA, "before": [30, 30], "after": [30, 15]},
    )
    return {**result, "applied": 1}
