import re
from collections.abc import Sequence

from django.core import mail
from django.db import connection
from django.db.models.signals import post_save
from django.test.utils import CaptureQueriesContext

import pytest

from apps.accounts.models import UserProfile
from apps.legacy_import.services.account_cutover import (
    AccountCutoverOutcome,
    EmailTrustDecision,
    LegacyAccountCutoverError,
    ProjectedAccountIdentity,
    classify_projected_account_cutover,
    deny_all_email_trust,
    stage_classified_account_cutover,
)
from apps.legacy_import.services.field_contracts import (
    STUDENT_IDENTITY_FIELDS,
    WORKER_IDENTITY_FIELDS,
    LegacyFieldContractError,
    LegacySourceFieldContract,
    compile_safe_projection,
)
from apps.organizations.models import Membership, Organization, Role
from apps.organizations.signals import create_default_roles
from core.constants import OrganizationType, RoleScopeType


def _projected_row(contract, *, email, source_id):
    projection = compile_safe_projection(contract, discovered_fields=contract.allowed_fields)
    values = {field_name: None for field_name in contract.allowed_fields}
    values["id"] = source_id
    values["email"] = email
    return projection.accept_extracted_row(values)


def _identity(*, email, username, worker=False, source_id=1):
    contract = WORKER_IDENTITY_FIELDS if worker else STUDENT_IDENTITY_FIELDS
    return ProjectedAccountIdentity(
        projected_row=_projected_row(contract, email=email, source_id=source_id),
        proposed_username=username,
    )


def _authoritative(_identity):
    return EmailTrustDecision.AUTHORITATIVE


@pytest.mark.django_db
def test_authoritative_unique_identity_is_only_classified_for_locked_staging():
    identity = _identity(email="new.student@example.com", username=" NewStudent ")

    result = classify_projected_account_cutover(
        [identity],
        authoritative_email_policy=_authoritative,
    )[0]

    assert result.outcome is AccountCutoverOutcome.LOCKED_STAGING_ELIGIBLE
    assert result.rule_codes == ()
    assert result.to_safe_log_dict() == {
        "cohort_index": 0,
        "outcome": "locked_staging_eligible",
        "rule_codes": (),
        "source_kind": "student",
        "validation_result": "eligible",
    }
    assert mail.outbox == []


@pytest.mark.django_db
def test_default_deny_and_non_enum_true_never_establish_email_authority():
    identities = (
        _identity(email="deny@example.com", username="deny_user", source_id=1),
        _identity(email="bool@example.com", username="bool_user", source_id=2),
    )

    denied = classify_projected_account_cutover(
        [identities[0]],
        authoritative_email_policy=deny_all_email_trust,
    )[0]
    boolean_true = classify_projected_account_cutover(
        [identities[1]],
        authoritative_email_policy=lambda _identity: True,
    )[0]

    assert denied.outcome is AccountCutoverOutcome.CONTACT_VERIFICATION_REQUIRED
    assert boolean_true.outcome is AccountCutoverOutcome.CONTACT_VERIFICATION_REQUIRED
    assert denied.rule_codes == ("legacy_account_email_untrusted",)
    assert boolean_true.rule_codes == ("legacy_account_email_untrusted",)
    assert mail.outbox == []


@pytest.mark.django_db
def test_email_trust_policy_is_mandatory_and_exceptions_fail_closed():
    identity = _identity(email="policy@example.com", username="policy_user")

    with pytest.raises(TypeError):
        classify_projected_account_cutover([identity])

    def unavailable(_identity):
        raise RuntimeError("raw-policy-failure-value")

    result = classify_projected_account_cutover(
        [identity],
        authoritative_email_policy=unavailable,
    )[0]

    assert result.outcome is AccountCutoverOutcome.CONTACT_VERIFICATION_REQUIRED
    assert result.rule_codes == ("legacy_account_email_trust_policy_unavailable",)
    assert "raw-policy-failure-value" not in repr(result)


@pytest.mark.django_db
def test_blank_invalid_and_untrusted_email_are_stable_contact_blocks():
    identities = (
        _identity(email="", username="blank_email", source_id=1),
        _identity(email="not-an-email", username="invalid_email", source_id=2),
        _identity(email="untrusted@example.com", username="untrusted_email", source_id=3),
    )

    results = classify_projected_account_cutover(
        identities,
        authoritative_email_policy=deny_all_email_trust,
    )

    assert [result.outcome for result in results] == [
        AccountCutoverOutcome.CONTACT_VERIFICATION_REQUIRED,
        AccountCutoverOutcome.CONTACT_VERIFICATION_REQUIRED,
        AccountCutoverOutcome.CONTACT_VERIFICATION_REQUIRED,
    ]
    assert results[0].rule_codes == ("legacy_account_email_blank",)
    assert results[1].rule_codes == ("legacy_account_email_invalid",)
    assert results[2].rule_codes == ("legacy_account_email_untrusted",)


@pytest.mark.django_db
def test_case_insensitive_source_username_and_email_duplicates_require_review():
    policy_calls = []

    def policy(identity):
        policy_calls.append(identity.source_kind)
        return EmailTrustDecision.AUTHORITATIVE

    identities = (
        _identity(email="Shared@Example.com", username="DuplicateUser", source_id=1),
        _identity(
            email="shared@example.COM",
            username="duplicateuser",
            worker=True,
            source_id=2,
        ),
    )

    results = classify_projected_account_cutover(
        identities,
        authoritative_email_policy=policy,
    )

    assert all(result.outcome is AccountCutoverOutcome.MANUAL_REVIEW_REQUIRED for result in results)
    assert all("legacy_account_username_duplicate_source" in result.rule_codes for result in results)
    assert all("legacy_account_email_duplicate_source" in result.rule_codes for result in results)
    assert policy_calls == []
    assert mail.outbox == []


@pytest.mark.django_db
def test_existing_user_and_membership_remain_byte_for_byte_unchanged(django_user_model):
    existing = django_user_model.objects.create_user(
        username="ExistingUser",
        email="existing@example.com",
        password="Existing-Password-Only!",
        is_active=True,
    )
    profile = existing.profile
    profile.email_verified = True
    profile.password_change_required = False
    profile.save(update_fields=["email_verified", "password_change_required", "updated_at"])

    post_save.disconnect(create_default_roles, sender=Organization)
    try:
        organization = Organization.objects.create(
            name="Cutover invariant organization",
            slug="cutover-invariant-organization",
            org_type=OrganizationType.UNIVERSITY,
            owner=existing,
        )
    finally:
        post_save.connect(create_default_roles, sender=Organization)
    role = Role.objects.create(
        organization=organization,
        name="student",
        display_name="Student",
        level=10,
        scope_type=RoleScopeType.ORGANIZATION,
        permissions=[],
    )
    membership = Membership.objects.create(
        user=existing,
        organization=organization,
        role=role,
        assigned_by=existing,
        is_primary=True,
        is_active=True,
    )

    before_user = {
        "password": existing.password,
        "is_active": existing.is_active,
        "email": existing.email,
    }
    before_profile = {
        "email_verified": profile.email_verified,
        "password_change_required": profile.password_change_required,
        "updated_at": profile.updated_at,
    }
    before_membership = {
        "role_id": membership.role_id,
        "scope_unit_id": membership.scope_unit_id,
        "is_primary": membership.is_primary,
        "is_active": membership.is_active,
        "updated_at": membership.updated_at,
    }
    identity = _identity(
        email="EXISTING@example.COM",
        username=" existinguser ",
    )

    with CaptureQueriesContext(connection) as queries:
        result = classify_projected_account_cutover(
            [identity],
            authoritative_email_policy=_authoritative,
        )[0]

    existing.refresh_from_db()
    profile.refresh_from_db()
    membership.refresh_from_db()

    assert result.outcome is AccountCutoverOutcome.MANUAL_REVIEW_REQUIRED
    assert "legacy_account_username_collision" in result.rule_codes
    assert "legacy_account_email_collision" in result.rule_codes
    assert {
        "password": existing.password,
        "is_active": existing.is_active,
        "email": existing.email,
    } == before_user
    assert {
        "email_verified": profile.email_verified,
        "password_change_required": profile.password_change_required,
        "updated_at": profile.updated_at,
    } == before_profile
    assert {
        "role_id": membership.role_id,
        "scope_unit_id": membership.scope_unit_id,
        "is_primary": membership.is_primary,
        "is_active": membership.is_active,
        "updated_at": membership.updated_at,
    } == before_membership
    assert all(not re.search(r"\b(?:INSERT|UPDATE|DELETE)\b", query["sql"], re.IGNORECASE) for query in queries)
    assert mail.outbox == []


def test_existing_duplicate_email_probe_is_reported_without_raw_identity_values():
    raw_email = "duplicate-owner@example.com"

    class ProbeQuery:
        def __init__(self, count):
            self._count = count

        def count(self):
            return self._count

    class ProbeManager:
        def filter(self, **lookup):
            return ProbeQuery(2 if lookup.get("email__iexact") == raw_email else 0)

    class ProbeUserModel:
        _default_manager = ProbeManager()

    identity = _identity(email=raw_email, username="fresh_username")

    result = classify_projected_account_cutover(
        [identity],
        authoritative_email_policy=_authoritative,
        user_model=ProbeUserModel,
    )[0]

    assert result.outcome is AccountCutoverOutcome.MANUAL_REVIEW_REQUIRED
    assert result.rule_codes == (
        "legacy_account_email_collision",
        "legacy_account_email_duplicate_existing",
    )
    assert raw_email not in repr(identity)
    assert raw_email not in repr(result)
    assert raw_email not in str(identity.to_safe_log_dict())
    assert raw_email not in str(result.to_safe_log_dict())


@pytest.mark.django_db
def test_complete_cohort_reads_existing_target_identities_once(django_user_model):
    django_user_model.objects.create_user(
        username="snapshot_existing",
        email="snapshot-existing@example.com",
        password="test-only",
    )
    identities = tuple(
        _identity(
            email=f"snapshot-{index}@example.com",
            username=f"snapshot_candidate_{index}",
            source_id=index,
        )
        for index in range(1, 31)
    )

    with CaptureQueriesContext(connection) as queries:
        results = classify_projected_account_cutover(
            identities,
            authoritative_email_policy=_authoritative,
        )

    auth_user_reads = [
        query["sql"] for query in queries if re.search(r'\bFROM\s+["`]?auth_user["`]?', query["sql"], re.IGNORECASE)
    ]
    assert len(results) == 30
    assert len(auth_user_reads) == 1


@pytest.mark.django_db
def test_approved_classification_bridges_only_to_locked_staging(django_user_model):
    actor = django_user_model.objects.create_superuser(
        username="cutover_stage_actor",
        email="cutover-stage-actor@example.com",
        password="test-only",
    )
    organization = Organization.objects.create(
        name="Cutover staging organization",
        slug="cutover-staging-organization",
        org_type=OrganizationType.UNIVERSITY,
        owner=actor,
        status="active",
        is_active=True,
    )
    role = organization.roles.get(name="student")
    identity = _identity(email="bridge@example.com", username=" BridgeUser ")
    classification = classify_projected_account_cutover(
        [identity],
        authoritative_email_policy=_authoritative,
    )[0]

    result = stage_classified_account_cutover(
        identity=identity,
        classification=classification,
        organization=organization,
        role=role,
        actor=actor,
        student_identifier=" BRIDGE-1001 ",
    )

    result.user.refresh_from_db()
    assert result.created is True
    assert result.user.is_active is False
    assert result.user.has_usable_password() is False
    assert result.user.profile.access_state == UserProfile.AccessState.STAGED
    assert result.user.profile.institutional_identifier == "BRIDGE-1001"
    assert result.user.memberships.get(organization=organization).is_active is False
    assert mail.outbox == []


@pytest.mark.django_db
def test_unapproved_or_unmapped_student_classification_cannot_stage(django_user_model):
    actor = django_user_model.objects.create_superuser(
        username="cutover_block_actor",
        email="cutover-block-actor@example.com",
        password="test-only",
    )
    organization = Organization.objects.create(
        name="Cutover block organization",
        slug="cutover-block-organization",
        org_type=OrganizationType.UNIVERSITY,
        owner=actor,
        status="active",
        is_active=True,
    )
    role = organization.roles.get(name="student")
    identity = _identity(email="blocked-bridge@example.com", username="blocked_bridge")
    denied = classify_projected_account_cutover(
        [identity],
        authoritative_email_policy=deny_all_email_trust,
    )[0]
    with pytest.raises(LegacyAccountCutoverError, match="legacy_account_staging_not_approved"):
        stage_classified_account_cutover(
            identity=identity,
            classification=denied,
            organization=organization,
            role=role,
            actor=actor,
            student_identifier="BLOCK-1001",
        )

    approved = classify_projected_account_cutover(
        [identity],
        authoritative_email_policy=_authoritative,
    )[0]
    with pytest.raises(LegacyAccountCutoverError, match="legacy_account_student_identifier_required"):
        stage_classified_account_cutover(
            identity=identity,
            classification=approved,
            organization=organization,
            role=role,
            actor=actor,
        )
    assert not django_user_model.objects.filter(username="blocked_bridge").exists()
    assert mail.outbox == []


def test_credential_fields_and_plain_mappings_cannot_enter_classifier_contract():
    raw_secret = "never-enter-classifier"

    with pytest.raises(LegacyFieldContractError) as field_error:
        LegacySourceFieldContract(
            source_table="students",
            version="unsafe-v1",
            allowed_fields=("id", "password"),
        )
    with pytest.raises(LegacyAccountCutoverError) as input_error:
        ProjectedAccountIdentity(
            projected_row={"id": 1, "email": "safe@example.com", "password": raw_secret},
            proposed_username="safe_username",
        )

    assert field_error.value.code == "legacy_credential_field_forbidden"
    assert input_error.value.code == "legacy_account_projection_required"
    assert raw_secret not in str(field_error.value)
    assert raw_secret not in str(input_error.value)


class _ExplodingIdentityCohort(Sequence):
    def __len__(self):
        return 1

    def __getitem__(self, _index):
        raise RuntimeError("postgresql://raw-user:raw-password@private-host/private-db")

    def __iter__(self):
        raise RuntimeError("student@example.com")


def test_cohort_iteration_failure_is_sanitized_without_dsn_or_pii():
    with pytest.raises(LegacyAccountCutoverError) as exc_info:
        classify_projected_account_cutover(
            _ExplodingIdentityCohort(),
            authoritative_email_policy=deny_all_email_trust,
        )

    assert exc_info.value.code == "legacy_account_identity_cohort_invalid"
    assert "postgresql://" not in str(exc_info.value)
    assert "raw-password" not in str(exc_info.value)
    assert "student@example.com" not in str(exc_info.value)


def test_accounts_module_has_no_reverse_dependency_on_legacy_import():
    from scripts.module_deps import build_graph

    dependencies, _core_dependencies = build_graph()

    assert "legacy_import" not in dependencies.get("accounts", set())
