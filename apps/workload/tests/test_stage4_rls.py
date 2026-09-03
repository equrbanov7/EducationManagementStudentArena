"""Mərhələ 4 cədvəllərinin DB səviyyəli qorumaları (miqrasiya ``0005``).

Naxış ``test_rls.py`` ilə eynidir: data bypass rejimində yaradılır, sonra
``SET LOCAL ROLE rls_app_role`` ilə məhdud rola keçilir — yalnız onda RLS
siyasətləri tətbiq olunur (``emsarena_agent`` BYPASSRLS olduğu üçün mənfi
assert-lər onunla YALANÇI keçər).
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.db import connection, transaction

import pytest

from apps.workload.constants import ObjectionReason, SliceStatus
from apps.workload.models import LoadObjection, TaskFacultySlice, TaskRowReview
from apps.workload.tests.factories import make_org, make_row, make_structure, make_task

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
        pytest.skip("Mərhələ 4 RLS testləri PostgreSQL tələb edir")
    result = {}
    for tag in ("a", "b"):
        org = make_org(f"wl-s4-{tag}")
        stack = make_structure(org, code=f"S4{tag.upper()}")
        task = make_task(org, stack["chair"])
        row = make_row(task, stack, lecture_total=10, seminar_total=0)
        teacher = User.objects.create_user(f"s4rls_{tag}", f"s4rls_{tag}@x.test", "pw")
        TaskFacultySlice.objects.create(
            organization=org, task=task, faculty=stack["faculty"], revision=0, status=SliceStatus.PENDING
        )
        TaskRowReview.objects.create(organization=org, row=row, coordinator=teacher, status="reviewed")
        LoadObjection.objects.create(
            organization=org,
            row=row,
            teacher=teacher,
            reason_key=ObjectionReason.HOURS,
            text="Saat sayı düz deyil — plan sətri ilə uyğunsuzluq var.",
        )
        result[tag] = (org, row, teacher)
    return result


def test_slices_reviews_and_objections_are_tenant_isolated(two_tenants):
    org_a = two_tenants["a"][0]
    _enable_rls_for_tenant(org_a.pk)
    assert TaskFacultySlice.objects.count() == 1
    assert TaskRowReview.objects.count() == 1
    assert LoadObjection.objects.count() == 1
    assert set(LoadObjection.objects.values_list("organization_id", flat=True)) == {org_a.pk}


def test_missing_tenant_context_denies_all(two_tenants):
    _enable_rls_for_tenant("")
    assert TaskFacultySlice.objects.count() == 0
    assert TaskRowReview.objects.count() == 0
    assert LoadObjection.objects.count() == 0


def test_objection_text_is_append_only(two_tenants):
    """Mətn heç vaxt redaktə olunmur — DB trigger-i UPDATE-i rədd edir."""
    objection = LoadObjection.objects.filter(organization=two_tenants["a"][0]).get()
    with pytest.raises(Exception) as excinfo:
        with transaction.atomic():
            with connection.cursor() as cur:
                cur.execute(
                    "UPDATE workload_loadobjection SET text = %s WHERE id = %s",
                    ["dəyişdirilmiş mətn", str(objection.pk)],
                )
    assert "append-only" in str(excinfo.value)


def test_objection_cannot_be_deleted(two_tenants):
    objection = LoadObjection.objects.filter(organization=two_tenants["a"][0]).get()
    with pytest.raises(Exception) as excinfo:
        with transaction.atomic():
            with connection.cursor() as cur:
                cur.execute("DELETE FROM workload_loadobjection WHERE id = %s", [str(objection.pk)])
    assert "append-only" in str(excinfo.value)


def test_resolution_fields_stay_editable(two_tenants):
    """Kafedra müdirinin qərarı (status + qeyd) icazəlidir — mətn yox."""
    objection = LoadObjection.objects.filter(organization=two_tenants["a"][0]).get()
    with connection.cursor() as cur:
        cur.execute(
            "UPDATE workload_loadobjection SET status = %s, resolution_note = %s WHERE id = %s",
            ["accepted", "Sətir yenidən bölündü.", str(objection.pk)],
        )
    objection.refresh_from_db()
    assert objection.status == "accepted"
    assert objection.resolution_note == "Sətir yenidən bölündü."
