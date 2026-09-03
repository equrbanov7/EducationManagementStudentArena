"""Açılış → sillabus həlli və jurnal vəziyyət kodları (mətnsiz domen qatı)."""

from __future__ import annotations

from django.contrib.auth import get_user_model

import pytest

from apps.syllabus import services
from apps.syllabus.constants import SyllabusStatus
from apps.syllabus.services.offerings import (
    STATE_APPROVED,
    STATE_DRAFT,
    STATE_MISSING,
    STATE_PENDING,
    STATE_REJECTED,
    STATE_REVISION,
)
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
CHAIR_PERMS = ["syllabus.view", "syllabus.review", "syllabus.approve", "syllabus.revise", "syllabus.reject"]

pytestmark = pytest.mark.django_db


@pytest.fixture()
def world():
    org = make_org("syl-off")
    teacher = User.objects.create_user("off_teacher", "off_teacher@x.test", "pw")
    chair = User.objects.create_user("off_chair", "off_chair@x.test", "pw")
    stack = make_academic_stack(org, code="OFF101")
    activate_member(org, teacher, "teacher", permissions=TEACHER_PERMS)
    activate_member(
        org,
        chair,
        "chair_head",
        permissions=CHAIR_PERMS,
        scope_unit=stack["chair"],
        level=70,
        scope_type=RoleScopeType.UNIT,
    )
    offering = make_offering(org, stack, teacher)
    return {"org": org, "teacher": teacher, "chair": chair, "stack": stack, "offering": offering}


def _actor(user, org):
    return services.resolve_actor(user, org)


def _draft(world, **overrides):
    actor = _actor(world["teacher"], world["org"])
    payload = {
        "organization": world["org"],
        "subject": world["stack"]["subject"],
        "period": world["stack"]["period"],
        "actor": actor,
        "offering": world["offering"],
        "program": world["stack"]["program"],
        "chair_unit": world["stack"]["chair"],
        "plan_hours": PLAN_HOURS,
    }
    payload.update(overrides)
    syllabus, version = services.create_draft(**payload)
    return syllabus, version, actor


def _fill_and_submit(world, version, actor):
    for section_id, data in complete_section_data().items():
        if section_id in {"prev", "send"}:
            continue
        services.save_section(version=version, section_id=section_id, data=data, actor=actor)
    version.refresh_from_db()
    return services.submit(version=version, actor=actor)


def _lookup(world):
    offering = world["offering"]
    return services.syllabus_for_offering(
        organization=world["org"],
        offering_id=offering.id,
        subject_id=offering.subject_id,
        period_id=offering.period_id,
        instructor_id=offering.instructor_id,
    )


# ── 1. Üç pilləli həll ──────────────────────────────────────────────────────


def test_missing_syllabus_resolves_to_none_and_missing_state(world):
    assert _lookup(world) is None
    state = services.offering_syllabus_state(None)
    assert state["state"] == STATE_MISSING
    assert state["needs_action"] is True
    assert state["has_approved"] is False


def test_offering_bound_syllabus_is_found_first(world):
    syllabus, _version, _actor_obj = _draft(world)
    assert _lookup(world) == syllabus


def test_period_level_syllabus_is_found_when_offering_not_bound(world):
    """2-ci pillə: açılışa bağlanmamış, amma (fənn, semestr) üzrə dosye."""
    syllabus, _version, _actor_obj = _draft(world, offering=None)
    assert _lookup(world) == syllabus


def test_base_syllabus_without_period_is_found_last(world):
    """3-cü pillə: köçürülmüş SEMESTRSİZ «baza sillabus» (fənn + müəllim)."""
    syllabus, _version, _actor_obj = _draft(world, offering=None, period=None)
    assert _lookup(world) == syllabus


def test_other_organizations_syllabus_is_never_resolved(world):
    """Tenant filtri: başqa təşkilatın dosyesi bu açılışa bağlanmır."""
    _draft(world)
    other = make_org("syl-off-other")
    found = services.syllabus_for_offering(
        organization=other,
        offering_id=world["offering"].id,
        subject_id=world["offering"].subject_id,
        period_id=world["offering"].period_id,
        instructor_id=world["offering"].instructor_id,
    )
    assert found is None


# ── 2. Banner vəziyyət kodları ──────────────────────────────────────────────


def test_draft_then_pending_then_revision_then_approved_states(world):
    syllabus, version, actor = _draft(world)
    assert services.offering_syllabus_state(syllabus)["state"] == STATE_DRAFT

    version = _fill_and_submit(world, version, actor)
    syllabus.refresh_from_db()
    assert services.offering_syllabus_state(syllabus)["state"] == STATE_PENDING

    chair_actor = _actor(world["chair"], world["org"])
    version = services.start_review(version=version, actor=chair_actor)
    assert services.offering_syllabus_state(syllabus)["state"] == STATE_PENDING

    version = services.request_revision(version=version, actor=chair_actor, reason="Ədəbiyyat siyahısı yenilənməlidir")
    state = services.offering_syllabus_state(syllabus)
    assert state["state"] == STATE_REVISION
    assert state["reason"] == "Ədəbiyyat siyahısı yenilənməlidir"
    assert state["needs_action"] is True


def test_approved_state_needs_no_action_and_exposes_approved_version(world):
    syllabus, version, actor = _draft(world)
    version = _fill_and_submit(world, version, actor)
    chair_actor = _actor(world["chair"], world["org"])
    version = services.start_review(version=version, actor=chair_actor)
    version = services.approve(version=version, actor=chair_actor, comment="Uyğundur")
    syllabus.refresh_from_db()

    state = services.offering_syllabus_state(syllabus)
    assert state["state"] == STATE_APPROVED
    assert state["needs_action"] is False
    assert state["has_approved"] is True
    assert services.approved_version_for(syllabus) == version


def test_rejected_state_carries_the_reason(world):
    syllabus, version, actor = _draft(world)
    version = _fill_and_submit(world, version, actor)
    chair_actor = _actor(world["chair"], world["org"])
    version = services.start_review(version=version, actor=chair_actor)
    services.reject(version=version, actor=chair_actor, reason="Universitet siyasətinə uyğun deyil")
    syllabus.refresh_from_db()

    state = services.offering_syllabus_state(syllabus)
    assert state["state"] == STATE_REJECTED
    assert state["reason"] == "Universitet siyasətinə uyğun deyil"


# ── 3. ⚠️ Tələbənin gördüyü versiya — ƏSAS QAYDA ───────────────────────────


def test_student_keeps_seeing_previous_approved_version_while_v2_is_pending(world):
    """Yeni versiya təsdiqlənməyibsə ƏVVƏLKİ təsdiqlənmiş versiya qüvvədə qalır."""
    syllabus, version, actor = _draft(world)
    version = _fill_and_submit(world, version, actor)
    chair_actor = _actor(world["chair"], world["org"])
    version = services.start_review(version=version, actor=chair_actor)
    v1 = services.approve(version=version, actor=chair_actor, comment="ok")
    syllabus.refresh_from_db()

    v2 = services.create_next_version(syllabus=syllabus, actor=actor, kind="minor")
    for section_id, data in complete_section_data().items():
        if section_id in {"prev", "send"}:
            continue
        services.save_section(version=v2, section_id=section_id, data=data, actor=actor)
    v2.refresh_from_db()
    v2 = services.submit(version=v2, actor=actor)
    syllabus.refresh_from_db()

    # Müəllimin banneri AÇIQ versiyanı izləyir…
    state = services.offering_syllabus_state(syllabus)
    assert state["state"] == STATE_PENDING
    assert state["version"] == v2
    # …tələbə isə hələ də v1-i görür.
    assert services.approved_version_for(syllabus) == v1
    assert state["has_approved"] is True


def test_approved_version_falls_back_to_status_when_pointer_is_stale(world):
    """Dosyedəki göstərici köhnəlsə də təsdiqlənmiş versiya statusa görə tapılır."""
    syllabus, version, actor = _draft(world)
    version = _fill_and_submit(world, version, actor)
    chair_actor = _actor(world["chair"], world["org"])
    version = services.start_review(version=version, actor=chair_actor)
    approved = services.approve(version=version, actor=chair_actor, comment="ok")

    syllabus.refresh_from_db()
    type(syllabus).objects.filter(pk=syllabus.pk).update(approved_version=None)
    syllabus.refresh_from_db()

    assert syllabus.approved_version_id is None
    assert services.approved_version_for(syllabus) == approved
    assert approved.status == SyllabusStatus.APPROVED
