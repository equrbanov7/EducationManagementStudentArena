"""Phase B: the ``students`` + ``workers`` identity cohort.

Both audited contracts are streamed in primary-key order, the complete cohort
is classified in a single call so cross-table duplicates are detected, one
ledger observation (plus its sanitized issues) is written per row and every
window is sealed with a ``PhaseBatchRecord``.  The phase opens no source
connection of its own, never calls ``finish_run`` and never reports a value.
Staging is capped by ``policy.max_staged_accounts``; a staged row binds its
``auth.user`` target and its observation inside ONE transaction, so an
interrupted attempt cannot leave an orphan account behind.  A resumed attempt
short-circuits on the recorded observation, which is why
``rebase_target_snapshot_for_run`` first subtracts this run's own staged
identities from the target snapshot.
"""

from __future__ import annotations

import hashlib
import os
import unicodedata
from collections import Counter
from collections.abc import Iterator, Sequence
from dataclasses import asdict, dataclass, fields
from types import MappingProxyType

from django.apps import apps as django_apps
from django.core.exceptions import PermissionDenied
from django.db import transaction

from apps.legacy_import.models import LegacyEntityMap, LegacyEntityObservation, LegacyImportBatch, LegacyMigrationIssue

from .account_cutover import (
    CONTACT_PENDING_STAGEABLE_RULES,
    TARGET_IDENTITY_SNAPSHOT_CHUNK_SIZE,
    AccountCutoverClassification,
    AccountCutoverOutcome,
    AuthoritativeEmailPolicy,
    EmailTrustDecision,
    LegacyAccountCutoverError,
    ProjectedAccountIdentity,
    TargetIdentitySnapshot,
    classify_projected_account_cutover,
    deny_all_email_trust,
    stage_classified_account_cutover,
)
from .batch_accounting import record_batch
from .field_contracts import STUDENT_IDENTITY_FIELDS, WORKER_IDENTITY_FIELDS
from .ledger import upsert_entity_map, upsert_issue
from .pk_inventory_contracts import MAX_LEDGER_PRIMARY_KEY
from .rehearsal_authorizer import USER_MODEL_LABEL
from .rehearsal_contracts import (
    IDENTITY_COHORT_MAX_ROWS,
    EmailTrustPolicy,
    LegacyRehearsalConfigError,
    LegacyRehearsalEvidenceError,
    LegacyRehearsalInterrupted,
    OrderedDigest,
    PhaseBatchRecord,
    PhaseReport,
    RehearsalContext,
    RehearsalPolicy,
    UsernamePolicy,
    encoded_part,
    source_row_hash,
)
from .source_extraction import open_audited_identity_stream

STUDENT_ENTITY_TYPE = "student"
WORKER_ENTITY_TYPE = "worker"
IDENTITY_PHASE_KEY = "identity_cohort"
IDENTITY_PHASE_ORDER = 20  # table_plan._DOMAIN_PHASES["identity_rbac"]
MAX_EMAIL_TRUST_MANIFEST_BYTES = 1 << 20
_COHORT_CONTRACTS = (
    ("students", STUDENT_ENTITY_TYPE, STUDENT_IDENTITY_FIELDS),
    ("workers", WORKER_ENTITY_TYPE, WORKER_IDENTITY_FIELDS),
)
_SOURCE_DIGEST_NAMESPACE = "legacy-rehearsal-source-v1"
_CLASSIFICATION_DIGEST_NAMESPACE = "legacy-rehearsal-classification-v1"
_TARGET_DIGEST_NAMESPACE = "legacy-rehearsal-target-v1"
_PHASE_DIGEST_NAMESPACE = "legacy-rehearsal-phase-v1"
_SEVERITY = LegacyMigrationIssue.Severity
_STATE = LegacyEntityMap.State

# Error taxonomy (SPEC §14).  A missing key fails closed instead of defaulting
# to INFO, because an unmapped rule code would silently stop blocking a run.
ISSUE_SEVERITY = MappingProxyType(
    {
        **dict.fromkeys(
            ("legacy_account_email_untrusted", "legacy_account_email_blank", "legacy_rehearsal_attestation"),
            _SEVERITY.INFO,
        ),
        **dict.fromkeys(
            (
                "legacy_account_email_invalid",
                "legacy_account_username_blank",
                "legacy_account_username_invalid",
                "legacy_account_username_collision",
                "legacy_account_email_collision",
                "legacy_account_email_duplicate_existing",
                "legacy_account_email_duplicate_source",
                "legacy_account_username_duplicate_source",
                "legacy_account_username_email_collision",
                "legacy_account_username_email_duplicate_source",
                "legacy_rehearsal_stage_cap_reached",
            ),
            _SEVERITY.WARNING,
        ),
        **dict.fromkeys(
            (
                "legacy_account_identity_probe_unavailable",
                "legacy_account_email_trust_policy_unavailable",
                "legacy_rehearsal_staging_refused",
            ),
            _SEVERITY.ERROR,
        ),
    }
)
_BLOCKING_SEVERITIES = frozenset({_SEVERITY.ERROR, _SEVERITY.CRITICAL})
# Every sealed batch value except its (source_table, sequence) lookup key.
_REPLAY_FIELDS = tuple(item.name for item in fields(PhaseBatchRecord) if item.name not in ("source_table", "sequence"))
_STAGING_ERRORS: tuple[type[BaseException], ...] = ()


def _staging_error_types() -> tuple[type[BaseException], ...]:
    """Resolve the refusal types staging may raise (the facade omits its error)."""

    global _STAGING_ERRORS
    if not _STAGING_ERRORS:
        from apps.accounts.services.identity_access import IdentityAccessError

        _STAGING_ERRORS = (IdentityAccessError, PermissionDenied, LegacyAccountCutoverError)
    return _STAGING_ERRORS


def _canonical_identity_key(value: object) -> str:
    """Canonicalise byte-identically to ``account_cutover._load_existing_identity_snapshot``."""

    return unicodedata.normalize("NFKC", str(value or "")).strip().lower()


def email_evidence_digest(value: object) -> str:
    """Digest one canonical email key for the PII-free evidence manifest."""

    digest = hashlib.sha256(b"legacy-rehearsal-email-evidence-v1\x00")
    digest.update(encoded_part(_canonical_identity_key(value)))
    return digest.hexdigest()


def load_email_trust_manifest(path: str) -> tuple[frozenset[str], str]:
    """Read a reviewer-attested digest manifest and return it with its own sha256."""

    if type(path) is not str or not path:
        raise LegacyRehearsalConfigError("legacy_rehearsal_email_manifest_invalid")
    try:
        if os.path.islink(path):
            raise LegacyRehearsalConfigError("legacy_rehearsal_email_manifest_invalid")
        with open(path, "rb") as handle:
            payload = handle.read(MAX_EMAIL_TRUST_MANIFEST_BYTES + 1)
    except LegacyRehearsalConfigError:
        raise
    except Exception:
        raise LegacyRehearsalConfigError("legacy_rehearsal_email_manifest_unreadable") from None
    if len(payload) > MAX_EMAIL_TRUST_MANIFEST_BYTES:
        raise LegacyRehearsalConfigError("legacy_rehearsal_email_manifest_too_large")
    manifest_digest = hashlib.sha256(payload).hexdigest()
    digests: set[str] = set()
    try:
        lines = payload.decode("ascii", "strict").splitlines()
    except Exception:
        raise LegacyRehearsalConfigError("legacy_rehearsal_email_manifest_invalid") from None
    for line in lines:
        entry = line.strip()
        if not entry or entry.startswith("#"):
            continue
        if len(entry) != 64 or any(character not in "0123456789abcdef" for character in entry):
            raise LegacyRehearsalConfigError("legacy_rehearsal_email_manifest_invalid")
        digests.add(entry)
    if not digests:
        raise LegacyRehearsalConfigError("legacy_rehearsal_email_manifest_invalid")
    return frozenset(digests), manifest_digest


def build_email_trust_policy(policy: RehearsalPolicy, manifest_digests: frozenset[str]) -> AuthoritativeEmailPolicy:
    """Return the only email-authority policy this run is allowed to inject."""

    if not isinstance(policy, RehearsalPolicy):
        raise LegacyRehearsalConfigError("legacy_rehearsal_policy_invalid")
    if policy.email_trust_policy is EmailTrustPolicy.DENY_ALL:
        if manifest_digests:
            raise LegacyRehearsalConfigError("legacy_rehearsal_policy_email_trust_invalid")
        return deny_all_email_trust
    if not isinstance(manifest_digests, frozenset) or not manifest_digests:
        raise LegacyRehearsalConfigError("legacy_rehearsal_policy_email_trust_invalid")

    def evidence_manifest_trust(identity: ProjectedAccountIdentity) -> EmailTrustDecision:
        if not isinstance(identity, ProjectedAccountIdentity):
            return EmailTrustDecision.DENIED
        try:
            key = _canonical_identity_key(identity.projected_row["email"])
        except Exception:
            return EmailTrustDecision.DENIED
        if key and email_evidence_digest(key) in manifest_digests:
            return EmailTrustDecision.AUTHORITATIVE
        return EmailTrustDecision.DENIED

    return evidence_manifest_trust


def _chunked(items: Sequence[object], size: int) -> Iterator[Sequence[object]]:
    for start in range(0, len(items), size):
        yield items[start : start + size]


def rebase_target_snapshot_for_run(snapshot: TargetIdentitySnapshot, *, run_id) -> TargetIdentitySnapshot:
    """Subtract this run's own staged identities so classification sees the pre-run baseline."""

    if not isinstance(snapshot, TargetIdentitySnapshot):
        raise LegacyRehearsalEvidenceError("legacy_rehearsal_resume_snapshot_invalid")
    staged_pks = list(
        LegacyEntityObservation.objects.filter(
            run_id=run_id,
            state=_STATE.MIGRATED,
            target_model_label=USER_MODEL_LABEL,
        ).values_list("target_pk", flat=True)
    )
    if not staged_pks:
        return snapshot
    usernames: Counter[str] = Counter(snapshot.usernames)
    emails: Counter[str] = Counter(snapshot.emails)
    row_count = snapshot.row_count
    user_model = django_apps.get_model("auth", "User")
    seen = 0
    for chunk in _chunked(staged_pks, TARGET_IDENTITY_SNAPSHOT_CHUNK_SIZE):
        try:
            rows = list(user_model._default_manager.filter(pk__in=chunk).values_list("username", "email"))
        except Exception:
            raise LegacyRehearsalEvidenceError("legacy_rehearsal_resume_target_missing") from None
        for username, email in rows:
            seen += 1
            row_count -= 1
            for counter, raw in ((usernames, username), (emails, email)):
                key = _canonical_identity_key(raw)
                if not key:
                    continue
                counter[key] -= 1
                if counter[key] <= 0:
                    del counter[key]
    if seen != len(staged_pks) or row_count < 0:
        raise LegacyRehearsalEvidenceError("legacy_rehearsal_resume_target_missing")
    return TargetIdentitySnapshot(
        usernames=MappingProxyType(dict(usernames)),
        emails=MappingProxyType(dict(emails)),
        row_count=row_count,
    )


def _proposed_username(policy: RehearsalPolicy, entity_type: str, legacy_pk: int) -> str:
    if getattr(policy, "username_policy", None) is not UsernamePolicy.LEGACY_KEY:
        raise LegacyRehearsalConfigError("legacy_rehearsal_username_policy_unsupported")
    return f"myedu.{entity_type}.{legacy_pk}"


def _student_identifier(policy: RehearsalPolicy, entity_type: str, legacy_pk: int) -> str:
    if entity_type != STUDENT_ENTITY_TYPE:
        return ""
    if getattr(policy, "student_identifier_policy", None) is None:
        raise LegacyRehearsalConfigError("legacy_rehearsal_student_identifier_policy_unsupported")
    return f"myedu-student-{legacy_pk}"


@dataclass(frozen=True)
class _CohortRow:
    """The only per-row object retained for the whole cohort."""

    source_table: str
    entity_type: str
    legacy_pk: int
    source_row_hash: str
    identity: ProjectedAccountIdentity


def _build_cohort(context: RehearsalContext) -> list[_CohortRow]:
    """Stream both contracts in attested, strictly ascending primary-key order."""

    rows: list[_CohortRow] = []
    for source_table, entity_type, contract in _COHORT_CONTRACTS:
        entry = context.plan.entry_for(source_table)
        if entry.expected_rows > IDENTITY_COHORT_MAX_ROWS:
            raise LegacyRehearsalConfigError("legacy_rehearsal_cohort_too_large")
        previous_pk = 0
        observed = 0
        with open_audited_identity_stream(
            connection_factory=context.source_connection_factory,
            contract=contract,
            chunk_size=context.policy.source_chunk_size,
            cancellation_requested=context.cancellation_requested,
        ) as stream:
            for projected_row in stream:
                legacy_pk = projected_row["id"]
                # Mirror pk_inventory._row_pk exactly: no coercion, fail closed.
                if type(legacy_pk) is not int:
                    raise LegacyRehearsalEvidenceError("legacy_rehearsal_source_pk_type_drift")
                if not 1 <= legacy_pk <= MAX_LEDGER_PRIMARY_KEY:
                    raise LegacyRehearsalEvidenceError("legacy_rehearsal_source_pk_out_of_range")
                if legacy_pk <= previous_pk:
                    raise LegacyRehearsalEvidenceError("legacy_rehearsal_source_pk_order_invalid")
                previous_pk = legacy_pk
                observed += 1
                if observed > entry.expected_rows:
                    raise LegacyRehearsalEvidenceError("legacy_rehearsal_source_row_count_mismatch")
                rows.append(
                    _CohortRow(
                        source_table,
                        entity_type,
                        legacy_pk,
                        source_row_hash(contract=contract, legacy_pk=legacy_pk, projected_row=projected_row),
                        ProjectedAccountIdentity(
                            projected_row=projected_row,
                            proposed_username=_proposed_username(context.policy, entity_type, legacy_pk),
                        ),
                    )
                )
        if observed != entry.expected_rows:
            raise LegacyRehearsalEvidenceError("legacy_rehearsal_source_row_count_mismatch")
    return rows


def _severity_for(rule_code: str) -> str:
    try:
        return ISSUE_SEVERITY[rule_code]
    except (KeyError, TypeError):
        raise LegacyRehearsalEvidenceError("legacy_rehearsal_issue_severity_unmapped") from None


def _state_for(classification: AccountCutoverClassification, extra_rules: Sequence[str]) -> str:
    if classification.outcome is AccountCutoverOutcome.MANUAL_REVIEW_REQUIRED:
        return _STATE.QUARANTINED
    for rule_code in (*classification.rule_codes, *extra_rules):
        if _severity_for(rule_code) in _BLOCKING_SEVERITIES:
            return _STATE.QUARANTINED
    return _STATE.SKIPPED


def _target_identity_digest(row: _CohortRow, state: str) -> str:
    """Digest the canonical identity keys — deliberately never the target UUID."""

    if state != _STATE.MIGRATED:
        return ""
    digest = hashlib.sha256(b"legacy-rehearsal-target-identity-v1\x00")
    digest.update(encoded_part(_canonical_identity_key(row.identity.proposed_username)))
    digest.update(encoded_part(_canonical_identity_key(row.identity.projected_row["email"])))
    return digest.hexdigest()


def _existing_observation(context: RehearsalContext, row: _CohortRow):
    return (
        LegacyEntityObservation.objects.filter(
            run_id=context.run_id,
            entity_map__entity_type=row.entity_type,
            entity_map__legacy_pk=str(row.legacy_pk),
        )
        .select_related("entity_map")
        .first()
    )


def _recorded_batches(run_id, source_table: str) -> dict[int, LegacyImportBatch]:
    return {b.sequence: b for b in LegacyImportBatch.objects.filter(run_id=run_id, source_table=source_table)}


def _assert_batch_matches(existing: LegacyImportBatch, record: PhaseBatchRecord) -> None:
    if any(getattr(existing, name) != getattr(record, name) for name in _REPLAY_FIELDS):
        raise LegacyRehearsalEvidenceError("legacy_rehearsal_batch_replay_mismatch")


def _roles_for_staging(context: RehearsalContext) -> dict[str, object]:
    if context.policy.max_staged_accounts <= 0:
        return {}
    role_model = django_apps.get_model("organizations", "Role")
    roles: dict[str, object] = {}
    for entity_type, role_name in (
        (STUDENT_ENTITY_TYPE, context.policy.student_role_name),
        (WORKER_ENTITY_TYPE, context.policy.worker_role_name),
    ):
        role = role_model.objects.filter(organization=context.organization, name=role_name, is_active=True).first()
        if role is None:
            raise LegacyRehearsalConfigError("legacy_rehearsal_staging_role_unavailable")
        roles[entity_type] = role
    return roles


def _write_map(context: RehearsalContext, row: _CohortRow, *, state: str, target_pk: str = ""):
    return upsert_entity_map(
        run_id=context.run_id,
        actor=context.actor,
        authorize=context.authorize,
        entity_type=row.entity_type,
        legacy_pk=str(row.legacy_pk),
        source_row_hash=row.source_row_hash,
        state=state,
        target_model_label=USER_MODEL_LABEL if state == _STATE.MIGRATED else "",
        target_pk=target_pk,
        target_validators=context.target_validators,
    )


def _stageable(classification: AccountCutoverClassification, policy) -> bool:
    """Bridge-in qəbul qaydası ilə EYNİ məntiq (drift olmasın deyə çoxluq oradandır)."""
    if classification.outcome is AccountCutoverOutcome.LOCKED_STAGING_ELIGIBLE and not classification.rule_codes:
        return True
    return (
        policy.stage_contact_pending is True
        and classification.outcome is AccountCutoverOutcome.CONTACT_VERIFICATION_REQUIRED
        and set(classification.rule_codes) <= CONTACT_PENDING_STAGEABLE_RULES
    )


def _stage_row(
    context: RehearsalContext,
    *,
    row: _CohortRow,
    classification: AccountCutoverClassification,
    roles: dict[str, object],
) -> tuple[str, object, tuple[str, ...]]:
    """Bind the target account and its ledger observation in ONE unit of work."""

    try:
        with transaction.atomic():
            staged = stage_classified_account_cutover(
                identity=row.identity,
                classification=classification,
                organization=context.organization,
                role=roles[row.entity_type],
                actor=context.actor,
                student_identifier=_student_identifier(context.policy, row.entity_type, row.legacy_pk),
                allow_contact_pending=context.policy.stage_contact_pending,
            )
            entity_map = _write_map(context, row, state=_STATE.MIGRATED, target_pk=str(staged.user.pk))
    except _staging_error_types():
        # The transaction is already rolled back: no orphan user, no ledger row.
        refused = _write_map(context, row, state=_STATE.QUARANTINED)
        return _STATE.QUARANTINED, refused, ("legacy_rehearsal_staging_refused",)
    return _STATE.MIGRATED, entity_map, ()


def _process_window(
    context: RehearsalContext,
    *,
    contract,
    entity_type: str,
    source_table: str,
    sequence: int,
    window: Sequence[tuple[_CohortRow, AccountCutoverClassification]],
    roles: dict[str, object],
    staged_so_far: int,
    state_counts: Counter,
    issue_counts: Counter,
) -> tuple[PhaseBatchRecord, int]:
    source_chain = OrderedDigest(_SOURCE_DIGEST_NAMESPACE)
    classification_chain = OrderedDigest(_CLASSIFICATION_DIGEST_NAMESPACE)
    target_chain = OrderedDigest(_TARGET_DIGEST_NAMESPACE)
    window_counts: Counter[str] = Counter()
    staged_delta = 0

    for row, classification in window:
        legacy_pk_text = str(row.legacy_pk)
        eligible = _stageable(classification, context.policy)
        observation = _existing_observation(context, row)
        if observation is not None:
            state, entity_map, extra_rules = observation.state, observation.entity_map, ()
            if state == _STATE.MIGRATED:
                # Resume replay: əvvəlki cəhddə staged olunmuş sətir bu run-un
                # staged cəminə VƏ qapaq hesabına daxildir (2026-08-26 tapıntısı —
                # canlı total ilə ledger-rekonstruksiya fərqlənirdi).
                staged_delta += 1
        elif eligible and staged_so_far + staged_delta < context.policy.max_staged_accounts:
            state, entity_map, extra_rules = _stage_row(context, row=row, classification=classification, roles=roles)
            if state == _STATE.MIGRATED:
                staged_delta += 1
        else:
            extra_rules = ("legacy_rehearsal_stage_cap_reached",) if eligible else ()
            state = _state_for(classification, extra_rules)
            entity_map = _write_map(context, row, state=state)

        for rule_code in (*classification.rule_codes, *extra_rules):
            severity = _severity_for(rule_code)
            upsert_issue(
                run_id=context.run_id,
                actor=context.actor,
                authorize=context.authorize,
                source_table=row.source_table,
                entity_type=row.entity_type,
                legacy_pk=legacy_pk_text,
                rule_code=rule_code,
                severity=severity,
                payload_digest=row.source_row_hash,
                entity_map_id=entity_map.pk,
            )
            issue_counts[(rule_code, severity)] += 1

        window_counts[state] += 1
        state_counts[state] += 1
        source_chain.advance(legacy_pk_text, row.source_row_hash)
        classification_chain.advance(
            legacy_pk_text, state, classification.outcome.value, "|".join(classification.rule_codes)
        )
        target_chain.advance(
            legacy_pk_text,
            USER_MODEL_LABEL if state == _STATE.MIGRATED else "",
            _target_identity_digest(row, state),
        )

    record = PhaseBatchRecord(
        source_table=source_table,
        entity_type=entity_type,
        sequence=sequence,
        first_legacy_pk=window[0][0].legacy_pk,
        last_legacy_pk=window[-1][0].legacy_pk,
        migrated_count=window_counts[_STATE.MIGRATED],
        skipped_count=window_counts[_STATE.SKIPPED],
        quarantined_count=window_counts[_STATE.QUARANTINED],
        contract_fingerprint=contract.fingerprint,
        source_digest=source_chain.hexdigest(),
        classification_digest=classification_chain.hexdigest(),
        target_digest=target_chain.hexdigest(),
    )
    return record, staged_delta


class IdentityCohortPhase:
    """The v1 row-accounting phase: students and workers as one cohort."""

    phase_key = IDENTITY_PHASE_KEY
    order = IDENTITY_PHASE_ORDER
    source_tables = ("students", "workers")
    entity_types = (STUDENT_ENTITY_TYPE, WORKER_ENTITY_TYPE)

    def declared_source_rows(self, plan) -> int:
        return sum(plan.entry_for(source_table).expected_rows for source_table in self.source_tables)

    def run(self, context: RehearsalContext) -> PhaseReport:
        if not isinstance(context, RehearsalContext):
            raise LegacyRehearsalConfigError("legacy_rehearsal_context_invalid")
        rows = _build_cohort(context)
        # One call for the WHOLE cohort: a student and a worker sharing an
        # email are only detected when both tables are classified together.
        classifications = classify_projected_account_cutover(
            [row.identity for row in rows],
            authoritative_email_policy=context.authoritative_email_policy,
            target_identity_snapshot=context.target_identity_snapshot,
        )
        if len(classifications) != len(rows):
            raise LegacyRehearsalEvidenceError("legacy_rehearsal_classification_shape_invalid")

        roles = _roles_for_staging(context)
        batches: list[PhaseBatchRecord] = []
        state_counts: Counter[str] = Counter({_STATE.MIGRATED: 0, _STATE.SKIPPED: 0, _STATE.QUARANTINED: 0})
        issue_counts: Counter[tuple[str, str]] = Counter()
        staged = 0

        for source_table, entity_type, contract in _COHORT_CONTRACTS:
            table_rows = [pair for pair in zip(rows, classifications) if pair[0].source_table == source_table]
            recorded = _recorded_batches(context.run_id, source_table)
            for sequence, window in enumerate(_chunked(table_rows, context.policy.batch_rows), start=1):
                # Anything but an explicit ``False`` requests a cancellation.
                if context.cancellation_requested() is not False:
                    raise LegacyRehearsalInterrupted("legacy_rehearsal_cancelled")
                record, staged_delta = _process_window(
                    context,
                    contract=contract,
                    entity_type=entity_type,
                    source_table=source_table,
                    sequence=sequence,
                    window=window,
                    roles=roles,
                    staged_so_far=staged,
                    state_counts=state_counts,
                    issue_counts=issue_counts,
                )
                staged += staged_delta
                existing = recorded.get(sequence)
                if existing is not None:
                    _assert_batch_matches(existing, record)
                record_batch(
                    run_id=context.run_id,
                    actor=context.actor,
                    authorize=context.authorize,
                    **asdict(record),
                )
                batches.append(record)
                context.stdout_note(f"{IDENTITY_PHASE_KEY}.{source_table}.batch.{sequence}")

        phase_chain = OrderedDigest(_PHASE_DIGEST_NAMESPACE)
        for record in batches:
            phase_chain.advance(
                record.source_table,
                str(record.sequence),
                record.source_digest,
                record.classification_digest,
                record.target_digest,
            )
        return PhaseReport(
            phase_key=self.phase_key,
            order=self.order,
            source_tables=self.source_tables,
            declared_source_rows=self.declared_source_rows(context.plan),
            observed_source_rows=len(rows),
            batches=tuple(batches),
            state_counts=MappingProxyType(dict(state_counts)),
            issue_counts=MappingProxyType(dict(issue_counts)),
            staged_account_count=staged,
            phase_digest=phase_chain.hexdigest(),
        )
