"""The default review stays fixed; explicit batches may include audited closure."""

import hashlib
import json
from copy import deepcopy
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from apps.legacy_import.services.reaudit_syllabi import RestoreError, contracts, run, source_plan, state
from apps.legacy_import.tests import test_reaudit_syllabi as fixtures
from apps.legacy_import.tests import test_reaudit_syllabus_source_plan as source_fixtures
from apps.organizations.models import OrgUnit
from apps.registrar.models import CourseOffering
from apps.syllabus.models import SyllabusShare
from apps.syllabus.tests.factories import make_academic_stack, make_offering, make_org

world = fixtures.world
pytestmark = pytest.mark.django_db


@pytest.fixture
def expanded(world, monkeypatch):
    org, _owner, teacher, offering, _syllabus, _version = world
    group = OrgUnit.objects.create(organization=org, name="Synthetic closure", slug="closure", unit_type="group")
    extra = make_offering(org, {"subject": offering.subject, "period": offering.period, "group": group}, teacher)
    scope = {**contracts.SCOPE, "allowed_offering_ids": [str(offering.pk), str(extra.pk)]}
    for module in (contracts, state, source_plan):
        monkeypatch.setattr(module, "SCOPE", scope)
    return extra


def test_checked_in_default385_unchanged_and_allowed1700_are_exact_ids():
    scope = json.loads((Path(contracts.__file__).parent / "scope.json").read_bytes())
    assert len(scope["offering_ids"]) == 385
    assert hashlib.sha256(json.dumps(scope["offering_ids"], sort_keys=True).encode()).hexdigest() == (
        "41a051f2051349b52c7ad97309240cbd6143c65a00eac247493e9b7661887697"
    )
    assert len(scope["allowed_offering_ids"]) == len(set(scope["allowed_offering_ids"])) == 1700
    assert set(scope["offering_ids"]) <= set(scope["allowed_offering_ids"])
    assert all(str(UUID(pk)) == pk for pk in scope["allowed_offering_ids"])


def test_default_and_legacy_fixture_fallback_stay_narrow(world):
    oid = str(world[3].pk)
    assert contracts.selected_ids(None) == contracts.selected_ids(()) == (oid,)
    assert contracts.selected_ids([oid]) == (oid,)
    with pytest.raises(RestoreError, match="fixed_audit_offering_scope_required"):
        contracts.selected_ids([str(uuid4())])


def test_explicit_audited_unknown_is_included_without_expanding_default(world, expanded):
    org, owner, _teacher, offering, _syllabus, _version = world
    assert contracts.selected_ids(()) == (str(offering.pk),)
    selected = contracts.selected_ids([str(expanded.pk)])
    assert selected == (str(expanded.pk),)
    result = run(org, owner, offering_ids=selected)
    assert {row["offering_id"] for row in result["held"]} == {str(expanded.pk)}
    assert result["status"] == "dry_run"


def test_shared_publication_requires_entire_explicit_batch(world, expanded):
    org, owner, teacher, offering, syllabus, version = world
    fixtures.fill(version, teacher, org)
    SyllabusShare.objects.create(organization=org, syllabus=syllabus, offering=expanded, created_by=owner)
    held = run(org, owner)
    assert held["counts"] == {}
    assert held["held"] == [{"offering_id": str(offering.pk), "code": "publication_reaches_unreviewed_offering"}]
    reviewed = run(org, owner, offering_ids=[str(offering.pk), str(expanded.pk)])
    assert reviewed["counts"] == {"publish": 1}
    assert not reviewed["held"]
    assert set(reviewed["actions"][0]["affected_offering_ids"]) == {str(offering.pk), str(expanded.pk)}
    version.refresh_from_db()
    assert version.status == "draft"  # Inclusion is a read-only plan, not approval.


def test_unreviewed_share_outside_explicit_batch_stays_blocked(world, expanded):
    org, owner, teacher, offering, syllabus, version = world
    fixtures.fill(version, teacher, org)
    third_group = OrgUnit.objects.create(organization=org, name="Synthetic third", slug="third", unit_type="group")
    third = make_offering(org, {"subject": offering.subject, "period": offering.period, "group": third_group}, teacher)
    SyllabusShare.objects.create(organization=org, syllabus=syllabus, offering=third, created_by=owner)
    result = run(org, owner, offering_ids=[str(offering.pk), str(expanded.pk)])
    assert any(row["code"] == "publication_reaches_unreviewed_offering" for row in result["held"])
    assert not any(row["action"] == "publish" for row in result["actions"])


def test_foreign_and_unreviewed_ids_remain_refused(world, expanded):
    org, owner, _teacher, _offering, _syllabus, _version = world
    foreign_org = make_org("foreign-scope", owner=owner)
    foreign = make_offering(foreign_org, make_academic_stack(foreign_org, code="FOREIGN"), None)
    for pk in (str(foreign.pk), str(uuid4())):
        with pytest.raises(RestoreError, match="fixed_audit_offering_scope_required"):
            run(org, owner, offering_ids=[pk])


def test_audited_id_moved_to_new_period_is_refused(world, expanded):
    org, owner, _teacher, _offering, _syllabus, _version = world
    later = make_academic_stack(org, code="LATER")["period"]
    CourseOffering.objects.filter(pk=expanded.pk).update(period=later)
    with pytest.raises(RestoreError, match="audit_period_changed"):
        run(org, owner, offering_ids=[str(expanded.pk)])


def test_source_packet_explicit_binding_and_tenant_period_guards(world, expanded, tmp_path):
    packet = {
        "format": "reaudit-syllabi-source/1",
        "organization_id": contracts.SCOPE["organization_id"],
        "period_id": contracts.SCOPE["period_id"],
        "sources": {},
        "bindings": {str(expanded.pk): {"source_id": 1}},
    }

    def read(value):
        raw = json.dumps(value).encode()
        path = tmp_path / "private-source.json"
        path.write_bytes(raw)
        return contracts.source_packet(path, hashlib.sha256(raw).hexdigest())

    assert set(read(packet)["bindings"]) == {str(expanded.pk)}
    for mutation in (
        {"organization_id": str(uuid4())},
        {"period_id": str(uuid4())},
        {"bindings": {str(uuid4()): {"source_id": 1}}},
    ):
        with pytest.raises(RestoreError, match="reviewed_source_packet_scope"):
            read({**packet, **mutation})


def test_prepare_sources_accepts_explicit_audited_id_and_keeps_default(world, expanded, monkeypatch):
    snapshot, source, header, journal = source_fixtures.inputs(world, monkeypatch)
    packet, plan = source_plan.prepare_sources(
        snapshot, [header], [journal], lambda _h: deepcopy(source), offering_ids=[str(expanded.pk)]
    )
    assert plan["scope_count"] == 1
    assert set(packet["bindings"]) == {str(expanded.pk)}
    default_packet, default_plan = source_plan.prepare_sources(
        snapshot, [header], [journal], lambda _h: deepcopy(source)
    )
    assert default_plan["scope_count"] == 1
    assert set(default_packet["bindings"]) == {str(world[3].pk)}
    with pytest.raises(RestoreError, match="fixed_audit_offering_scope_required"):
        source_plan.prepare_sources(snapshot, [], [], lambda _h: None, offering_ids=[str(uuid4())])


@pytest.mark.parametrize("field", ["organization_id", "period_id"])
def test_source_plan_wrong_current_identity_yields_no_binding(world, expanded, monkeypatch, field):
    snapshot, source, header, journal = source_fixtures.inputs(world, monkeypatch)
    row = next(r for r in snapshot["tables"]["registrar.CourseOffering"] if r["id"] == str(expanded.pk))
    row[field] = str(uuid4())
    packet, plan = source_plan.prepare_sources(
        snapshot, [header], [journal], lambda _h: deepcopy(source), offering_ids=[str(expanded.pk)]
    )
    assert not packet["bindings"]
    assert plan["counts"] == {"current_target_not_in_snapshot": 1}
