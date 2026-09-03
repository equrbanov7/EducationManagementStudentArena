"""P1-2 reqressiya: «köçür» əməli də ƏHATƏ qapısından keçir.

2026-09-02 auditi (`docs/audits/2026-09-02/PHASE23_SECURITY.md`) `teacher_b`
kimi `POST /accounts/profile/syllabus/action/` + `{"action": "copy",
"syllabus": <teacher_a-nın sillabusu>}` göndərdi və **200** aldı: qurbanın
məzmunu ilə dolu YENİ sillabus hücumçunun adına yaradıldı.

Səbəb: `services.copy_from_previous` mənbə sillabusu heç yoxlamırdı, halbuki
qonşu `create_next_version` eyni məqsəd üçün `is_author(...) or covers_unit(...)`
qapısını tətbiq edir.  Bu testlər həmin asimmetriyanı bağlayır.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model

import pytest

from apps.syllabus import services
from apps.syllabus.models import Syllabus
from apps.syllabus.state_machine import TransitionDenied
from apps.syllabus.tests.factories import (
    PLAN_HOURS,
    activate_member,
    make_academic_stack,
    make_offering,
    make_org,
)
from core.constants import RoleScopeType

User = get_user_model()

TEACHER_PERMS = ["syllabus.view", "syllabus.edit", "syllabus.submit", "grade.input"]
CHAIR_PERMS = ["syllabus.view", "syllabus.edit", "syllabus.review", "syllabus.approve"]

pytestmark = pytest.mark.django_db


@pytest.fixture()
def world():
    org = make_org("syl-copy")
    teacher_a = User.objects.create_user("copy_ta", "copy_ta@x.test", "pw")
    teacher_b = User.objects.create_user("copy_tb", "copy_tb@x.test", "pw")
    chair_a = User.objects.create_user("copy_ca", "copy_ca@x.test", "pw")

    stack_a = make_academic_stack(org, code="CPA101")
    # ⚠️ Müəllim rolu canlıda ``RoleScopeType.COURSE``-dur
    # (``apps/organizations/default_roles_university.py``) — yəni struktur
    # əhatəsi YOXDUR.  ORGANIZATION qoysaq ``get_permission_scope`` org-wide
    # verər və test qapını yalançı-yaşıl göstərərdi.
    activate_member(org, teacher_a, "teacher_a", permissions=TEACHER_PERMS, scope_type=RoleScopeType.COURSE)
    activate_member(org, teacher_b, "teacher_b", permissions=TEACHER_PERMS, scope_type=RoleScopeType.COURSE)
    activate_member(
        org,
        chair_a,
        "chair_head",
        permissions=CHAIR_PERMS,
        scope_unit=stack_a["chair"],
        level=70,
        scope_type=RoleScopeType.UNIT,
    )

    actor_a = services.resolve_actor(teacher_a, org)
    syllabus, _version = services.create_draft(
        organization=org,
        subject=stack_a["subject"],
        period=stack_a["period"],
        actor=actor_a,
        offering=make_offering(org, stack_a, teacher_a),
        program=stack_a["program"],
        chair_unit=stack_a["chair"],
        author=teacher_a,
        plan_hours=dict(PLAN_HOURS),
    )
    return {
        "org": org,
        "teacher_a": teacher_a,
        "teacher_b": teacher_b,
        "chair_a": chair_a,
        "syllabus": syllabus,
    }


def _copy_as(world, user):
    return services.copy_from_previous(
        source_syllabus=world["syllabus"],
        target_period=world["syllabus"].period,
        actor=services.resolve_actor(user, world["org"]),
    )


def test_foreign_teacher_cannot_copy_another_syllabus(world):
    before = Syllabus.objects.count()

    with pytest.raises(TransitionDenied) as excinfo:
        _copy_as(world, world["teacher_b"])

    assert excinfo.value.code == "transition.out_of_scope"
    assert Syllabus.objects.count() == before  # klon YARANMADI


def test_author_can_copy_their_own_syllabus(world):
    _new, version = _copy_as(world, world["teacher_a"])

    assert version is not None
    assert version.syllabus.author_id == world["teacher_a"].pk


def test_owning_chair_can_copy_within_scope(world):
    _new, version = _copy_as(world, world["chair_a"])

    assert version is not None
