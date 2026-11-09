"""Prepare live-qualified actions without saving, simulating or rolling back writes."""

from copy import deepcopy

from apps.registrar.public import choose_syllabus_carry_source, plan_hours_for_offering
from apps.syllabus.public import (
    approved_version_for,
    content_fingerprints,
    reviewed_completion_report,
    section_data_map,
)

from .contracts import RestoreError, digest, fill_empty, hours, model, nonblank
from .sources import checked_content, legacy_for
from .state import resolved


def _source(offering, packet, official, dossier, approved):
    legacy = legacy_for(offering, packet, official)
    if legacy:
        return legacy
    if approved is not None:
        sections = section_data_map(approved)
        try:
            checked_content(sections, official)
            return {
                "kind": "current",
                "sections": sections,
                "version_id": str(approved.pk),
                "syllabus_id": str(dossier.pk),
                "approval_source": approved.approval_source,
            }
        except RestoreError:
            pass
    _code, donor = choose_syllabus_carry_source(offering, allow_existing=True)
    if donor is None:
        return None
    version = approved_version_for(donor)
    if version is None or donor.subject_id != offering.subject_id or donor.period_id != offering.period_id:
        raise RestoreError("current_donor_scope_changed")
    sections = section_data_map(version)
    checked_content(sections, official)
    return {
        "kind": "current",
        "sections": sections,
        "version_id": str(version.pk),
        "syllabus_id": str(donor.pk),
        "approval_source": version.approval_source,
    }


def _unshared(dossier, ids):
    if dossier is None:
        return
    if model("syllabus.SyllabusShare").objects.filter(syllabus=dossier).exclude(offering_id__in=ids).exists():
        raise RestoreError("publication_reaches_unreviewed_offering")
    if (
        model("syllabus.Syllabus").objects.filter(reused_from=dossier).exists()
        or model("syllabus.SyllabusVersion")
        .objects.filter(source_version__syllabus=dossier)
        .exclude(syllabus=dossier)
        .exists()
    ):
        raise RestoreError("publication_has_unreviewed_dependents")


def action_for(offering, packet, ids):
    if (
        not offering.is_active
        or offering.instructor_id is None
        or not offering.instructor.is_active
        or not offering.period.is_current
        or not offering.period.is_active
        or offering.period.locked_at is not None
        or offering.group_id is None
    ):
        raise RestoreError("active_current_teacher_group_required")
    official = hours(plan_hours_for_offering(offering))
    if offering.lesson_hours != sum(official.values()):
        raise RestoreError("offering_and_official_hours_disagree")
    dossier = resolved(offering)
    if dossier is None:
        # Strict readers exclude wrong-subject dossiers; repair still checks the occupied slot.
        dossier = (
            model("syllabus.Syllabus").objects.filter(organization=offering.organization, offering=offering).first()
        )
    if dossier is not None and not dossier.is_active:
        raise RestoreError("inactive_owned_dossier_requires_review")
    approved = approved_version_for(dossier)
    base = {
        "offering_id": str(offering.pk),
        "official_hours": official,
        "syllabus_id": str(dossier.pk) if dossier else None,
        "action": "none",
    }
    if dossier is None:
        code, donor = choose_syllabus_carry_source(offering)
        if donor is not None:
            version = approved_version_for(donor)
            checked_content(section_data_map(version), official)
            return {
                **base,
                "action": "carry",
                "donor_id": str(donor.pk),
                "donor_version_id": str(version.pk),
                "body_sha256": digest(section_data_map(version)),
            }
        source = legacy_for(offering, packet, official)
        if source is None:
            raise RestoreError("missing_verified_source_" + code)
        return {**base, "action": "restore", "source": source, "sections": source["sections"]}
    scope_ok = dossier.subject_id == offering.subject_id and dossier.period_id in (None, offering.period_id)
    drafts = list(model("syllabus.SyllabusVersion").objects.filter(syllabus=dossier, status__in=("draft", "revision")))
    if len(drafts) > 1:
        raise RestoreError("multiple_open_revisions_require_review")
    draft = drafts[0] if drafts else None
    if not scope_ok:
        # Fixing a label alone can hide the wrong course body. Exact source is mandatory.
        source = legacy_for(offering, packet, official)
        if source is None or dossier.offering_id != offering.pk or dossier.author_id != offering.instructor_id:
            raise RestoreError("subject_binding_requires_exact_source")
        if draft and any(nonblank(v) for k, v in section_data_map(draft).items() if k != "info"):
            raise RestoreError("subject_binding_human_draft_preserved")
        _unshared(dossier, ids)
        return {**base, "action": "restore", "rebind_subject": True, "source": source, "sections": source["sections"]}
    if draft is None:
        if approved is None:
            raise RestoreError("no_approved_or_draft_version")
        checked_content(section_data_map(approved), official)
        stored = {key: (approved.plan_hours or {}).get(key, 0) for key in official}
        if stored != official:
            _unshared(dossier, ids)
            return {**base, "action": "plan_hours", "version_id": str(approved.pk)}
        return base
    if dossier.author_id != offering.instructor_id:
        raise RestoreError("draft_author_identity_requires_review")
    if draft.applies_to_period_id not in (None, offering.period_id):
        raise RestoreError("draft_applies_to_other_period")
    _unshared(dossier, ids)
    existing = section_data_map(draft)
    source = _source(offering, packet, official, dossier, approved)
    proposed = deepcopy(existing) if source is None else fill_empty(existing, source["sections"])
    report = reviewed_completion_report(version=draft, sections=proposed, plan_hours=official)
    if report.is_complete:
        checked_content(proposed, official)
        return {
            **base,
            "action": "publish",
            "version_id": str(draft.pk),
            "sections": proposed,
            "source": source,
            "body_sha256": content_fingerprints(proposed)["canonical_body_sha256"],
        }
    academic_content = any(nonblank(v) for k, v in existing.items() if k not in {"info", "prev", "send"})
    if not academic_content and source and source["kind"] == "legacy":
        # A new migration version preserves the old draft in history; no fake 100% cache.
        proposed = deepcopy(source["sections"])
        proposed["info"] = fill_empty(existing.get("info", {}), proposed.get("info", {}))
        return {
            **base,
            "action": "restore",
            "source": source,
            "sections": proposed,
            "preserved_draft_id": str(draft.pk),
        }
    raise RestoreError(
        "human_draft_requires_missing_academic_content"
        if academic_content
        else "blank_draft_requires_exact_legacy_source"
    )


def prepare(offerings, packet, ids):
    actions, held, seen = [], [], {}
    for offering in offerings:
        try:
            action = action_for(offering, packet, ids)
            identity = action.get("version_id") or (
                action.get("syllabus_id") if action["action"] == "restore" else None
            )
            if identity and identity in seen:
                previous = seen[identity]
                if previous is None:
                    raise RestoreError("shared_dossier_plan_conflict")
                if any(previous.get(key) != action.get(key) for key in ("action", "official_hours", "sections")):
                    actions.remove(previous)
                    held.extend(
                        {"offering_id": oid, "code": "shared_dossier_plan_conflict"}
                        for oid in previous["affected_offering_ids"]
                    )
                    seen[identity] = None
                    raise RestoreError("shared_dossier_plan_conflict")
                previous["affected_offering_ids"].append(str(offering.pk))
                continue
            if action["action"] != "none":
                action["affected_offering_ids"] = [str(offering.pk)]
                actions.append(action)
                if identity:
                    seen[identity] = action
        except RestoreError as error:
            held.append({"offering_id": str(offering.pk), "code": str(error)})
    return actions, held


def safe_actions(actions):
    return [
        {key: value for key, value in row.items() if key not in {"sections", "source"}}
        | {"source_sha256": digest(row["source"]) if row.get("source") else None}
        for row in actions
    ]
