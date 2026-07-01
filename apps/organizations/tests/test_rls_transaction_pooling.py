"""
Transaction-scoped RLS regression tests for PgBouncer transaction pooling.

These tests simulate the important transaction-pooling invariants on one Django
connection: each request/worker transaction must set its own RLS context with
SET LOCAL, and that context must disappear before the connection is reused.
"""

from django.contrib.auth import get_user_model
from django.db import connection, transaction
from django.test import override_settings

import pytest

from apps.organizations.models import Organization, OrgUnit
from core.constants import OrganizationType
from core.rls import set_rls_bypass, set_rls_tenant
from core.rls_pooling import RLSTransactionGuard, reset_txn_flags, rls_worker_atomic

pytestmark = [pytest.mark.postgres, pytest.mark.django_db(transaction=True)]


def _is_postgresql():
    return connection.vendor == "postgresql"


def _set_setting(name: str, value: str, *, local: bool) -> None:
    with connection.cursor() as cur:
        cur.execute("SELECT set_config(%s, %s, %s)", [name, value, local])


def _current_setting(name: str) -> str:
    with connection.cursor() as cur:
        cur.execute("SELECT current_setting(%s, true)", [name])
        row = cur.fetchone()
    return str(row[0] or "") if row else ""


def _skip_if_not_pg():
    if not _is_postgresql():
        pytest.skip("Transaction-pooling RLS tests require PostgreSQL")


@pytest.fixture(autouse=True)
def _rls_bypass_for_tests(transactional_db):
    """Keep setup unrestricted, then let each test enable RLS inside a txn."""
    if not _is_postgresql():
        yield
        return

    _set_setting("app.bypass_rls", "on", local=False)
    _set_setting("app.current_org_id", "", local=False)
    _set_setting("app.current_user_id", "", local=False)
    try:
        yield
    finally:
        _set_setting("app.bypass_rls", "off", local=False)
        _set_setting("app.current_org_id", "", local=False)
        _set_setting("app.current_user_id", "", local=False)
        reset_txn_flags(connection)


@pytest.fixture()
def two_org_units():
    _skip_if_not_pg()
    User = get_user_model()
    owner_a = User.objects.create_user("txn_pool_owner_a", "txn-a@example.test", "pw")
    owner_b = User.objects.create_user("txn_pool_owner_b", "txn-b@example.test", "pw")
    org_a = Organization.objects.create(
        name="Transaction Pool Org A",
        slug="transaction-pool-org-a",
        org_type=OrganizationType.UNIVERSITY,
        owner=owner_a,
        status="active",
        is_active=True,
    )
    org_b = Organization.objects.create(
        name="Transaction Pool Org B",
        slug="transaction-pool-org-b",
        org_type=OrganizationType.SCHOOL,
        owner=owner_b,
        status="active",
        is_active=True,
    )
    unit_a = OrgUnit.objects.create(organization=org_a, name="Tenant A Unit", slug="tenant-a-unit", unit_type="faculty")
    unit_b = OrgUnit.objects.create(organization=org_b, name="Tenant B Unit", slug="tenant-b-unit", unit_type="faculty")
    return org_a, org_b, unit_a, unit_b


def _enable_rls_for_transaction() -> None:
    set_rls_bypass(False, local=True)
    _set_setting("app.current_org_id", "", local=True)
    _set_setting("app.current_user_id", "", local=True)
    with connection.cursor() as cur:
        cur.execute("SET LOCAL ROLE rls_app_role")


def _run_guarded_request(*, user_id: int, org_id: int | None):
    with transaction.atomic():
        _enable_rls_for_transaction()
        tenant_before_query = _current_setting("app.current_org_id")
        guard = RLSTransactionGuard(user_id=user_id, org_id=org_id, bypass=False)
        wrapper_cm = connection.execute_wrapper(guard)
        wrapper_cm.__enter__()
        try:
            names = list(OrgUnit.objects.order_by("name").values_list("name", flat=True))
            tenant_during_query = _current_setting("app.current_org_id")
        finally:
            wrapper_cm.__exit__(None, None, None)
            reset_txn_flags(connection)
    return names, tenant_before_query, tenant_during_query


@override_settings(RLS_TRANSACTION_SCOPED=True)
def test_reused_connection_gets_fresh_tenant_context(two_org_units):
    """Request A then request B on one connection must not leak tenant state."""
    org_a, org_b, _unit_a, _unit_b = two_org_units

    names_a, before_a, during_a = _run_guarded_request(user_id=org_a.owner_id, org_id=org_a.pk)
    assert before_a == ""
    assert names_a == ["Tenant A Unit"]
    assert during_a == str(org_a.pk)
    assert _current_setting("app.current_org_id") == ""

    names_b, before_b, during_b = _run_guarded_request(user_id=org_b.owner_id, org_id=org_b.pk)
    assert before_b == ""
    assert names_b == ["Tenant B Unit"]
    assert during_b == str(org_b.pk)
    assert "Tenant A Unit" not in names_b


@override_settings(RLS_TRANSACTION_SCOPED=True)
def test_worker_atomic_sets_local_tenant_and_clears_after_block(two_org_units):
    """Worker path uses an explicit tenant and loses it when the txn closes."""
    org_a, _org_b, _unit_a, _unit_b = two_org_units

    with rls_worker_atomic():
        _enable_rls_for_transaction()
        set_rls_tenant(org_a.pk)
        names = list(OrgUnit.objects.order_by("name").values_list("name", flat=True))
        tenant_during_worker = _current_setting("app.current_org_id")

    assert names == ["Tenant A Unit"]
    assert tenant_during_worker == str(org_a.pk)
    assert _current_setting("app.current_org_id") == ""


@override_settings(RLS_TRANSACTION_SCOPED=True)
def test_missing_tenant_context_fails_closed(two_org_units):
    """No org in transaction-scoped guard must resolve to deny-all."""
    org_a, _org_b, _unit_a, _unit_b = two_org_units

    names, before_query, during_query = _run_guarded_request(user_id=org_a.owner_id, org_id=None)

    assert before_query == ""
    assert during_query == ""
    assert names == []
