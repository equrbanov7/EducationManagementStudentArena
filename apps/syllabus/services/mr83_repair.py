"""Exact SBIO2 correction: retain old dossier and share its teacher's approved source."""

import hashlib
import json

from django.apps import apps
from django.db import transaction

from core.audit import log_action
from core.constants import AuditAction

from .sharing import link_legacy

ORG = "526cfa63-4f80-4bba-a7a7-61c8fbb3d918"
TARGET = "8daaec47-1ba2-4507-a57f-52d6a406fabc"
SOURCE_OFFERING = "bc43c298-975e-4a1e-9b5a-f53cb7e845e1"
OLD = "3f12a9dd-3fac-48db-8545-af533efd2321"
SOURCE = "4e0a8d4a-2e22-4111-819b-79d9c0218919"
OLD_VERSION = "b3d1e4fd-b719-4b71-9c7d-81ccb1992706"
SOURCE_VERSION = "2a28d4df-5a12-469e-a5e2-d802efcf4ba5"
SUBJECT = "215f1821-689d-4cdd-a251-5de892d9ce6c"
PERIOD = "a4f88744-8d49-4772-84ef-c28a96c3b372"
TEACHER = 8429
RESOURCE = "syllabus.mr83_repair"


class MR83Error(ValueError):
    pass


def model(label):
    return apps.get_model(label)


def rows(query):
    return list(query.order_by("pk").values())


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


def capture():
    lessons = model("registrar.Lesson").objects.filter(offering_id=TARGET, organization_id=ORG)
    versions = model("syllabus.SyllabusVersion").objects.filter(syllabus_id__in=(OLD, SOURCE), organization_id=ORG)
    return {
        "syllabi": rows(model("syllabus.Syllabus").objects.filter(pk__in=(OLD, SOURCE), organization_id=ORG)),
        "shares": rows(model("syllabus.SyllabusShare").objects.filter(offering_id__in=(TARGET, SOURCE_OFFERING))),
        "offerings": rows(model("registrar.CourseOffering").objects.filter(pk__in=(TARGET, SOURCE_OFFERING))),
        "versions": rows(versions),
        "sections": rows(model("syllabus.SyllabusSection").objects.filter(version__in=versions)),
        "enrollments": rows(model("registrar.Enrollment").objects.filter(offering_id=TARGET, organization_id=ORG)),
        "lessons": rows(lessons),
        "marks": rows(model("registrar.LessonMark").objects.filter(lesson__in=lessons, organization_id=ORG)),
    }


def protected(value):
    result = {k: v for k, v in value.items() if k not in ("syllabi", "shares")}
    result["syllabi"] = [
        {k: v for k, v in row.items() if not (str(row["id"]) == OLD and k == "is_active")} for row in value["syllabi"]
    ]
    result["other_shares"] = [row for row in value["shares"] if str(row["offering_id"]) != TARGET]
    return result


@transaction.atomic
def repair_mr83_syllabus(*, organization, user, apply=False, expected_baseline="", undo=False):
    if str(organization.pk) != ORG or not user.is_active or not user.is_superuser:
        raise MR83Error("fixed_tenant_active_superadmin_required")
    Offering, Syllabus = model("registrar.CourseOffering"), model("syllabus.Syllabus")
    offerings = {
        str(x.pk): x
        for x in Offering.objects.select_for_update().filter(pk__in=(TARGET, SOURCE_OFFERING), organization_id=ORG)
    }
    syllabi = {
        str(x.pk): x for x in Syllabus.objects.select_for_update().filter(pk__in=(OLD, SOURCE), organization_id=ORG)
    }
    if set(offerings) != {TARGET, SOURCE_OFFERING} or set(syllabi) != {OLD, SOURCE}:
        raise MR83Error("fixed_scope_missing")
    for offering in offerings.values():
        if (str(offering.subject_id), str(offering.period_id), offering.instructor_id, offering.is_active) != (
            SUBJECT,
            PERIOD,
            TEACHER,
            True,
        ):
            raise MR83Error("offering_scope_changed")
    for sid, oid, vid in ((OLD, TARGET, OLD_VERSION), (SOURCE, SOURCE_OFFERING, SOURCE_VERSION)):
        syllabus = syllabi[sid]
        if (
            str(syllabus.offering_id),
            str(syllabus.subject_id),
            str(syllabus.period_id),
            syllabus.author_id,
            str(syllabus.approved_version_id),
            str(syllabus.current_version_id),
            syllabus.reused_from_id,
        ) != (oid, SUBJECT, PERIOD, TEACHER, vid, vid, None):
            raise MR83Error("syllabus_scope_changed")
        if Syllabus.objects.filter(reused_from_id=sid).exists():
            raise MR83Error("reused_dossier_requires_review")
        version = (
            model("syllabus.SyllabusVersion")
            .objects.select_for_update()
            .get(pk=vid, syllabus_id=sid, organization_id=ORG)
        )
        if version.status != "approved":
            raise MR83Error("approved_source_changed")
        sections = list(model("syllabus.SyllabusSection").objects.select_for_update().filter(version=version))
        topics = sum(
            bool(str(row.get("topic") or "").strip())
            for section in sections
            if section.section_id == "week"
            for row in section.data.get("rows", [])
            if isinstance(row, dict)
        )
        if topics != (8 if sid == OLD else 23):
            raise MR83Error("reviewed_topic_count_changed")
    Share = model("syllabus.SyllabusShare")
    if Share.objects.filter(syllabus_id=OLD).exists() or Share.objects.filter(offering_id=SOURCE_OFFERING).exists():
        raise MR83Error("unexpected_share_collision")
    if not syllabi[SOURCE].is_active:
        raise MR83Error("source_inactive")
    before = capture()
    baseline = digest(before)
    if expected_baseline and expected_baseline != baseline:
        raise MR83Error("live_baseline_changed")
    receipt = (
        model("audit.AuditLog")
        .objects.filter(organization_id=ORG, resource_type=RESOURCE, resource_id=TARGET)
        .order_by("-created_at")
        .first()
    )
    share = Share.objects.select_for_update().filter(offering_id=TARGET).first()
    if undo:
        if (
            not receipt
            or digest(before) != receipt.new_values.get("after_hash")
            or syllabi[OLD].is_active
            or not share
            or str(share.pk) != receipt.new_values["share"]
        ):
            raise MR83Error("undo_live_state_changed")
    elif not syllabi[OLD].is_active:
        if receipt and share and str(share.syllabus_id) == SOURCE:
            return {"already_present": 1, "baseline": baseline}
        raise MR83Error("unverified_previous_correction")
    elif share:
        raise MR83Error("target_share_collision")
    if not apply:
        return {"baseline": baseline, "links_to_restore" if undo else "links_to_correct": 1}
    if not expected_baseline:
        raise MR83Error("fresh_live_baseline_required")
    if undo:
        share.delete()
        Syllabus.objects.filter(pk=OLD, organization_id=ORG).update(is_active=True)
    else:
        Syllabus.objects.filter(pk=OLD, organization_id=ORG).update(is_active=False)
        if link_legacy(syllabus=syllabi[SOURCE], offering=offerings[TARGET], user=user) != "linked":
            raise MR83Error("canonical_share_failed")
        share = Share.objects.get(offering_id=TARGET, syllabus_id=SOURCE)
    after = capture()
    if digest(protected(before)) != digest(protected(after)):
        raise MR83Error("academic_or_version_data_changed")
    log_action(
        AuditAction.UPDATE,
        user=user,
        organization=organization,
        resource_type=RESOURCE + (".undo" if undo else ""),
        resource_id=TARGET,
        reason="MR-000083: yalnız SBIO2 üçün müəllimin təsdiqli sillabusunun bağlantısı",
        new_values={
            "share": str(share.pk),
            "before_hash": baseline,
            "after_hash": digest(after),
            "old_syllabus": OLD,
            "source_syllabus": SOURCE,
        },
    )
    return {"links_restored" if undo else "links_corrected": 1, "baseline": baseline}
