"""Sahib 2026-10-10: sillabusun baxış paneli / sənəd səhifəsi / siyahı baxışı sərbəst işsiz qaydada.

Bölmə kartlarının gövdəsi sənəd bloklarından MÖVQEYƏ görə yox, AÇARA görə götürülür: «Sərbəst iş» bloku
düşəndə ədəbiyyat öz kartında qalmalıdır (əvvəl bir pillə sürüşüb «Sərbəst iş» kartına düşərdi).
Köhnə (2025/2026) semestrin sənədi dəyişmir.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model

import pytest

from apps.accounts.views.syllabus.detail_context import _section_rows
from apps.accounts.views.syllabus.preview import APPROVED_BANNER_NO_SELFWORK, BANNERS, banner_for, build_preview_payload
from apps.accounts.views.syllabus.review_panel import build_diffs, build_sections, compose_bodies
from apps.organizations.models import AcademicPeriod
from apps.syllabus import services
from apps.syllabus.constants import SectionKey, SyllabusStatus
from apps.syllabus.rules import LEGACY, SyllabusRule
from apps.syllabus.tests.factories import (
    PLAN_HOURS,
    activate_member,
    complete_section_data,
    make_academic_stack,
    make_offering,
    make_org,
)

User = get_user_model()

NO_SELF = SyllabusRule(selfwork=False, split=True)
SEVEN = ["info", "desc", "out", "week", "method", "assess", "lit"]


# ── 1. Gövdələr AÇARLA (DB-siz) ──────────────────────────────────────────────
def test_bodies_are_taken_by_key_when_the_selfwork_block_is_dropped():
    bodies = compose_bodies(complete_section_data(), rule=NO_SELF)

    assert SectionKey.SELF.value not in bodies
    assert bodies[SectionKey.LIT.value].startswith("Cormen")  # ədəbiyyat öz kartında
    assert "Midterm (aralıq imtahan) 30" in bodies[SectionKey.ASSESS.value]
    assert "Sərbəst iş" not in bodies[SectionKey.ASSESS.value]


def test_legacy_bodies_keep_the_selfwork_card():
    bodies = compose_bodies(complete_section_data(), rule=LEGACY)

    assert bodies[SectionKey.SELF.value].startswith("1. Birinci sərbəst iş mövzusu")
    assert bodies[SectionKey.LIT.value].startswith("Cormen")
    assert "Midterm (aralıq imtahan) 20" in bodies[SectionKey.ASSESS.value]


def test_review_cards_and_diff_follow_the_rule():
    data = complete_section_data()

    assert [row["id"] for row in build_sections(data, {}, {}, rule=NO_SELF)] == SEVEN
    assert len(build_sections(data, {}, {}, rule=LEGACY)) == 8
    diff = build_diffs(data, data, {SectionKey.SELF.value: {"changed": True}}, rule=NO_SELF)
    assert [row["id"] for row in diff["rows"]] == SEVEN  # gizli bölmənin dəyişikliyi kart vermir


def test_approved_banner_does_not_mention_selfwork_without_it():
    approved = SyllabusStatus.APPROVED.value
    assert banner_for(approved, NO_SELF) == str(APPROVED_BANNER_NO_SELFWORK)
    assert banner_for(approved, LEGACY) == str(BANNERS[approved])


# ── 2. Sənəd səhifəsi / siyahı baxışı — versiyanın semestrinə görə ───────────
@pytest.mark.django_db
@pytest.mark.parametrize(("year", "has_selfwork"), [("2026/2027", False), ("2025/2026", True)])
def test_detail_and_preview_follow_the_version_semester(year, has_selfwork):
    org = make_org(f"swr-acc-{year[:4]}")
    teacher = User.objects.create_user(f"swr_acc_{year[:4]}", f"swr_acc_{year[:4]}@x.test", "pw")
    activate_member(org, teacher, "teacher", permissions=["syllabus.view", "syllabus.edit", "grade.input"])
    stack = make_academic_stack(org, code=f"SWA{year[:4]}")
    AcademicPeriod.objects.filter(pk=stack["period"].pk).update(academic_year=year)
    stack["period"].refresh_from_db()
    actor = services.resolve_actor(teacher, org)
    syllabus, version = services.create_draft(
        organization=org,
        subject=stack["subject"],
        period=stack["period"],
        actor=actor,
        offering=make_offering(org, stack, teacher),
        plan_hours=PLAN_HOURS,
    )
    for section_id in (SectionKey.SELF.value, SectionKey.LIT.value):  # data birbaşa — `self` gizli ola bilər
        version.sections.filter(section_id=section_id).update(data=complete_section_data()[section_id])
    syllabus.refresh_from_db()

    rows = _section_rows(version)
    keys = [block["key"] for block in build_preview_payload(syllabus)["blocks"]]

    assert (SectionKey.SELF.value in [row["id"] for row in rows]) is has_selfwork
    assert ("selfwork" in keys) is has_selfwork
    lit = next(row for row in rows if row["id"] == SectionKey.LIT.value)
    assert "Cormen" in " ".join(str(line) for line in lit["lines"])
