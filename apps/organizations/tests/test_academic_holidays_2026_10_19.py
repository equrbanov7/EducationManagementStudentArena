"""«Bayram və qeyri-iş günləri» — model, keşli iş təqvimi, sabit bayramlar, RLS (sahib 2026-10-19)."""

from __future__ import annotations

from datetime import date

from django.db import IntegrityError, connection, transaction

import pytest

from apps.organizations import holidays
from apps.organizations.models import AcademicHoliday, HolidayKind
from apps.syllabus.tests.factories import make_org

pytestmark = pytest.mark.django_db


def _cold(org, years):
    """Keşi soyut — ``invalidate`` tranzaksiya içində açarı commit-ə qədər «gözləyən» edir (keşsiz oxu)."""
    for year in years:
        key = holidays._KEY.format(org=org.pk, year=year)
        holidays._local.pop(key, None)
        holidays._pending.pop(key, None)


@pytest.fixture()
def org():
    return make_org("hol-org")


def test_unique_date_per_organization(org):
    AcademicHoliday.objects.create(organization=org, date=date(2026, 11, 8), name="Zəfər günü")
    with pytest.raises(IntegrityError), transaction.atomic():
        AcademicHoliday.objects.create(organization=org, date=date(2026, 11, 8), name="Təkrar")
    other = make_org("hol-org-2")
    AcademicHoliday.objects.create(organization=other, date=date(2026, 11, 8), name="Zəfər günü")


def test_work_calendar_kinds_and_weekends(org):
    AcademicHoliday.objects.create(organization=org, date=date(2026, 11, 9), name="Bayraq günü")  # bazar ertəsi
    AcademicHoliday.objects.create(
        organization=org, date=date(2026, 11, 10), name="Köçürülmüş istirahət", kind=HolidayKind.DAY_OFF
    )
    AcademicHoliday.objects.create(
        organization=org, date=date(2026, 11, 14), name="İş günü elan olunub", kind=HolidayKind.WORKDAY
    )  # şənbə
    calendar = holidays.work_calendar(org)
    assert not calendar.is_working_day(date(2026, 11, 9))
    assert not calendar.is_working_day(date(2026, 11, 10))
    assert calendar.is_working_day(date(2026, 11, 11))
    assert calendar.is_working_day(date(2026, 11, 14))  # şənbə, amma iş günü köçürməsi
    assert not calendar.is_working_day(date(2026, 11, 15))  # bazar
    assert date(2026, 11, 9) in calendar and date(2026, 11, 14) not in calendar
    assert calendar.non_working_between(date(2026, 11, 1), date(2026, 11, 30)) == {
        date(2026, 11, 9),
        date(2026, 11, 10),
    }
    assert calendar.extra_workdays_between(date(2026, 11, 1), date(2026, 11, 30)) == {date(2026, 11, 14)}


def test_year_map_is_invalidated_on_save_and_delete(org, django_assert_num_queries):
    _cold(org, {2027})
    assert holidays.year_map(org, 2027) == {}
    with django_assert_num_queries(0):  # proses daxili keş — ikinci oxu bazaya getmir
        holidays.year_map(org, 2027)
    item = AcademicHoliday.objects.create(organization=org, date=date(2027, 3, 8), name="Qadınlar günü")
    assert holidays.year_map(org, 2027) == {"2027-03-08": "holiday"}
    item.date = date(2027, 5, 9)
    item.save()
    assert holidays.year_map(org, 2027) == {"2027-05-09": "holiday"}
    item.delete()
    assert holidays.year_map(org, 2027) == {}


def test_calendar_reads_each_year_once(org, django_assert_num_queries):
    """Sorğu sayı gün sayından asılı deyil: hər təqvim ili bir oxu (≤4 sorğu: RLS bypass GUC-ları daxil), sonra 0."""
    from django.test.utils import CaptureQueriesContext

    _cold(org, {2026, 2027})
    calendar = holidays.work_calendar(org)
    with CaptureQueriesContext(connection) as first_year:
        calendar.is_working_day(date(2026, 9, 1))
    assert 1 <= len(first_year.captured_queries) <= 4  # SELECT + bypass GUC oxu/yaz/bərpa
    with django_assert_num_queries(0):
        for day in range(1, 31):
            calendar.is_working_day(date(2026, 11, day))
    with django_assert_num_queries(len(first_year.captured_queries)):
        for month in range(1, 9):
            calendar.is_working_day(date(2027, month, 1))
    with django_assert_num_queries(0):  # yeni obyekt — proses daxili keş
        holidays.work_calendar(org).non_working_between(date(2026, 9, 1), date(2027, 8, 31))


def test_fixed_holidays_for_academic_year():
    rows = holidays.fixed_holidays_for(2026)
    items = {day: name for day, name, _kind in rows}
    kinds = {day: kind for day, _name, kind in rows}
    assert kinds[date(2027, 1, 20)] == "day_off"  # Ümumxalq hüzn günü — qeyri-iş günü (ƏM m. 105)
    assert {kind for day, kind in kinds.items() if day != date(2027, 1, 20)} == {"holiday"}
    assert date(2026, 11, 8) in items and date(2026, 12, 31) in items
    assert date(2027, 1, 1) in items and date(2027, 1, 2) in items
    assert [day for day in items if day.month == 3 and 20 <= day.day <= 24] == [date(2027, 3, d) for d in range(20, 25)]
    assert {date(2027, 3, 8), date(2027, 5, 9), date(2027, 5, 28), date(2027, 6, 15), date(2027, 6, 26)} <= set(items)
    assert len(items) == 16


def test_seed_fixed_holidays_skips_existing_and_is_idempotent(org):
    AcademicHoliday.objects.create(
        organization=org, date=date(2027, 3, 20), name="Novruz (əl ilə)", kind=HolidayKind.DAY_OFF
    )
    first = holidays.seed_fixed_holidays(organization=org, actor=None, start_year=2026)
    assert (first["created"], first["skipped"]) == (15, 1)
    assert AcademicHoliday.objects.get(organization=org, date=date(2027, 3, 20)).name == "Novruz (əl ilə)"
    again = holidays.seed_fixed_holidays(organization=org, actor=None, start_year=2026)
    assert (again["created"], again["skipped"]) == (0, 16)
    # Toplu əlavə də keşi təzələyir.
    assert holidays.work_calendar(org).is_non_working(date(2026, 11, 8))
    assert AcademicHoliday.objects.get(organization=org, date=date(2027, 1, 20)).kind == HolidayKind.DAY_OFF


def test_save_holiday_validation(org):
    with pytest.raises(holidays.HolidayError) as exc:
        holidays.save_holiday(organization=org, actor=None, raw_date="2026-11-11", name="X", kind="workday")
    assert exc.value.code == "workday_on_weekday"
    with pytest.raises(holidays.HolidayError) as exc:
        holidays.save_holiday(organization=org, actor=None, raw_date="bad", name="X")
    assert exc.value.field == "date"
    holidays.save_holiday(organization=org, actor=None, raw_date="2026-11-08", name="Zəfər günü")
    with pytest.raises(holidays.HolidayError) as exc:
        holidays.save_holiday(organization=org, actor=None, raw_date="2026-11-08", name="Təkrar")
    assert exc.value.code == "duplicate"
    with pytest.raises(holidays.HolidayError) as exc:
        holidays.delete_holiday(organization=org, actor=None, holiday_id="not-a-uuid")
    assert exc.value.status == 404


@pytest.mark.postgres
def test_rls_isolates_holidays_and_calendar_reads_explicit_org(org):
    if connection.vendor != "postgresql":
        pytest.skip("RLS PostgreSQL tələb edir")
    from apps.organizations.tests.test_rls import _enable_rls, _set_tenant

    other = make_org("hol-org-rls")
    AcademicHoliday.objects.create(organization=org, date=date(2026, 12, 31), name="Həmrəylik günü")
    AcademicHoliday.objects.create(organization=other, date=date(2026, 11, 8), name="Zəfər günü")
    _cold(org, {2026})
    _enable_rls()  # bypass off + məhdud rol
    assert AcademicHoliday.objects.count() == 0  # tenant yoxdur → heç nə
    _set_tenant(other.pk)
    assert list(AcademicHoliday.objects.values_list("name", flat=True)) == ["Zəfər günü"]
    # İş təqvimi fon işlərində də (tenant başqa / yoxdur) öz təşkilatını AÇIQ süzgəclə oxuyur.
    calendar = holidays.work_calendar(org)
    assert calendar.is_non_working(date(2026, 12, 31))
    assert not calendar.is_non_working(date(2026, 11, 8))


LOCMEM = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "holidays-commit"}}


def test_shared_cache_is_invalidated_only_after_commit(org, settings, django_capture_on_commit_callbacks):
    """Rəy 2026-10-19: Redis silinməsi ``on_commit``-dədir; commit-ə qədər oxu keşə HEÇ NƏ yazmır."""
    from django.core.cache import cache

    settings.CACHES = LOCMEM
    cache.clear()
    key = holidays._KEY.format(org=org.pk, year=2026)
    holidays._local.pop(key, None)
    holidays._pending.pop(key, None)
    cache.set(key, {"2026-01-01": "holiday"})  # köhnə paylaşılan dəyər
    with django_capture_on_commit_callbacks(execute=False) as callbacks:
        AcademicHoliday.objects.create(organization=org, date=date(2026, 11, 8), name="Zəfər günü")
        assert cache.get(key) == {"2026-01-01": "holiday"}  # commit-dən əvvəl Redis-ə toxunulmur
        assert holidays.year_map(org, 2026) == {"2026-11-08": "holiday"}  # oxu bazadan …
        assert cache.get(key) == {"2026-01-01": "holiday"}  # … və commit olunmamış dəyər keşə yazılmır
        assert key not in holidays._local
    assert callbacks, "invalidasiya on_commit-ə qoyulmalıdır"
    for callback in callbacks:
        callback()
    assert cache.get(key) is None and key not in holidays._pending
    assert holidays.year_map(org, 2026) == {"2026-11-08": "holiday"}
    assert cache.get(key) == {"2026-11-08": "holiday"}  # commit-dən sonra yenidən keşlənir


def test_seed_invalidation_waits_for_commit(org, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=False) as callbacks:
        holidays.seed_fixed_holidays(organization=org, actor=None, start_year=2026)
    assert callbacks
