"""Siyasət dəyərləri, qiymətləndirmə kilidi, saat balansı və avto-MAJOR qaydası.

Dizayn təhvili (`docs/design/handoff_full/README.md`) §8/4, §8/11 və §10.3–§10.4
qaydalarının kod qarşılığı burada kilidlənir.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model

import pytest

from apps.syllabus import policy, services
from apps.syllabus.constants import SectionKey, SyllabusStatus
from apps.syllabus.models import ChangeKind
from apps.syllabus.state_machine import TransitionDenied
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


# ─────────────────────────────────────────────────────────────────────────────
# Siyasət (DB-siz)
# ─────────────────────────────────────────────────────────────────────────────


class _Org:
    """Yalnız ``settings`` daşıyan ördək obyekt — siyasət oxucusu modelə bağlı deyil."""

    def __init__(self, settings=None):
        self.settings = settings


@pytest.mark.django_db(transaction=False)
def test_policy_defaults_match_the_owner_decisions():
    assert policy.sla_days(None) == 5
    assert policy.escalation_days(None) == 10
    assert policy.second_approval_enabled(None) is False
    assert policy.assessment_weights(None) == {"attendance": 10, "selfwork": 10, "final": 50, "flex": 30}


def test_policy_reads_the_organization_override():
    org = _Org({"syllabus": {"sla_days": 3, "escalation_days": 7, "second_approval_enabled": True}})
    assert policy.sla_days(org) == 3
    assert policy.escalation_days(org) == 7
    assert policy.second_approval_enabled(org) is True


def test_escalation_can_never_be_shorter_than_the_sla():
    org = _Org({"syllabus": {"sla_days": 9, "escalation_days": 2}})
    assert policy.escalation_days(org) == 9


def test_broken_policy_values_fall_back_instead_of_raising():
    org = _Org({"syllabus": {"sla_days": "üç", "assessment": {"final": "x"}}})
    assert policy.sla_days(org) == 5
    assert policy.assessment_weights(org)["final"] == 50


def test_flex_is_derived_so_a_policy_change_cannot_break_the_hundred():
    org = _Org({"syllabus": {"assessment": {"final": 40}}})
    weights = policy.assessment_weights(org)
    assert weights["flex"] == 40
    assert sum(weights[key] for key in ("attendance", "selfwork", "final", "flex")) == 100


# ─────────────────────────────────────────────────────────────────────────────
# Dünya
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture()
def world():
    org = make_org("syl-pol")
    teacher = User.objects.create_user("pol_teacher", "pol_teacher@x.test", "pw")
    chair = User.objects.create_user("pol_chair", "pol_chair@x.test", "pw")
    stack = make_academic_stack(org, code="POL101")
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


def _draft(world, *, plan_hours=None):
    actor = _actor(world["teacher"], world["org"])
    syllabus, version = services.create_draft(
        organization=world["org"],
        subject=world["stack"]["subject"],
        period=world["stack"]["period"],
        actor=actor,
        offering=world["offering"],
        program=world["stack"]["program"],
        chair_unit=world["stack"]["chair"],
        plan_hours=plan_hours if plan_hours is not None else PLAN_HOURS,
    )
    return syllabus, version, actor


def _fill(version, actor, data=None):
    for section_id, payload in (data or complete_section_data()).items():
        if section_id in {SectionKey.PREV.value, SectionKey.SEND.value}:
            continue
        services.save_section(version=version, section_id=section_id, data=payload, actor=actor)
    version.refresh_from_db()
    return version


# ─────────────────────────────────────────────────────────────────────────────
# §8/4 — qiymətləndirmə çəkiləri
# ─────────────────────────────────────────────────────────────────────────────


def test_a_new_draft_starts_with_a_valid_assessment_split(world):
    _syllabus, version, _actor_obj = _draft(world)
    data = services.section_data_map(version)[SectionKey.ASSESS.value]
    assert data["midterm"] + data["project"] == 30


def test_the_server_rejects_an_assessment_split_that_does_not_add_up(world):
    _syllabus, version, actor = _draft(world)
    with pytest.raises(TransitionDenied) as excinfo:
        services.save_section(
            version=version,
            section_id=SectionKey.ASSESS.value,
            data={"midterm": 90, "project": 90},
            actor=actor,
        )
    assert excinfo.value.code == "assess.split_mismatch"


def test_a_partial_assessment_payload_is_validated_against_the_stored_half(world):
    """Kliyent yalnız `midterm` göndərəndə `project` sətirdən gəlir."""
    _syllabus, version, actor = _draft(world)
    with pytest.raises(TransitionDenied):
        services.save_section(version=version, section_id=SectionKey.ASSESS.value, data={"midterm": 25}, actor=actor)
    services.save_section(
        version=version, section_id=SectionKey.ASSESS.value, data={"midterm": 25, "project": 5}, actor=actor
    )
    assert services.section_data_map(version)[SectionKey.ASSESS.value]["project"] == 5


def test_an_unallocated_split_blocks_submission(world):
    _syllabus, version, actor = _draft(world)
    data = complete_section_data()
    _fill(version, actor, data)
    assert version.completion_percent == 100
    # Bölgünü DOMEN qatından pozuruq (HTTP səthi buna icazə vermir) — məqsəd
    # tamamlanma qaydasının qapını bağladığını göstərməkdir.
    row = version.sections.get(section_id=SectionKey.ASSESS.value)
    row.data = {"midterm": 0, "project": 0}
    row.save(update_fields=["data"])
    services.recompute_completion(version)
    version.refresh_from_db()
    assert version.completion_percent < 100
    with pytest.raises(TransitionDenied) as excinfo:
        services.submit(version=version, actor=actor)
    assert excinfo.value.code == "transition.incomplete"


# ─────────────────────────────────────────────────────────────────────────────
# §8/11 — auditoriya saatları tədris planı ilə üst-üstə düşməlidir
# ─────────────────────────────────────────────────────────────────────────────


def test_contact_hours_that_disagree_with_the_plan_block_submission(world):
    _syllabus, version, actor = _draft(world, plan_hours={"lecture": 30, "seminar": 16, "lab": 14})
    # Məzmun BAŞQA plana görə doldurulub → saat balansı pozulur.
    _fill(version, actor, complete_section_data({"lecture": 28, "seminar": 16, "lab": 14}))
    codes = {issue["code"] for issue in services.recompute_completion(version).as_dict()["issues"]}
    assert "week.hours_mismatch" in codes
    with pytest.raises(TransitionDenied) as excinfo:
        services.submit(version=version, actor=actor)
    assert excinfo.value.code == "transition.incomplete"


def test_set_plan_hours_reruns_the_balance_check_and_unblocks_submission(world):
    _syllabus, version, actor = _draft(world, plan_hours={})
    _fill(version, actor, complete_section_data(PLAN_HOURS))
    assert version.completion_percent == 100

    services.set_plan_hours(version, {"lecture": 99, "seminar": 16, "lab": 14})
    version.refresh_from_db()
    assert version.completion_percent < 100

    services.set_plan_hours(version, PLAN_HOURS)
    version.refresh_from_db()
    assert version.completion_percent == 100


def test_set_plan_hours_never_touches_a_locked_version(world):
    _syllabus, version, actor = _draft(world)
    _fill(version, actor)
    version = services.submit(version=version, actor=actor)
    services.set_plan_hours(version, {"lecture": 1})
    version.refresh_from_db()
    assert version.plan_hours == PLAN_HOURS


# ─────────────────────────────────────────────────────────────────────────────
# §10.3 — struktur dəyişikliyi avtomatik MAJOR
# ─────────────────────────────────────────────────────────────────────────────


def _approved(world):
    _syllabus, version, actor = _draft(world)
    _fill(version, actor)
    version = services.submit(version=version, actor=actor)
    chair_actor = _actor(world["chair"], world["org"])
    version = services.approve(version=version, actor=chair_actor)
    return version, actor, chair_actor


def test_a_minor_version_with_untouched_structure_stays_minor(world):
    approved, actor, _chair = _approved(world)
    syllabus = approved.syllabus
    syllabus.refresh_from_db()
    minor = services.create_next_version(syllabus=syllabus, actor=actor, kind=ChangeKind.MINOR.value)
    assert minor.label == "v1.1"
    # Yalnız ədəbiyyat dəyişir — struktur bölmələri toxunulmur.
    services.save_section(
        version=minor,
        section_id=SectionKey.LIT.value,
        data={
            "primary": ["Cormen, Introduction to Algorithms, 2022", "Sedgewick, Algorithms, 2011"],
            "additional": ["Knuth, TAOCP, 1997", "Skiena, Algorithm Design Manual, 2020"],
        },
        actor=actor,
    )
    minor.refresh_from_db()
    submitted = services.submit(version=minor, actor=actor)
    assert submitted.label == "v1.1"
    assert submitted.change_kind == ChangeKind.MINOR
    assert submitted.escalated_sections == ()


@pytest.mark.parametrize(
    ("section_id", "payload"),
    [
        (SectionKey.ASSESS.value, {"midterm": 5, "project": 25}),
        (SectionKey.SELF.value, {"option": "1x10", "topics": [{"title": "Tək böyük sərbəst iş"}], "archived": []}),
    ],
)
def test_a_structural_change_escalates_a_minor_version_to_major(world, section_id, payload):
    approved, actor, _chair = _approved(world)
    syllabus = approved.syllabus
    syllabus.refresh_from_db()
    minor = services.create_next_version(syllabus=syllabus, actor=actor, kind=ChangeKind.MINOR.value)
    services.save_section(version=minor, section_id=section_id, data=payload, actor=actor)
    minor.refresh_from_db()

    submitted = services.submit(version=minor, actor=actor)

    assert submitted.change_kind == ChangeKind.MAJOR
    assert submitted.label == "v2.0"
    assert section_id in submitted.escalated_sections
    assert submitted.status == SyllabusStatus.SUBMITTED


def test_a_changed_weekly_plan_escalates_too(world):
    approved, actor, _chair = _approved(world)
    syllabus = approved.syllabus
    syllabus.refresh_from_db()
    minor = services.create_next_version(syllabus=syllabus, actor=actor, kind=ChangeKind.MINOR.value)
    rows = complete_section_data()[SectionKey.WEEK.value]["rows"]
    rows[0] = {**rows[0], "topic": "Tamamilə yeni mövzu"}
    services.save_section(version=minor, section_id=SectionKey.WEEK.value, data={"rows": rows}, actor=actor)
    minor.refresh_from_db()

    submitted = services.submit(version=minor, actor=actor)

    assert submitted.label == "v2.0"
    assert SectionKey.WEEK.value in submitted.escalated_sections


def test_a_teacher_chosen_major_is_never_renumbered(world):
    approved, actor, _chair = _approved(world)
    syllabus = approved.syllabus
    syllabus.refresh_from_db()
    major = services.create_next_version(syllabus=syllabus, actor=actor, kind=ChangeKind.MAJOR.value)
    assert major.label == "v2.0"
    services.save_section(
        version=major, section_id=SectionKey.ASSESS.value, data={"midterm": 5, "project": 25}, actor=actor
    )
    major.refresh_from_db()
    submitted = services.submit(version=major, actor=actor)
    assert submitted.label == "v2.0"
    assert submitted.escalated_sections == ()


def test_the_first_version_has_no_baseline_and_is_never_escalated(world):
    _syllabus, version, actor = _draft(world)
    _fill(version, actor)
    assert services.structural_changes(version) == ()
    submitted = services.submit(version=version, actor=actor)
    assert submitted.label == "v1.0"
