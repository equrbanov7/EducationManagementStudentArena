"""Sabit kod müqaviləsi ilə dəqiq mənbə sillabusunun auditli bərpa nüvəsi."""

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from django.apps import apps
from django.utils import timezone

from apps.audit.public import log_action
from apps.registrar.public import eligible_instructor_user_ids
from apps.syllabus.public import (
    import_migrated_version,
    resolve_actor,
    section_data_map,
    services,
    syllabus_for_offering,
)
from core.constants import AuditAction

from .delta.syllabi import document_for
from .rehearsal_syllabus_targets import TEXT_TRUNCATED, build_section_data
from .syllabus_migration_contracts import SYLLABUS_SECTION_CONTRACTS


@dataclass(frozen=True)
class RecoverySpec:
    organization: str
    period: str
    offering: str
    author: int
    uniqid: str
    resource: str
    journal: int
    source_author: int
    journal_lesson: int
    source_syllabus: int
    source_lesson: int
    hours: int
    topics: int
    selfwork: int
    format: str
    subject_code: str
    allowed_owners: tuple
    batch_prefix: str
    label: str
    authority: str
    note: str
    group_id: str = ""
    contact_hours: tuple = ()
    selfwork_topics: int | None = None
    optional_empty_sections: tuple = ()

    @property
    def restore_reason(self):
        return f"{self.label} source syllabus restore"

    @property
    def undo_reason(self):
        return f"{self.label} source syllabus undo"


class RestoreError(ValueError):
    pass


def digest(data):
    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=True, default=str).encode()).hexdigest()


def metadata_digest(obj):
    """Auditdə yalnız hash: saatlar, göstəricilər və müəllif/status metadatası da qorunur."""
    return digest({field.attname: getattr(obj, field.attname) for field in obj._meta.concrete_fields})


def model(label):
    return apps.get_model(label)


def load(path, expected, spec):
    raw = Path(path).read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    if len(raw) > 1000000 or sha != expected:
        raise RestoreError("plan_digest_mismatch")
    try:
        data = json.loads(raw)
        source = data["source"]
        journal = data["source_journal"]
        if data["format"] != spec.format or (
            journal["id"],
            journal["teacher_id"],
            journal["lesson_id"],
            journal["sillabus_id"],
        ) != (spec.journal, spec.source_author, spec.journal_lesson, spec.source_syllabus):
            raise RestoreError("journal_source_scope")
        if (
            source["id"],
            source["teacher_id"],
            source["lesson_id"],
            source["uniqid"],
            source["ders_saati"],
            source["active"],
        ) != (spec.source_syllabus, spec.source_author, spec.source_lesson, spec.uniqid, spec.hours, 1):
            raise RestoreError("syllabus_source_scope")
        week = source["week"]
        if (
            len(week) != spec.topics
            or len({r["id"] for r in week}) != spec.topics
            or any((r["uniqid"] != spec.uniqid for r in week))
        ):
            raise RestoreError("week_source_scope")
        expected_tables = set(SYLLABUS_SECTION_CONTRACTS)
        source_tables = set(source["sections"])
        if (
            not expected_tables.difference(spec.optional_empty_sections).issubset(source_tables)
            or not source_tables.issubset(expected_tables)
            or len(source["sections"]["sillabus_serbest_is"]) != spec.selfwork
        ):
            raise RestoreError("section_source_scope")
        sections, codes = build_section_data(document_for(source))
        if (
            TEXT_TRUNCATED in codes
            or len(sections["week"]["rows"]) != spec.topics
            or len(sections["self"]["topics"])
            != (spec.selfwork if spec.selfwork_topics is None else spec.selfwork_topics)
        ):
            raise RestoreError("source_content_loss")
        if (
            spec.contact_hours
            and tuple(
                sum(row.get(kind, 0) for row in sections["week"]["rows"])
                for kind in ("lecture", "seminar", "practical", "lab")
            )
            != spec.contact_hours
        ):
            raise RestoreError("source_hour_scope")
    except RestoreError:
        raise
    except (ValueError, TypeError, KeyError, AttributeError):
        raise RestoreError("plan_shape") from None
    return (data, sections, codes, sha)


def scope(org, actor, spec):
    if str(org.pk) != spec.organization or not actor.is_active or (not actor.is_superuser):
        raise RestoreError("actor_or_tenant_scope")
    offering = (
        model("registrar.CourseOffering")
        .objects.select_for_update(of=("self",))
        .select_related("subject", "period", "instructor")
        .get(pk=spec.offering, organization=org)
    )
    if (
        str(offering.period_id) != spec.period
        or offering.instructor_id not in spec.allowed_owners
        or offering.subject.code != spec.subject_code
        or (not offering.is_active)
        or (not offering.period.is_current)
        or (not offering.instructor.is_active)
        or (spec.group_id and str(offering.group_id) != spec.group_id)
    ):
        raise RestoreError("live_offering_scope")
    author = model("auth.User").objects.get(pk=spec.author, is_active=True)
    if spec.author not in eligible_instructor_user_ids(organization=org):
        raise RestoreError("author_permission_missing")
    if not model("accounts.UserProfile").objects.filter(user=author, organization=org, access_state="active").exists():
        raise RestoreError("author_identity_scope")
    if offering.instructor_id != spec.author and (
        not model("registrar.JournalShare")
        .objects.filter(organization=org, offering=offering, teacher=author, is_active=True, source="legacy")
        .exists()
    ):
        raise RestoreError("author_journal_access_missing")
    offering.restoration_author = author
    return offering


def write_audit(org, actor, batch, values, reason, spec):
    log_action(
        action=AuditAction.UPDATE,
        user=actor,
        organization=org,
        resource_type=spec.resource,
        resource_id=batch,
        resource_repr=batch,
        reason=reason,
        new_values=values,
    )


def apply(org, actor, loaded, spec):
    offering = scope(org, actor, spec=spec)
    data, sections, codes, sha = loaded
    Syllabus = model("syllabus.Syllabus")
    previous = (
        model("audit.AuditLog")
        .objects.filter(
            organization=org, resource_type=spec.resource, reason=spec.restore_reason, new_values__sha256=sha
        )
        .order_by("created_at")
        .last()
    )
    if previous:
        values = previous.new_values
        if (
            model("audit.AuditLog")
            .objects.filter(
                organization=org, resource_type=spec.resource, resource_id=previous.resource_id, reason=spec.undo_reason
            )
            .exists()
        ):
            raise RestoreError("previous_undo_requires_review")
        version = (
            model("syllabus.SyllabusVersion")
            .objects.select_for_update()
            .get(pk=values["version"], organization=org, syllabus_id=values["syllabus"])
        )
        if (
            version.status != "approved"
            or version.syllabus.author_id != spec.author
            or version.syllabus.offering_id != offering.pk
            or (not version.syllabus.is_active)
            or (digest(section_data_map(version)) != values["content_hash"])
        ):
            raise RestoreError("existing_restore_changed")
        return ({"already_present": 1}, previous.resource_id)
    existing = syllabus_for_offering(
        organization=org,
        offering_id=offering.pk,
        subject_id=offering.subject_id,
        period_id=offering.period_id,
        instructor_id=spec.author,
    )
    if existing or Syllabus.objects.filter(organization=org, offering=offering).exists():
        raise RestoreError("existing_syllabus_no_overwrite")
    batch = f"{spec.batch_prefix}{timezone.now():%Y%m%d-%H%M%S}-{uuid4().hex[:4]}"
    syllabus, version = import_migrated_version(
        organization=org,
        subject=offering.subject,
        period=offering.period,
        offering=offering,
        chair_unit=offering.subject.chair_unit,
        author=offering.restoration_author,
        approved_at=timezone.now(),
        section_data=sections,
        note=spec.note,
    )
    actual = section_data_map(version)
    if actual != sections:
        raise RestoreError("import_content_mismatch")
    syllabus.refresh_from_db()
    version.refresh_from_db()
    manifest = {
        "sha256": sha,
        "syllabus": str(syllabus.pk),
        "version": str(version.pk),
        "content_hash": digest(actual),
        "syllabus_metadata_hash": metadata_digest(syllabus),
        "version_metadata_hash": metadata_digest(version),
        "source_syllabus": spec.source_syllabus,
        "source_uniqid": spec.uniqid,
        "source_author": spec.source_author,
        "target_author": spec.author,
        "journal_owner": offering.instructor_id,
        "author_access": "current owner or active legacy journal share; grade.input eligible",
        "source_journal": spec.journal,
        "source_lesson": spec.source_lesson,
        "journal_lesson": spec.journal_lesson,
        "target_offering": spec.offering,
        "authority": spec.authority,
        "source_section_hashes": {key: digest(value) for key, value in data["source"]["sections"].items()},
        "section_hashes": {key: digest(value) for key, value in actual.items()},
        "conversion_codes": list(codes),
    }
    write_audit(org, actor, batch, manifest, spec.restore_reason, spec=spec)
    return (
        {
            "syllabi_created": 1,
            "versions_created": 1,
            "sections_created": len(actual),
            "topics_restored": spec.topics,
            "selfwork_restored": len(actual["self"]["topics"]),
        },
        batch,
    )


def undo(org, actor, batch, spec):
    offering = scope(org, actor, spec=spec)
    logs = model("audit.AuditLog").objects.filter(organization=org, resource_type=spec.resource, resource_id=batch)
    if logs.filter(reason=spec.undo_reason).exists():
        return {"already_undone": 1}
    receipt = logs.filter(reason=spec.restore_reason).first()
    if receipt is None:
        raise RestoreError("undo_batch_missing")
    values = receipt.new_values
    syllabus = (
        model("syllabus.Syllabus")
        .objects.select_for_update()
        .get(pk=values["syllabus"], organization=org, offering=offering, author_id=spec.author)
    )
    version = (
        model("syllabus.SyllabusVersion")
        .objects.select_for_update()
        .get(pk=values["version"], organization=org, syllabus=syllabus)
    )
    if (
        values.get("syllabus_metadata_hash") != metadata_digest(syllabus)
        or values.get("version_metadata_hash") != metadata_digest(version)
        or version.status != "approved"
        or version.approval_source != "migration"
        or syllabus.subject_id != offering.subject_id
        or (syllabus.period_id != offering.period_id)
        or (not syllabus.is_active)
        or (digest(section_data_map(version)) != values["content_hash"])
        or model("syllabus.Syllabus").objects.filter(reused_from=syllabus).exists()
        or model("syllabus.SyllabusVersion").objects.filter(source_version=version).exists()
        or (syllabus.versions.count() != 1)
        or model("syllabus.SyllabusShare").objects.filter(syllabus=syllabus).exists()
    ):
        raise RestoreError("undo_content_or_usage_changed")
    services.archive(version=version, actor=resolve_actor(actor, org))
    syllabus.is_active = False
    syllabus.save(update_fields=["is_active", "updated_at"])
    write_audit(
        org,
        actor,
        batch,
        {"original": str(receipt.pk), "syllabus": str(syllabus.pk), "version": str(version.pk)},
        spec.undo_reason,
        spec=spec,
    )
    return {"versions_archived": 1, "syllabi_retired": 1}
