"""Immutable base mappings cannot hide applied canonical remap versions."""

from copy import deepcopy

import pytest

from apps.legacy_import.services.reaudit_syllabi.contracts import RestoreError
from apps.legacy_import.services.reaudit_syllabi.readonly_mapping import FIELDS, effective_maps


def chain():
    base = dict(
        id="base",
        organization_id="tenant",
        created_run_id="run1",
        source_row_hash="a" * 64,
        transform_version="v1",
        target_model_label="registrar.subject",
        target_pk="old",
        state="migrated",
        reconciliation_status="verified",
    )
    first = {key: base[key] for key in FIELDS} | dict(
        id="v1",
        organization_id="tenant",
        entity_map_id="base",
        version_number=1,
        recorded_run_id="run1",
        supersedes_id=None,
    )
    remap = first | dict(
        id="v2",
        version_number=2,
        recorded_run_id="run2",
        supersedes_id="v1",
        target_pk="new",
        approved_issue_id="issue",
        reviewed_by_id=1,
        reviewed_at="2026-11-09",
        review_reason_code="reviewed",
        review_evidence_digest="b" * 64,
        applied_by_id=2,
    )
    return base, first, remap


def test_latest_applied_version_wins_and_base_is_unchanged():
    base, first, remap = chain()
    original = deepcopy(base)
    assert effective_maps([base], [remap, first])[0]["target_pk"] == "new"
    assert base == original
    assert effective_maps([base], [first])[0]["target_pk"] == "old"
    assert effective_maps([base], [])[0]["target_pk"] == "old"


@pytest.mark.parametrize(
    "field,value",
    [
        ("applied_by_id", None),
        ("reviewed_by_id", None),
        ("approved_issue_id", None),
        ("organization_id", "foreign"),
        ("supersedes_id", "other"),
        ("version_number", 3),
    ],
)
def test_foreign_pending_or_broken_chain_is_never_a_route(field, value):
    base, first, remap = chain()
    remap[field] = value
    with pytest.raises(RestoreError):
        effective_maps([base], [first, remap])


def test_latest_quarantine_never_resurrects_old_migrated_route():
    base, first, remap = chain()
    remap["state"] = "quarantined"
    remap["target_pk"] = remap["target_model_label"] = ""
    assert effective_maps([base], [first, remap]) == []


@pytest.mark.django_db
def test_live_route_uses_applied_review_and_never_creates_initial_version(db, django_user_model):
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    from apps.legacy_import.models import LegacyEntityMapVersion, LegacyMigrationRun
    from apps.legacy_import.services.ledger import finish_run
    from apps.legacy_import.services.reaudit_syllabi.sources import _mapped
    from apps.legacy_import.services.review import review_and_remap_entity, review_issue
    from apps.legacy_import.tests.test_review_workflow import _allow, _conflict_issue, _map, _run, _target_ok
    from apps.syllabus.tests.factories import make_org

    actor = django_user_model.objects.create_user("mapping-reviewer")
    org = make_org("mapping-proof", owner=actor)
    initial_run = _run(org, actor)
    mapping = _map(initial_run, actor)
    finish_run(run_id=initial_run.pk, actor=actor, authorize=_allow, outcome=LegacyMigrationRun.Status.SUCCEEDED)
    second = _run(org, actor, transform_version="transform-v2")
    issue = _conflict_issue(second, actor, mapping)
    review_issue(
        issue_id=issue.pk,
        actor=actor,
        authorize=_allow,
        decision="resolved",
        reason_code="reviewed-remap",
        evidence_digest="a" * 64,
    )
    assert _mapped(org, "student", 1001, "accounts.profile", "42")  # resolved but not applied
    assert not _mapped(org, "student", 1001, "accounts.profile", "43")
    review_and_remap_entity(
        issue_id=issue.pk,
        actor=actor,
        authorize=_allow,
        source_row_hash="b" * 64,
        state="migrated",
        target_model_label="accounts.profile",
        target_pk="43",
        target_validators={"accounts.profile": _target_ok},
    )
    with CaptureQueriesContext(connection) as captured:
        assert _mapped(org, "student", 1001, "accounts.profile", "43")
        assert not _mapped(org, "student", 1001, "accounts.profile", "42")
    assert not [q for q in captured if q["sql"].lstrip().upper().startswith(("INSERT ", "UPDATE ", "DELETE "))]
    assert LegacyEntityMapVersion.objects.filter(entity_map=mapping).count() == 2
    mapping.refresh_from_db()
    assert mapping.target_pk == "42"
