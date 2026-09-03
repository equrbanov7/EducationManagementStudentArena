"""Sillabus cədvəllərinin DB səviyyəli tenant izolyasiyası (RLS).

Nümunə: ``apps/registrar/tests/test_rls.py``. Data bypass rejimində yaradılır,
sonra tranzaksiya daxilində ``SET LOCAL ROLE rls_app_role`` ilə məhdud rola
keçilir — yalnız onda siyasətlər tətbiq olunur (``emsarena_agent`` superuser +
BYPASSRLS olduğu üçün mənfi assert-lər onunla YALANÇI keçər).
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.db import connection

import pytest

from apps.syllabus.models import Syllabus, SyllabusReview, SyllabusSection, SyllabusVersion
from apps.syllabus.tests.factories import make_academic_stack, make_org

User = get_user_model()

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
def two_org_syllabi():
    if not _is_pg():
        pytest.skip("sillabus RLS testləri PostgreSQL tələb edir")
    orgs = {}
    for tag in ("a", "b"):
        org = make_org(f"syl-rls-{tag}")
        stack = make_academic_stack(org, code=f"RLS{tag.upper()}")
        syllabus = Syllabus.objects.create(
            organization=org,
            subject=stack["subject"],
            period=stack["period"],
            chair_unit=stack["chair"],
        )
        version = SyllabusVersion.objects.create(organization=org, syllabus=syllabus, major=1, minor=0)
        SyllabusSection.objects.create(organization=org, version=version, section_id="desc", data={"description": tag})
        SyllabusReview.objects.create(organization=org, version=version, decision="opened", reason="")
        orgs[tag] = org
    return orgs["a"], orgs["b"]


def test_syllabus_rows_are_tenant_isolated(two_org_syllabi):
    org_a, _org_b = two_org_syllabi
    _enable_rls_for_tenant(org_a.pk)
    assert Syllabus.objects.count() == 1
    assert set(Syllabus.objects.values_list("organization_id", flat=True)) == {org_a.pk}


def test_versions_sections_and_reviews_are_tenant_isolated(two_org_syllabi):
    _org_a, org_b = two_org_syllabi
    _enable_rls_for_tenant(org_b.pk)
    assert SyllabusVersion.objects.count() == 1
    assert SyllabusSection.objects.count() == 1
    assert SyllabusReview.objects.count() == 1
    assert list(SyllabusSection.objects.values_list("data", flat=True)) == [{"description": "b"}]


def test_missing_tenant_context_denies_all(two_org_syllabi):
    _enable_rls_for_tenant("")
    assert Syllabus.objects.count() == 0
    assert SyllabusVersion.objects.count() == 0
    assert SyllabusSection.objects.count() == 0
    assert SyllabusReview.objects.count() == 0


def test_cross_tenant_write_is_rejected(two_org_syllabi):
    org_a, org_b = two_org_syllabi
    _enable_rls_for_tenant(org_a.pk)
    foreign = Syllabus.objects.all()  # yalnız A görünür
    assert foreign.count() == 1
    with connection.cursor() as cur:
        cur.execute("SELECT count(*) FROM syllabus_syllabus WHERE organization_id = %s", [str(org_b.pk)])
        assert cur.fetchone()[0] == 0
