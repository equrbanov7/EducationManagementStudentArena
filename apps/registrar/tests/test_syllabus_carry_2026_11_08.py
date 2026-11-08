"""Təsdiqlənmiş sillabus müəllimin başqa qrupunda da (sahib 2026-11-08).

Dünya (``reuse_fixtures``): müəllim — o1 (101A), o2 (102A), o3 (103B, saat FƏRQLİ), o4 (104C, başqa kafedra, saat
eyni); ikinci müəllim — o5 (105A).  Yoxlanılır: təsdiqlənmiş sillabus boş jurnala paylaşılır (surət yox); qaralama,
fərqli dil / saat, birmənalı olmayan namizəd, artıq sillabusu olan jurnal — toxunulmur; təsdiq və müəllim təyini
qarmaqları; əmrin dry-run / apply / undo axını (stdout-da yalnız saylar).
"""

from __future__ import annotations

import io
import re

from django.core.management import call_command
from django.core.management.base import CommandError

import pytest

from apps.organizations.models import OrgUnit
from apps.registrar import syllabus_carry
from apps.registrar.models import CourseOffering
from apps.syllabus import services
from apps.syllabus.models import ShareSource, Syllabus, SyllabusShare
from apps.syllabus.tests.reuse_fixtures import approved_syllabus, build_world, draft_for
from core.constants import OrgUnitType

pytestmark = pytest.mark.django_db

SUMMARY = re.compile(r"^syllabus_carry: [a-z_]+=[0-9a-z_-]+( [a-z_]+=[0-9a-z_-]+)*$")


@pytest.fixture()
def world(settings):
    settings.ACADEMIC_SELFWORK_ENABLED = True  # fixture 8 bölməni doldurur (apps/syllabus/tests/conftest.py)
    return build_world("syl-carry")


def _offering(world, key):
    return CourseOffering.objects.select_related("organization", "subject", "group").get(pk=world["offerings"][key].pk)


def _resolved(world, key):
    return services.syllabus_for_offering_obj(_offering(world, key))


def _carry(world, key):
    return syllabus_carry.carry_approved(_offering(world, key))


def test_approved_syllabus_is_shared_to_the_teachers_empty_journal(world):
    source, _version = approved_syllabus(world, "o1")
    code, row = _carry(world, "o2")
    assert code == syllabus_carry.SHARED
    assert (row.syllabus_id, row.source, row.offering_id) == (
        source.pk,
        ShareSource.CARRY.value,
        world["offerings"]["o2"].pk,
    )
    assert Syllabus.objects.filter(organization=world["org"]).count() == 1  # surət yoxdur
    found = _resolved(world, "o2")
    assert found.pk == source.pk
    assert services.offering_syllabus_state(found)["state"] == "approved"
    # İdempotent: ikinci keçid heç nə yazmır.
    assert _carry(world, "o2") == (syllabus_carry.HAS_SYLLABUS, None)
    assert SyllabusShare.objects.filter(offering=world["offerings"]["o2"]).count() == 1


def test_draft_is_not_carried(world):
    draft_for(world, "o1")
    assert _carry(world, "o2") == (syllabus_carry.UNAPPROVED, None)
    assert _resolved(world, "o2") is None
    assert _carry(world, "o5") == (syllabus_carry.NO_CANDIDATE, None)  # başqa müəllim


def test_other_teacher_never_receives_the_syllabus(world):
    approved_syllabus(world, "o1")
    assert _carry(world, "o5") == (syllabus_carry.NO_CANDIDATE, None)
    assert not SyllabusShare.objects.filter(offering=world["offerings"]["o5"]).exists()


def test_different_hours_are_not_carried(world):
    approved_syllabus(world, "o1")
    assert _carry(world, "o3") == (syllabus_carry.HOURS, None)  # 103B planı 30/30/0
    assert _resolved(world, "o3") is None


def test_different_teaching_language_is_not_carried(world):
    approved_syllabus(world, "o1")
    group = world["groups"]["g2"]
    OrgUnit.objects.filter(pk=group.pk).update(settings={"language_sector": "EN"})
    assert _carry(world, "o2") == (syllabus_carry.LANGUAGE, None)
    assert _resolved(world, "o2") is None


def test_group_language_reads_metadata_then_name_suffix():
    def unit(name, settings=None):
        return OrgUnit(name=name, unit_type=OrgUnitType.GROUP, settings=settings or {})

    assert syllabus_carry.group_language(unit("236 EM")) == "az"
    assert syllabus_carry.group_language(unit("236 EM ing")) == "ing"
    assert syllabus_carry.group_language(unit("236 EM en")) == "ing"
    assert syllabus_carry.group_language(unit("236 EM", {"sector": "ru"})) == "rus"
    assert syllabus_carry.group_language(unit("236 EM ing", {"language_sector": "az"})) == "az"
    assert syllabus_carry.group_language(None) == ""


def test_ambiguous_candidates_are_left_alone(world):
    approved_syllabus(world, "o1")
    approved_syllabus(world, "o2")
    assert _carry(world, "o4") == (syllabus_carry.AMBIGUOUS, None)
    assert _resolved(world, "o4") is None


def test_journal_with_own_draft_is_untouched(world):
    approved_syllabus(world, "o1")
    own, version = draft_for(world, "o2")
    assert _carry(world, "o2") == (syllabus_carry.HAS_SYLLABUS, None)
    assert _resolved(world, "o2").pk == own.pk
    version.refresh_from_db()
    assert version.status == "draft"
    assert not SyllabusShare.objects.filter(offering=world["offerings"]["o2"]).exists()


def test_approval_hook_carries_to_every_matching_journal(world, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        source, _version = approved_syllabus(world, "o1")
    shared = dict(SyllabusShare.objects.filter(organization=world["org"]).values_list("offering_id", "source"))
    offerings = world["offerings"]
    assert shared == {offerings["o2"].pk: ShareSource.CARRY.value, offerings["o4"].pk: ShareSource.CARRY.value}
    assert _resolved(world, "o2").pk == source.pk
    assert _resolved(world, "o3") is None  # saat fərqli
    assert _resolved(world, "o5") is None  # başqa müəllim


def test_teacher_assignment_hook_carries(world, django_capture_on_commit_callbacks):
    source, _version = approved_syllabus(world, "o1")
    spec_a = world["groups"]["g1"].parent
    group = OrgUnit.objects.create(
        organization=world["org"], name="106A", slug="syl-carry-106a", unit_type=OrgUnitType.GROUP, parent=spec_a
    )
    with django_capture_on_commit_callbacks(execute=True):
        new = CourseOffering.objects.create(
            organization=world["org"],
            subject=world["subject"],
            period=world["period"],
            group=group,
            instructor=world["teacher"],
            lesson_hours=60,
        )
    assert SyllabusShare.objects.get(offering=new).syllabus_id == source.pk
    # Fənn müəllimə təhvil verilir (``instructor`` dəyişir) — boş jurnal onun sillabusunu alır.
    offering = _offering(world, "o5")
    offering.instructor = world["teacher"]
    with django_capture_on_commit_callbacks(execute=True):
        offering.save(update_fields=["instructor", "updated_at"])
    assert _resolved(world, "o5").pk == source.pk


def _call(world, *extra):
    out = io.StringIO()
    call_command(
        "carry_approved_syllabi_20261108",
        "--org",
        world["org"].slug,
        "--actor",
        world["admin"].username,
        *extra,
        stdout=out,
    )
    counts = {}
    for line in out.getvalue().splitlines():
        assert SUMMARY.match(line), line
        if "mode=" not in line:
            counts.update(pair.split("=", 1) for pair in line[len("syllabus_carry: ") :].split())
    return counts


def test_command_dry_run_apply_and_undo(world):
    world["admin"] = world["teacher"].__class__.objects.create_superuser("syl-carry-admin", "a@x.test", "pw")
    source, _version = approved_syllabus(world, "o1")
    dry = _call(world)
    assert (dry["shared"], dry["skipped_hours"], dry["ambiguous"]) == ("2", "1", "0")
    assert "batch" not in dry
    assert not SyllabusShare.objects.filter(organization=world["org"]).exists()

    applied = _call(world, "--apply")
    assert applied["shared"] == "2"
    batch = applied["batch"]
    assert re.fullmatch(r"sylcarry-[0-9]{8}-[0-9]{6}-[0-9a-f]{4}", batch)
    assert set(SyllabusShare.objects.filter(organization=world["org"]).values_list("syllabus_id", flat=True)) == {
        source.pk
    }
    again = _call(world, "--apply")  # idempotent
    assert again["shared"] == "0" and "batch" not in again

    undone = _call(world, "--undo", batch, "--apply")
    assert (undone["undo_removed"], undone["undo_missing"]) == ("2", "0")
    assert not SyllabusShare.objects.filter(organization=world["org"]).exists()
    with pytest.raises(CommandError, match="already_undone"):
        _call(world, "--undo", batch, "--apply")
    with pytest.raises(CommandError, match="bad_batch"):
        _call(world, "--undo", "nonsense", "--apply")


def test_command_is_wired_into_prod_data_ops():
    from pathlib import Path

    root = Path(__file__).resolve().parents[3]
    workflow = (root / ".github/workflows/prod-data-ops.yml").read_text(encoding="utf-8")
    assert "- carry_approved_syllabi_20261108" in workflow
    assert '[ "$COMMAND" = "carry_approved_syllabi_20261108" ]' in workflow
    assert "|syllabus_carry|" in workflow
    coverage = (root / "scripts/check_worker_atomic_coverage.py").read_text(encoding="utf-8")
    assert "carry_approved_syllabi_20261108.py" in coverage
