"""Sahib 2026-10-10: sərbəst iş ləğv olunub (RİM tənzimləməsi söndürülü — defolt) — sillabusun qaydası.

Redaktorda 9 bölmə (``self`` yoxdur), tamamlanma 7 qayda bölməsi üzrə — sərbəst işsiz 100% və göndərmə
mümkündür; qiymətləndirmə standartı midterm 30; sənəddə «Sərbəst iş» bloku yoxdur. ``self`` bölməsinin
datası SİLİNMİR. Sahib 2026-10-11: qayda SEMESTRDƏN ASILI DEYİL — köhnə (2025/2026) semestrin sillabusu
da cari qaydadadır; sərbəst iş yalnız RİM ``academic.selfwork_enabled`` açarı ilə (bütün semestrlərdə)
geri qayıdır. ``recompute_syllabus_completion`` əmri açıq versiyaların keşini (faiz, bal bölgüsü) cari
qaydaya gətirir; təsdiqlənmiş versiyaya toxunmur.
"""

from __future__ import annotations

from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.utils import timezone

import pytest

from apps.organizations.models import AcademicPeriod
from apps.syllabus import rules, services
from apps.syllabus.assessment_formula import LABELS
from apps.syllabus.constants import SectionKey, SyllabusStatus
from apps.syllabus.document import BLOCK_TITLES, build_document
from apps.syllabus.models import SyllabusSection, SyllabusVersion
from apps.syllabus.state_machine import TransitionDenied
from apps.syllabus.tests.editor_dom import render_editor_dom
from apps.syllabus.tests.factories import (
    PLAN_HOURS,
    activate_member,
    complete_section_data,
    make_academic_stack,
    make_offering,
    make_org,
)

User = get_user_model()

pytestmark = pytest.mark.django_db

TEACHER_PERMS = ["syllabus.view", "syllabus.edit", "syllabus.submit", "grade.input"]
SELF = SectionKey.SELF.value
SKIP = {SectionKey.PREV.value, SectionKey.SEND.value}


@pytest.fixture(autouse=True)
def selfwork_rule(settings):
    """``conftest``-dəki eyni adlı fixture-u əvəzləyir: burada DEFOLT (yeni) qayda — sərbəst iş söndürülüb."""
    settings.ACADEMIC_SELFWORK_ENABLED = False


def _world(slug, *, new_rule):
    org = make_org(slug)
    teacher = User.objects.create_user(f"{slug}_teacher", f"{slug}_teacher@x.test", "pw")
    activate_member(org, teacher, "teacher", permissions=TEACHER_PERMS)
    stack = make_academic_stack(org, code=f"{slug[:3].upper()}101")
    if new_rule:
        AcademicPeriod.objects.filter(pk=stack["period"].pk).update(
            academic_year="2026/2027", start_date="2026-09-01", end_date="2027-01-31"
        )
        stack["period"].refresh_from_db()
    offering = make_offering(org, stack, teacher)
    actor = services.resolve_actor(teacher, org)
    syllabus, version = services.create_draft(
        organization=org,
        subject=stack["subject"],
        period=stack["period"],
        actor=actor,
        offering=offering,
        program=stack["program"],
        chair_unit=stack["chair"],
        plan_hours=PLAN_HOURS,
    )
    return {"org": org, "teacher": teacher, "actor": actor, "syllabus": syllabus, "version": version}


@pytest.fixture()
def new_world():
    return _world("swr-new", new_rule=True)


@pytest.fixture()
def legacy_world():
    return _world("swr-old", new_rule=False)


def _fill(world, *, with_self):
    version = world["version"]
    for section_id, data in complete_section_data().items():
        if section_id in SKIP or (section_id == SELF and not with_self):
            continue
        services.save_section(version=version, section_id=section_id, data=data, actor=world["actor"])
    version.refresh_from_db()
    return version


def _split(version):
    data = services.section_data_map(version)[SectionKey.ASSESS.value]
    return data["midterm"], data["project"]


# ── 1. Yeni qayda: 9 bölmə, sərbəst işsiz 100%, göndərmə ─────────────────────
def test_new_rule_draft_is_complete_without_selfwork_and_can_be_submitted(new_world):
    version = new_world["version"]
    assert version.sections.count() == 10  # `self` sətri DB-də qalır (data saxlanılır)
    with pytest.raises(TransitionDenied) as excinfo:
        services.save_section(version=version, section_id=SELF, data={"option": "2x5"}, actor=new_world["actor"])
    assert excinfo.value.code == "section.unknown"

    version = _fill(new_world, with_self=False)

    assert version.completion_percent == 100
    assert _split(version) == (30, 10)  # standart: midterm 30 + fəallıq 10
    submitted = services.submit(version=version, actor=new_world["actor"])
    assert submitted.status == SyllabusStatus.SUBMITTED


def test_new_rule_editor_has_nine_steps_and_the_midterm_thirty_formula(new_world):
    version = _fill(new_world, with_self=False)
    root, se = render_editor_dom(user=new_world["teacher"], organization=new_world["org"], version=version)

    assert [step["id"] for step in se["nav"]] == [
        "info",
        "desc",
        "out",
        "week",
        "method",
        "assess",
        "lit",
        "prev",
        "send",
    ]
    assert [step["index"] for step in se["nav"]] == list(range(1, 10))
    assert (se["completion"]["done"], se["completion"]["total"], se["completion"]["percent"]) == (7, 7, 100)
    assert se["selfwork"] is None and not root.xpath("//*[@data-syl-panel='self']")
    rows = {row["key"]: row["score"] for row in se["assessment"]["rows"]}
    assert rows == {"attendance": 10, "midterm": 30, "activity": 10, "final": 50}
    assert "midterm 30" in str(se["panels"][SectionKey.ASSESS.value]["hint"])
    assert str(LABELS["selfwork"]) not in se["assessment"]["formula"]


def test_new_rule_document_has_no_selfwork_block_but_keeps_the_data(new_world):
    version = _fill(new_world, with_self=False)
    stored = complete_section_data()[SELF]
    SyllabusSection.objects.filter(version=version, section_id=SELF).update(data=stored)

    document = build_document(new_world["syllabus"], version)

    keys = [block["key"] for block in document["blocks"]]
    assert keys == ["description", "goal", "outcomes", "weeks", "methods", "assessment", "literature"]
    assert str(BLOCK_TITLES["selfwork"]) not in [block["title"] for block in document["blocks"]]
    assessment = next(block["body"] for block in document["blocks"] if block["key"] == "assessment")
    assert f"{LABELS['midterm']} 30" in assessment
    assert services.section_data_map(version)[SELF] == stored  # gizli bölmənin datası yerindədir


# ── 2. Köhnə (2025/2026) semestr — sahib 2026-10-11: cari qayda, sərbəst iş YOXDUR ──
def test_old_period_syllabus_follows_the_current_rule(legacy_world):
    """Köhnə semestrin sillabusu da sərbəst işsiz 100% olur və göndərilir; sənəddə 7 blok, midterm 30."""
    assert legacy_world["syllabus"].period.academic_year == "2025/2026"
    assert rules.for_syllabus(legacy_world["syllabus"]) == rules.SyllabusRule(selfwork=False, split=True)
    assert rules.for_version(legacy_world["version"]) == rules.for_version(legacy_world["version"], None)
    with pytest.raises(TransitionDenied) as excinfo:  # `self` paneli yoxdur — gizli bölməyə yazı qəbul edilmir
        services.save_section(
            version=legacy_world["version"], section_id=SELF, data={"option": "2x5"}, actor=legacy_world["actor"]
        )
    assert excinfo.value.code == "section.unknown"

    version = _fill(legacy_world, with_self=False)

    assert version.completion_percent == 100
    assert _split(version) == (30, 10)
    document = build_document(legacy_world["syllabus"], version)
    keys = [block["key"] for block in document["blocks"]]
    assert "selfwork" not in keys and len(keys) == 7
    assessment = next(block["body"] for block in document["blocks"] if block["key"] == "assessment")
    assert f"{LABELS['midterm']} 30" in assessment and str(LABELS["selfwork"]) not in assessment
    assert services.submit(version=version, actor=legacy_world["actor"]).status == SyllabusStatus.SUBMITTED


def test_old_period_formula_rows_have_midterm_thirty_and_no_selfwork_key(legacy_world):
    """2025/2026 semestrinin sillabusu: düstur sətirləri midterm 30, «selfwork» açarı YOXDUR (defolt)."""
    version = _fill(legacy_world, with_self=False)
    _root, se = render_editor_dom(user=legacy_world["teacher"], organization=legacy_world["org"], version=version)

    rows = {row["key"]: row["score"] for row in se["assessment"]["rows"]}
    assert rows == {"attendance": 10, "midterm": 30, "activity": 10, "final": 50}
    assert "selfwork" not in rows
    assert "midterm 30" in str(se["panels"][SectionKey.ASSESS.value]["hint"])
    assert se["selfwork"] is None and len(se["nav"]) == 9


def test_toggle_restores_selfwork_for_the_old_period_too(legacy_world, settings):
    """RİM ``academic.selfwork_enabled`` yandırılanda köhnə semestrdə də midterm 20 + sərbəst iş qayıdır."""
    settings.ACADEMIC_SELFWORK_ENABLED = True
    version = _fill(legacy_world, with_self=False)
    assert version.completion_percent < 100
    assert _split(version) == (20, 10)

    version = _fill(legacy_world, with_self=True)
    assert version.completion_percent == 100
    keys = [block["key"] for block in build_document(legacy_world["syllabus"], version)["blocks"]]
    assert "selfwork" in keys and len(keys) == 8


# ── 3. Tənzimləmə yandırılıb — yeni dövrdə də köhnə qayda ─────────────────────
def test_toggle_brings_the_selfwork_section_back_for_the_new_period(new_world, settings):
    settings.ACADEMIC_SELFWORK_ENABLED = True
    version = _fill(new_world, with_self=False)
    assert version.completion_percent < 100
    assert _split(version) == (20, 10)

    version = _fill(new_world, with_self=True)
    assert version.completion_percent == 100
    _root, se = render_editor_dom(user=new_world["teacher"], organization=new_world["org"], version=version)
    assert len(se["nav"]) == 10 and se["selfwork"] is not None


# ── 4. Keşin yenidən hesablanması (əmr) ──────────────────────────────────────
def test_recompute_command_is_dry_by_default_idempotent_and_skips_approved(new_world, settings):
    # Tənzimləmə yanılı ikən doldurulmuş qaralama: `self` boşdur → 7/8, bölgü köhnə standart (20/10).
    settings.ACADEMIC_SELFWORK_ENABLED = True
    version = _fill(new_world, with_self=False)
    stale_percent = version.completion_percent
    assert stale_percent < 100 and _split(version) == (20, 10)
    # Eyni vəziyyətdə TƏSDİQLƏNMİŞ versiya — kilidli sənəd, əmr ona toxunmamalıdır.
    other = _world("swr-appr", new_rule=True)
    approved = _fill(other, with_self=False)
    SyllabusVersion.objects.filter(pk=approved.pk).update(
        status=SyllabusStatus.APPROVED,
        locked_at=timezone.now(),
        approved_at=timezone.now(),
        approved_by=other["teacher"],
    )
    approved_split, approved_percent = _split(approved), approved.completion_percent
    settings.ACADEMIC_SELFWORK_ENABLED = False  # RİM sərbəst işi söndürür (defolt)

    dry = StringIO()
    call_command("recompute_syllabus_completion", stdout=dry)
    version.refresh_from_db()
    assert "QURU İCRA" in dry.getvalue() and str(version.pk) in dry.getvalue()
    assert (version.completion_percent, _split(version)) == (stale_percent, (20, 10))

    applied = StringIO()
    call_command("recompute_syllabus_completion", "--apply", stdout=applied)
    version.refresh_from_db()
    assert version.completion_percent == 100
    assert _split(version) == (30, 10)
    assert services.section_data_map(version)[SectionKey.ASSESS.value]["note"] == ""  # mətn açarları toxunulmur

    again = StringIO()
    call_command("recompute_syllabus_completion", "--apply", stdout=again)
    assert "0 açıq versiya yeniləndi" in again.getvalue()

    approved.refresh_from_db()
    assert approved.status == SyllabusStatus.APPROVED
    assert (_split(approved), approved.completion_percent) == (approved_split, approved_percent)
