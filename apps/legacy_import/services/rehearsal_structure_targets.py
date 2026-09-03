"""Target side of the ``academic_structure`` phase: units, programs, ledger rows.

Split out of ``rehearsal_structure_phase`` purely for the module-size budget; the
phase module keeps the batch/window accounting and imports everything here.  The
one invariant this module owns is that a target and its ledger observation are
bound inside ONE ``transaction.atomic()``, so an interrupted attempt can never
leave an ``OrgUnit``/``Program`` behind without the ledger row that accounts for
it, and a resumed attempt short-circuits on the recorded observation instead of
creating anything a second time.

Departments are materialised in DEPENDENCY order because ``department_id`` may
point at a HIGHER legacy id; the phase module still seals every batch in strictly
ascending ``legacy_pk`` order, so the chain never sees creation order.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, replace
from functools import partial
from types import MappingProxyType

from django.apps import apps as django_apps
from django.db import transaction

from apps.legacy_import.models import LegacyEntityMap, LegacyEntityObservation, LegacyMigrationIssue
from core.constants import OrgUnitType

from .ledger import upsert_entity_map, upsert_issue
from .legacy_text import canonical_settings_digest, legacy_slug
from .rehearsal_authorizer import ORG_UNIT_MODEL_LABEL, PROGRAM_MODEL_LABEL
from .rehearsal_contracts import (
    SOURCE_SYSTEM,
    LegacyRehearsalEvidenceError,
    LegacyRehearsalInterrupted,
    encoded_part,
)
from .rehearsal_structure_source import ProgramPlan

DEPARTMENT_ENTITY_TYPE = "department_unit"
SPECIALITY_ENTITY_TYPE = "speciality_unit"
PROGRAM_ENTITY_TYPE = "speciality_program"  # derived (SA-1): no batch of its own
GROUP_ENTITY_TYPE = "group_unit"
MAX_DEPARTMENT_DEPTH = 8

_SEMANTIC_DIGEST_PREFIX = b"legacy-rehearsal-structure-semantic-v1\x00"
_PROGRAM_ROW_DIGEST_PREFIX = b"legacy-rehearsal-structure-program-v1\x00"
_SEVERITY = LegacyMigrationIssue.Severity
_STATE = LegacyEntityMap.State

# Error taxonomy (SPEC §5).  A missing key fails closed instead of defaulting to
# INFO, because an unmapped rule code would silently stop blocking a run.
ISSUE_SEVERITY = MappingProxyType(
    {
        **dict.fromkeys(
            (
                "legacy_structure_name_truncated",
                "legacy_speciality_without_groups",
                "legacy_group_sector_unknown",
                "legacy_group_education_form_unknown",
                "legacy_group_degree_level_defaulted",
            ),
            _SEVERITY.INFO,
        ),
        **dict.fromkeys(
            (
                "legacy_structure_department_type_nonstandard",
                "legacy_structure_parent_missing",
                "legacy_structure_name_blank",
                "legacy_program_code_truncated",
                "legacy_program_code_collision",
                "legacy_group_speciality_missing",
                "legacy_group_start_year_invalid",
            ),
            _SEVERITY.WARNING,
        ),
        **dict.fromkeys(
            ("legacy_structure_department_type_unknown", "legacy_structure_parent_cycle"),
            _SEVERITY.ERROR,
        ),
    }
)


@dataclass(frozen=True)
class Accounted:
    """One batch-accounted source row after its target and map are bound."""

    legacy_pk: int
    source_row_hash: str
    state: str
    target_model_label: str
    decision_token: str
    semantic_digest: str


@dataclass(frozen=True)
class Resolved:
    """A materialised parent: its target primary key and its stable slug."""

    target_pk: str
    slug: str


NO_PARENT = Resolved("", "")


def severity_for(rule_code: str) -> str:
    try:
        return ISSUE_SEVERITY[rule_code]
    except (KeyError, TypeError):
        raise LegacyRehearsalEvidenceError("legacy_rehearsal_issue_severity_unmapped") from None


def probe_cancellation(context) -> None:
    # Anything but an explicit ``False`` requests a cancellation.
    if context.cancellation_requested() is not False:
        raise LegacyRehearsalInterrupted("legacy_rehearsal_cancelled")


def _semantic_digest(state: str, parts) -> str:
    """Digest the semantic target shape — deliberately never a target UUID."""

    if state != _STATE.MIGRATED:
        return ""
    digest = hashlib.sha256(_SEMANTIC_DIGEST_PREFIX)
    for part in parts:
        digest.update(encoded_part(part))
    return digest.hexdigest()


def _program_row_hash(plan: ProgramPlan, speciality_row_hash: str) -> str:
    """Derivation hash for a program map; a re-derived code fails the ledger."""

    digest = hashlib.sha256(_PROGRAM_ROW_DIGEST_PREFIX)
    for part in (speciality_row_hash, plan.degree_level, plan.code, str(plan.ects_total)):
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


def _ensure_org_unit(context, slug, unit_type, name, code, parent_pk, settings):
    unit, _created = django_apps.get_model("organizations", "OrgUnit").objects.get_or_create(
        organization=context.organization,
        slug=slug,
        defaults={
            "unit_type": unit_type,
            "name": name,
            "code": code,
            "parent_id": parent_pk or None,
            "settings": settings,
        },
    )
    return unit


def _ensure_program(context, plan, specialty_unit_pk):
    program, _created = django_apps.get_model("registrar", "Program").objects.get_or_create(
        organization=context.organization,
        code=plan.code,
        defaults={
            "specialty_unit_id": specialty_unit_pk or None,
            "name": plan.name,
            "degree_level": plan.degree_level,
            "ects_total": plan.ects_total,
            "is_active": True,
        },
    )
    return program


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


def _account_unit(context, source_table, entity_type, row, rule_codes, plan, issue_counts):
    """Materialise one ``OrgUnit`` row, write its issues and account for it.

    ``plan`` is ``(slug, unit_type, name, code, parent, settings, decision_token,
    quarantined)`` — everything the target and the digests need, and nothing else.
    """

    slug, unit_type, name, code, parent, settings, decision_token, quarantined = plan
    legacy_pk = str(row.legacy_pk)
    create = (
        None
        if quarantined
        else partial(_ensure_org_unit, context, slug, unit_type, name, code, parent.target_pk, settings)
    )
    state, entity_map, target_pk = _account_row(
        context, entity_type, legacy_pk, row.source_row_hash, create, ORG_UNIT_MODEL_LABEL
    )
    _write_issues(
        context, source_table, entity_type, legacy_pk, row.source_row_hash, entity_map, rule_codes, issue_counts
    )
    return target_pk, Accounted(
        legacy_pk=row.legacy_pk,
        source_row_hash=row.source_row_hash,
        state=state,
        target_model_label=ORG_UNIT_MODEL_LABEL if state == _STATE.MIGRATED else "",
        decision_token=decision_token,
        semantic_digest=_semantic_digest(
            state, (slug, unit_type, parent.slug, canonical_settings_digest(settings), "")
        ),
    )


def ordered_departments(departments):
    """Topologically sort the tree; ``departments.department_id`` is not id-ordered."""

    by_pk = {department.legacy_pk: department for department in departments}
    ordered = []
    placed: set[int] = set()
    pending = list(departments)
    for _depth in range(MAX_DEPARTMENT_DEPTH):
        remaining = []
        for department in pending:
            parent = department.parent_legacy_pk
            if parent == 0 or parent not in by_pk or parent in placed:
                ordered.append(department)
                placed.add(department.legacy_pk)
            else:
                remaining.append(department)
        if not remaining:
            return tuple(ordered), ()
        if len(remaining) == len(pending):
            break  # nothing moved: the residue is a cycle, not a deep tree
        pending = remaining
    return tuple(ordered), tuple(pending)


def materialise_departments(context, cohort, *, resolved, issue_counts):
    """Create the department tree parents-first; return rows in ``legacy_pk`` order."""

    ordered, cycled = ordered_departments(cohort.departments)
    cycled_pks = {department.legacy_pk for department in cycled}
    accounted: dict[int, Accounted] = {}
    for department in (*ordered, *cycled):
        probe_cancellation(context)
        rule_codes = list(department.rule_codes)
        parent = NO_PARENT
        if department.legacy_pk in cycled_pks:
            rule_codes.append("legacy_structure_parent_cycle")
        elif department.parent_legacy_pk:
            parent = resolved.get(department.parent_legacy_pk, NO_PARENT)
            if not parent.target_pk:
                rule_codes.append("legacy_structure_parent_missing")
        slug = legacy_slug("dep", department.legacy_pk)
        settings = {
            "legacy": {
                "source_system": SOURCE_SYSTEM,
                "table": "departments",
                "id": department.legacy_pk,
                "parent_id": department.parent_legacy_pk,
                "type_id": department.type_id,
                "kollec_or_uni": department.kollec_or_uni,
            }
        }
        quarantined = not department.unit_type or department.legacy_pk in cycled_pks
        target_pk, item = _account_unit(
            context,
            "departments",
            DEPARTMENT_ENTITY_TYPE,
            department,
            rule_codes,
            (slug, department.unit_type, department.name, "", parent, settings, department.unit_type, quarantined),
            issue_counts,
        )
        if target_pk:
            resolved[department.legacy_pk] = Resolved(target_pk, slug)
        accounted[department.legacy_pk] = item
    return tuple(accounted[department.legacy_pk] for department in cohort.departments)


def _materialise_programs(context, plans, *, speciality, specialty_unit_pk, issue_counts) -> str:
    """Create the derived programs and return the speciality's program token."""

    tokens = []
    for plan in plans:
        legacy_pk = f"{plan.speciality_legacy_pk}:{plan.degree_level}"
        row_hash = _program_row_hash(plan, speciality.source_row_hash)
        _state, entity_map, _target_pk = _account_row(
            context,
            PROGRAM_ENTITY_TYPE,
            legacy_pk,
            row_hash,
            partial(_ensure_program, context, plan, specialty_unit_pk),
            PROGRAM_MODEL_LABEL,
        )
        _write_issues(
            context,
            "speciality",
            PROGRAM_ENTITY_TYPE,
            legacy_pk,
            row_hash,
            entity_map,
            plan.rule_codes,
            issue_counts,
        )
        tokens.append(f"{plan.code}:{plan.degree_level}")
    return "|".join(sorted(tokens))


def materialise_specialities(context, cohort, *, departments, resolved, issue_counts):
    """Create each speciality unit, then the programs that hang off it."""

    plans_by_speciality: dict[int, list[ProgramPlan]] = {}
    for plan in cohort.programs:
        plans_by_speciality.setdefault(plan.speciality_legacy_pk, []).append(plan)
    accounted = []
    for speciality in cohort.specialities:
        probe_cancellation(context)
        rule_codes = list(speciality.rule_codes)
        parent = departments.get(speciality.parent_legacy_pk, NO_PARENT)
        if not parent.target_pk:
            # Quarantining a speciality would cascade into its groups and their
            # students, so an unresolvable parent only ever warns.
            rule_codes.append("legacy_structure_parent_missing")
        slug = legacy_slug("spec", speciality.legacy_pk)
        settings = {
            "legacy": {
                "source_system": SOURCE_SYSTEM,
                "table": "speciality",
                "id": speciality.legacy_pk,
                "department_id": speciality.parent_legacy_pk,
                "code": speciality.code,
            }
        }
        plans = plans_by_speciality.get(speciality.legacy_pk, [])
        degrees = ",".join(sorted({plan.degree_level for plan in plans}))
        target_pk, item = _account_unit(
            context,
            "speciality",
            SPECIALITY_ENTITY_TYPE,
            speciality,
            rule_codes,
            (
                slug,
                OrgUnitType.SPECIALTY,
                speciality.name,
                speciality.code,
                parent,
                settings,
                f"{OrgUnitType.SPECIALTY}|{degrees}",
                False,
            ),
            issue_counts,
        )
        resolved[speciality.legacy_pk] = Resolved(target_pk, slug)
        tokens = _materialise_programs(
            context, plans, speciality=speciality, specialty_unit_pk=target_pk, issue_counts=issue_counts
        )
        # Folding the program tuple into the speciality's target digest is what
        # keeps the derived Program rows under cross-run comparison (SA-1).
        accounted.append(
            replace(
                item,
                semantic_digest=_semantic_digest(
                    item.state,
                    (slug, OrgUnitType.SPECIALTY, parent.slug, canonical_settings_digest(settings), tokens),
                ),
            )
        )
    return tuple(accounted)


def materialise_groups(context, cohort, *, departments, specialities, issue_counts):
    """Create each group unit under its speciality, or the department fallback."""

    accounted = []
    for group in cohort.groups:
        probe_cancellation(context)
        rule_codes = list(group.rule_codes)
        parent = specialities.get(group.speciality_legacy_pk, NO_PARENT)
        if not parent.target_pk:
            rule_codes.append("legacy_group_speciality_missing")
            parent = departments.get(group.department_legacy_pk, NO_PARENT)
        slug = legacy_slug("grp", group.legacy_pk)
        year = "" if group.admission_year is None else str(group.admission_year)
        settings = {
            "education_form": group.education_form,
            "admission_year": group.admission_year,
            "sector": group.sector,
            "degree_level": group.degree_level,
            "legacy": {
                "source_system": SOURCE_SYSTEM,
                "table": "groups",
                "id": group.legacy_pk,
                "speciality_id": group.speciality_legacy_pk,
                "department_id": group.department_legacy_pk,
                "curricula_id": group.curricula_legacy_pk,
                "kollec_or_uni": group.kollec_or_uni,
            },
        }
        token = f"{OrgUnitType.GROUP}|{group.education_form}|{group.sector}|{group.degree_level}|{year}"
        _target_pk, item = _account_unit(
            context,
            "groups",
            GROUP_ENTITY_TYPE,
            group,
            rule_codes,
            (slug, OrgUnitType.GROUP, group.name, "", parent, settings, token, False),
            issue_counts,
        )
        accounted.append(item)
    return tuple(accounted)
