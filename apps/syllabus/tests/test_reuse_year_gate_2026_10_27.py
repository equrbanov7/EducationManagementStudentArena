"""Sahib 2026-10-27: «müəllimin köhnə illərdəki yazdığı sillabuslar görünməsin — sistemdə 2025/2026-cı illərdən
əvvələ aiddir». Siyahı artıq cari ilə bağlıdır; burada təkrar istifadə / köçürmə MƏNBƏLƏRİ yoxlanılır:
keçmiş tədris ilinin dosyesi müəllimə nə «Keçən ildən köçür» siyahısında, nə qonşu siyahısında görünür, POST ilə
göndərilsə də rədd olunur; semestrsiz baza dosye (köhnə sistemdən cari jurnallar üçün gətirilib) görünür qalır.
"""

from __future__ import annotations

import pytest

from apps.organizations.models import AcademicPeriod
from apps.syllabus import services
from apps.syllabus.models import Syllabus
from apps.syllabus.services import reuse_rules as rules
from apps.syllabus.services.queries import current_year_source_q
from apps.syllabus.state_machine import TransitionDenied
from apps.syllabus.tests.reuse_fixtures import actor, approved_syllabus, build_world, target
from core.constants import AcademicPeriodType

pytestmark = pytest.mark.django_db


@pytest.fixture()
def world():
    data = build_world("syl-year")
    old_period = AcademicPeriod.objects.create(
        organization=data["org"],
        name="Payız",
        period_type=AcademicPeriodType.SEMESTER,
        academic_year="2024/2025",
        start_date="2024-09-01",
        end_date="2025-01-31",
    )
    old, _version = approved_syllabus(data, "o1")
    Syllabus.objects.filter(pk=old.pk).update(period=old_period, offering=None)
    data["old"] = Syllabus.objects.get(pk=old.pk)
    base, _version = approved_syllabus(data, "o3")
    Syllabus.objects.filter(pk=base.pk).update(period=None, offering=None)  # köçürmənin semestrsiz baza dosyesi
    data["base"] = Syllabus.objects.get(pk=base.pk)
    return data


def _previous(world, key="teacher"):
    return list(
        rules.previous_queryset(
            organization=world["org"],
            actor=actor(world, key),
            subject_id=world["subject"].pk,
            period_id=world["period"].pk,
        )
    )


def test_teacher_sources_skip_old_years_but_keep_the_base(world):
    ids = {row.pk for row in _previous(world)}
    assert ids == {world["base"].pk}
    pairs = rules.previous_source_pairs(
        organization=world["org"], actor=actor(world), subject_ids={world["subject"].pk}
    )
    assert (world["subject"].pk, world["old"].period_id) not in pairs
    assert (world["subject"].pk, None) in pairs


def test_posting_an_old_year_source_is_refused(world):
    with pytest.raises(TransitionDenied) as denied:
        services.reuse.copy_adjust(source=world["old"], target=target(world, "o2"), actor=actor(world), previous=True)
    assert denied.value.code == rules.CODE_OLD_YEAR
    _syllabus, version = services.reuse.copy_adjust(
        source=world["base"], target=target(world, "o2"), actor=actor(world), previous=True
    )
    assert version.source_version_id == world["base"].approved_version_id


def test_leaders_are_not_year_gated(world):
    assert current_year_source_q(world["org"], actor(world, "head")) is None
    assert current_year_source_q(world["org"], actor(world)) is not None
