"""Müraciətin cavab müddəti iş günü ilə — bayram / qeyri-iş günü çıxılır, iş günü köçürməsi sayılır (2026-10-19)."""

from __future__ import annotations

from datetime import date
from unittest import mock

import pytest

from apps.applications.services import submit
from apps.applications.sla import add_working_days, calendar_for, sla_banner, working_days_between
from apps.applications.tests.factories import kind_of, make_world
from apps.organizations.models import AcademicHoliday, HolidayKind

pytestmark = pytest.mark.django_db

FRIDAY = date(2026, 11, 6)
MONDAY_HOLIDAY = date(2026, 11, 9)  # Dövlət Bayrağı günü


@pytest.fixture()
def world():
    return make_world("sla-hol")


def test_calendar_skips_holidays_and_counts_transfer_workdays(world):
    org = world["organization"]
    AcademicHoliday.objects.create(organization=org, date=MONDAY_HOLIDAY, name="Dövlət Bayrağı günü")
    calendar = calendar_for(org)
    assert add_working_days(FRIDAY, 1, calendar) == date(2026, 11, 10)
    assert working_days_between(FRIDAY, date(2026, 11, 10), calendar) == 1
    AcademicHoliday.objects.create(
        organization=org, date=date(2026, 11, 7), name="Şənbə iş günü", kind=HolidayKind.WORKDAY
    )
    calendar = calendar_for(org)
    assert add_working_days(FRIDAY, 1, calendar) == date(2026, 11, 7)
    banner = sla_banner(
        due_on=date(2026, 11, 10), sla_days=3, today=FRIDAY, is_open=True, status_label="x", holidays=calendar
    )
    assert banner == {"tone": "ontime", "days": 2, "sla_days": 3, "status_label": "x"}


def test_calendar_for_without_organization_is_none():
    assert calendar_for(None) is None
    assert add_working_days(FRIDAY, 1, None) == MONDAY_HOLIDAY


def test_submission_due_date_skips_the_holiday(world):
    org = world["organization"]
    AcademicHoliday.objects.create(organization=org, date=MONDAY_HOLIDAY, name="Dövlət Bayrağı günü")
    kind = kind_of(world, "diger")
    with mock.patch("apps.applications.services.submit.timezone.localdate", return_value=FRIDAY):
        application = submit.submit_application(
            organization=org,
            user=world["student"],
            kind=kind,
            subject="Bayram testi",
            body="Bayram günü cavab müddətinə daxil edilməməlidir — yoxlama mətni.",
        )
    assert application.sla_due_on == add_working_days(FRIDAY, kind.sla_days, {MONDAY_HOLIDAY})
    assert application.sla_due_on != add_working_days(FRIDAY, kind.sla_days)
