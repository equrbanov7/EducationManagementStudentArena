"""Müraciət cədvəllərinin DB səviyyəli tenant izolyasiyası (RLS).

``emsarena_agent`` superuser + BYPASSRLS-dir, ona görə mənfi assert-lər yalnız
``SET LOCAL ROLE rls_app_role`` altında etibarlıdır (bax
``apps/syllabus/tests/test_rls.py``).
"""

from __future__ import annotations

from django.db import connection

import pytest

from apps.applications.models import (
    Application,
    ApplicationAttachment,
    ApplicationEvent,
    ApplicationKind,
    ApplicationUnit,
    ApplicationWatch,
)
from apps.applications.services import submit, workflow
from apps.applications.tests.factories import kind_of, make_world, unit_of

pytestmark = pytest.mark.postgres


def _is_pg():
    return connection.vendor == "postgresql"


def _set(name, value):
    with connection.cursor() as cur:
        cur.execute("SELECT set_config(%s, %s, false)", [name, str(value)])


def _enable_rls_for_tenant(org_id):
    _set("app.bypass_rls", "off")
    _set("app.current_org_id", str(org_id))
    _set("app.current_user_id", "")
    with connection.cursor() as cur:
        cur.execute("SET LOCAL ROLE rls_app_role")


@pytest.fixture(autouse=True)
def _rls_bypass_for_tests(db):
    if not _is_pg():
        yield
        return
    _set("app.bypass_rls", "on")
    _set("app.current_org_id", "")
    try:
        yield
    finally:
        _set("app.bypass_rls", "off")
        _set("app.current_org_id", "")


@pytest.fixture()
def two_tenants():
    if not _is_pg():
        pytest.skip("müraciət RLS testləri PostgreSQL tələb edir")
    worlds = {}
    for tag in ("a", "b"):
        world = make_world(f"rls-{tag}")
        application = submit.submit_application(
            organization=world["organization"],
            user=world["student"],
            kind=kind_of(world, "diger"),
            subject=f"Tenant {tag} müraciəti",
            body=f"Tenant {tag} üçün kifayət qədər uzun müraciət mətni burada.",
        )
        workflow.mark_seen(application=application, user=world["coordinator"])
        workflow.forward(
            application=application,
            user=world["coordinator"],
            target_unit=unit_of(world, "rim"),
            note="İzləmə sətri yaransın deyə yönləndirilir.",
        )
        worlds[tag] = world
    return worlds["a"], worlds["b"]


def test_applications_are_tenant_isolated(two_tenants):
    world_a, _world_b = two_tenants
    _enable_rls_for_tenant(world_a["organization"].pk)
    assert Application.objects.count() == 1
    assert set(Application.objects.values_list("organization_id", flat=True)) == {world_a["organization"].pk}


def test_catalog_events_and_watches_are_tenant_isolated(two_tenants):
    _world_a, world_b = two_tenants
    _enable_rls_for_tenant(world_b["organization"].pk)
    assert ApplicationUnit.objects.count() == 9
    assert ApplicationKind.objects.count() == 15
    assert ApplicationWatch.objects.count() == 1
    assert ApplicationEvent.objects.count() == 3
    assert set(ApplicationEvent.objects.values_list("organization_id", flat=True)) == {world_b["organization"].pk}


def test_missing_tenant_context_denies_all(two_tenants):
    _enable_rls_for_tenant("")
    assert Application.objects.count() == 0
    assert ApplicationUnit.objects.count() == 0
    assert ApplicationEvent.objects.count() == 0
    assert ApplicationAttachment.objects.count() == 0


def test_cross_tenant_read_is_rejected_at_the_table(two_tenants):
    world_a, world_b = two_tenants
    _enable_rls_for_tenant(world_a["organization"].pk)
    with connection.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM applications_application WHERE organization_id = %s",
            [str(world_b["organization"].pk)],
        )
        assert cur.fetchone()[0] == 0
