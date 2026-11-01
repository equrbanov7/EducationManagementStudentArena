"""Only explicit identities, enum codes, numeric facts, flags and opaque content hashes."""

from apps.syllabus.public import content_fingerprints, syllabus_content_hours

from . import spec

SYLLABUS_FIELDS = (
    "id",
    "organization_id",
    "subject_id",
    "offering_id",
    "period_id",
    "author_id",
    "chair_unit_id",
    "program_id",
    "is_active",
    "current_version_id",
    "approved_version_id",
    "reused_from_id",
    "created_at",
    "updated_at",
)
VERSION_FIELDS = (
    "id",
    "organization_id",
    "syllabus_id",
    "major",
    "minor",
    "status",
    "change_kind",
    "applies_to_period_id",
    "source_version_id",
    "completion_percent",
    "approval_source",
    "approved_by_id",
    "approved_at",
    "locked_at",
    "archived_at",
    "created_by_id",
    "submitted_by_id",
    "submitted_at",
    "reviewer_id",
    "review_started_at",
    "decided_at",
    "created_at",
    "updated_at",
)
OFFERING_FIELDS = (
    "id",
    "organization_id",
    "subject_id",
    "period_id",
    "group_id",
    "instructor_id",
    "lesson_hours",
    "is_active",
)
SHARE_FIELDS = (
    "id",
    "organization_id",
    "syllabus_id",
    "offering_id",
    "source",
    "created_by_id",
    "created_at",
    "updated_at",
)
COHORT_FIELDS = (
    "id",
    "organization_id",
    "offering_id",
    "source_offering_id",
    "period_id",
    "department_id",
    "group_id",
    "lecture_hours",
    "seminar_hours",
    "lab_hours",
)
VERSION_ENUMS = {
    "status": {"draft", "submitted", "review", "revision", "rejected", "approved", "archived"},
    "change_kind": {"initial", "minor", "major", "copied", "imported", "reused"},
    "approval_source": {"human", "migration", "reuse", "auto"},
}


def digest(value):
    # Pure public helper uses the same canonical source-converter serialization.
    import hashlib
    import json

    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=True, default=str).encode()).hexdigest()


def raw_record(obj):
    return {field.attname: getattr(obj, field.attname) for field in obj._meta.concrete_fields}


def fields(obj, names):
    return {name: getattr(obj, name) for name in names}


def hours(value):
    return syllabus_content_hours(value)


def syllabus(obj, body_included):
    return {
        **fields(obj, SYLLABUS_FIELDS),
        "body_included": body_included,
        "plan_hours_override": hours(obj.plan_hours_override),
        "record_sha256": digest(raw_record(obj)),
    }


def version(obj, sections):
    from ..scoped_snapshot import SnapshotError

    for key, allowed in VERSION_ENUMS.items():
        if getattr(obj, key) not in allowed:
            raise SnapshotError("syllabus_version_enum_unknown")
    summary = content_fingerprints({s.section_id: s.data for s in sections})
    result = {
        **fields(obj, VERSION_FIELDS),
        "plan_hours": hours(obj.plan_hours),
        "decision_reason_present": bool(obj.decision_reason),
        "record_sha256": digest(raw_record(obj)),
    }
    result.update(
        {
            k: summary[k]
            for k in (
                "canonical_policy",
                "canonical_body_sha256",
                "course_body_sha256",
                "known_section_count",
                "unknown_section_count",
                "topic_summary",
            )
        }
    )
    section_map = {m["section_key_sha256"]: m for m in summary["sections"]}
    projected = []
    for row in sections:
        projected.append(
            {
                **fields(
                    row,
                    (
                        "id",
                        "organization_id",
                        "version_id",
                        "revision",
                        "is_complete",
                        "updated_by_id",
                        "created_at",
                        "updated_at",
                    ),
                ),
                **section_map[digest(row.section_id)],
                "record_sha256": digest(raw_record(row)),
            }
        )
    topics = [{"organization_id": spec.ORG, "version_id": obj.pk, **m} for m in summary["topics"]]
    return result, projected, topics
