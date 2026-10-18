"""«Mühasibatlıq» — planın aylara bölgüsü bayram / qeyri-iş günlərini iş günü saymır (2026-10-19)."""

from __future__ import annotations

from datetime import date

import pytest

from apps.accounts.services.accounting import periods
from apps.organizations.models import AcademicHoliday, HolidayKind
from apps.syllabus.tests.factories import make_academic_stack, make_org

pytestmark = pytest.mark.django_db


@pytest.fixture()
def semester():
    org = make_org("acc-hol")
    stack = make_academic_stack(org, code="ACH101")  # 2025-09-01 … 2026-01-31, imtahan sessiyası yoxdur
    stack["period"].refresh_from_db()
    (item,) = periods.semesters([stack["period"]], today=date(2025, 10, 1))
    return org, item


def test_semester_carries_organization(semester):
    org, item = semester
    assert item.organization_id == str(org.pk)


def test_holidays_are_not_teaching_days_and_transfer_workday_is(semester):
    org, item = semester
    before = periods.teaching_days(item)
    AcademicHoliday.objects.create(organization=org, date=date(2025, 11, 10), name="Bayraq günü (köçürülmüş)")
    AcademicHoliday.objects.create(
        organization=org, date=date(2025, 11, 11), name="Qeyri-iş günü", kind=HolidayKind.DAY_OFF
    )
    AcademicHoliday.objects.create(
        organization=org, date=date(2025, 11, 15), name="Şənbə iş günü", kind=HolidayKind.WORKDAY
    )
    AcademicHoliday.objects.create(organization=org, date=date(2025, 11, 9), name="Bazar — onsuz da iş günü deyil")
    after = periods.teaching_days(item)
    assert after["2025-11"] == before["2025-11"] - 2 + 1
    assert {key: value for key, value in after.items() if key != "2025-11"} == {
        key: value for key, value in before.items() if key != "2025-11"
    }
    days = periods.teaching_day_set(item)
    assert date(2025, 11, 10) not in days and date(2025, 11, 15) in days
    # Bölgü yenə semestr planına DƏQİQ bərabərdir.
    assert round(sum(periods.apportion(90, after).values()), 1) == 90


def test_semester_without_organization_counts_weekdays_only(semester):
    org, item = semester
    AcademicHoliday.objects.create(organization=org, date=date(2025, 11, 10), name="Bayram")
    bare = periods.Semester(**{**item.__dict__, "organization_id": None})
    assert date(2025, 11, 10) in periods.teaching_day_set(bare)
