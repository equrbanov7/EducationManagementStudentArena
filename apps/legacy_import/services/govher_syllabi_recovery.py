"""MR-000250 / MR-000251 — müəllimin öz köhnə sillabusu təsdiqli versiya kimi; köhnə versiyalar arxivdə qalır.

* ``replace`` (MR-250): jurnalın göstərdiyi baza dosyedəki səhv dilli v1.0 ARXİVƏ keçir (silinmir), EYNİ dosyeyə
  müəllimin Azərbaycan dilli mənbəsi ``approval_source=migration`` ilə v2.0 kimi yazılır.
* ``beside_blank_draft`` (MR-251, jurnalın öz dosyesi BOŞ qaralamadırsa): qaralama arxivə keçir, yanına təsdiqli
  versiya yazılır. ``create`` (dosye yoxdursa): jurnala bağlı yeni təsdiqli dosye.

Dərs / xana / qeydiyyat / qiymət toxunulmur (``state.protected`` əvvəl = sonra). Hər icra bir audit qəbzidir
(``govsyl-…``); ``--undo`` yeni versiyanı arxivləyir, köhnə versiyaların statusunu qaytarır, yaradılmış dosyeni
söndürür — yalnız qəbzdən sonra heç nə dəyişməyibsə.
"""

from collections import Counter
from uuid import uuid4

from django.db import transaction
from django.utils import timezone

from apps.syllabus.public import import_migrated_version, resolve_actor, section_data_map, services

from . import exact_syllabus_recovery as core
from . import govher_syllabi_spec as spec
from . import govher_syllabi_state as state
from .govher_syllabi_source import load  # noqa: F401

RestoreError = core.RestoreError
RESOURCE = "legacy_import.govher_own_syllabi"
RESTORE_REASON = "MR-000250/251 own legacy syllabus restore"
UNDO_REASON = "MR-000250/251 own legacy syllabus undo"
NOTE = (
    "Müəllimin köhnə sistemdəki öz sillabusu (cari jurnalın birbaşa sillabus göstəricisi) bərpa olunub; "
    "köhnə sistemin təsdiqi iddia edilmir (MR-000250 / MR-000251)."
)


def _receipts(org, batch=None):
    logs = core.model("audit.AuditLog").objects.filter(organization=org, resource_type=RESOURCE)
    return logs.filter(resource_id=batch) if batch else logs


def _audit(org, actor, batch, reason, values):
    core.log_action(
        action=core.AuditAction.UPDATE,
        user=actor,
        organization=org,
        resource_type=RESOURCE,
        resource_id=batch,
        resource_repr=batch,
        reason=reason,
        new_values=values,
    )


def _already_present(org, receipt):
    if _receipts(org, receipt.resource_id).filter(reason=UNDO_REASON).exists():
        raise RestoreError("previous_undo_requires_review")
    for child in receipt.new_values["children"]:
        version = core.model("syllabus.SyllabusVersion").objects.filter(pk=child["version"], organization=org).first()
        if (
            version is None
            or version.status != "approved"
            or not version.syllabus.is_active
            or core.digest(section_data_map(version)) != child["content_hash"]
        ):
            raise RestoreError("existing_restore_changed")
    return {"already_present": len(receipt.new_values["children"])}


def _restore_case(org, actor, case, sections, codes):
    offering = state.offering_scope(org, case)
    action, dossier, retired = state.dossier_plan(org, case, offering)
    before = state.protected(org, offering)
    now = timezone.now()
    counts = Counter()
    retired_rows = []
    if action == "replace":
        services.archive(version=retired, actor=resolve_actor(actor, org))
        retired_rows.append({"id": str(retired.pk), "status": "approved"})
        target = {"subject": dossier.subject, "period": None, "offering": None}
        counts["wrong_versions_archived"] += 1
    elif action == "beside_blank_draft":
        updated = (
            core.model("syllabus.SyllabusVersion")
            .objects.filter(pk=retired.pk, organization=org, status="draft")
            .update(status="archived", archived_at=now)
        )
        if updated != 1:
            raise RestoreError("blank_draft_changed")
        retired_rows.append({"id": str(retired.pk), "status": "draft"})
        target = {"subject": offering.subject, "period": offering.period, "offering": offering}
        counts["blank_drafts_archived"] += 1
    else:
        target = {"subject": offering.subject, "period": offering.period, "offering": offering}
    if dossier is not None:
        target.update(author=dossier.author, chair_unit=dossier.chair_unit, program=dossier.program)
        major = 1 + max(
            core.model("syllabus.SyllabusVersion").objects.filter(syllabus=dossier).values_list("major", flat=True)
        )
    else:
        target.update(
            author=core.model("auth.User").objects.get(pk=spec.AUTHOR), chair_unit=offering.subject.chair_unit
        )
        major = 1
    syllabus, version = import_migrated_version(
        organization=org,
        approved_at=now,
        plan_hours=dict(case["plan"]),
        section_data=sections,
        major=major,
        minor=0,
        note=NOTE,
        **target,
    )
    if (dossier is not None and syllabus.pk != dossier.pk) or section_data_map(version) != sections:
        raise RestoreError("import_target_or_content_mismatch")
    syllabus.refresh_from_db()
    version.refresh_from_db()
    shown = state.resolved_for(offering)
    if shown is None or shown.pk != syllabus.pk or shown.approved_version_id != version.pk:
        raise RestoreError("journal_resolution_after_restore")
    if shown.current_version_id != version.pk:
        raise RestoreError("journal_open_version_remains")
    if state.protected(org, offering) != before:
        raise RestoreError("protected_journal_content_changed")
    counts.update(
        versions_created=1,
        syllabi_created=int(action == "create"),
        topics_restored=len(sections["week"]["rows"]),
        selfwork_restored=len(sections["self"]["topics"]),
    )
    child = {
        "key": case["key"],
        "offering": case["offering_id"],
        "action": action,
        "created": action == "create",
        "syllabus": str(syllabus.pk),
        "version": str(version.pk),
        "retired": retired_rows,
        "content_hash": core.digest(sections),
        "after": state.dossier_state(org, syllabus),
        "source_syllabus": case["source"]["id"],
        "source_journal": case["journal"]["id"],
        "conversion_codes": list(codes),
    }
    return counts, child


@transaction.atomic
def apply(org, actor, loaded):
    state.actor_scope(org, actor)
    if [case["offering_id"] for case, _, _ in loaded] != [case["offering_id"] for case in spec.CASES]:
        raise RestoreError("fixed_target_set_required")
    previous = _receipts(org).filter(reason=RESTORE_REASON).order_by("created_at").last()
    if previous is not None:
        return _already_present(org, previous), str(previous.resource_id)
    counts, children = Counter(), []
    for case, sections, codes in loaded:
        result, child = _restore_case(org, actor, case, sections, codes)
        counts.update(result)
        children.append(child)
    batch = f"govsyl-{timezone.now():%Y%m%d-%H%M%S}-{uuid4().hex[:4]}"
    _audit(
        org,
        actor,
        batch,
        RESTORE_REASON,
        {"packet_sha256": spec.PACKET_SHA256, "legacy_approval_asserted": False, "children": children},
    )
    return dict(counts), batch


def _undo_child(org, actor, child):
    Version = core.model("syllabus.SyllabusVersion")
    syllabus = core.model("syllabus.Syllabus").objects.select_for_update().get(pk=child["syllabus"], organization=org)
    version = Version.objects.select_for_update().get(pk=child["version"], syllabus=syllabus, organization=org)
    if state.dossier_state(org, syllabus) != child["after"] or version.status != "approved":
        raise RestoreError("undo_live_state_changed")
    if (
        core.model("syllabus.Syllabus").objects.filter(reused_from=syllabus).exists()
        or Version.objects.filter(source_version__syllabus=syllabus).exists()
    ):
        raise RestoreError("undo_live_state_changed")
    services.archive(version=version, actor=resolve_actor(actor, org))
    for item in child["retired"]:
        restored = Version.objects.filter(pk=item["id"], syllabus=syllabus, status="archived").update(
            status=item["status"], archived_at=None
        )
        if restored != 1:
            raise RestoreError("undo_retired_version_changed")
    services.refresh_pointers(syllabus)
    if child["created"]:
        syllabus.is_active = False
        syllabus.save(update_fields=["is_active", "updated_at"])
    return Counter(versions_archived=1, versions_restored=len(child["retired"]), syllabi_retired=int(child["created"]))


@transaction.atomic
def undo(org, actor, batch):
    state.actor_scope(org, actor)
    logs = _receipts(org, batch)
    if logs.filter(reason=UNDO_REASON).exists():
        return {"already_undone": 1}
    receipt = logs.filter(reason=RESTORE_REASON).first()
    if receipt is None:
        raise RestoreError("undo_batch_missing")
    children = receipt.new_values["children"]
    if sorted(child["offering"] for child in children) != sorted(case["offering_id"] for case in spec.CASES):
        raise RestoreError("undo_target_set_changed")
    counts = Counter()
    for child in reversed(children):
        counts.update(_undo_child(org, actor, child))
    _audit(org, actor, batch, UNDO_REASON, {"receipt": str(receipt.pk)})
    return dict(counts)
