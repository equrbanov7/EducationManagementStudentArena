"""``ledger_batch`` testləri: sətir-sətir ledger ilə BAYT-BAYT eyni nəticə.

Bu modul sürət optimallaşdırmasıdır, ona görə əsas sübut PARİTETdir: eyni
qərarlar üçün batch yolu ``upsert_entity_map``/``upsert_issue`` ilə eyni
sətirləri, eyni dəyərlərlə və eyni xəta kodları ilə yazır.
"""

from django.core.exceptions import ValidationError
from django.db.models.signals import post_save

import pytest

from apps.legacy_import.models import (
    LegacyEntityMap,
    LegacyEntityObservation,
    LegacyMigrationIssue,
    LegacyMigrationRun,
)
from apps.legacy_import.review_models import LegacyEntityMapVersion
from apps.legacy_import.services.ledger import (
    LegacyLedgerAuthorizationError,
    LegacyLedgerConflictError,
    LegacyLedgerTargetError,
    TargetValidation,
    create_run,
    start_run,
    upsert_entity_map,
    upsert_issue,
)
from apps.legacy_import.services.ledger_batch import (
    BATCH_ROWS,
    IssueRequest,
    SealRequest,
    record_issues,
    seal_entity_maps,
)
from apps.organizations.models import Organization
from apps.organizations.signals import create_default_roles
from core.constants import OrganizationType

SHA_A = "a" * 64
SHA_B = "b" * 64
LABEL = "registrar.enrollment"
SNAPSHOT_FIELDS = (
    "source_row_hash",
    "transform_version",
    "target_model_label",
    "target_pk",
    "state",
    "reconciliation_status",
)


def _allow(**_kwargs):
    return True


def _deny(**_kwargs):
    return False


def _valid_target(**_kwargs):
    return TargetValidation(exists=True, organization_matches=True)


def _missing_target(**_kwargs):
    return TargetValidation(exists=False, organization_matches=False)


VALIDATORS = {LABEL: _valid_target}


def _organization(django_user_model, code):
    owner = django_user_model.objects.create_user(
        username=f"batch_{code}_owner", email=f"batch-{code}@example.test", password="test-only"
    )
    post_save.disconnect(create_default_roles, sender=Organization)
    try:
        organization = Organization.objects.create(
            name=f"Batch {code}",
            slug=f"batch-{code}",
            org_type=OrganizationType.UNIVERSITY,
            owner=owner,
            status="active",
            is_active=True,
        )
    finally:
        post_save.connect(create_default_roles, sender=Organization)
    return organization, owner


def _running_run(organization, actor, *, snapshot=SHA_A):
    run = create_run(
        actor=actor,
        authorize=_allow,
        organization=organization,
        source_system="myedu_mariadb",
        snapshot_sha256=snapshot,
        snapshot_size_bytes=100,
        source_row_count=10,
        schema_version="legacy-v1",
        transform_version="transform-v1",
        mode=LegacyMigrationRun.Mode.REHEARSAL,
    )
    return start_run(run_id=run.pk, actor=actor, authorize=_allow)


@pytest.fixture()
def batch_env(db, django_user_model):
    organization, actor = _organization(django_user_model, "primary")
    return organization, actor, _running_run(organization, actor)


def _snapshot(queryset):
    return sorted(
        tuple(getattr(row, field) for field in SNAPSHOT_FIELDS) + (row.legacy_pk,)
        for row in queryset.select_related(None)
    )


# ── paritet ──────────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_the_batch_seal_writes_the_same_ledger_rows_as_the_row_by_row_upsert(django_user_model):
    """Eyni qərarlar → eyni map/version/observation dəyərləri.

    Canonical map açarı ``(org, source_system, entity_type, legacy_pk)``-dır, ona
    görə paritet İKİ AYRI tenantda ölçülür: eyni org-da ikinci run onsuz da
    mövcud map-a müşahidə yazardı və müqayisə mənasız olardı.
    """

    row_organization, actor = _organization(django_user_model, "parity-row")
    batch_organization, batch_actor = _organization(django_user_model, "parity-batch")
    row_run = _running_run(row_organization, actor, snapshot=SHA_A)
    batch_run = _running_run(batch_organization, batch_actor, snapshot=SHA_A)
    decisions = [
        ("jrn-1:41", SHA_A, LegacyEntityMap.State.MIGRATED, LABEL, "target-41"),
        ("jrn-1:42", SHA_B, LegacyEntityMap.State.SKIPPED, "", ""),
        ("jrn-2", SHA_A, LegacyEntityMap.State.QUARANTINED, "", ""),
    ]
    for legacy_pk, row_hash, state, label, target_pk in decisions:
        upsert_entity_map(
            run_id=row_run.pk,
            actor=actor,
            authorize=_allow,
            entity_type="journal_enrollment",
            legacy_pk=legacy_pk,
            source_row_hash=row_hash,
            state=state,
            target_model_label=label,
            target_pk=target_pk,
            target_validators=VALIDATORS,
        )

    seal_entity_maps(
        run_id=batch_run.pk,
        actor=batch_actor,
        authorize=_allow,
        entity_type="journal_enrollment",
        requests=[
            SealRequest(
                legacy_pk=legacy_pk,
                source_row_hash=row_hash,
                state=state,
                target_model_label=label,
                target_pk=target_pk,
            )
            for legacy_pk, row_hash, state, label, target_pk in decisions
        ],
        target_validators=VALIDATORS,
    )

    row_maps = LegacyEntityMap.objects.filter(created_run=row_run)
    batch_maps = LegacyEntityMap.objects.filter(created_run=batch_run)
    assert _snapshot(row_maps) == _snapshot(batch_maps)
    assert row_maps.count() == batch_maps.count() == 3
    assert (
        LegacyEntityObservation.objects.filter(run=row_run).count()
        == LegacyEntityObservation.objects.filter(run=batch_run).count()
        == 3
    )
    assert (
        LegacyEntityMapVersion.objects.filter(recorded_run=row_run).count()
        == LegacyEntityMapVersion.objects.filter(recorded_run=batch_run).count()
        == 3
    )
    assert all(version.version_number == 1 for version in LegacyEntityMapVersion.objects.all())


@pytest.mark.django_db
def test_the_batch_issue_writer_matches_the_row_by_row_issue_upsert(batch_env):
    organization, actor, run = batch_env
    entity_maps = seal_entity_maps(
        run_id=run.pk,
        actor=actor,
        authorize=_allow,
        entity_type="lesson",
        requests=[SealRequest(legacy_pk="17", source_row_hash=SHA_A, state=LegacyEntityMap.State.SKIPPED)],
        target_validators=VALIDATORS,
    )
    record_issues(
        run_id=run.pk,
        actor=actor,
        authorize=_allow,
        source_table="journals_dates_added_by_teacher",
        entity_type="lesson",
        requests=[
            IssueRequest(
                legacy_pk="17", rule_code="legacy_journal_lesson_orphan", severity="info", payload_digest=SHA_A
            )
        ],
        entity_maps=entity_maps,
    )

    issue = LegacyMigrationIssue.objects.get(run=run, legacy_pk="17")
    assert issue.rule_code == "legacy_journal_lesson_orphan"
    assert issue.severity == "info"
    assert issue.review_status == LegacyMigrationIssue.ReviewStatus.OPEN
    assert issue.entity_map_id == entity_maps["17"].pk
    assert issue.payload_digest == SHA_A

    # Sətir-sətir upsert eyni sətri təkrar yazmır (idempotent).
    upsert_issue(
        run_id=run.pk,
        actor=actor,
        authorize=_allow,
        source_table="journals_dates_added_by_teacher",
        entity_type="lesson",
        legacy_pk="17",
        rule_code="legacy_journal_lesson_orphan",
        severity="info",
        payload_digest=SHA_A,
        entity_map_id=entity_maps["17"].pk,
    )
    assert LegacyMigrationIssue.objects.filter(run=run).count() == 1


# ── idempotentlik / resume ───────────────────────────────────────────────────


@pytest.mark.django_db
def test_resealing_the_same_decision_is_idempotent(batch_env):
    organization, actor, run = batch_env
    requests = [SealRequest(legacy_pk="jrn-1:41", source_row_hash=SHA_A, state=LegacyEntityMap.State.SKIPPED)]
    for _attempt in range(3):
        seal_entity_maps(
            run_id=run.pk,
            actor=actor,
            authorize=_allow,
            entity_type="journal_enrollment",
            requests=requests,
            target_validators=VALIDATORS,
        )

    assert LegacyEntityMap.objects.count() == 1
    assert LegacyEntityObservation.objects.count() == 1
    assert LegacyEntityMapVersion.objects.count() == 1


@pytest.mark.django_db
def test_a_changed_decision_for_the_same_key_fails_closed(batch_env):
    organization, actor, run = batch_env
    seal_entity_maps(
        run_id=run.pk,
        actor=actor,
        authorize=_allow,
        entity_type="journal_enrollment",
        requests=[SealRequest(legacy_pk="jrn-1:41", source_row_hash=SHA_A, state=LegacyEntityMap.State.SKIPPED)],
        target_validators=VALIDATORS,
    )

    with pytest.raises(LegacyLedgerConflictError) as exc_info:
        seal_entity_maps(
            run_id=run.pk,
            actor=actor,
            authorize=_allow,
            entity_type="journal_enrollment",
            requests=[SealRequest(legacy_pk="jrn-1:41", source_row_hash=SHA_B, state=LegacyEntityMap.State.SKIPPED)],
            target_validators=VALIDATORS,
        )

    assert exc_info.value.code == "legacy_entity_identity_conflict"


@pytest.mark.django_db
def test_two_different_decisions_for_one_key_inside_one_chunk_fail_closed(batch_env):
    organization, actor, run = batch_env

    with pytest.raises(LegacyLedgerConflictError) as exc_info:
        seal_entity_maps(
            run_id=run.pk,
            actor=actor,
            authorize=_allow,
            entity_type="journal_enrollment",
            requests=[
                SealRequest(legacy_pk="jrn-1:41", source_row_hash=SHA_A, state=LegacyEntityMap.State.SKIPPED),
                SealRequest(legacy_pk="jrn-1:41", source_row_hash=SHA_A, state=LegacyEntityMap.State.QUARANTINED),
            ],
            target_validators=VALIDATORS,
        )

    assert exc_info.value.code == "legacy_entity_identity_conflict"
    assert LegacyEntityMap.objects.count() == 0


# ── fail-closed qapıları ─────────────────────────────────────────────────────


@pytest.mark.django_db
def test_the_target_allowlist_gate_holds_on_the_batch_path(batch_env):
    organization, actor, run = batch_env

    with pytest.raises(LegacyLedgerTargetError) as exc_info:
        seal_entity_maps(
            run_id=run.pk,
            actor=actor,
            authorize=_allow,
            entity_type="journal_enrollment",
            requests=[
                SealRequest(
                    legacy_pk="jrn-1:41",
                    source_row_hash=SHA_A,
                    state=LegacyEntityMap.State.MIGRATED,
                    target_model_label="registrar.unregistered",
                    target_pk="x",
                )
            ],
            target_validators=VALIDATORS,
        )

    assert exc_info.value.code == "legacy_target_unregistered"


@pytest.mark.django_db
def test_a_bulk_validator_that_misses_a_key_falls_back_to_the_row_validator(batch_env):
    """Toplu validator "yoxdur" desə, dəqiq kod sətir-başına validatordan gəlir."""

    organization, actor, run = batch_env

    with pytest.raises(LegacyLedgerTargetError) as exc_info:
        seal_entity_maps(
            run_id=run.pk,
            actor=actor,
            authorize=_allow,
            entity_type="journal_enrollment",
            requests=[
                SealRequest(
                    legacy_pk="jrn-1:41",
                    source_row_hash=SHA_A,
                    state=LegacyEntityMap.State.MIGRATED,
                    target_model_label=LABEL,
                    target_pk="target-41",
                )
            ],
            target_validators={LABEL: _missing_target},
            bulk_target_validators={LABEL: lambda *, target_pks, organization: set()},
        )

    assert exc_info.value.code == "legacy_target_not_found"
    assert LegacyEntityMap.objects.count() == 0


@pytest.mark.django_db
def test_an_unauthorized_actor_cannot_seal_in_batch(batch_env):
    organization, actor, run = batch_env

    with pytest.raises(LegacyLedgerAuthorizationError) as exc_info:
        seal_entity_maps(
            run_id=run.pk,
            actor=actor,
            authorize=_deny,
            entity_type="journal_enrollment",
            requests=[SealRequest(legacy_pk="jrn-1:41", source_row_hash=SHA_A, state=LegacyEntityMap.State.SKIPPED)],
            target_validators=VALIDATORS,
        )

    assert exc_info.value.code == "legacy_authorization_denied"
    assert LegacyEntityMap.objects.count() == 0


@pytest.mark.django_db
def test_field_validators_still_reject_a_malformed_opaque_key(batch_env):
    """``validate_columns`` regex qapısını saxlayır (FK sorğuları çıxarılıb)."""

    organization, actor, run = batch_env

    with pytest.raises(ValidationError):
        seal_entity_maps(
            run_id=run.pk,
            actor=actor,
            authorize=_allow,
            entity_type="journal_enrollment",
            requests=[SealRequest(legacy_pk="boşluq var", source_row_hash=SHA_A, state="skipped")],
            target_validators=VALIDATORS,
        )

    assert LegacyEntityMap.objects.count() == 0


@pytest.mark.django_db
def test_an_issue_without_its_own_map_is_refused(batch_env):
    organization, actor, run = batch_env

    with pytest.raises(LegacyLedgerConflictError) as exc_info:
        record_issues(
            run_id=run.pk,
            actor=actor,
            authorize=_allow,
            source_table="journals",
            entity_type="journal_enrollment",
            requests=[
                IssueRequest(
                    legacy_pk="jrn-1:41",
                    rule_code="legacy_journal_lesson_orphan",
                    severity="info",
                    payload_digest=SHA_A,
                )
            ],
            entity_maps={},
        )

    assert exc_info.value.code == "legacy_issue_map_not_found"


# ── dəstə sərhədi ────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_more_requests_than_one_chunk_are_written_in_order(batch_env):
    organization, actor, run = batch_env
    total = BATCH_ROWS + 5
    requests = [
        SealRequest(legacy_pk=f"jrn-1:{index}", source_row_hash=SHA_A, state=LegacyEntityMap.State.SKIPPED)
        for index in range(total)
    ]

    sealed = seal_entity_maps(
        run_id=run.pk,
        actor=actor,
        authorize=_allow,
        entity_type="journal_enrollment",
        requests=requests,
        target_validators=VALIDATORS,
    )

    assert len(sealed) == total
    assert LegacyEntityMap.objects.count() == total
    assert LegacyEntityObservation.objects.filter(run=run).count() == total
