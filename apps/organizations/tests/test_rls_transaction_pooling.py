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
from core.rls import apply_rls_request_context, reset_rls_context, set_rls_bypass, set_rls_tenant
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

    # Org creation above runs during FIXTURE setup, where the per-test
    # @override_settings(RLS_TRANSACTION_SCOPED=True) is not yet active (the
    # decorator only wraps the test body). So the create_default_roles signal's
    # rls_worker_atomic() is a no-op and set_rls_tenant() writes
    # app.current_org_id at SESSION scope, polluting the shared connection
    # baseline. Reset the secure default here so that the transaction-scoped
    # SET LOCAL performed inside each test reverts to "" (no tenant) on commit.
    # In production the flag is a stable setting, so the signal always runs
    # transaction-scoped and this pollution cannot occur.
    _set_setting("app.bypass_rls", "on", local=False)
    _set_setting("app.current_org_id", "", local=False)
    _set_setting("app.current_user_id", "", local=False)
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


def _run_session_scoped_request(*, user_id: int, org_id: int | None):
    apply_rls_request_context(user_id=user_id, org_id=org_id, bypass=False, local=False)
    try:
        with transaction.atomic():
            with connection.cursor() as cur:
                cur.execute("SET LOCAL ROLE rls_app_role")
            names = list(OrgUnit.objects.order_by("name").values_list("name", flat=True))
            tenant_during_query = _current_setting("app.current_org_id")
    finally:
        reset_rls_context(local=False)
    return names, tenant_during_query


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


@override_settings(RLS_TRANSACTION_SCOPED=False)
def test_session_scoped_requests_reset_before_connection_reuse(two_org_units):
    """Flag-off fallback still resets one request before the next tenant runs."""
    org_a, org_b, _unit_a, _unit_b = two_org_units

    names_a, during_a = _run_session_scoped_request(user_id=org_a.owner_id, org_id=org_a.pk)
    assert names_a == ["Tenant A Unit"]
    assert during_a == str(org_a.pk)
    assert _current_setting("app.current_org_id") == ""

    names_b, during_b = _run_session_scoped_request(user_id=org_b.owner_id, org_id=org_b.pk)
    assert names_b == ["Tenant B Unit"]
    assert during_b == str(org_b.pk)
    assert "Tenant A Unit" not in names_b
    assert _current_setting("app.current_org_id") == ""


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


# ── FAZA 4 / Task 2 (2026-07-04) — güclənmiş izolyasiya testləri ─────────
# Transaction pooling altında ən risk-doğuran ssenariləri açıq şəkildə yoxlayır:
# çarpaz-tenant sızıntı simulyasiyası, bypass qorunması, uzun pool-reuse zəncirinin
# hər addımının fresh olması.


@override_settings(RLS_TRANSACTION_SCOPED=True)
def test_five_sequential_tenants_each_isolated(two_org_units):
    """Uzun pool-reuse zənciri: A→B→A→B→A hər addımda yalnız öz datasını görsün.

    Failure mode: RLSTransactionGuard `_rls_txn_applied` bayrağını hər transaction
    sonunda sıfırlamasa, ikinci A request-i B-nin (əvvəlki) tenant konteksti
    ilə işləyəcək. Bu test bu regressiyanı tutmaq üçündür.
    """
    org_a, org_b, _unit_a, _unit_b = two_org_units

    sequence = [org_a, org_b, org_a, org_b, org_a]
    for idx, org in enumerate(sequence, start=1):
        names, before, during = _run_guarded_request(user_id=org.owner_id, org_id=org.pk)
        expected_name = "Tenant A Unit" if org.pk == org_a.pk else "Tenant B Unit"
        forbidden_name = "Tenant B Unit" if org.pk == org_a.pk else "Tenant A Unit"
        assert before == "", f"step {idx}: leftover context from previous txn"
        assert during == str(org.pk), f"step {idx}: wrong tenant in guard"
        assert names == [expected_name], f"step {idx}: {org.slug} saw {names}"
        assert forbidden_name not in names, f"step {idx}: cross-tenant leak"


@override_settings(RLS_TRANSACTION_SCOPED=True)
def test_worker_atomic_sequence_isolates_tenants(two_org_units):
    """Ardıcıl worker/task zənciri: A tenant-ı → B tenant-ı → A tenant-ı.

    `rls_worker_atomic()` daxilində `set_rls_tenant` `SET LOCAL` (transaction
    scope) etməlidir; transaction sonunda kontekst yox olmalıdır.
    """
    org_a, org_b, _unit_a, _unit_b = two_org_units

    seen_by_tenant: list[tuple[str, list[str]]] = []
    for org in (org_a, org_b, org_a):
        with rls_worker_atomic():
            _enable_rls_for_transaction()
            set_rls_tenant(org.pk)
            names = list(OrgUnit.objects.order_by("name").values_list("name", flat=True))
            seen_by_tenant.append((org.slug, names))
        # Transaction bitdi — kontekst sıfırlanmış olmalıdır.
        assert (
            _current_setting("app.current_org_id") == ""
        ), f"tenant {org.slug}: session-scope context leaked past atomic block"

    # A yalnız A, B yalnız B görsün.
    assert seen_by_tenant[0] == (org_a.slug, ["Tenant A Unit"])
    assert seen_by_tenant[1] == (org_b.slug, ["Tenant B Unit"])
    assert seen_by_tenant[2] == (org_a.slug, ["Tenant A Unit"])


@override_settings(RLS_TRANSACTION_SCOPED=True)
def test_bypass_in_worker_atomic_does_not_persist(two_org_units):
    """Superadmin `bypass_rls` yalnız öz worker transaction-ında qüvvədədir.

    Bir sonrakı worker transaction (bypass qoyulmadan) tenant konteksti
    yenidən deny-all olmalıdır (yəni bypass sızmamalıdır).
    """
    from core.rls import bypass_rls

    org_a, org_b, _unit_a, _unit_b = two_org_units

    # 1) Bypass açıq — bütün OrgUnit-ləri görsün. `bypass_rls()` arqumentsizdir;
    # atomik blok daxilində olduğu üçün SET LOCAL avtomatik seçilir (in_atomic).
    with rls_worker_atomic():
        _enable_rls_for_transaction()
        with bypass_rls():
            all_names = set(OrgUnit.objects.values_list("name", flat=True))
    assert {"Tenant A Unit", "Tenant B Unit"}.issubset(all_names)

    # 2) Növbəti worker — bypass olmadan, tenant B üçün. Yalnız B-ni görməlidir.
    with rls_worker_atomic():
        _enable_rls_for_transaction()
        set_rls_tenant(org_b.pk)
        names = list(OrgUnit.objects.order_by("name").values_list("name", flat=True))
    assert names == ["Tenant B Unit"]

    # 3) Növbəti worker — heç bir kontekst qoyma. Deny-all olmalıdır.
    with rls_worker_atomic():
        _enable_rls_for_transaction()
        names = list(OrgUnit.objects.values_list("name", flat=True))
    assert names == [], "bypass leaked into un-tenanted worker transaction"


@override_settings(RLS_TRANSACTION_SCOPED=True)
def test_cross_tenant_write_denied_under_transaction_pooling(two_org_units):
    """Tenant A guard altında Tenant B üçün OrgUnit yaratmağa cəhd → RLS blok.

    Bu, hətta guard SET LOCAL etsə də, tenant B üçün yeni obyekt yaratmaq
    üçün gərəkli WITH CHECK-in işlədiyini yoxlayır (fail-closed WRITE).
    """
    from django.db import DataError, IntegrityError, ProgrammingError

    org_a, org_b, _unit_a, _unit_b = two_org_units

    with transaction.atomic():
        _enable_rls_for_transaction()
        guard = RLSTransactionGuard(user_id=org_a.owner_id, org_id=org_a.pk, bypass=False)
        wrapper_cm = connection.execute_wrapper(guard)
        wrapper_cm.__enter__()
        try:
            # Tenant A guard-ı altında B-nin org-una OrgUnit yaratmaq cəhdi.
            with pytest.raises((IntegrityError, ProgrammingError, DataError)):
                OrgUnit.objects.create(
                    organization=org_b,
                    name="Leaked Unit",
                    slug="leaked-unit-cross-tenant",
                    unit_type="faculty",
                )
        finally:
            wrapper_cm.__exit__(None, None, None)
            reset_txn_flags(connection)


@override_settings(RLS_TRANSACTION_SCOPED=True)
def test_txn_applied_flag_reset_between_transactions(two_org_units):
    """`_rls_txn_applied` bayrağı hər transaction sonunda sıfırlanmalıdır.

    Bu, guard-ın yeni transaction-da yenidən SET LOCAL tətbiq etməsini təmin
    edir. Regressiya: reset olmasa, ikinci transaction öz konteksti tətbiq
    etməyəcək və birincinin state-ini (session scope-da) miras alacaq.
    """
    org_a, org_b, _unit_a, _unit_b = two_org_units

    # İlk transaction — bayraq açılmalı, sonra reset-də sıfırlanmalı.
    with transaction.atomic():
        _enable_rls_for_transaction()
        guard = RLSTransactionGuard(user_id=org_a.owner_id, org_id=org_a.pk, bypass=False)
        with connection.execute_wrapper(guard):
            list(OrgUnit.objects.values_list("pk", flat=True))
            assert getattr(connection, "_rls_txn_applied", False) is True
    reset_txn_flags(connection)
    assert getattr(connection, "_rls_txn_applied", False) is False

    # İkinci transaction — bayraq təzədən qoyulmalı və B tenant-ının kontekstini görməli.
    with transaction.atomic():
        _enable_rls_for_transaction()
        guard = RLSTransactionGuard(user_id=org_b.owner_id, org_id=org_b.pk, bypass=False)
        with connection.execute_wrapper(guard):
            list(OrgUnit.objects.values_list("pk", flat=True))
            assert getattr(connection, "_rls_txn_applied", False) is True
            assert _current_setting("app.current_org_id") == str(org_b.pk)
    reset_txn_flags(connection)
