"""Command-surface tests (SPEC §15.1/44-47).

The orchestrator is stubbed out: what is under test here is the production
gate, the single-line JSON contract, the bare-code exception funnel and the
exit-3 mapping that tells an operator a run is still resumable.
"""

import json
from io import StringIO
from types import SimpleNamespace

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings

import pytest

from apps.legacy_import.management.commands import legacy_import_rehearse as command_module
from apps.legacy_import.services.mariadb_gateway import MariaDBSourceGatewayError
from apps.legacy_import.services.rehearsal_contracts import (
    LegacyRehearsalConfigError,
    LegacyRehearsalInterrupted,
    PlanSemesterScheme,
    SarCurriculumFallback,
)
from apps.legacy_import.services.source_extraction import LegacySourceExtractionCancelled
from apps.organizations.models import Organization
from core.constants import OrganizationType

_SOURCE = "/nonexistent/legacy-snapshot.sql"
_SIZE = "2142912818"
_SLUG = "rehearsal-command-organization"
_ACTOR = "rehearsal_command_actor"
_PLAN_PAYLOAD = {
    "snapshot_sha256": "a" * 64,
    "mode": "rehearsal",
    "attestation_digest": "b" * 64,
    "status": "planned",
}


@pytest.fixture()
def command_environment(db):
    actor = get_user_model().objects.create_superuser(
        username=_ACTOR,
        email="rehearsal-command-actor@example.test",
        password="test-only",
    )
    Organization.objects.create(
        name="Rehearsal Command Organization",
        slug=_SLUG,
        org_type=OrganizationType.UNIVERSITY,
        owner=actor,
        status="active",
        is_active=True,
    )
    return actor


def _plan_arguments():
    return [
        "--mode=plan",
        f"--organization-slug={_SLUG}",
        f"--actor-username={_ACTOR}",
        f"--source={_SOURCE}",
        f"--expected-size-bytes={_SIZE}",
    ]


def _apply_arguments():
    return [
        "--mode=apply",
        "--apply-confirm=emsarena_rehearsal_ab12cd34ef56",
        "--rehearsal-ordinal=1",
        f"--organization-slug={_SLUG}",
        f"--actor-username={_ACTOR}",
        f"--source={_SOURCE}",
        f"--expected-size-bytes={_SIZE}",
    ]


def test_command_denies_production_environment(command_environment, monkeypatch):
    monkeypatch.setattr(command_module, "plan_rehearsal", lambda **_kwargs: dict(_PLAN_PAYLOAD))

    with override_settings(MANAGEMENT_COMMAND_ENVIRONMENT="production"):
        with pytest.raises(CommandError) as exc_info:
            call_command("legacy_import_rehearse", *_plan_arguments())

    assert "management_command_safety_denied" in str(exc_info.value)
    assert "legacy_import_rehearse" in str(exc_info.value)


def test_command_emits_single_line_sorted_json(command_environment, monkeypatch):
    captured = {}

    def fake_plan(**kwargs):
        captured.update(kwargs)
        return dict(_PLAN_PAYLOAD)

    monkeypatch.setattr(command_module, "plan_rehearsal", fake_plan)
    stdout = StringIO()

    with override_settings(MANAGEMENT_COMMAND_ENVIRONMENT="test"):
        call_command("legacy_import_rehearse", *_plan_arguments(), stdout=stdout)

    output = stdout.getvalue()
    assert output.count("\n") == 1
    document = json.loads(output)
    assert document == _PLAN_PAYLOAD
    assert output.strip() == json.dumps(document, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
    # No ``--phase`` was passed, so the policy defaults to the WHOLE attested
    # registry — now five phases; ``RehearsalPolicy`` sorts the keys, hence the
    # alphabetical order rather than the registry's ascending ``order``.
    assert captured["policy"].phase_keys == (
        "academic_catalog",
        "academic_structure",
        "identity_cohort",
        "sar_materialisation",
        "student_placement",
    )
    assert captured["policy"].email_trust_manifest_digest == ""
    assert captured["organization"].slug == _SLUG
    assert captured["actor"].username == _ACTOR
    assert captured["source_size_bytes"] == 2_142_912_818


@pytest.mark.parametrize(
    "error, expected",
    [
        (LegacyRehearsalConfigError("legacy_rehearsal_target_not_opted_in"), "legacy_rehearsal_target_not_opted_in"),
        (MariaDBSourceGatewayError("legacy_mariadb_gateway_disabled"), "legacy_mariadb_gateway_disabled"),
    ],
)
def test_command_maps_service_errors_to_bare_codes(command_environment, monkeypatch, error, expected):
    def fail(**_kwargs):
        raise error

    monkeypatch.setattr(command_module, "plan_rehearsal", fail)

    with override_settings(MANAGEMENT_COMMAND_ENVIRONMENT="test"):
        with pytest.raises(CommandError) as exc_info:
            call_command("legacy_import_rehearse", *_plan_arguments())

    assert str(exc_info.value) == expected
    assert exc_info.value.returncode == 1


def test_command_reports_an_unexpected_failure_without_a_raw_message(command_environment, monkeypatch):
    def fail(**_kwargs):
        raise RuntimeError("raw-internal-detail")

    monkeypatch.setattr(command_module, "plan_rehearsal", fail)

    with override_settings(MANAGEMENT_COMMAND_ENVIRONMENT="test"):
        with pytest.raises(CommandError) as exc_info:
            call_command("legacy_import_rehearse", *_plan_arguments())

    assert str(exc_info.value) == "legacy_rehearsal_failed"
    assert "raw-internal-detail" not in str(exc_info.value)


@pytest.mark.parametrize(
    "error, expected",
    [
        (LegacyRehearsalInterrupted("legacy_rehearsal_cancelled"), "legacy_rehearsal_cancelled"),
        (
            LegacySourceExtractionCancelled("legacy_source_extraction_cancelled"),
            "legacy_source_extraction_cancelled",
        ),
    ],
)
def test_command_exits_three_on_interruption(command_environment, monkeypatch, error, expected):
    def fail(**_kwargs):
        raise error

    monkeypatch.setattr(command_module, "execute_rehearsal", fail)

    with override_settings(MANAGEMENT_COMMAND_ENVIRONMENT="test"):
        with pytest.raises(CommandError) as exc_info:
            call_command("legacy_import_rehearse", *_apply_arguments())

    assert str(exc_info.value) == expected
    # Exit 3 tells the operator the run is still RUNNING and resumable.
    assert exc_info.value.returncode == 3


def test_command_fails_a_failed_outcome_with_its_ledger_failure_code(command_environment, monkeypatch):
    outcome = SimpleNamespace(status="failed", failure_code="legacy_rehearsal_blocking_issue", payload={})
    monkeypatch.setattr(command_module, "execute_rehearsal", lambda **_kwargs: outcome)

    with override_settings(MANAGEMENT_COMMAND_ENVIRONMENT="test"):
        with pytest.raises(CommandError) as exc_info:
            call_command("legacy_import_rehearse", *_apply_arguments())

    assert str(exc_info.value) == "legacy_rehearsal_blocking_issue"
    assert exc_info.value.returncode == 1


def test_command_refuses_an_unknown_organization_or_inactive_actor(command_environment, monkeypatch):
    monkeypatch.setattr(command_module, "plan_rehearsal", lambda **_kwargs: dict(_PLAN_PAYLOAD))
    inactive = get_user_model().objects.create_user(
        username="rehearsal_command_inactive",
        email="rehearsal-command-inactive@example.test",
        password="test-only",
        is_active=False,
    )

    with override_settings(MANAGEMENT_COMMAND_ENVIRONMENT="test"):
        with pytest.raises(CommandError) as exc_info:
            call_command(
                "legacy_import_rehearse",
                "--mode=plan",
                "--organization-slug=no-such-organization",
                f"--actor-username={_ACTOR}",
                f"--source={_SOURCE}",
                f"--expected-size-bytes={_SIZE}",
            )
        assert str(exc_info.value) == "legacy_rehearsal_organization_invalid"

        with pytest.raises(CommandError) as exc_info:
            call_command(
                "legacy_import_rehearse",
                "--mode=plan",
                f"--organization-slug={_SLUG}",
                f"--actor-username={inactive.username}",
                f"--source={_SOURCE}",
                f"--expected-size-bytes={_SIZE}",
            )
        assert str(exc_info.value) == "legacy_rehearsal_actor_invalid"


def test_command_requires_a_manifest_for_the_evidence_email_policy(command_environment, monkeypatch):
    monkeypatch.setattr(command_module, "plan_rehearsal", lambda **_kwargs: dict(_PLAN_PAYLOAD))

    with override_settings(MANAGEMENT_COMMAND_ENVIRONMENT="test"):
        with pytest.raises(CommandError) as exc_info:
            call_command(
                "legacy_import_rehearse",
                *_plan_arguments(),
                "--email-trust-policy=evidence_manifest",
            )

    assert str(exc_info.value) == "legacy_rehearsal_email_manifest_invalid"


# ---------------------------------------------------------------------------
# FAZA 3 — SLICE 2 (§3.12 / §10 item 7): the four activation-policy flags.
# ---------------------------------------------------------------------------


def _capturing_plan(monkeypatch):
    captured = {}

    def fake_plan(**kwargs):
        captured.update(kwargs)
        return dict(_PLAN_PAYLOAD)

    monkeypatch.setattr(command_module, "plan_rehearsal", fake_plan)
    return captured


def test_slice_two_flags_default_to_the_no_account_touching_rehearsal(command_environment, monkeypatch):
    """The first slice-2 rehearsal must prove the catalogue without activating."""

    captured = _capturing_plan(monkeypatch)

    with override_settings(MANAGEMENT_COMMAND_ENVIRONMENT="test"):
        call_command("legacy_import_rehearse", *_plan_arguments(), stdout=StringIO())

    policy = captured["policy"]
    assert policy.stage_and_activate is False
    assert policy.max_activated_accounts == 0
    assert policy.sar_curriculum_fallback is SarCurriculumFallback.SYNTHESISE
    # V-13: ``payiz_N``/``yaz_N`` are ordinal semester numbers in the live dump.
    assert policy.plan_semester_scheme is PlanSemesterScheme.ORDINAL


def test_slice_two_flags_reach_the_policy_and_bind_the_run_identity(command_environment, monkeypatch):
    """SA-5: the four values are policy, so they change ``transform_version``."""

    captured = _capturing_plan(monkeypatch)

    with override_settings(MANAGEMENT_COMMAND_ENVIRONMENT="test"):
        call_command(
            "legacy_import_rehearse",
            *_plan_arguments(),
            "--stage-and-activate",
            "--max-staged-accounts=50",
            "--max-activated-accounts=20",
            "--student-role-name=student",
            "--worker-role-name=teacher",
            "--sar-curriculum-fallback=strict",
            "--plan-semester-scheme=term_pair",
            stdout=StringIO(),
        )
        activating = captured["policy"]

        call_command(
            "legacy_import_rehearse",
            *_plan_arguments(),
            "--max-staged-accounts=50",
            "--student-role-name=student",
            "--worker-role-name=teacher",
            "--sar-curriculum-fallback=strict",
            "--plan-semester-scheme=term_pair",
            stdout=StringIO(),
        )
        disabled = captured["policy"]

    assert activating.stage_and_activate is True
    assert activating.max_activated_accounts == 20
    assert activating.sar_curriculum_fallback is SarCurriculumFallback.STRICT
    assert activating.plan_semester_scheme is PlanSemesterScheme.TERM_PAIR
    # The four values are inside ``_digest_payload``: a run that touches accounts
    # can never share a ledger scope with one that does not.
    assert activating.transform_version() != disabled.transform_version()
    assert len(activating.transform_version()) <= 64


@pytest.mark.parametrize(
    "extra, expected",
    [
        # The switch without a blast-radius cap is refused before any run row.
        (("--stage-and-activate",), "legacy_rehearsal_policy_activation_invalid"),
        # A cap larger than the staging cap could never be honoured.
        (
            (
                "--stage-and-activate",
                "--max-activated-accounts=20",
                "--max-staged-accounts=10",
                "--student-role-name=student",
                "--worker-role-name=teacher",
            ),
            "legacy_rehearsal_policy_activation_invalid",
        ),
        # Out of the argparse bound (IDENTITY_COHORT_MAX_ROWS).
        (("--max-activated-accounts=20001",), "legacy_rehearsal_activation_cap_invalid"),
        (("--max-activated-accounts=-1",), "legacy_rehearsal_activation_cap_invalid"),
    ],
)
def test_command_refuses_an_incoherent_activation_policy(command_environment, monkeypatch, extra, expected):
    monkeypatch.setattr(command_module, "plan_rehearsal", lambda **_kwargs: dict(_PLAN_PAYLOAD))

    with override_settings(MANAGEMENT_COMMAND_ENVIRONMENT="test"):
        with pytest.raises(CommandError) as exc_info:
            call_command("legacy_import_rehearse", *_plan_arguments(), *extra)

    assert expected in str(exc_info.value)
    # Exit 1, never 3: nothing is resumable — no run row was ever created.
    assert getattr(exc_info.value, "returncode", 1) == 1


@pytest.mark.parametrize(
    "flag",
    ["--sar-curriculum-fallback=guess", "--plan-semester-scheme=trimester"],
)
def test_command_refuses_an_unknown_enum_token(command_environment, monkeypatch, flag):
    monkeypatch.setattr(command_module, "plan_rehearsal", lambda **_kwargs: dict(_PLAN_PAYLOAD))

    with override_settings(MANAGEMENT_COMMAND_ENVIRONMENT="test"):
        with pytest.raises(CommandError):
            call_command("legacy_import_rehearse", *_plan_arguments(), flag)
