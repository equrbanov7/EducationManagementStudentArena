"""Təkrar istifadə QAYDALARI: saat uyğunluğu, həftə uyğunlaşdırması, qonşu axtarışı və əhatə."""

from __future__ import annotations

import pytest

from apps.syllabus import services
from apps.syllabus.models import Syllabus
from apps.syllabus.services import reuse_rules as rules
from apps.syllabus.state_machine import Transition, TransitionDenied, check
from apps.syllabus.tests.factories import PLAN_HOURS, make_academic_stack, make_offering, make_org
from apps.syllabus.tests.reuse_fixtures import (
    OTHER_HOURS,
    TEACHER_PERMS,
    actor,
    approved_syllabus,
    build_world,
    draft_for,
)
from apps.syllabus.week_plan import fit_rows_to_hours

pytestmark = pytest.mark.django_db


# ── Saat uyğunluğu (sırf funksiyalar) ─────────────────────────────────────────


def test_hours_match_needs_known_and_equal_hours():
    assert rules.hours_match({"lecture": 30, "seminar": "16", "lab": 14}, {"lab": 14, "lecture": 30, "seminar": 16})
    # 0 / boş dəyər «yoxdur» deməkdir — normallaşdırmadan sonra eynidir.
    assert rules.hours_match({"lecture": 30, "lab": 0}, {"lecture": "30"})
    assert not rules.hours_match(PLAN_HOURS, OTHER_HOURS)
    # Hər iki tərəf boşdursa saat MƏLUM DEYİL — bağlama üçün «eyni» sayılmır.
    assert not rules.hours_match({}, {})
    assert not rules.hours_match({"lecture": "x"}, {})


def test_hours_rows_marks_each_kind():
    rows = rules.hours_rows(PLAN_HOURS, OTHER_HOURS)
    assert rows == [
        {"kind": "lecture", "source": 30, "target": 30, "same": True},
        {"kind": "seminar", "source": 16, "target": 30, "same": False},
        {"kind": "lab", "source": 14, "target": 0, "same": False},
    ]


def test_fit_rows_to_hours_redistributes_only_mismatching_kinds():
    rows = [
        {"topic": f"Mövzu {index + 1}", "lecture": 2, "seminar": 2 if index < 8 else 0, "lab": 2, "outcome": "TN1"}
        for index in range(15)
    ]
    fitted, changed = fit_rows_to_hours(rows, OTHER_HOURS)
    assert changed
    assert sum(row["lecture"] for row in fitted) == 30
    assert [row["lecture"] for row in fitted] == [row["lecture"] for row in rows]  # toxunulmadı
    assert sum(row["seminar"] for row in fitted) == 30
    assert all(row["seminar"] == 2 for row in fitted)  # 1 dərs = 2 saat, 15 sətir
    assert all(row["lab"] == 0 for row in fitted)  # hədəfdə laboratoriya yoxdur
    assert [row["topic"] for row in fitted] == [row["topic"] for row in rows]  # mövzular qalır


def test_fit_rows_to_hours_pads_rows_and_keeps_extra_topics():
    rows = [{"topic": "A", "lecture": 2, "seminar": 0, "lab": 0, "outcome": ""}]
    fitted, changed = fit_rows_to_hours(rows, {"lecture": 15})
    assert changed
    assert len(fitted) == 8  # ceil(15 / 2)
    assert [row["lecture"] for row in fitted] == [2, 2, 2, 2, 2, 2, 2, 1]
    assert fitted[0]["topic"] == "A" and fitted[1]["topic"] == ""
    same, unchanged = fit_rows_to_hours(fitted, {"lecture": 15})
    assert not unchanged and same == fitted
    untouched, no_plan = fit_rows_to_hours(rows, {})
    assert not no_plan and untouched == rows


def test_reuse_state_machine_rule():
    rule = check(name=Transition.REUSE, status="draft", permissions=["syllabus.edit"], is_author=True, in_scope=True)
    assert rule.target == "approved"
    with pytest.raises(TransitionDenied) as denied:
        check(name=Transition.REUSE, status="approved", permissions=["syllabus.edit"], is_author=True)
    assert denied.value.code == "version.approved_locked"
    with pytest.raises(TransitionDenied) as denied:
        check(name=Transition.REUSE, status="draft", permissions=["syllabus.view"], is_author=True)
    assert denied.value.code == "transition.permission_denied"
    with pytest.raises(TransitionDenied) as denied:
        check(name=Transition.REUSE, status="draft", permissions=["syllabus.edit"], is_author=False)
    assert denied.value.code == "transition.author_only"


# ── Qonşu axtarışı və əhatə ─────────────────────────────────────────────────


@pytest.fixture()
def world():
    return build_world("syl-reuse-rules")


def _siblings(world, user_key="teacher", **kwargs):
    return list(
        services.sibling_queryset(
            organization=world["org"],
            actor=actor(world, user_key),
            subject_id=world["subject"].pk,
            period_id=world["period"].pk,
            **kwargs,
        )
    )


def test_siblings_are_same_subject_and_period_other_offering(world):
    source, _version = approved_syllabus(world, "o1")
    draft, _draft_version = draft_for(world, "o3")
    rows = _siblings(world, exclude_offering_id=world["offerings"]["o2"].pk)
    assert [row.pk for row in rows] == [source.pk, draft.pk]  # təsdiqlənmiş əvvəl
    assert all(row._own == 1 and row._copyable == 1 for row in rows)
    # Hədəfin öz dosyesi və açılışı siyahıya düşmür.
    assert [
        row.pk for row in _siblings(world, exclude_syllabus_id=draft.pk, exclude_offering_id=draft.offering_id)
    ] == [source.pk]


def test_linked_targets_are_not_offered_as_sources(world):
    source, _version = approved_syllabus(world, "o1")
    linked, _draft_version = draft_for(world, "o2")
    Syllabus.objects.filter(pk=linked.pk).update(reused_from=source)
    rows = _siblings(world, exclude_offering_id=world["offerings"]["o3"].pk)
    assert [row.pk for row in rows] == [source.pk]
    assert rows[0]._linked == 1


def test_other_teachers_syllabi_are_hidden_from_a_course_scoped_teacher(world):
    foreign, _version = approved_syllabus(world, "o5", user_key="teacher2")
    assert _siblings(world) == []
    # Kafedra müdiri (syllabus.view + kafedra əhatəsi) oxuyur, amma kopyalaya bilmir (edit yoxdur).
    rows = _siblings(world, user_key="head")
    assert [row.pk for row in rows] == [foreign.pk]
    assert rows[0]._own == 0 and rows[0]._copyable == 0


def test_other_period_and_other_organization_are_never_siblings(world):
    approved_syllabus(world, "o1")
    other_org = make_org("syl-reuse-foreign")
    stack = make_academic_stack(other_org, code="RSE101")
    from apps.syllabus.tests.factories import activate_member

    activate_member(other_org, world["teacher"], "teacher", permissions=TEACHER_PERMS)
    foreign_actor = services.resolve_actor(world["teacher"], other_org)
    services.create_draft(
        organization=other_org,
        subject=stack["subject"],
        period=stack["period"],
        actor=foreign_actor,
        offering=make_offering(other_org, stack, world["teacher"]),
        author=world["teacher"],
    )
    # Başqa təşkilatın fənn/semestr id-ləri ilə sorğu — təşkilat filtri hər şeyi kəsir.
    leaked = services.sibling_queryset(
        organization=world["org"],
        actor=actor(world),
        subject_id=stack["subject"].pk,
        period_id=stack["period"].pk,
    )
    assert list(leaked) == []
    assert (
        services.sibling_queryset(
            organization=world["org"], actor=actor(world), subject_id=world["subject"].pk, period_id=None
        ).count()
        == 0
    )


def test_link_code_explains_every_refusal(world):
    source, _version = approved_syllabus(world, "o1")
    act = actor(world)
    chair_id = source.chair_unit_id
    assert rules.link_code(source, actor=act, target_hours=PLAN_HOURS, target_chair_unit_id=chair_id) == ""
    assert rules.link_code(source, actor=act, target_hours=OTHER_HOURS, target_chair_unit_id=chair_id) == (
        rules.CODE_HOURS_DIFFER
    )
    assert rules.link_code(source, actor=act, target_hours={}, target_chair_unit_id=chair_id) == (
        rules.CODE_HOURS_UNKNOWN
    )
    assert rules.link_code(
        source, actor=act, target_hours=PLAN_HOURS, target_chair_unit_id=world["other_chair"].pk
    ) == (rules.CODE_CHAIR_DIFFERS)
    assert rules.link_code(
        source, actor=actor(world, "teacher2"), target_hours=PLAN_HOURS, target_chair_unit_id=chair_id
    ) == (rules.CODE_NOT_OWN)
    draft, _draft_version = draft_for(world, "o2")
    assert rules.link_code(draft, actor=act, target_hours=PLAN_HOURS, target_chair_unit_id=chair_id) == (
        rules.CODE_SOURCE_NOT_APPROVED
    )
    # Köçürmə damğalı təsdiq zəncirlənmir.
    source.approved_version.approval_source = "migration"
    assert rules.link_code(source, actor=act, target_hours=PLAN_HOURS, target_chair_unit_id=chair_id) == (
        rules.CODE_SOURCE_NOT_HUMAN
    )
