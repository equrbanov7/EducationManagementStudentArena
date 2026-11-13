"""Gizlədilmiş jurnalın sillabusu siyahıda «Təsdiqlənib» kimi qalmır (sahib 2026-11-13, Aytən Heydərli).

Kollec jurnalları ``hide_college_journals_20261110`` ilə deaktiv edildi, amma müəllimin «Sillabuslar»
siyahısında onların təsdiqlənmiş dosyeləri qalırdı — müəllim «təsdiqlənmiş sillabusum jurnala gəlmir» deyirdi.
Birləşdirilmiş ikiz jurnalın (deaktiv) sillabusu AKTİV jurnala paylaşılıbsa siyahıda qalır.
"""

from __future__ import annotations

import pytest

from apps.registrar.models import CourseOffering
from apps.syllabus import services
from apps.syllabus.models import SyllabusShare
from apps.syllabus.tests.test_workflow import _actor, draft, world  # noqa: F401 — pytest fikstürləri

pytestmark = pytest.mark.django_db


def _listed(world):  # noqa: F811
    actor = _actor(world["teacher"], world["org"])
    return set(services.list_syllabi(organization=world["org"], actor=actor).values_list("pk", flat=True))


def test_syllabus_of_a_hidden_journal_is_not_listed(draft, world):  # noqa: F811
    syllabus, _version, _actor_ = draft
    assert syllabus.pk in _listed(world)
    CourseOffering.objects.filter(pk=world["offering"].pk).update(is_active=False)
    assert syllabus.pk not in _listed(world)


def test_hidden_journal_syllabus_shared_to_an_active_journal_stays(draft, world):  # noqa: F811
    syllabus, _version, _actor_ = draft
    survivor = CourseOffering.objects.create(
        organization=world["org"],
        subject=world["stack"]["subject"],
        period=world["stack"]["period"],
        group=None,
        instructor=world["teacher"],
        lesson_hours=world["offering"].lesson_hours,
    )
    SyllabusShare.objects.create(organization=world["org"], syllabus=syllabus, offering=survivor)
    CourseOffering.objects.filter(pk=world["offering"].pk).update(is_active=False)
    assert syllabus.pk in _listed(world)
    CourseOffering.objects.filter(pk=survivor.pk).update(is_active=False)
    assert syllabus.pk not in _listed(world)
