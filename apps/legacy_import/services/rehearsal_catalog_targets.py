"""Target side of the ``academic_catalog`` phase: subjects, curricula, plan rows.

Split out of ``rehearsal_catalog_phase`` purely for the module-size budget; the
phase module keeps the batch/window accounting and imports everything here.  The
one invariant this module owns is that a target and its ledger observation are
bound inside ONE ``transaction.atomic()``, so an interrupted attempt can never
leave a ``Subject``/``Curriculum``/``CurriculumSubject`` behind without the
ledger row that accounts for it, and a resumed attempt short-circuits on the
recorded observation instead of creating anything a second time.

Every writer is a ``get_or_create`` on the model's own tenant-unique key, which
is what makes the three collision rules deterministic rather than accidental:
a deduplicated lesson (E-4) converges on the winner's ``Subject.code``, two
legacy curricula for one ``(program, admission_year)`` converge on one
``Curriculum`` (§5.1), and a repeated ``(curriculum, subject, semester)`` adopts
the existing ``CurriculumSubject`` (§5.2).  Collisions are detected from the
KEYS CLAIMED IN THIS PHASE RUN, never from ``get_or_create``'s ``created`` flag,
so a resumed attempt — which creates nothing at all — reports them identically.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from functools import partial
from types import MappingProxyType

from django.apps import apps as django_apps
from django.db import transaction

from apps.legacy_import.models import LegacyEntityMap, LegacyEntityObservation, LegacyMigrationIssue

from .ledger import upsert_entity_map, upsert_issue
from .rehearsal_authorizer import CURRICULUM_MODEL_LABEL, CURRICULUM_SUBJECT_MODEL_LABEL, SUBJECT_MODEL_LABEL
from .rehearsal_catalog_source import ELECTIVE_REQUIRED_CHOICES
from .rehearsal_contracts import LegacyRehearsalEvidenceError, encoded_part

# Imported rather than repeated: one ``Accounted`` shape and ONE cancellation
# probe keep the two batch-accounted phases byte-compatible with each other.
from .rehearsal_structure_targets import Accounted, probe_cancellation

SUBJECT_ENTITY_TYPE = "lesson_subject"
CURRICULUM_ENTITY_TYPE = "curriculum_plan"
PLAN_ROW_ENTITY_TYPE = "curriculum_plan_row"

_SEMANTIC_DIGEST_PREFIX = b"legacy-rehearsal-catalog-semantic-v1\x00"
_SEVERITY = LegacyMigrationIssue.Severity
_STATE = LegacyEntityMap.State

# Error taxonomy (SPEC §6.1).  A missing key fails closed instead of defaulting
# to INFO, because an unmapped rule code would silently stop blocking a run.
# E-13: nothing here is ERROR — the first catalogue rehearsal must be allowed to
# reach SUCCEEDED and produce a complete histogram.
ISSUE_SEVERITY = MappingProxyType(
    {
        **dict.fromkeys(
            (
                "legacy_subject_name_truncated",
                "legacy_subject_deduplicated",
                "legacy_subject_ects_unavailable",
                "legacy_curriculum_degree_defaulted",
                "legacy_curriculum_education_form_not_modelled",
                "legacy_plan_type_unmapped",
                "legacy_plan_credit_unsupported",
                "legacy_plan_hours_not_modelled",
                "legacy_plan_prerequisite_not_modelled",
                # V-14: an expansion is normal information flow (26% of the live
                # plan rows), so it informs and never warns.
                "legacy_plan_lesson_reference_expanded",
                # V-21: an elective block is a FACT the university confirmed, so
                # it only annotates the row it was read from.
                "legacy_plan_elective_block",
            ),
            _SEVERITY.INFO,
        ),
        **dict.fromkeys(
            (
                "legacy_subject_name_blank",
                "legacy_subject_ects_ambiguous",
                "legacy_curriculum_program_unresolved",
                # V-20: the year ladder's two DERIVED tiers.  Both migrate the
                # row, and both warn, because an inferred intake year is not a
                # year the source ever recorded.
                "legacy_curriculum_admission_year_inferred",
                "legacy_curriculum_admission_year_neighbor",
                "legacy_curriculum_admission_year_unresolved",
                "legacy_curriculum_merged_into_existing",
                "legacy_plan_curriculum_unresolved",
                "legacy_plan_lesson_reference_invalid",
                "legacy_plan_lesson_reference_partial",
                "legacy_plan_lesson_unresolved",
                "legacy_plan_semester_invalid",
                "legacy_plan_semester_out_of_range",
                "legacy_plan_semester_scheme_conflict",
                "legacy_plan_row_duplicate",
            ),
            _SEVERITY.WARNING,
        ),
    }
)


@dataclass(frozen=True)
class TargetRef:
    """A materialised catalogue target: its primary key and its digest key."""

    target_pk: str
    key: str  # Subject.code · f"{program_code}:{year}" · Program.code


NO_TARGET = TargetRef("", "")


def severity_for(rule_code: str) -> str:
    try:
        return ISSUE_SEVERITY[rule_code]
    except (KeyError, TypeError):
        raise LegacyRehearsalEvidenceError("legacy_rehearsal_issue_severity_unmapped") from None


def _semantic_digest(state: str, parts) -> str:
    """Digest the semantic target shape — deliberately never a target UUID."""

    if state != _STATE.MIGRATED:
        return ""
    digest = hashlib.sha256(_SEMANTIC_DIGEST_PREFIX)
    for part in parts:
        digest.update(encoded_part(part))
    return digest.hexdigest()


def _existing_observation(context, entity_type: str, legacy_pk: str):
    return (
        LegacyEntityObservation.objects.filter(
            run_id=context.run_id, entity_map__entity_type=entity_type, entity_map__legacy_pk=legacy_pk
        )
        .select_related("entity_map")
        .first()
    )


def _account_row(context, entity_type, legacy_pk, row_hash, create, label):
    """Bind one row's target and its observation inside a single unit of work."""

    observation = _existing_observation(context, entity_type, legacy_pk)
    if observation is not None:
        return observation.state, observation.entity_map, observation.target_pk
    write = partial(
        upsert_entity_map,
        run_id=context.run_id,
        actor=context.actor,
        authorize=context.authorize,
        entity_type=entity_type,
        legacy_pk=legacy_pk,
        source_row_hash=row_hash,
        target_validators=context.target_validators,
    )
    if create is None:
        return _STATE.QUARANTINED, write(state=_STATE.QUARANTINED, target_model_label="", target_pk=""), ""
    with transaction.atomic():
        target_pk = str(create().pk)
        entity_map = write(state=_STATE.MIGRATED, target_model_label=label, target_pk=target_pk)
    return _STATE.MIGRATED, entity_map, target_pk


def _write_issues(context, source_table, entity_type, legacy_pk, row_hash, entity_map, rule_codes, issue_counts):
    """Issues always follow their map: the ledger rejects the other order."""

    for rule_code in rule_codes:
        severity = severity_for(rule_code)
        upsert_issue(
            run_id=context.run_id,
            actor=context.actor,
            authorize=context.authorize,
            source_table=source_table,
            entity_type=entity_type,
            legacy_pk=legacy_pk,
            rule_code=rule_code,
            severity=severity,
            payload_digest=row_hash,
            entity_map_id=entity_map.pk,
        )
        issue_counts[(rule_code, severity)] += 1


def _ensure_subject(context, plan):
    subject, _created = django_apps.get_model("registrar", "Subject").objects.get_or_create(
        organization=context.organization,
        code=plan.code,
        defaults={"name": plan.name, "ects": plan.ects, "description": "", "is_active": True},
    )
    return subject


def _ensure_curriculum(context, program_pk, admission_year):
    curriculum, _created = django_apps.get_model("registrar", "Curriculum").objects.get_or_create(
        organization=context.organization,
        program_id=program_pk,
        admission_year=admission_year,
        defaults={"name": "", "is_active": True},
    )
    return curriculum


def _ensure_plan_rows(context, curriculum_pk, subject_pks, row):
    """Create one row per RESOLVED subject (V-14); the map targets the first.

    V-21: the elective shape comes from the source row.  Every row sharing a
    ``(curriculum, semester, elective_group)`` triple is one block, which is the
    shape ``GroupElectiveChoice`` already expects.
    """

    model = django_apps.get_model("registrar", "CurriculumSubject")
    rows = [
        model.objects.get_or_create(
            organization=context.organization,
            curriculum_id=curriculum_pk,
            subject_id=subject_pk,
            semester_number=row.semester_number,
            defaults={
                "is_elective": row.is_elective,
                "elective_group": row.elective_group,
                "required_choices": ELECTIVE_REQUIRED_CHOICES,
                "order": row.order,
            },
        )[0]
        for subject_pk in subject_pks
    ]
    return rows[0]


def materialise_subjects(context, cohort, *, resolved, issue_counts):
    """Create one ``Subject`` per dedup group; every lesson row still gets a map."""

    plans = {plan.legacy_pk: plan for plan in cohort.subjects}
    accounted = []
    for lesson in cohort.lessons:
        probe_cancellation(context)
        owner = cohort.subject_owner[lesson.legacy_pk]
        plan = plans[owner]
        rule_codes = list(lesson.rule_codes)
        if owner == lesson.legacy_pk:
            rule_codes.extend(plan.rule_codes)
        else:
            # E-4: the non-winner is MIGRATED too — ``get_or_create`` on the
            # winner's code returns the very same row, so batch accounting
            # stays exactly 1:1 with the source table.
            rule_codes.append("legacy_subject_deduplicated")
        legacy_pk = str(lesson.legacy_pk)
        state, entity_map, target_pk = _account_row(
            context,
            SUBJECT_ENTITY_TYPE,
            legacy_pk,
            lesson.source_row_hash,
            partial(_ensure_subject, context, plan),
            SUBJECT_MODEL_LABEL,
        )
        _write_issues(
            context,
            "lessons",
            SUBJECT_ENTITY_TYPE,
            legacy_pk,
            lesson.source_row_hash,
            entity_map,
            rule_codes,
            issue_counts,
        )
        resolved[owner] = TargetRef(target_pk, plan.code)
        accounted.append(
            Accounted(
                legacy_pk=lesson.legacy_pk,
                source_row_hash=lesson.source_row_hash,
                state=state,
                target_model_label=SUBJECT_MODEL_LABEL if state == _STATE.MIGRATED else "",
                decision_token=(
                    f"{owner}|{plan.ects}|{lesson.type_token}|{lesson.department_legacy_pk}|{lesson.only_az}"
                ),
                semantic_digest=_semantic_digest(state, (plan.code, plan.name, str(plan.ects))),
            )
        )
    return tuple(accounted)


def materialise_curricula(context, cohort, *, programs, resolved, claimed_keys, issue_counts):
    """Create one ``Curriculum`` per ``(program, admission_year)``; merges warn."""

    accounted = []
    for curriculum in cohort.curricula:
        probe_cancellation(context)
        rule_codes = list(curriculum.rule_codes)
        program = programs.get(f"{curriculum.speciality_legacy_pk}:{curriculum.degree_level}", NO_TARGET)
        if not program.target_pk:
            # A missing ``Program`` is never minted here: the structure phase
            # folds its programs into the speciality's target digest (SA-1).
            rule_codes.append("legacy_curriculum_program_unresolved")
        year_text = "" if curriculum.admission_year is None else str(curriculum.admission_year)
        quarantined = not program.target_pk or curriculum.admission_year is None
        merged = False
        if not quarantined:
            key = (program.target_pk, curriculum.admission_year)
            merged = key in claimed_keys
            if merged:
                rule_codes.append("legacy_curriculum_merged_into_existing")
            claimed_keys.add(key)
        legacy_pk = str(curriculum.legacy_pk)
        create = (
            None if quarantined else partial(_ensure_curriculum, context, program.target_pk, curriculum.admission_year)
        )
        state, entity_map, target_pk = _account_row(
            context,
            CURRICULUM_ENTITY_TYPE,
            legacy_pk,
            curriculum.source_row_hash,
            create,
            CURRICULUM_MODEL_LABEL,
        )
        _write_issues(
            context,
            "curricula",
            CURRICULUM_ENTITY_TYPE,
            legacy_pk,
            curriculum.source_row_hash,
            entity_map,
            rule_codes,
            issue_counts,
        )
        if target_pk:
            resolved[curriculum.legacy_pk] = TargetRef(target_pk, f"{program.key}:{year_text}")
        accounted.append(
            Accounted(
                legacy_pk=curriculum.legacy_pk,
                source_row_hash=curriculum.source_row_hash,
                state=state,
                target_model_label=CURRICULUM_MODEL_LABEL if state == _STATE.MIGRATED else "",
                decision_token=(
                    f"{curriculum.degree_level}|{year_text}|{curriculum.admission_year_source}"
                    f"|{curriculum.education_form}|{'1' if merged else '0'}"
                ),
                semantic_digest=_semantic_digest(state, (program.key, year_text)),
            )
        )
    return tuple(accounted)


def _resolved_subjects(row, cohort, subjects) -> tuple[list[str], list[str], int]:
    """V-14: map every element of the reference onto a materialised ``Subject``.

    The third value counts the ELEMENTS that resolved, not the distinct targets:
    two elements that dedup onto one ``Subject`` (E-4) are a full resolution and
    must not be reported as a partial one.
    """

    target_pks: list[str] = []
    codes: list[str] = []
    resolved = 0
    for reference in row.lesson_legacy_pks:
        owner = cohort.subject_owner.get(reference)
        subject = subjects.get(owner, NO_TARGET) if owner is not None else NO_TARGET
        if not subject.target_pk:
            continue
        resolved += 1
        if subject.target_pk in target_pks:
            continue
        target_pks.append(subject.target_pk)
        codes.append(subject.key)
    return target_pks, codes, resolved


def materialise_plan_rows(context, cohort, *, curricula, subjects, issue_counts):
    """Create the plan rows; a multi-element reference becomes several rows."""

    claimed_rows: set[tuple[str, str, int]] = set()
    accounted = []
    for row in cohort.plan_rows:
        probe_cancellation(context)
        rule_codes = list(row.rule_codes)
        curriculum = curricula.get(row.curriculum_legacy_pk, NO_TARGET)
        if not curriculum.target_pk:
            rule_codes.append("legacy_plan_curriculum_unresolved")
        target_pks, codes, resolved = _resolved_subjects(row, cohort, subjects)
        if row.lesson_legacy_pks and not target_pks:
            rule_codes.append("legacy_plan_lesson_unresolved")
        elif target_pks and resolved < len(row.lesson_legacy_pks):
            rule_codes.append("legacy_plan_lesson_reference_partial")
        quarantined = not curriculum.target_pk or not row.semester_number or not target_pks
        if not quarantined:
            keys = [(curriculum.target_pk, target_pk, row.semester_number) for target_pk in target_pks]
            if any(key in claimed_rows for key in keys):
                rule_codes.append("legacy_plan_row_duplicate")
            claimed_rows.update(keys)
        legacy_pk = str(row.legacy_pk)
        create = None if quarantined else partial(_ensure_plan_rows, context, curriculum.target_pk, target_pks, row)
        state, entity_map, _target_pk = _account_row(
            context,
            PLAN_ROW_ENTITY_TYPE,
            legacy_pk,
            row.source_row_hash,
            create,
            CURRICULUM_SUBJECT_MODEL_LABEL,
        )
        _write_issues(
            context,
            "curricula_plan",
            PLAN_ROW_ENTITY_TYPE,
            legacy_pk,
            row.source_row_hash,
            entity_map,
            rule_codes,
            issue_counts,
        )
        references = ",".join(str(reference) for reference in row.lesson_legacy_pks)
        accounted.append(
            Accounted(
                legacy_pk=row.legacy_pk,
                source_row_hash=row.source_row_hash,
                state=state,
                target_model_label=CURRICULUM_SUBJECT_MODEL_LABEL if state == _STATE.MIGRATED else "",
                # V-14: the element COUNT is part of the decision, so an array
                # that gained or lost a member is visible in the digest chain.
                decision_token=(
                    f"{references}|{len(row.lesson_legacy_pks)}|{row.semester_number}|{row.type_token}"
                    f"|{row.credit_text}|{row.hours_token}|{row.prerequisite_legacy_pk}"
                ),
                semantic_digest=_semantic_digest(
                    state,
                    # V-21 answered V-9, so the trailing slot that used to be a
                    # reserved "0" now carries the real elective shape — which is
                    # why every catalogue digest changed with this amendment.
                    (
                        curriculum.key,
                        ",".join(codes),
                        str(row.semester_number),
                        str(row.order),
                        f"{int(row.is_elective)}|{row.elective_group}",
                    ),
                ),
            )
        )
    return tuple(accounted)
