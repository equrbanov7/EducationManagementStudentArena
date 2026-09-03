"""Target side of ``sar_materialisation``: activation, curriculum, SAR write.

Three things live here and nothing else — the activation bridge, the §5.5
curriculum decision matrix and the ``StudentAcademicRecord`` write.  The phase
module owns iteration, indexes and the digest chain.

The activation bridge calls the SHIPPED ``apps.accounts.public``
``activate_staged_account`` verbatim (E-10): no trigger, no SECURITY DEFINER
function and no accounts service is touched by this slice.  Immediately after
it, inside the SAME unit of work, the legacy e-mail is neutralised (E-11):
activation asserts *the institution's registry says this person exists*, never
*this address is verified*, so ``email_verified`` goes False and
``password_change_required`` goes True and the account lands in the existing
first-login flow.

The ``except`` clause deliberately sits OUTSIDE ``transaction.atomic()``: a
PostgreSQL ``23514``/``42501`` refusal poisons the transaction, so the ledger
row that ACCOUNTS for the refusal must be written in a fresh one.  This is the
``rehearsal_identity_phase._stage_row`` shape, for the same reason.

Both fallback branches of §5.5 are literally one ``get_or_create`` on
``uniq_curriculum_program_year``: the unique key IS the lookup key, so a
synthetic curriculum and a legacy plan row for the same ``(program, year)`` are
the same database row whichever phase reaches it first, and ``created`` is what
distinguishes "substituted" from "synthesised".
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from types import MappingProxyType

from django.apps import apps as django_apps
from django.core.exceptions import PermissionDenied
from django.db import DatabaseError, transaction
from django.utils import timezone

from apps.legacy_import.models import LegacyEntityMap, LegacyMigrationIssue

from .field_contracts import STUDENT_IDENTITY_FIELDS
from .ledger import upsert_entity_map, upsert_issue
from .rehearsal_authorizer import STUDENT_RECORD_MODEL_LABEL
from .rehearsal_contracts import (
    LegacyRehearsalConfigError,
    LegacyRehearsalEvidenceError,
    SarCurriculumFallback,
    encoded_part,
)

SAR_ENTITY_TYPE = "student_record"
# ``LegacyMigrationIssue`` is unique on (run, source_table, legacy_pk, rule_code)
# and ``student_placement`` writes under the same table, so every code here
# carries the ``legacy_sar_`` prefix to stay disjoint from ``legacy_record_*``.
SAR_SOURCE_TABLE = "students"
ACTIVATION_REASON_CODE = "signed_authoritative_export"  # AccountActivationEvidence.Reason
ACTIVATION_PERMISSION = "member.edit"  # identity_access._assert_tenant_permission
STUDENT_STATUS_ENROLLED = "enrolled"  # registrar.AcademicStatus.ENROLLED

_ACTIVATION_EVIDENCE_PREFIX = b"legacy-rehearsal-activation-evidence-v1\x00"
_DERIVATION_PREFIX = b"legacy-rehearsal-sar-derivation-v1\x00"
_SEVERITY = LegacyMigrationIssue.Severity
_STATE = LegacyEntityMap.State
_REFUSAL_TYPES: tuple[type[BaseException], ...] = ()

# Error taxonomy (SPEC §6.2).  A missing key fails closed instead of defaulting
# to INFO.  E-13: nothing here is ERROR — the first activation rehearsal must be
# allowed to reach SUCCEEDED and produce a complete histogram.
ISSUE_SEVERITY = MappingProxyType(
    {
        **dict.fromkeys(
            (
                "legacy_sar_admission_year_missing",
                # A2: SAR-ın ili UYDURULMADI, attestasiya olunmuş domenin DÖŞƏMƏ
                # sentineli (``ARCHIVE_FALLBACK_ADMISSION_YEAR``) yazıldı — sətir
                # sonradan düzəldilə bilsin deyə WARNING olaraq görünür.
                "legacy_sar_admission_year_fallback",
                "legacy_sar_activation_cap_reached",
                "legacy_sar_activation_refused",
                "legacy_sar_archive_refused",
                "legacy_sar_curriculum_program_conflict",
                "legacy_sar_curriculum_unmapped",
                "legacy_sar_curriculum_substituted",
                "legacy_sar_curriculum_synthesised",
                "legacy_sar_write_refused",
            ),
            _SEVERITY.WARNING,
        ),
        # V-18: ~200 released students are a SOURCE FACT, not an anomaly.
        "legacy_sar_departed_student": _SEVERITY.INFO,
        # Arxiv qolu (A): məzun/xaric hesab üzvlüyü quruldu, giriş bağlı qaldı.
        "legacy_sar_archived_student": _SEVERITY.INFO,
        # A2: sətir arxivə MƏHZ qəbul ili həll olunmadığı üçün düşdü — bu, «niyə
        # arxivləndi» sualının cavabıdır və mənbə faktıdır, anomaliya deyil.
        "legacy_sar_archived_no_admission_year": _SEVERITY.INFO,
        # A2-fix (2026-09-02): qəbul ili bilinməyən, amma BURAXILMAMIŞ tələbə —
        # hesab AKTİV tələbə qalır, il isə sentinel daşıyır. Arxiv qərarı DEYİL.
        "legacy_sar_active_no_admission_year": _SEVERITY.INFO,
        "legacy_sar_group_missing": _SEVERITY.INFO,
    }
)


@dataclass(frozen=True)
class CurriculumDecision:
    """§5.5 M1..M4 reduced to what the atomic block still has to do."""

    target_pk: str  # non-empty ⇒ M1: bind the legacy curriculum verbatim
    source: str  # legacy | fallback | none
    blocked: bool  # ``strict`` refused the row: no SAR, no activation
    rule_codes: tuple[str, ...]


@dataclass(frozen=True)
class RecordRequest:
    """Everything one student's activation-and-SAR unit of work needs."""

    legacy_pk: int
    user_pk: str
    placement_row_hash: str
    program_pk: str
    program_code: str
    group_pk: str
    group_slug: str
    admission_year: int
    decision: CurriculumDecision
    role: object
    evidence_digest: str
    needs_activation: bool


@dataclass(frozen=True)
class RecordOutcome:
    """The sealed result of one row: ledger state, digest, map and issues."""

    state: str
    digest: str
    entity_map: object
    rule_codes: tuple[str, ...]
    activation_state: str


def severity_for(rule_code: str) -> str:
    try:
        return ISSUE_SEVERITY[rule_code]
    except (KeyError, TypeError):
        raise LegacyRehearsalEvidenceError("legacy_rehearsal_issue_severity_unmapped") from None


def _refusal_types() -> tuple[type[BaseException], ...]:
    """Resolve the refusal types activation may raise (the facade omits them)."""

    global _REFUSAL_TYPES
    if not _REFUSAL_TYPES:
        from apps.accounts.services.identity_access import IdentityAccessError

        # ``IdentityCollisionError`` subclasses ``IdentityAccessError`` and
        # ``IntegrityError`` subclasses ``DatabaseError``; both are covered.
        _REFUSAL_TYPES = (IdentityAccessError, PermissionDenied, DatabaseError)
    return _REFUSAL_TYPES


def activation_evidence_digest(
    *, transform_version: str, snapshot_sha256: str, legacy_pk: int, subject: str = "student"
) -> str:
    """Mint the activation evidence deterministically from the pinned snapshot.

    The 2.14 GB dump is sha256-pinned in ``table_plan.SOURCE_SNAPSHOT_SHA256``
    and attested by Phase A; that pin IS the signature behind
    ``signed_authoritative_export``.  Being a pure function of
    ``(transform_version, snapshot_sha256, legacy_pk)`` also makes a re-activation
    match the recorded ``AccountActivationEvidence`` by construction (§7).
    """

    digest = hashlib.sha256(_ACTIVATION_EVIDENCE_PREFIX)
    # ``subject`` qolu ayırır: tələbə aktivasiyası "student", arxiv qolu
    # "alumni" — eyni legacy sətir üçün iki fərqli qərar eyni evidence-i
    # paylaşa bilməz.
    for part in (transform_version, snapshot_sha256, subject, str(legacy_pk)):
        digest.update(encoded_part(part))
    return digest.hexdigest()


def sar_derivation_hash(
    *,
    legacy_pk: int,
    placement_row_hash: str,
    outcome_token: str,
    program_code: str,
    group_slug: str,
    admission_year_text: str,
    curriculum_source: str,
    curriculum_key: str,
    activation_state: str,
) -> str:
    """The cross-run-stable SAR identity; zero UUIDs ever enter it.

    Folding the placement map's own ``source_row_hash`` chains slice 1's
    evidence into slice 2's: a placement decision that changed would change
    every downstream SAR hash, and ``upsert_entity_map`` turns a divergent
    re-derivation into ``legacy_entity_identity_conflict`` on its own.
    """

    digest = hashlib.sha256(_DERIVATION_PREFIX)
    for part in (
        STUDENT_IDENTITY_FIELDS.fingerprint,
        str(legacy_pk),
        placement_row_hash,
        outcome_token,
        program_code,
        group_slug,
        admission_year_text,
        curriculum_source,
        curriculum_key,
        activation_state,
    ):
        digest.update(encoded_part(part))
    return digest.hexdigest()


def assert_activation_actor(context) -> None:
    """One pre-flight probe instead of N per-row ``PermissionDenied`` refusals.

    The ledger authorizer gates on ``member.invite`` while
    ``activate_staged_account`` gates on ``member.edit``; an operator holding
    only the first would see every single row refused.
    """

    from core.permissions import has_permission, is_superadmin_user

    actor = context.actor
    if is_superadmin_user(actor):
        return
    membership_model = django_apps.get_model("organizations", "Membership")
    permissions = {
        item
        for membership in membership_model.objects.filter(
            user=actor, organization=context.organization, is_active=True, role__is_active=True
        ).select_related("role")
        for item in (membership.role.permissions or [])
    }
    if not has_permission(list(permissions), ACTIVATION_PERMISSION):
        raise LegacyRehearsalConfigError("legacy_rehearsal_activation_actor_unauthorized")


def resolve_student_role(context):
    """The SAME role ``identity_cohort`` staged with (C-5): one policy name."""

    role = (
        django_apps.get_model("organizations", "Role")
        .objects.filter(organization=context.organization, name=context.policy.student_role_name, is_active=True)
        .first()
    )
    if role is None:
        raise LegacyRehearsalConfigError("legacy_rehearsal_sar_role_unavailable")
    return role


def account_is_active(context, user_pk: str) -> bool:
    """A resumed or pre-existing activation: the ladder adopts it as-is."""

    profile_model = django_apps.get_model("accounts", "UserProfile")
    return profile_model.objects.filter(
        user_id=user_pk,
        organization=context.organization,
        access_state=profile_model.AccessState.ACTIVE,
        user__is_active=True,
    ).exists()


def resolve_curriculum(context, *, program_pk, group_curricula_pk, curriculum_index) -> CurriculumDecision:
    """§5.5 M1..M4; the fallback itself runs inside the row's atomic block."""

    mapped = curriculum_index.get(str(group_curricula_pk)) if group_curricula_pk else None
    strict = context.policy.sar_curriculum_fallback is SarCurriculumFallback.STRICT
    if mapped is None:
        # M3 (unmapped or quarantined plan) and M4 (the group names no plan).
        # ``strict`` means "no legacy curriculum ⇒ no student record at all".
        return CurriculumDecision("", "none" if strict else "fallback", strict, ("legacy_sar_curriculum_unmapped",))
    curriculum_pk, curriculum_program_pk = mapped
    if curriculum_program_pk == str(program_pk):
        return CurriculumDecision(curriculum_pk, "legacy", False, ())  # M1
    # M2 — the group's plan belongs to a different program.  Binding it would be
    # refused by ``registrar_guard_student_record_coherence`` anyway.
    return CurriculumDecision("", "none" if strict else "fallback", strict, ("legacy_sar_curriculum_program_conflict",))


def _bind_curriculum(context, *, decision, program_pk, admission_year) -> tuple[str, str, tuple[str, ...]]:
    if decision.target_pk:
        return decision.target_pk, "legacy", ()
    curriculum, created = django_apps.get_model("registrar", "Curriculum").objects.get_or_create(
        organization=context.organization,
        program_id=program_pk,
        admission_year=admission_year,
        defaults={"name": "", "is_active": True},
    )
    if created:
        return str(curriculum.pk), "synthesised", ("legacy_sar_curriculum_synthesised",)
    return str(curriculum.pk), "substituted", ("legacy_sar_curriculum_substituted",)


def _neutralise_legacy_email(context, user_pk: str) -> None:
    """E-11: the legacy address is authoritative for EXISTENCE, never for trust."""

    django_apps.get_model("accounts", "UserProfile").objects.filter(
        user_id=user_pk, organization=context.organization
    ).update(email_verified=False, password_change_required=True, updated_at=timezone.now())


def _ensure_record(context, *, request, curriculum_pk):
    """``uniq_student_program`` is the identity, so this is the idempotent form.

    An existing record is ADOPTED, never updated: on INSERT ``_state.adding`` is
    True and ``ReferenceIdentityValidationMixin`` short-circuits, so the
    group-transfer service is not bypassed by an update that never happens.
    """

    record, _created = django_apps.get_model("registrar", "StudentAcademicRecord").objects.get_or_create(
        organization=context.organization,
        student_id=request.user_pk,
        program_id=request.program_pk,
        defaults={
            "curriculum_id": curriculum_pk,
            "group_id": request.group_pk or None,
            "admission_year": request.admission_year,
            "status": STUDENT_STATUS_ENROLLED,
            "is_active": True,
        },
    )
    return record


def _activate(context, *, request) -> None:
    from apps.accounts.public import activate_staged_account

    activate_staged_account(
        user=django_apps.get_model("auth", "User")._default_manager.filter(pk=request.user_pk).first(),
        organization=context.organization,
        expected_role=request.role,
        actor=context.actor,
        email_authoritative=True,
        email_authority_evidence_digest=request.evidence_digest,
        email_authority_reason_code=ACTIVATION_REASON_CODE,
    )
    _neutralise_legacy_email(context, request.user_pk)


def _seal(context, *, legacy_pk: str, digest: str, state: str, label: str = "", target_pk: str = ""):
    return upsert_entity_map(
        run_id=context.run_id,
        actor=context.actor,
        authorize=context.authorize,
        entity_type=SAR_ENTITY_TYPE,
        legacy_pk=legacy_pk,
        source_row_hash=digest,
        state=state,
        target_model_label=label,
        target_pk=target_pk,
        target_validators=context.target_validators,
    )


def seal_deferred(context, *, request, activation_state: str, rule_codes: tuple[str, ...]) -> RecordOutcome:
    """A row that produces no target at all still owns a ledger decision."""

    digest = sar_derivation_hash(
        legacy_pk=request.legacy_pk,
        placement_row_hash=request.placement_row_hash,
        outcome_token="deferred",
        program_code=request.program_code,
        group_slug=request.group_slug,
        admission_year_text="" if not request.admission_year else str(request.admission_year),
        curriculum_source="none",
        curriculum_key="",
        activation_state=activation_state,
    )
    entity_map = _seal(context, legacy_pk=str(request.legacy_pk), digest=digest, state=_STATE.SKIPPED)
    return RecordOutcome(_STATE.SKIPPED, digest, entity_map, rule_codes, activation_state)


def materialise_record(context, *, request: RecordRequest) -> RecordOutcome:
    """Activate (when needed) and write the SAR in ONE unit of work (§8)."""

    year_text = str(request.admission_year)
    activation_state = "activated" if request.needs_activation else "preexisting"
    rule_codes: list[str] = []
    stage = "activation"
    try:
        with transaction.atomic():
            if request.needs_activation:
                _activate(context, request=request)
            stage = "write"
            curriculum_pk, curriculum_source, curriculum_rules = _bind_curriculum(
                context, decision=request.decision, program_pk=request.program_pk, admission_year=request.admission_year
            )
            rule_codes.extend(curriculum_rules)
            if not request.group_pk:
                # A missing group never blocks a SAR: the column is nullable and
                # ``registrar_same_org_group_guard`` returns early on NULL.
                rule_codes.append("legacy_sar_group_missing")
            record = _ensure_record(context, request=request, curriculum_pk=curriculum_pk)
            digest = sar_derivation_hash(
                legacy_pk=request.legacy_pk,
                placement_row_hash=request.placement_row_hash,
                outcome_token="created",
                program_code=request.program_code,
                group_slug=request.group_slug,
                admission_year_text=year_text,
                curriculum_source=curriculum_source,
                curriculum_key=f"{request.program_code}:{year_text}",
                activation_state=activation_state,
            )
            entity_map = _seal(
                context,
                legacy_pk=str(request.legacy_pk),
                digest=digest,
                state=_STATE.MIGRATED,
                label=STUDENT_RECORD_MODEL_LABEL,
                target_pk=str(record.pk),
            )
    except _refusal_types():
        # The transaction is already rolled back: no half-activated account, no
        # SAR without a ledger row.  ``activation_state`` still records WHICH
        # half of the unit of work the run got to (§5.6).
        refused = "legacy_sar_activation_refused" if stage == "activation" else "legacy_sar_write_refused"
        if stage == "activation":
            activation_state = "refused"
        digest = sar_derivation_hash(
            legacy_pk=request.legacy_pk,
            placement_row_hash=request.placement_row_hash,
            outcome_token="unresolved",
            program_code=request.program_code,
            group_slug=request.group_slug,
            admission_year_text=year_text,
            curriculum_source="none",
            curriculum_key="",
            activation_state=activation_state,
        )
        entity_map = _seal(context, legacy_pk=str(request.legacy_pk), digest=digest, state=_STATE.QUARANTINED)
        return RecordOutcome(_STATE.QUARANTINED, digest, entity_map, (refused,), activation_state)
    return RecordOutcome(_STATE.MIGRATED, digest, entity_map, tuple(rule_codes), activation_state)


def write_issues(context, *, legacy_pk: str, digest: str, entity_map, rule_codes, issue_counts) -> None:
    """Issues always follow their map: the ledger rejects the other order."""

    for rule_code in rule_codes:
        severity = severity_for(rule_code)
        upsert_issue(
            run_id=context.run_id,
            actor=context.actor,
            authorize=context.authorize,
            source_table=SAR_SOURCE_TABLE,
            entity_type=SAR_ENTITY_TYPE,
            legacy_pk=legacy_pk,
            rule_code=rule_code,
            severity=severity,
            payload_digest=digest,
            entity_map_id=entity_map.pk,
        )
        issue_counts[(rule_code, severity)] += 1
