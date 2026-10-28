"""MR46: bir müəllimin jurnalına bağlı mənbə sillabusunu dar, auditli qaydada bərpa et."""

import hashlib
import json
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

ORG = "526cfa63-4f80-4bba-a7a7-61c8fbb3d918"
PERIOD = "a4f88744-8d49-4772-84ef-c28a96c3b372"
OFFERING = "acc97b99-90bc-4fb3-b01b-b56ff630b7d2"
AUTHOR = 7942
UNIQID = "qVHmrlOPQd3p6Rk4UBsT"
RESOURCE = "legacy_import.mr46_syllabus"


class RestoreError(ValueError):
    pass


def digest(data):
    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=True, default=str).encode()).hexdigest()


def model(label):
    return apps.get_model(label)


def load(path, expected):
    raw = Path(path).read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    if len(raw) > 1_000_000 or sha != expected:
        raise RestoreError("plan_digest_mismatch")
    try:
        data = json.loads(raw)
        source = data["source"]
        journal = data["source_journal"]
        if data["format"] != "mr46-syllabus/1" or (
            journal["id"],
            journal["teacher_id"],
            journal["lesson_id"],
            journal["sillabus_id"],
        ) != (15363, 442, 1500, 8891):
            raise RestoreError("journal_source_scope")
        if (
            source["id"],
            source["teacher_id"],
            source["lesson_id"],
            source["uniqid"],
            source["ders_saati"],
            source["active"],
        ) != (8891, 442, 457, UNIQID, 90, 1):
            raise RestoreError("syllabus_source_scope")
        week = source["week"]
        if len(week) != 23 or len({r["id"] for r in week}) != 23 or any(r["uniqid"] != UNIQID for r in week):
            raise RestoreError("week_source_scope")
        if (
            set(source["sections"]) != set(SYLLABUS_SECTION_CONTRACTS)
            or len(source["sections"]["sillabus_serbest_is"]) != 18
        ):
            raise RestoreError("section_source_scope")
        sections, codes = build_section_data(document_for(source))
        if TEXT_TRUNCATED in codes or len(sections["week"]["rows"]) != 23 or len(sections["self"]["topics"]) != 18:
            raise RestoreError("source_content_loss")
    except RestoreError:
        raise
    except (ValueError, TypeError, KeyError, AttributeError):
        raise RestoreError("plan_shape") from None
    return data, sections, codes, sha


def scope(org, actor):
    if str(org.pk) != ORG or not actor.is_active or not actor.is_superuser:
        raise RestoreError("actor_or_tenant_scope")
    offering = (
        model("registrar.CourseOffering")
        .objects.select_for_update(of=("self",))
        .select_related("subject", "period", "instructor")
        .get(pk=OFFERING, organization=org)
    )
    if (
        str(offering.period_id) != PERIOD
        or offering.instructor_id not in (7942, 8415)
        or offering.subject.code != "QKU-1500"
        or not offering.is_active
        or not offering.period.is_current
        or not offering.instructor.is_active
    ):
        raise RestoreError("live_offering_scope")
    author = model("auth.User").objects.get(pk=AUTHOR, is_active=True)
    if AUTHOR not in eligible_instructor_user_ids(organization=org):
        raise RestoreError("author_permission_missing")
    if not model("accounts.UserProfile").objects.filter(user=author, organization=org, access_state="active").exists():
        raise RestoreError("author_identity_scope")
    if (
        offering.instructor_id != AUTHOR
        and not model("registrar.JournalShare")
        .objects.filter(organization=org, offering=offering, teacher=author, is_active=True, source="legacy")
        .exists()
    ):
        raise RestoreError("author_journal_access_missing")
    offering.restoration_author = author
    return offering


def write_audit(org, actor, batch, values, reason):
    log_action(
        action=AuditAction.UPDATE,
        user=actor,
        organization=org,
        resource_type=RESOURCE,
        resource_id=batch,
        resource_repr=batch,
        reason=reason,
        new_values=values,
    )


def apply(org, actor, loaded):
    offering = scope(org, actor)
    data, sections, codes, sha = loaded
    Syllabus = model("syllabus.Syllabus")
    previous = (
        model("audit.AuditLog")
        .objects.filter(
            organization=org, resource_type=RESOURCE, reason="MR46 source syllabus restore", new_values__sha256=sha
        )
        .order_by("created_at")
        .last()
    )
    if previous:
        values = previous.new_values
        if (
            model("audit.AuditLog")
            .objects.filter(
                organization=org,
                resource_type=RESOURCE,
                resource_id=previous.resource_id,
                reason="MR46 source syllabus undo",
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
            or version.syllabus.author_id != AUTHOR
            or version.syllabus.offering_id != offering.pk
            or not version.syllabus.is_active
            or digest(section_data_map(version)) != values["content_hash"]
        ):
            raise RestoreError("existing_restore_changed")
        return {"already_present": 1}, previous.resource_id
    existing = syllabus_for_offering(
        organization=org,
        offering_id=offering.pk,
        subject_id=offering.subject_id,
        period_id=offering.period_id,
        instructor_id=AUTHOR,
    )
    if existing or Syllabus.objects.filter(organization=org, offering=offering).exists():
        raise RestoreError("existing_syllabus_no_overwrite")
    batch = f"mr46-{timezone.now():%Y%m%d-%H%M%S}-{uuid4().hex[:4]}"
    syllabus, version = import_migrated_version(
        organization=org,
        subject=offering.subject,
        period=offering.period,
        offering=offering,
        chair_unit=offering.subject.chair_unit,
        author=offering.restoration_author,
        approved_at=timezone.now(),
        section_data=sections,
        note="MR-000046: müəllimin legacy8891 sillabusu öz 15363 jurnalına bağlıdır. Mənbədə 457 → jurnalda 1500 fərqi sistem sahibinin bu jurnal üçün açıq bərpa qərarı ilə həll edilib.",
    )
    actual = section_data_map(version)
    if actual != sections:
        raise RestoreError("import_content_mismatch")
    manifest = {
        "sha256": sha,
        "syllabus": str(syllabus.pk),
        "version": str(version.pk),
        "content_hash": digest(actual),
        "source_syllabus": 8891,
        "source_uniqid": UNIQID,
        "source_author": 442,
        "target_author": AUTHOR,
        "journal_owner": offering.instructor_id,
        "author_access": "current owner or active legacy journal share; grade.input eligible",
        "source_journal": 15363,
        "source_lesson": 457,
        "journal_lesson": 1500,
        "target_offering": OFFERING,
        "authority": "MR46 teacher requests own old journal syllabus; owner authorizes this exact target despite legacy subject-id mismatch",
        "source_section_hashes": {key: digest(value) for key, value in data["source"]["sections"].items()},
        "section_hashes": {key: digest(value) for key, value in actual.items()},
        "conversion_codes": list(codes),
    }
    write_audit(org, actor, batch, manifest, "MR46 source syllabus restore")
    return {
        "syllabi_created": 1,
        "versions_created": 1,
        "sections_created": len(actual),
        "topics_restored": 23,
        "selfwork_restored": 18,
    }, batch


def undo(org, actor, batch):
    offering = scope(org, actor)
    logs = model("audit.AuditLog").objects.filter(organization=org, resource_type=RESOURCE, resource_id=batch)
    if logs.filter(reason="MR46 source syllabus undo").exists():
        return {"already_undone": 1}
    receipt = logs.filter(reason="MR46 source syllabus restore").first()
    if receipt is None:
        raise RestoreError("undo_batch_missing")
    values = receipt.new_values
    syllabus = (
        model("syllabus.Syllabus")
        .objects.select_for_update()
        .get(pk=values["syllabus"], organization=org, offering=offering, author_id=AUTHOR)
    )
    version = (
        model("syllabus.SyllabusVersion")
        .objects.select_for_update()
        .get(pk=values["version"], organization=org, syllabus=syllabus)
    )
    if (
        version.status != "approved"
        or version.approval_source != "migration"
        or syllabus.subject_id != offering.subject_id
        or syllabus.period_id != offering.period_id
        or not syllabus.is_active
        or digest(section_data_map(version)) != values["content_hash"]
        or model("syllabus.Syllabus").objects.filter(reused_from=syllabus).exists()
        or model("syllabus.SyllabusVersion").objects.filter(source_version=version).exists()
        or syllabus.versions.count() != 1
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
        "MR46 source syllabus undo",
    )
    return {"versions_archived": 1, "syllabi_retired": 1}
