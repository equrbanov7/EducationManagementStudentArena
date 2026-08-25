import datetime
import decimal
import re
from collections.abc import Mapping

from django.core.exceptions import ValidationError
from django.db.models.signals import post_save

import pytest

from apps.legacy_import.models import MODEL_LABEL_PATTERN, token_validator
from apps.legacy_import.services import rehearsal_contracts as contracts
from apps.legacy_import.services.field_contracts import STUDENT_IDENTITY_FIELDS, compile_safe_projection
from apps.legacy_import.services.ledger import LedgerAction, TargetValidation
from apps.legacy_import.services.rehearsal_authorizer import (
    CURRICULUM_MODEL_LABEL,
    CURRICULUM_SUBJECT_MODEL_LABEL,
    ORG_UNIT_MODEL_LABEL,
    PROGRAM_MODEL_LABEL,
    STUDENT_RECORD_MODEL_LABEL,
    SUBJECT_MODEL_LABEL,
    USER_MODEL_LABEL,
    build_rehearsal_authorizer,
    build_target_validators,
)
from apps.legacy_import.services.rehearsal_contracts import (
    DEFAULT_BATCH_ROWS,
    MAX_STABLE_TEXT_BYTES,
    EmailTrustPolicy,
    LegacyRehearsalConfigError,
    LegacyRehearsalEvidenceError,
    OrderedDigest,
    PlanSemesterScheme,
    RehearsalPolicy,
    SarCurriculumFallback,
    StudentIdentifierPolicy,
    UsernamePolicy,
    canonical_json_digest,
    compute_phase_registry_fingerprint,
    load_rehearsal_phase_registry,
    source_row_hash,
    stable_source_value,
    validate_rehearsal_phases,
)
from apps.legacy_import.services.table_plan import TABLE_PLAN_VERSION, load_legacy_table_plan
from apps.organizations.models import Membership, Organization, Role
from apps.organizations.signals import create_default_roles
from apps.registrar.models import Subject
from core.constants import OrganizationType, RoleScopeType


class _StubPhase:
    """Registry member used to exercise the validator without an adapter."""

    def __init__(self, *, phase_key, order, source_tables, entity_types=("student",), declared_rows=None):
        self.phase_key = phase_key
        self.order = order
        self.source_tables = source_tables
        self.entity_types = entity_types
        self._declared_rows = declared_rows

    def declared_source_rows(self, plan):
        if self._declared_rows is not None:
            return self._declared_rows
        return sum(plan.entry_for(source_table).expected_rows for source_table in self.source_tables)

    def run(self, context):  # pragma: no cover - the validator never runs a phase
        raise AssertionError("the registry validator must never run a phase")


class _ReversedRow(Mapping):
    """Projected row whose iteration order is reversed but lookups are not."""

    def __init__(self, row):
        self._row = row

    def __getitem__(self, key):
        return self._row[key]

    def __iter__(self):
        return iter(tuple(reversed(tuple(self._row))))

    def __len__(self):
        return len(self._row)


def _policy(**overrides):
    values = {
        "phase_keys": ("identity_cohort",),
        "username_policy": UsernamePolicy.LEGACY_KEY,
        "student_identifier_policy": StudentIdentifierPolicy.LEGACY_PK,
        "email_trust_policy": EmailTrustPolicy.DENY_ALL,
        "email_trust_manifest_digest": "",
        "batch_rows": DEFAULT_BATCH_ROWS,
        "source_chunk_size": 1_000,
        "max_staged_accounts": 0,
        "student_role_name": "",
        "worker_role_name": "",
    }
    values.update(overrides)
    return RehearsalPolicy(**values)


def _student_row(**overrides):
    values = {field_name: "" for field_name in STUDENT_IDENTITY_FIELDS.allowed_fields}
    values.update(
        {
            "id": 7421,
            "first_name": "Aysel",
            "last_name": "Quliyeva",
            "email": "aysel@example.test",
            "group_id": 12,
            "birthday": datetime.date(2001, 5, 4),
            "fincode": None,
        }
    )
    values.update(overrides)
    projection = compile_safe_projection(
        STUDENT_IDENTITY_FIELDS,
        discovered_fields=STUDENT_IDENTITY_FIELDS.allowed_fields,
    )
    return projection.accept_extracted_row(values)


def _make_organization(django_user_model, code):
    owner = django_user_model.objects.create_user(
        username=f"rehearsal_{code}_owner",
        email=f"rehearsal-{code}@example.test",
        password="test-only",
    )
    post_save.disconnect(create_default_roles, sender=Organization)
    try:
        organization = Organization.objects.create(
            name=f"Rehearsal {code.title()} Organization",
            slug=f"rehearsal-{code}-organization",
            org_type=OrganizationType.UNIVERSITY,
            owner=owner,
            status="active",
            is_active=True,
        )
    finally:
        post_save.connect(create_default_roles, sender=Organization)
    return organization, owner


def _grant(organization, user, *, permissions, role_active=True, membership_active=True, name="importer"):
    role = Role.objects.create(
        organization=organization,
        name=name,
        display_name=name.title(),
        level=60,
        scope_type=RoleScopeType.ORGANIZATION,
        permissions=list(permissions),
        is_active=role_active,
    )
    return Membership.objects.create(
        user=user,
        organization=organization,
        role=role,
        is_primary=True,
        is_active=membership_active,
    )


def test_phase_registry_fingerprint_is_pinned():
    registry = load_rehearsal_phase_registry()

    assert compute_phase_registry_fingerprint(registry) == contracts._EXPECTED_PHASE_REGISTRY_FINGERPRINT
    # The pin is hardened HERE as a literal on purpose: a registry change must
    # update BOTH the constant and this line consciously (SLICE 3A gate 5).
    assert (
        contracts._EXPECTED_PHASE_REGISTRY_FINGERPRINT
        == "71f2001f8e2f43cdb64c2a3f7a0d739deb7bef5aafd359171eda2d9d5ca9c0d8"
    )
    assert [phase.phase_key for phase in registry] == [
        "academic_structure",
        "academic_catalog",
        "identity_cohort",
        "student_placement",
        "worker_materialisation",
        "sar_materialisation",
    ]
    # Structure (supplies Program) before the catalogue that resolves against
    # it, before identity, before placement, before the worker scope pass, and
    # before the record that needs all of them — strictly ascending, with 30
    # left free for the syllabus domain.  Every derived phase accounts for no
    # source table at all (D-2 / E-2 / V-22).
    assert [phase.order for phase in registry] == [10, 12, 20, 25, 26, 28]
    assert [tuple(phase.source_tables) for phase in registry] == [
        ("departments", "speciality", "groups"),
        ("lessons", "curricula", "curricula_plan"),
        ("students", "workers"),
        (),
        (),
        (),
    ]
    # The six-phase run accounts for exactly 880 + 6 071 + 8 545 source rows.
    assert sum(phase.declared_source_rows(load_legacy_table_plan()) for phase in registry) == 15_496


def test_registry_rejects_a_second_claim_on_students_beside_the_identity_phase():
    """A derived phase must not re-claim a table the identity phase accounts for."""

    from apps.legacy_import.services.rehearsal_identity_phase import IdentityCohortPhase

    plan = load_legacy_table_plan()
    double_claim = _StubPhase(
        phase_key="student_placement",
        order=25,
        source_tables=("students",),
        entity_types=("student_placement",),
    )

    with pytest.raises(LegacyRehearsalConfigError) as exc_info:
        validate_rehearsal_phases((IdentityCohortPhase(), double_claim), plan=plan)

    assert exc_info.value.code == "legacy_rehearsal_phase_table_conflict"


def test_registry_accepts_a_batch_less_phase():
    """``source_tables = ()`` means ACCOUNTS FOR nothing, not READS nothing."""

    plan = load_legacy_table_plan()
    derived = _StubPhase(
        phase_key="student_placement",
        order=25,
        source_tables=(),
        entity_types=("student_placement",),
        declared_rows=0,
    )

    validated = validate_rehearsal_phases((derived,), plan=plan)

    assert validated == (derived,)
    assert derived.declared_source_rows(plan) == 0


@pytest.mark.parametrize(
    "gated_table",
    ["sillabus", "students_telegram", "ntg", "curricula_tam", "books"],
)
def test_registry_rejects_design_gated_table(gated_table):
    plan = load_legacy_table_plan()
    phase = _StubPhase(phase_key="identity_cohort", order=20, source_tables=(gated_table,))

    with pytest.raises(LegacyRehearsalConfigError) as exc_info:
        validate_rehearsal_phases((phase,), plan=plan)

    assert exc_info.value.code == "legacy_rehearsal_phase_action_gated"


def test_registry_accepts_only_claimable_actions():
    plan = load_legacy_table_plan()
    phase = _StubPhase(
        phase_key="identity_cohort",
        order=20,
        source_tables=("students", "workers"),
        entity_types=("student", "worker"),
    )

    validated = validate_rehearsal_phases((phase,), plan=plan)

    assert validated == (phase,)
    assert phase.declared_source_rows(plan) == 7816 + 729


def test_registry_rejects_duplicate_table_claim():
    plan = load_legacy_table_plan()
    phases = (
        _StubPhase(phase_key="identity_cohort", order=20, source_tables=("students",)),
        _StubPhase(phase_key="second_cohort", order=30, source_tables=("students",)),
    )

    with pytest.raises(LegacyRehearsalConfigError) as exc_info:
        validate_rehearsal_phases(phases, plan=plan)

    assert exc_info.value.code == "legacy_rehearsal_phase_table_conflict"


def test_registry_rejects_duplicate_phase_key():
    plan = load_legacy_table_plan()
    phases = (
        _StubPhase(phase_key="identity_cohort", order=20, source_tables=("students",)),
        _StubPhase(phase_key="identity_cohort", order=30, source_tables=("workers",)),
    )

    with pytest.raises(LegacyRehearsalConfigError) as exc_info:
        validate_rehearsal_phases(phases, plan=plan)

    assert exc_info.value.code == "legacy_rehearsal_phase_key_invalid"


@pytest.mark.parametrize("second_order", [10, 20])
def test_registry_rejects_non_ascending_order(second_order):
    plan = load_legacy_table_plan()
    phases = (
        _StubPhase(phase_key="identity_cohort", order=20, source_tables=("students",)),
        _StubPhase(phase_key="second_cohort", order=second_order, source_tables=("workers",)),
    )

    with pytest.raises(LegacyRehearsalConfigError) as exc_info:
        validate_rehearsal_phases(phases, plan=plan)

    assert exc_info.value.code == "legacy_rehearsal_phase_order_invalid"


def test_registry_rejects_row_declaration_drift():
    plan = load_legacy_table_plan()
    phase = _StubPhase(
        phase_key="identity_cohort",
        order=20,
        source_tables=("students", "workers"),
        entity_types=("student", "worker"),
        declared_rows=7816 + 729 + 1,
    )

    with pytest.raises(LegacyRehearsalConfigError) as exc_info:
        validate_rehearsal_phases((phase,), plan=plan)

    assert exc_info.value.code == "legacy_rehearsal_phase_row_declaration_invalid"


def test_registry_rejects_unregistered_table_and_invalid_key():
    plan = load_legacy_table_plan()
    unregistered = _StubPhase(phase_key="identity_cohort", order=20, source_tables=("missing_table",))
    bad_key = _StubPhase(phase_key="Identity Cohort", order=20, source_tables=("students",))

    with pytest.raises(LegacyRehearsalConfigError) as exc_info:
        validate_rehearsal_phases((unregistered,), plan=plan)
    assert exc_info.value.code == "legacy_rehearsal_phase_table_unregistered"

    with pytest.raises(LegacyRehearsalConfigError) as exc_info:
        validate_rehearsal_phases((bad_key,), plan=plan)
    assert exc_info.value.code == "legacy_rehearsal_phase_key_invalid"

    with pytest.raises(LegacyRehearsalConfigError) as exc_info:
        validate_rehearsal_phases((), plan=plan)
    assert exc_info.value.code == "legacy_rehearsal_phase_registry_invalid"


def test_transform_version_is_token_valid_and_within_length():
    policy = _policy()
    transform_version = policy.transform_version()
    schema_version = f"{TABLE_PLAN_VERSION}.{load_legacy_table_plan().fingerprint[:12]}"

    # 21-char family + "." + 12 hex = 34 (the spec's "33 chars" is an off-by-one);
    # the binding invariants are TOKEN_PATTERN validity and max_length=64.
    assert transform_version.startswith("rehearsal-identity-v1.")
    assert len(transform_version) == 34
    assert len(schema_version) == 33
    for value in (transform_version, schema_version):
        assert len(value) <= 64
        token_validator(value)

    with pytest.raises(ValidationError):
        token_validator(f"{transform_version}!")


def test_policy_digest_is_order_independent_and_change_sensitive():
    forward = _policy(phase_keys=("a_cohort", "b_cohort"))
    reversed_keys = _policy(phase_keys=("b_cohort", "a_cohort"))

    assert forward.phase_keys == reversed_keys.phase_keys == ("a_cohort", "b_cohort")
    assert forward.policy_digest() == reversed_keys.policy_digest()
    assert forward.transform_version() == reversed_keys.transform_version()

    baseline = _policy().policy_digest()
    variants = [
        _policy(batch_rows=DEFAULT_BATCH_ROWS + 1),
        _policy(source_chunk_size=500),
        _policy(max_staged_accounts=2, student_role_name="student", worker_role_name="teacher"),
        _policy(email_trust_policy=EmailTrustPolicy.EVIDENCE_MANIFEST, email_trust_manifest_digest="a" * 64),
        _policy(phase_keys=("a_cohort",)),
    ]
    digests = {policy.policy_digest() for policy in variants}

    assert baseline not in digests
    assert len(digests) == len(variants)
    assert "email_trust_manifest_digest" in _policy().to_safe_log_dict()
    assert "manifest" not in repr(_policy(email_trust_policy=EmailTrustPolicy.DENY_ALL))


def test_policy_rejects_inconsistent_or_out_of_range_values():
    cases = {
        "legacy_rehearsal_policy_phase_keys_invalid": {"phase_keys": ()},
        "legacy_rehearsal_policy_email_trust_invalid": {"email_trust_manifest_digest": "a" * 64},
        "legacy_rehearsal_policy_batch_rows_invalid": {"batch_rows": 0},
        "legacy_rehearsal_policy_chunk_size_invalid": {"source_chunk_size": 10_001},
        "legacy_rehearsal_policy_staging_cap_invalid": {"max_staged_accounts": -1},
        "legacy_rehearsal_policy_role_name_required": {"max_staged_accounts": 1},
    }
    for code, overrides in cases.items():
        with pytest.raises(LegacyRehearsalConfigError) as exc_info:
            _policy(**overrides)
        assert exc_info.value.code == code

    with pytest.raises(LegacyRehearsalConfigError) as exc_info:
        _policy(email_trust_policy=EmailTrustPolicy.EVIDENCE_MANIFEST)
    assert exc_info.value.code == "legacy_rehearsal_policy_email_trust_invalid"


def _staging_policy(**overrides):
    """A policy whose staging cap is open, so the activation knobs are reachable."""

    values = {
        "max_staged_accounts": 8,
        "student_role_name": "student",
        "worker_role_name": "teacher",
    }
    values.update(overrides)
    return _policy(**values)


def test_activation_and_catalogue_knobs_default_closed():
    """SA-5: the first slice-2 rehearsal must touch no account and mint no plan."""

    policy = _policy()

    assert policy.stage_and_activate is False
    assert policy.max_activated_accounts == 0
    assert policy.sar_curriculum_fallback is SarCurriculumFallback.SYNTHESISE
    # V-13: payiz_N/yaz_N are ordinal semester numbers in the live dump.
    assert policy.plan_semester_scheme is PlanSemesterScheme.ORDINAL
    assert policy.to_safe_log_dict()["plan_semester_scheme"] == "ordinal"
    assert policy.to_safe_log_dict()["sar_curriculum_fallback"] == "synthesise"


def test_activation_policy_fields_bind_into_the_run_identity():
    """The activation decision is part of the run identity, not a module constant."""

    disabled = _staging_policy()
    enabled = _staging_policy(stage_and_activate=True, max_activated_accounts=8)

    assert disabled.policy_digest() != enabled.policy_digest()
    assert disabled.transform_version() != enabled.transform_version()

    baseline = enabled.policy_digest()
    variants = [
        _staging_policy(stage_and_activate=True, max_activated_accounts=4),
        _staging_policy(
            stage_and_activate=True,
            max_activated_accounts=8,
            sar_curriculum_fallback=SarCurriculumFallback.STRICT,
        ),
        _staging_policy(
            stage_and_activate=True,
            max_activated_accounts=8,
            plan_semester_scheme=PlanSemesterScheme.TERM_PAIR,
        ),
    ]
    digests = {policy.policy_digest() for policy in variants}

    assert baseline not in digests
    assert len(digests) == len(variants)

    payload = enabled.to_safe_log_dict()

    # Tokens and ints only — the four values are committed to the report artifact.
    assert payload["stage_and_activate"] is True
    assert payload["max_activated_accounts"] == 8
    assert payload["sar_curriculum_fallback"] == "synthesise"
    assert payload["plan_semester_scheme"] == "ordinal"
    for token in (payload["sar_curriculum_fallback"], payload["plan_semester_scheme"]):
        token_validator(token)


def test_transform_version_stays_bounded_with_the_activation_knobs():
    transform_version = _staging_policy(
        stage_and_activate=True,
        max_activated_accounts=8,
        sar_curriculum_fallback=SarCurriculumFallback.STRICT,
        plan_semester_scheme=PlanSemesterScheme.TERM_PAIR,
    ).transform_version()

    assert transform_version.startswith("rehearsal-identity-v1.")
    assert len(transform_version) == 34 <= 64
    token_validator(transform_version)


def test_policy_rejects_every_invalid_activation_or_catalogue_knob():
    cases = {
        "legacy_rehearsal_policy_invalid": {"stage_and_activate": 1},
        "legacy_rehearsal_policy_curriculum_fallback_invalid": {"sar_curriculum_fallback": "synthesise"},
        "legacy_rehearsal_policy_semester_scheme_invalid": {"plan_semester_scheme": "ordinal"},
    }
    for code, overrides in cases.items():
        with pytest.raises(LegacyRehearsalConfigError) as exc_info:
            _policy(**overrides)
        assert exc_info.value.code == code

    activation_cases = [
        # An open button with a closed blast-radius cap is a configuration bug.
        {"stage_and_activate": True, "max_activated_accounts": 0},
        {"max_activated_accounts": -1},
        {"max_activated_accounts": True},
        {"max_activated_accounts": 20_001},
        # The activation cap can never exceed the staging cap that feeds it.
        {"max_activated_accounts": 1},
    ]
    for overrides in activation_cases:
        with pytest.raises(LegacyRehearsalConfigError) as exc_info:
            _policy(**overrides)
        assert exc_info.value.code == "legacy_rehearsal_policy_activation_invalid"

    with pytest.raises(LegacyRehearsalConfigError) as exc_info:
        _staging_policy(stage_and_activate=True, max_activated_accounts=9)
    assert exc_info.value.code == "legacy_rehearsal_policy_activation_invalid"


def test_stable_source_value_covers_every_accepted_type_and_rejects_others():
    accepted = {
        "n:": None,
        "b:1": True,
        "b:0": False,
        "i:-7": -7,
        "f:" + (1.5).hex(): 1.5,
        "d:1.50": decimal.Decimal("1.50"),
        "s:a": "a",
        "y:0102": b"\x01\x02",
        "z:2026-01-02T03:04:05": datetime.datetime(2026, 1, 2, 3, 4, 5),
        "a:2026-01-02": datetime.date(2026, 1, 2),
        "c:03:04:05": datetime.time(3, 4, 5),
        "e:90.0": datetime.timedelta(seconds=90),
    }
    for expected, value in accepted.items():
        assert stable_source_value(value) == expected

    assert stable_source_value(bytearray(b"\x01\x02")) == "y:0102"
    assert stable_source_value("é") == stable_source_value("é")
    assert stable_source_value(True) != stable_source_value(1)
    assert stable_source_value(1) == "i:1"

    class _IntLike(int):
        pass

    for rejected in (object(), _IntLike(1), [1], {"a": 1}, (1,)):
        with pytest.raises(LegacyRehearsalEvidenceError) as exc_info:
            stable_source_value(rejected)
        assert exc_info.value.code == "legacy_rehearsal_source_value_type_unsupported"
        assert str(exc_info.value) == "legacy_rehearsal_source_value_type_unsupported"

    secret = "s" * (MAX_STABLE_TEXT_BYTES + 1)
    with pytest.raises(LegacyRehearsalEvidenceError) as exc_info:
        stable_source_value(secret)
    assert exc_info.value.code == "legacy_rehearsal_source_value_too_large"
    assert secret not in str(exc_info.value)


def test_source_row_hash_is_field_order_stable():
    row = _student_row()
    digest = source_row_hash(contract=STUDENT_IDENTITY_FIELDS, legacy_pk=7421, projected_row=row)

    assert digest == source_row_hash(
        contract=STUDENT_IDENTITY_FIELDS,
        legacy_pk=7421,
        projected_row=_ReversedRow(row),
    )
    assert tuple(_ReversedRow(row)) != tuple(row)
    assert digest != source_row_hash(
        contract=STUDENT_IDENTITY_FIELDS,
        legacy_pk=7422,
        projected_row=row,
    )
    swapped = _student_row(first_name="Quliyeva", last_name="Aysel")
    assert digest != source_row_hash(contract=STUDENT_IDENTITY_FIELDS, legacy_pk=7421, projected_row=swapped)

    with pytest.raises(LegacyRehearsalEvidenceError) as exc_info:
        source_row_hash(contract="students", legacy_pk=1, projected_row=row)
    assert exc_info.value.code == "legacy_rehearsal_source_row_contract_invalid"


def test_ordered_digest_is_order_sensitive():
    forward = OrderedDigest("legacy-rehearsal-source-v1")
    forward.advance("1")
    forward.advance("2")
    backward = OrderedDigest("legacy-rehearsal-source-v1")
    backward.advance("2")
    backward.advance("1")
    repeated = OrderedDigest("legacy-rehearsal-source-v1")
    repeated.advance("1")
    repeated.advance("2")
    other_namespace = OrderedDigest("legacy-rehearsal-target-v1")
    other_namespace.advance("1")
    other_namespace.advance("2")

    assert forward.hexdigest() == repeated.hexdigest()
    assert forward.hexdigest() != backward.hexdigest()
    assert forward.hexdigest() != other_namespace.hexdigest()

    split = OrderedDigest("legacy-rehearsal-source-v1")
    split.advance("a", "b")
    joined = OrderedDigest("legacy-rehearsal-source-v1")
    joined.advance("ab")

    assert split.hexdigest() != joined.hexdigest()
    assert len(forward.hexdigest()) == 64
    assert canonical_json_digest({"a": 1, "b": 2}) == canonical_json_digest({"b": 2, "a": 1})


@pytest.mark.django_db
def test_authorizer_allows_only_active_permitted_members(django_user_model):
    organization, owner = _make_organization(django_user_model, "authorizer")
    authorize = build_rehearsal_authorizer()
    permitted = django_user_model.objects.create_user(
        username="rehearsal-permitted",
        email="permitted@example.test",
        password="test-only",
    )
    _grant(organization, permitted, permissions=["member.invite"])
    wildcard = django_user_model.objects.create_user(
        username="rehearsal-wildcard",
        email="wildcard@example.test",
        password="test-only",
    )
    _grant(organization, wildcard, permissions=["*"], name="wildcard")

    assert authorize(actor=permitted, organization=organization, action=LedgerAction.CREATE_RUN) is True
    assert authorize(actor=wildcard, organization=organization, action=LedgerAction.UPSERT_MAP) is True
    assert authorize(actor=owner, organization=organization, action=LedgerAction.CREATE_RUN) is False


@pytest.mark.django_db
def test_authorizer_denies_inactive_actor_missing_org_and_foreign_action(django_user_model):
    organization, _owner = _make_organization(django_user_model, "denied")
    other_organization, _other_owner = _make_organization(django_user_model, "foreign")
    authorize = build_rehearsal_authorizer()
    actor = django_user_model.objects.create_user(
        username="rehearsal-denied",
        email="denied@example.test",
        password="test-only",
    )
    _grant(organization, actor, permissions=["member.invite"])

    assert authorize(actor=actor, organization=organization, action="legacy_import.create_run") is False
    assert authorize(actor=actor, organization=None, action=LedgerAction.CREATE_RUN) is False
    assert authorize(actor=None, organization=organization, action=LedgerAction.CREATE_RUN) is False
    assert authorize(actor=actor, organization=other_organization, action=LedgerAction.CREATE_RUN) is False

    actor.is_active = False
    actor.save(update_fields=["is_active"])
    assert authorize(actor=actor, organization=organization, action=LedgerAction.CREATE_RUN) is False


@pytest.mark.django_db
def test_authorizer_requires_active_membership_and_active_role(django_user_model):
    organization, _owner = _make_organization(django_user_model, "membership")
    authorize = build_rehearsal_authorizer()
    inactive_membership_actor = django_user_model.objects.create_user(
        username="rehearsal-inactive-membership",
        email="inactive-membership@example.test",
        password="test-only",
    )
    _grant(
        organization,
        inactive_membership_actor,
        permissions=["member.invite"],
        membership_active=False,
        name="inactive-membership",
    )
    inactive_role_actor = django_user_model.objects.create_user(
        username="rehearsal-inactive-role",
        email="inactive-role@example.test",
        password="test-only",
    )
    _grant(
        organization,
        inactive_role_actor,
        permissions=["member.invite"],
        role_active=False,
        name="inactive-role",
    )

    for actor in (inactive_membership_actor, inactive_role_actor):
        assert authorize(actor=actor, organization=organization, action=LedgerAction.CREATE_RUN) is False


@pytest.mark.django_db
def test_authorizer_allows_superadmin_without_membership(django_user_model):
    organization, _owner = _make_organization(django_user_model, "superadmin")
    authorize = build_rehearsal_authorizer()
    superadmin = django_user_model.objects.create_superuser(
        username="rehearsal-superadmin",
        email="superadmin@example.test",
        password="test-only",
    )

    assert Membership.objects.filter(user=superadmin).exists() is False
    assert authorize(actor=superadmin, organization=organization, action=LedgerAction.FINISH_RUN) is True

    superadmin.is_active = False
    superadmin.save(update_fields=["is_active"])
    assert authorize(actor=superadmin, organization=organization, action=LedgerAction.FINISH_RUN) is False


@pytest.mark.django_db
def test_target_validators_expose_only_allowlisted_models_and_require_tenant_ownership(django_user_model):
    organization, _owner = _make_organization(django_user_model, "target")
    other_organization, _other_owner = _make_organization(django_user_model, "target-foreign")
    validators = build_target_validators()

    # The registry is a closed, code-owned allowlist: a target model that is not
    # listed here can never be bound to a ledger row.
    assert tuple(validators) == (
        USER_MODEL_LABEL,
        ORG_UNIT_MODEL_LABEL,
        PROGRAM_MODEL_LABEL,
        SUBJECT_MODEL_LABEL,
        CURRICULUM_MODEL_LABEL,
        CURRICULUM_SUBJECT_MODEL_LABEL,
        STUDENT_RECORD_MODEL_LABEL,
    )
    assert all(re.fullmatch(MODEL_LABEL_PATTERN, label) for label in validators)

    member = django_user_model.objects.create_user(
        username="rehearsal-target-member",
        email="target-member@example.test",
        password="test-only",
    )
    profile = member.profile
    profile.organization = organization
    profile.save(update_fields=["organization", "updated_at"])
    outsider = django_user_model.objects.create_user(
        username="rehearsal-target-outsider",
        email="target-outsider@example.test",
        password="test-only",
    )

    validate_user = validators[USER_MODEL_LABEL]
    owned = validate_user(target_pk=str(member.pk), organization=organization)
    foreign = validate_user(target_pk=str(member.pk), organization=other_organization)
    unowned = validate_user(target_pk=str(outsider.pk), organization=organization)

    assert owned == TargetValidation(exists=True, organization_matches=True)
    assert foreign == TargetValidation(exists=True, organization_matches=False)
    assert unowned == TargetValidation(exists=True, organization_matches=False)

    # The four catalogue/record models all carry their own ``organization``
    # column, so the generic tenant validator is exact for every one of them.
    subject = Subject.objects.create(organization=organization, code="MYEDU-L1", name="Fənn", ects=5)
    validate_subject = validators[SUBJECT_MODEL_LABEL]

    assert validate_subject(target_pk=str(subject.pk), organization=organization) == TargetValidation(
        exists=True, organization_matches=True
    )
    assert validate_subject(target_pk=str(subject.pk), organization=other_organization) == TargetValidation(
        exists=True, organization_matches=False
    )
