"""Dərs yükü cədvəllərinin DB səviyyəli tenant izolyasiyası + saat trigger-i.

Naxış: ``apps/syllabus/tests/test_rls.py``. Data bypass rejimində yaradılır,
sonra tranzaksiya daxilində ``SET LOCAL ROLE rls_app_role`` ilə məhdud rola
keçilir — yalnız onda siyasətlər tətbiq olunur (``emsarena_agent`` superuser +
BYPASSRLS olduğu üçün mənfi assert-lər onunla YALANÇI keçər).
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.db import connection

import pytest

from apps.workload.constants import Activity
from apps.workload.models import TeacherAssignment, TeachingTask, TeachingTaskRow
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
def two_org_tasks():
    if not _is_pg():
        pytest.skip("dərs yükü RLS testləri PostgreSQL tələb edir")
    orgs = {}
    for tag in ("a", "b"):
        org = make_org(f"wl-rls-{tag}")
        stack = make_structure(org, code=f"RLS{tag.upper()}")
        task = make_task(org, stack["chair"])
        row = make_row(task, stack, lecture_total=10, seminar_total=0)
        TeacherAssignment.objects.create(organization=org, row=row, activity=Activity.LECTURE, hours=10)
        orgs[tag] = (org, row)
    return orgs["a"], orgs["b"]


def test_tasks_are_tenant_isolated(two_org_tasks):
    (org_a, _row_a), _b = two_org_tasks
    _enable_rls_for_tenant(org_a.pk)
    assert TeachingTask.objects.count() == 1
    assert set(TeachingTask.objects.values_list("organization_id", flat=True)) == {org_a.pk}


def test_rows_and_assignments_are_tenant_isolated(two_org_tasks):
    _a, (org_b, _row_b) = two_org_tasks
    _enable_rls_for_tenant(org_b.pk)
    assert TeachingTaskRow.objects.count() == 1
    assert TeacherAssignment.objects.count() == 1
    assert set(TeacherAssignment.objects.values_list("organization_id", flat=True)) == {org_b.pk}


def test_missing_tenant_context_denies_all(two_org_tasks):
    _enable_rls_for_tenant("")
    assert TeachingTask.objects.count() == 0
    assert TeachingTaskRow.objects.count() == 0
    assert TeacherAssignment.objects.count() == 0


def test_hour_balance_trigger_blocks_over_allocation(two_org_tasks):
    """Servis qatını YAN KEÇƏN yazı da DB trigger-i ilə bağlanır."""
    (org_a, row_a), _b = two_org_tasks
    from django.db import IntegrityError, transaction
    from django.db.utils import InternalError, ProgrammingError

    with pytest.raises((IntegrityError, InternalError, ProgrammingError, Exception)) as excinfo:
        with transaction.atomic():
            TeacherAssignment.objects.create(organization=org_a, row=row_a, activity=Activity.LECTURE, hours=1)
    assert "workload_hour_balance_exceeded" in str(excinfo.value)


def test_amendment_table_is_append_only(two_org_tasks):
    from django.db import transaction

    from apps.workload.constants import AmendmentReason, AmendmentTarget
    from apps.workload.models import WorkloadAmendment

    (org_a, row_a), _b = two_org_tasks
    amendment = WorkloadAmendment.objects.create(
        organization=org_a,
        task=row_a.task,
        target_kind=AmendmentTarget.ROW,
        target_id=row_a.pk,
        reason=AmendmentReason.OTHER,
        note="ilkin",
    )
    with pytest.raises(Exception) as excinfo:
        with transaction.atomic():
            with connection.cursor() as cur:
                cur.execute(
                    "UPDATE workload_workloadamendment SET note = %s WHERE id = %s",
                    ["dəyişdirilmiş", str(amendment.pk)],
                )
    assert "append-only" in str(excinfo.value)
