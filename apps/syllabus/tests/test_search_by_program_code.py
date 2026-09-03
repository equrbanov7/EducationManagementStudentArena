"""İxtisas şifri ilə axtarış — «göstərilən şifr tapılmalıdır» invariantı.

Qayda (sahibin tələbi): **ekranda ixtisas şifri GÖSTƏRƏN hər səth, həmin şifrlə
axtarışı da dəstəkləməlidir.**  Əks halda istifadəçi ekranda «Dünya iqtisadiyyatı
· 050401» görür, `050401` yazır və SIFIR nəticə alır.

Niyə bu fayl var
----------------
Sillabus siyahısı və təsdiq növbəsi şifri göstərir, amma süzgəcləri uzun müddət
yalnız fənn/müəllim üzrə idi.  Düzəliş edildi, LAKİN düşmən baxışı sübut etdi ki,
onu **tamamilə silsən heç bir test çökmür** (202 passed = baseline).  Bu dəst
həmin boşluğu bağlayır.

⚠️ İki şifr NƏSLİ var: cari (`official_code`, NK 503/2024 — 7 rəqəm) və əvvəlki
(`legacy_official_code` — `050XXX`/`060XXX`).  Ekranda hər ikisi görünə bilir,
ona görə hər ikisi axtarılmalıdır.  Oxuyan tələbələrin diplomunda KÖHNƏ şifr
yazılıb — onu axtarışdan çıxarmaq real istifadəçi ssenarisini sındırır.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model

import pytest

from apps.syllabus import services
from apps.syllabus.constants import SyllabusStatus
from apps.syllabus.tests.factories import (
    PLAN_HOURS,
    activate_member,
    complete_section_data,
    make_academic_stack,
    make_offering,
    make_org,
)
from core.constants import RoleScopeType

User = get_user_model()

TEACHER_PERMS = ["syllabus.view", "syllabus.edit", "syllabus.submit", "grade.input"]
CHAIR_PERMS = ["syllabus.view", "syllabus.review", "syllabus.approve"]

pytestmark = pytest.mark.django_db

CURRENT_CODE = "6002004"  # cari nəsil (NK 503/2024)
LEGACY_CODE = "050401"  # əvvəlki nəsil — yeni təsnifatda qarşılığı YOXDUR


@pytest.fixture
def world(db):
    org = make_org("srch-org")
    stack = make_academic_stack(org, code="SRCH")
    program = stack["program"]
    program.name = "Dünya iqtisadiyyatı"
    program.official_code = CURRENT_CODE
    program.legacy_official_code = LEGACY_CODE
    program.save(update_fields=["name", "official_code", "legacy_official_code"])

    teacher = User.objects.create_user("srch_teacher", "srch_teacher@x.test", "pw")
    activate_member(org, teacher, "teacher", permissions=TEACHER_PERMS)
    chair = User.objects.create_user("srch_chair", "srch_chair@x.test", "pw")
    activate_member(
        org,
        chair,
        "chair_head",
        permissions=CHAIR_PERMS,
        scope_unit=stack["chair"],
        level=70,
        scope_type=RoleScopeType.UNIT,
    )
    return {"org": org, "stack": stack, "teacher": teacher, "chair": chair, "program": program}


def _draft(world):
    actor = services.resolve_actor(world["teacher"], world["org"])
    offering = make_offering(world["org"], world["stack"], world["teacher"])
    syllabus, version = services.create_draft(
        organization=world["org"],
        subject=world["stack"]["subject"],
        period=world["stack"]["period"],
        actor=actor,
        offering=offering,
        program=world["program"],
        chair_unit=world["stack"]["chair"],
        author=world["teacher"],
        plan_hours=dict(PLAN_HOURS),
    )
    return syllabus, version, actor


def _submitted(world):
    _syllabus, version, actor = _draft(world)
    for section_id, data in complete_section_data().items():
        if section_id in {"prev", "send"}:
            continue
        services.save_section(version=version, section_id=section_id, data=data, actor=actor)
    return services.submit(version=version, actor=actor)


def _list_codes(world, search):
    actor = services.resolve_actor(world["teacher"], world["org"])
    return services.list_syllabi(organization=world["org"], actor=actor, search=search)


def test_the_list_finds_a_syllabus_by_its_current_programme_code(world):
    _draft(world)
    assert _list_codes(world, CURRENT_CODE).count() == 1


def test_the_list_finds_a_syllabus_by_its_previous_generation_code(world):
    """Diplomda köhnə şifr yazılıb — onunla da tapılmalıdır."""
    _draft(world)
    assert _list_codes(world, LEGACY_CODE).count() == 1


def test_the_list_finds_a_syllabus_by_programme_name(world):
    _draft(world)
    assert _list_codes(world, "Dünya iqtis").count() == 1


def test_an_unrelated_code_matches_nothing(world):
    """Süzgəc həqiqətən süzür — hər şeyi qaytarmır."""
    _draft(world)
    assert _list_codes(world, "9999999").count() == 0


def test_a_syllabus_without_a_programme_is_not_lost_from_an_empty_search(world):
    """İxtisası NULL olan sillabus boş axtarışda GÖRÜNMƏLİDİR."""
    actor = services.resolve_actor(world["teacher"], world["org"])
    offering = make_offering(world["org"], world["stack"], world["teacher"])
    services.create_draft(
        organization=world["org"],
        subject=world["stack"]["subject"],
        period=world["stack"]["period"],
        actor=actor,
        offering=offering,
        program=None,
        chair_unit=world["stack"]["chair"],
        plan_hours=dict(PLAN_HOURS),
    )
    assert services.list_syllabi(organization=world["org"], actor=actor, search="").count() == 1


def test_the_review_queue_is_reachable_at_all(world):
    """DİAQNOSTİKA: növbə süzgəcsiz nə qaytarır?"""
    _submitted(world)
    actor = services.resolve_actor(world["chair"], world["org"])
    assert services.review_queue(organization=world["org"], actor=actor).count() == 1


def test_the_review_queue_finds_a_syllabus_by_its_current_code(world):
    _submitted(world)
    actor = services.resolve_actor(world["chair"], world["org"])
    rows = services.review_queue(organization=world["org"], actor=actor, search=CURRENT_CODE)
    assert [r.status for r in rows] == [SyllabusStatus.SUBMITTED.value]


def test_the_review_queue_finds_a_syllabus_by_its_previous_generation_code(world):
    _submitted(world)
    actor = services.resolve_actor(world["chair"], world["org"])
    assert services.review_queue(organization=world["org"], actor=actor, search=LEGACY_CODE).count() == 1


def test_the_review_queue_filter_is_not_a_passthrough(world):
    _submitted(world)
    actor = services.resolve_actor(world["chair"], world["org"])
    assert services.review_queue(organization=world["org"], actor=actor, search="9999999").count() == 0
