"""RLS — dörd yeni cədvəlin tenant izolyasiyası (yalnız PostgreSQL).

``organizations/tests/test_rls.py`` naxışı: məlumat bypass ilə yaradılır, sonra
``SET LOCAL ROLE rls_app_role`` (superuser olmayan rol) + ``app.current_org_id``
ilə yalnız aktiv tenantın sətirlərinin göründüyü yoxlanılır.
"""

from __future__ import annotations

import datetime

from django.db import connection

import pytest

from apps.organizations.models import AcademicPeriod, Organization, OrgUnit
from apps.registrar.models import CourseOffering, Subject
from apps.timetable.models import GroupTimePolicy, TeacherAvailability, TimetableDraftSlot, TimetableRun
from core.constants import AcademicPeriodType, OrganizationType, OrgUnitType

pytestmark = pytest.mark.postgres


def _set(name, value):
    with connection.cursor() as cursor:
        cursor.execute("SELECT set_config(%s, %s, false)", [name, value])


@pytest.fixture(autouse=True)
def _rls_bypass_for_tests(db):
    if connection.vendor != "postgresql":
        pytest.skip("RLS PostgreSQL tələb edir")
    _set("app.bypass_rls", "on")
    try:
        yield
    finally:
        _set("app.bypass_rls", "off")
        _set("app.current_org_id", "")


def _tenant(slug, user):
    org = Organization.objects.create(
        name=slug, slug=slug, org_type=OrganizationType.UNIVERSITY, owner=user, status="active", is_active=True
    )
    group = OrgUnit.objects.create(organization=org, name=f"{slug}-g", slug=f"{slug}-g", unit_type=OrgUnitType.GROUP)
    period = AcademicPeriod.objects.create(
        organization=org,
        name="Payız",
        period_type=AcademicPeriodType.SEMESTER,
        academic_year="2026/2027",
        start_date=datetime.date(2026, 9, 1),
        end_date=datetime.date(2027, 1, 31),
    )
    subject = Subject.objects.create(organization=org, code=f"{slug}1", name="Fənn")
    offering = CourseOffering.objects.create(organization=org, subject=subject, period=period, group=group)
    TeacherAvailability.objects.create(organization=org, teacher=user, period=period, grid={"1": "u"})
    GroupTimePolicy.objects.create(organization=org, group=group, bands=["morning"])
    run = TimetableRun.objects.create(organization=org, period=period, title=slug)
    TimetableDraftSlot.objects.create(organization=org, run=run, event_key="L:x:0", offering=offering, kind="lecture")
    return org


@pytest.mark.django_db
def test_timetable_tables_are_tenant_isolated(django_user_model):
    user_a = django_user_model.objects.create_user("ttrls_a", "ttrls_a@x.test", "pw")
    user_b = django_user_model.objects.create_user("ttrls_b", "ttrls_b@x.test", "pw")
    org_a = _tenant("ttrls-a", user_a)
    _tenant("ttrls-b", user_b)

    _set("app.bypass_rls", "off")
    with connection.cursor() as cursor:
        cursor.execute("SET LOCAL ROLE rls_app_role")
    _set("app.current_org_id", str(org_a.pk))
    for model in (TeacherAvailability, GroupTimePolicy, TimetableRun, TimetableDraftSlot):
        orgs = set(model.objects.values_list("organization_id", flat=True))
        assert orgs == {org_a.pk}, model.__name__

    _set("app.current_org_id", "")
    for model in (TeacherAvailability, GroupTimePolicy, TimetableRun, TimetableDraftSlot):
        assert not model.objects.exists(), model.__name__
