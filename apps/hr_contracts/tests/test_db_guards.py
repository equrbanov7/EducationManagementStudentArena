"""DB səviyyəli qoruyucular (PostgreSQL): RLS tenant izolyasiyası, APPEND-ONLY hadisə jurnalı, eyni-təşkilat FK
trigger-ləri, CHECK / unikal məhdudiyyətlər, xatırlatmanın DB idempotentliyi."""

from __future__ import annotations

from django.db import DatabaseError, IntegrityError, connection, transaction
from django.utils import timezone

import pytest

from apps.hr_contracts.constants import EventKind
from apps.hr_contracts.models import EmploymentContract, EmploymentContractEvent
from apps.hr_contracts.services.contracts import record_event

from .world import build_world, days, make_contract

pytestmark = [pytest.mark.postgres, pytest.mark.django_db]

_TABLES = ("hr_contracts_employmentcontract", "hr_contracts_employmentcontractevent")


def _set(name, value):
    with connection.cursor() as cur:
        cur.execute("SELECT set_config(%s, %s, false)", [name, str(value)])


def _enter_tenant(org_id):
    _set("app.bypass_rls", "off")
    _set("app.current_org_id", str(org_id))
    _set("app.current_user_id", "")
    with connection.cursor() as cur:
        cur.execute("SET LOCAL ROLE rls_app_role")


@pytest.fixture()
def two_tenants(db):
    if connection.vendor != "postgresql":
        pytest.skip("PostgreSQL tələb olunur")
    _set("app.bypass_rls", "on")
    worlds = [build_world("hrcdba"), build_world("hrcdbb")]
    contracts = [make_contract(world, number=f"DB-{index}") for index, world in enumerate(worlds)]
    yield worlds, contracts
    _set("app.bypass_rls", "off")
    _set("app.current_org_id", "")


def test_policies_enabled_and_forced():
    with connection.cursor() as cur:
        cur.execute(
            "SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity, "
            "(SELECT count(*) FROM pg_policy p WHERE p.polrelid = c.oid AND p.polname = 'rls_tenant_isolation') "
            "FROM pg_class c WHERE c.relname = ANY(%s)",
            [list(_TABLES)],
        )
        rows = {name: (rls, forced, policies) for name, rls, forced, policies in cur.fetchall()}
    assert set(rows) == set(_TABLES)
    assert all(row == (True, True, 1) for row in rows.values()), rows


def test_tenant_isolation(two_tenants):
    (world_a, _world_b), _contracts = two_tenants
    _enter_tenant(world_a["org"].pk)
    for model in (EmploymentContract, EmploymentContractEvent):
        assert set(model.objects.values_list("organization_id", flat=True)) == {world_a["org"].pk}, model.__name__


def test_missing_tenant_sees_nothing(two_tenants):
    _enter_tenant("")
    assert EmploymentContract.objects.count() == 0
    assert EmploymentContractEvent.objects.count() == 0


def test_event_is_append_only(two_tenants):
    _worlds, (contract, _other) = two_tenants
    event = EmploymentContractEvent.objects.filter(contract=contract).first()
    with pytest.raises(DatabaseError), transaction.atomic():
        EmploymentContractEvent.objects.filter(pk=event.pk).update(note="dəyişdirildi")
    with pytest.raises(DatabaseError), transaction.atomic():
        EmploymentContractEvent.objects.filter(pk=event.pk).delete()


def test_cross_org_links_rejected(two_tenants):
    (world_a, world_b), (contract_a, contract_b) = two_tenants
    with pytest.raises(DatabaseError), transaction.atomic():
        EmploymentContract.objects.filter(pk=contract_a.pk).update(unit=world_b["f1"])
    with pytest.raises(DatabaseError), transaction.atomic():
        EmploymentContract.objects.filter(pk=contract_a.pk).update(renewed_by=contract_b)
    with pytest.raises(DatabaseError), transaction.atomic():
        EmploymentContractEvent.objects.create(organization=world_a["org"], contract=contract_b, kind=EventKind.EDITED)


def test_check_constraints(two_tenants):
    _worlds, (contract, _other) = two_tenants
    for values in (
        {"contract_type": "indefinite"},  # müddətsizdə bitmə tarixi olmur
        {"end_date": None},  # müddətlidə məcburidir
        {"end_date": days(-1000)},  # başlanğıcdan əvvəl
        {"acknowledged_at": timezone.now()},  # göndərilmədən təsdiq yoxdur
        {"status": "terminated"},  # xitamın tarixi və səbəbi
        {"status": "bogus"},
    ):
        with pytest.raises(IntegrityError), transaction.atomic():
            EmploymentContract.objects.filter(pk=contract.pk).update(**values)


def test_number_unique_per_org_but_free_across_orgs(two_tenants):
    (world_a, world_b), (contract_a, _contract_b) = two_tenants
    with pytest.raises(IntegrityError), transaction.atomic():
        EmploymentContract.objects.create(
            organization=world_a["org"], employee=world_a["t2"], number=contract_a.number, start_date=days(-10),
            end_date=days(10),
        )  # fmt: skip
    EmploymentContract.objects.create(
        organization=world_b["org"], employee=world_b["t2"], number=contract_a.number, start_date=days(-10),
        end_date=days(10),
    )  # fmt: skip


def test_reminder_event_unique_per_threshold(two_tenants):
    _worlds, (contract, _other) = two_tenants
    record_event(contract, EventKind.REMINDER_SENT, threshold=30, end_date=contract.end_date)
    with pytest.raises(IntegrityError), transaction.atomic():
        record_event(contract, EventKind.REMINDER_SENT, threshold=30, end_date=contract.end_date)
    record_event(contract, EventKind.REMINDER_SENT, threshold=14, end_date=contract.end_date)
    record_event(contract, EventKind.REMINDER_SENT, threshold=30, end_date=days(400))  # A4: uzadılmış tarix — yeni hədd
    record_event(contract, EventKind.SENT)
    record_event(contract, EventKind.SENT)  # adi hadisələr təkrarlana bilər
