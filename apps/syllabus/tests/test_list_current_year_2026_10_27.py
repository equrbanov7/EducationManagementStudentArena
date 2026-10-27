"""Sahib 2026-10-27: müəllimin «Sillabuslar» siyahısında YALNIZ cari tədris ili — köhnə illərin sillabusu yox."""

from __future__ import annotations

from django.test import RequestFactory

import pytest

from apps.organizations.models import AcademicPeriod
from apps.syllabus.models import Syllabus
from apps.syllabus.tests.reuse_fixtures import TEACHER_PERMS, approved_syllabus, build_world
from core.constants import AcademicPeriodType

pytestmark = pytest.mark.django_db


@pytest.fixture()
def world():
    data = build_world("syl-cur-year")
    current, _version = approved_syllabus(data, "o1")
    old, _old_version = approved_syllabus(data, "o2")
    last_year = AcademicPeriod.objects.create(
        organization=data["org"],
        name="Payız",
        period_type=AcademicPeriodType.SEMESTER,
        academic_year="2024/2025",
        start_date="2024-09-01",
        end_date="2025-01-31",
    )
    Syllabus.objects.filter(pk=old.pk).update(period=last_year, offering=None)
    data["current"], data["old"] = current, old
    return data


def _section(world, key, permissions, **params):
    from apps.accounts.views.syllabus.section import build_syllabus_list_section

    request = RequestFactory().get("/accounts/profile/", params)
    request.user = world[key]
    request.org_permissions = list(permissions)
    request.organization = world["org"]
    return build_syllabus_list_section(request, organization=world["org"])["syllabus_list_section"]


def _ids(section):
    return {row["id"] for row in section["rows"]}


def test_teacher_sees_only_the_current_academic_year(world):
    section = _section(world, "teacher", TEACHER_PERMS)
    assert str(world["current"].pk) in _ids(section)
    assert str(world["old"].pk) not in _ids(section)
    # İl süzgəcini əl ilə köhnə ilə göndərmək də köhnə sillabusu qaytarmır; seçimdə yalnız cari il var.
    forced = _section(world, "teacher", TEACHER_PERMS, year="2024/2025")
    assert str(world["old"].pk) not in _ids(forced)
    assert [year["key"] for year in forced["filter_options"]["years"]] == [world["period"].academic_year]


def test_leader_keeps_all_years(world):
    from apps.syllabus import services

    permissions = services.resolve_actor(world["head"], world["org"]).permissions
    section = _section(world, "head", permissions)
    assert {str(world["current"].pk), str(world["old"].pk)} <= _ids(section)


def test_teacher_current_year_keeps_periodless_base_syllabus(world):
    """Semestrsiz baza sillabus (köçürmə, ``syllabi_backfill``) müəllimin cari il görünüşündə də var."""
    from django.utils import timezone

    from apps.syllabus.services.drafts import import_migrated_version

    base, _version = import_migrated_version(
        organization=world["org"],
        subject=world["subject"],
        approved_at=timezone.now(),
        chair_unit=world["chair"],
        author=world["teacher"],
    )
    other, _other_version = import_migrated_version(
        organization=world["org"],
        subject=world["subject"],
        approved_at=timezone.now(),
        chair_unit=world["chair"],
        author=world["teacher2"],
    )
    section = _section(world, "teacher", TEACHER_PERMS)
    assert str(base.pk) in _ids(section)
    assert str(world["current"].pk) in _ids(section)
    assert str(world["old"].pk) not in _ids(section)
    assert str(other.pk) not in _ids(section), "başqa müəllimin baza sillabusu görünmür"
