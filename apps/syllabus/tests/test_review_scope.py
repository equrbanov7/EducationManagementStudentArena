"""Təsdiq səthinin ƏHATƏ və ANALİTİKA qapıları (dizayn təhvili §3.3).

Nəyi qoruyur
------------
1. **Fail-closed əhatə.** Kafedra müdiri YALNIZ öz kafedrasını görür; icazəsi
   olub struktur əhatəsi olmayan istifadəçiyə bütün təşkilat AÇILMIR. Bu, əvvəl
   real bloker olub — ona görə həm növbə, həm coverage, həm də ``has_scope``
   ayrıca yoxlanılır.
2. **«Gecikib» tərifi.** Semestri hələ başlamamış fənn gecikmiş sayılmır.
3. **Növbə filtrləri.** Axtarış/status/sıralama server tərəfdədir.
"""

from __future__ import annotations

import datetime

from django.contrib.auth import get_user_model

import pytest

from apps.syllabus import services
from apps.syllabus.constants import SyllabusStatus
from apps.syllabus.services.coverage import GROUP_CHAIR, GROUP_PROGRAM
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


def _actor(user, org):
    return services.resolve_actor(user, org)


def _submitted(org, stack, teacher):
    """Tam doldurulmuş və TƏSDİQƏ GÖNDƏRİLMİŞ versiya qaytarır."""
    actor = _actor(teacher, org)
    offering = make_offering(org, stack, teacher)
    syllabus, version = services.create_draft(
        organization=org,
        subject=stack["subject"],
        period=stack["period"],
        actor=actor,
        offering=offering,
        program=stack["program"],
        chair_unit=stack["chair"],
        author=teacher,
        plan_hours=dict(PLAN_HOURS),
    )
    for section_id, data in complete_section_data().items():
        if section_id in {"prev", "send"}:
            continue
        services.save_section(version=version, section_id=section_id, data=data, actor=actor)
    version = services.submit(version=version, actor=actor)
    return syllabus, version


@pytest.fixture()
def world():
    """İki kafedra, hər birində bir müəllim və bir təqdim edilmiş sillabus."""
    org = make_org("syl-scope")
    teacher_a = User.objects.create_user("scope_ta", "scope_ta@x.test", "pw")
    teacher_b = User.objects.create_user("scope_tb", "scope_tb@x.test", "pw")
    chair_a = User.objects.create_user("scope_ca", "scope_ca@x.test", "pw")
    dean = User.objects.create_user("scope_dean", "scope_dean@x.test", "pw")
    naked = User.objects.create_user("scope_naked", "scope_naked@x.test", "pw")

    stack_a = make_academic_stack(org, code="SCA101")
    stack_b = make_academic_stack(org, code="SCB202")
    activate_member(org, teacher_a, "teacher_a", permissions=TEACHER_PERMS)
    activate_member(org, teacher_b, "teacher_b", permissions=TEACHER_PERMS)
    activate_member(
        org,
        chair_a,
        "chair_head",
        permissions=CHAIR_PERMS,
        scope_unit=stack_a["chair"],
        level=70,
        scope_type=RoleScopeType.UNIT,
    )
    # Dekan/prorektor: ORG səviyyəli rol. ⚠️ `scoping.ORG_WIDE_MIN_LEVEL = 90` —
    # bundan aşağı səviyyə org-wide əhatə VERMİR, ona görə level 95-dir.
    activate_member(org, dean, "vice_rector", permissions=CHAIR_PERMS, level=95)
    # ⚠️ İcazə VAR, əhatə YOX — fail-closed halın özü.
    activate_member(org, naked, "chair_no_scope", permissions=CHAIR_PERMS, level=70, scope_type=RoleScopeType.UNIT)

    syl_a, ver_a = _submitted(org, stack_a, teacher_a)
    syl_b, ver_b = _submitted(org, stack_b, teacher_b)
    return {
        "org": org,
        "chair_a": chair_a,
        "dean": dean,
        "naked": naked,
        "stack_a": stack_a,
        "stack_b": stack_b,
        "syl_a": syl_a,
        "syl_b": syl_b,
        "ver_a": ver_a,
        "ver_b": ver_b,
    }


# ── Əhatə (fail-closed) ────────────────────────────────────────────────────


def test_chair_queue_contains_only_its_own_department(world):
    queue = services.review_queue(organization=world["org"], actor=_actor(world["chair_a"], world["org"]))

    assert [row.pk for row in queue] == [world["ver_a"].pk]


def test_org_wide_actor_sees_both_departments(world):
    queue = services.review_queue(organization=world["org"], actor=_actor(world["dean"], world["org"]))

    assert {row.pk for row in queue} == {world["ver_a"].pk, world["ver_b"].pk}


def test_permission_without_structure_scope_sees_nothing(world):
    """⚠️ Əhatəsizlik «bütün universitet» demək DEYİL — boş nəticə."""
    actor = _actor(world["naked"], world["org"])

    assert services.has_review_scope(actor=actor) is False
    assert list(services.review_queue(organization=world["org"], actor=actor)) == []
    assert list(services.review_scope_queryset(organization=world["org"], actor=actor)) == []


def test_actor_without_review_permission_sees_nothing(world):
    """`syllabus.view` təsdiq səthini AÇMIR — qərar açarı ayrıdır."""
    viewer = User.objects.create_user("scope_viewer", "scope_viewer@x.test", "pw")
    activate_member(world["org"], viewer, "viewer", permissions=["syllabus.view"])
    actor = _actor(viewer, world["org"])

    assert services.has_review_scope(actor=actor) is False
    assert list(services.review_queue(organization=world["org"], actor=actor)) == []


def test_coverage_is_scoped_to_the_chair_department(world):
    report = services.coverage_report(organization=world["org"], actor=_actor(world["chair_a"], world["org"]))

    assert report["by_chair"]["totals"]["total"] == 1
    assert {row["label"] for row in report["by_chair"]["rows"]} == {world["stack_a"]["chair"].name}


def test_coverage_for_org_wide_actor_covers_every_department(world):
    report = services.coverage_report(organization=world["org"], actor=_actor(world["dean"], world["org"]))

    assert report["by_chair"]["totals"]["total"] == 2
    assert len(report["by_chair"]["rows"]) == 2


# ── Sayğaclar ──────────────────────────────────────────────────────────────


def test_submitted_syllabus_counts_as_in_review_not_approved(world):
    report = services.coverage_report(organization=world["org"], actor=_actor(world["chair_a"], world["org"]))
    totals = report["by_program"]["totals"]

    assert totals["in_review"] == 1
    assert totals["approved"] == 0
    assert totals["percent"] == 0


def test_approval_moves_the_row_into_the_approved_bucket(world):
    services.approve(version=world["ver_a"], actor=_actor(world["chair_a"], world["org"]))

    report = services.coverage_report(organization=world["org"], actor=_actor(world["chair_a"], world["org"]))
    totals = report["by_program"]["totals"]

    assert totals["approved"] == 1
    assert totals["percent"] == 100
    assert totals["late"] == 0


def test_late_only_counts_periods_that_have_already_started(world):
    """Semestr başlamayıbsa «gecikib» sayılmır — normativ tərif budur."""
    actor = _actor(world["chair_a"], world["org"])
    started = services.coverage_breakdown(
        organization=world["org"], actor=actor, group_by=GROUP_PROGRAM, today=datetime.date(2026, 1, 1)
    )
    not_started = services.coverage_breakdown(
        organization=world["org"], actor=actor, group_by=GROUP_PROGRAM, today=datetime.date(2025, 1, 1)
    )

    assert started["totals"]["late"] == 1
    assert not_started["totals"]["late"] == 0


def test_breakdown_groups_by_the_requested_key(world):
    actor = _actor(world["dean"], world["org"])

    by_program = services.coverage_breakdown(organization=world["org"], actor=actor, group_by=GROUP_PROGRAM)
    by_chair = services.coverage_breakdown(organization=world["org"], actor=actor, group_by=GROUP_CHAIR)

    assert by_program["group_by"] == GROUP_PROGRAM
    assert by_chair["group_by"] == GROUP_CHAIR
    assert {row["label"] for row in by_chair["rows"]} == {
        world["stack_a"]["chair"].name,
        world["stack_b"]["chair"].name,
    }


# ── Növbənin filtr/sıralama səthi ──────────────────────────────────────────


def test_queue_search_matches_subject_code(world):
    actor = _actor(world["dean"], world["org"])

    hits = services.review_queue(organization=world["org"], actor=actor, search="SCB202")

    assert [row.pk for row in hits] == [world["ver_b"].pk]


def test_queue_status_filter_narrows_to_the_requested_status(world):
    actor = _actor(world["dean"], world["org"])
    services.start_review(version=world["ver_a"], actor=actor)

    in_review = services.review_queue(organization=world["org"], actor=actor, statuses=[SyllabusStatus.REVIEW.value])

    assert [row.pk for row in in_review] == [world["ver_a"].pk]


def test_queue_sorts_by_subject_name_when_asked(world):
    actor = _actor(world["dean"], world["org"])

    rows = list(services.review_queue(organization=world["org"], actor=actor, sort="subject"))

    assert len(rows) == 2
    names = [row.syllabus.subject.name for row in rows]
    assert names == sorted(names)


def test_queue_never_contains_approved_versions(world):
    actor = _actor(world["dean"], world["org"])
    services.approve(version=world["ver_a"], actor=actor)

    assert [row.pk for row in services.review_queue(organization=world["org"], actor=actor)] == [world["ver_b"].pk]
