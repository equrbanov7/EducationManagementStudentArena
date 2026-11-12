"""Sahib 2026-11-12: ``retire_uiux_syllabus_20261112`` — artıq «UI/UX» sillabusu passiv + undo; qoruyucular."""

from __future__ import annotations

import pathlib
import re
from collections import Counter

from django.apps import apps
from django.core.management.base import CommandError
from django.test import SimpleTestCase
from django.utils import timezone

import pytest

from apps.registrar import uiux_syllabus_retire_2026_11_12 as retire
from apps.syllabus.models import Syllabus
from apps.syllabus.services.queries import list_syllabi
from apps.syllabus.tests.reuse_fixtures import actor, build_world

WORKFLOW = pathlib.Path(__file__).resolve().parents[3] / ".github" / "workflows" / "prod-data-ops.yml"


class WiringTest(SimpleTestCase):
    def test_workflow_wiring_and_summary_keys(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("          - retire_uiux_syllabus_20261112\n", text)
        self.assertRegex(text, r"\|retire_uiux_syllabus_20261112[|)]")
        self.assertIn('[ "$COMMAND" = "retire_uiux_syllabus_20261112" ]', text)
        pattern = re.search(r"grep -E '(\^\(twin_relocate[^']+)'", text).group(1)
        self.assertRegex("syllabus_retire: syllabi_retired=1", pattern)
        self.assertRegex("syllabus_retire: undo_syllabi_reactivated=1", pattern)


@pytest.fixture
def world():
    value = build_world("uiux-retire")
    keeper = Syllabus.objects.create(
        organization=value["org"], subject=value["subject"], author=value["teacher"], chair_unit=value["chair"]
    )
    version = apps.get_model("syllabus", "SyllabusVersion").objects.create(
        organization=value["org"],
        syllabus=keeper,
        status="approved",
        locked_at=timezone.now(),
        approval_source="migration",
    )
    Syllabus.objects.filter(pk=keeper.pk).update(approved_version=version, current_version=version)
    Subject = apps.get_model("registrar", "Subject")
    uiux_subject = Subject.objects.create(organization=value["org"], code="UIUX-1", name="İnterfeys (UI/UX)")
    extra = Syllabus.objects.create(
        organization=value["org"],
        subject=uiux_subject,
        author=value["teacher"],
        chair_unit=value["chair"],
        program=keeper.program,
    )
    value.update(
        keeper=keeper,
        extra=extra,
        target={
            "syllabus": str(extra.pk),
            "author": value["teacher"].pk,
            "subject_code": "UIUX-1",
            "keeper_subject_code": value["subject"].code,
        },
    )
    return value


def _run(world, step=retire.run):
    counts = Counter()
    step(organization=world["org"], actor=world["teacher"], counts=counts, apply=True, target=world["target"])
    return counts


@pytest.mark.django_db
def test_retire_hides_only_the_extra_dossier_and_undo_restores_it(world):
    assert _run(world)["syllabi_retired"] == 1
    world["extra"].refresh_from_db()
    world["keeper"].refresh_from_db()
    assert world["extra"].is_active is False
    assert world["keeper"].is_active is True
    visible = set(list_syllabi(organization=world["org"], actor=actor(world)).values_list("pk", flat=True))
    assert world["extra"].pk not in visible and world["keeper"].pk in visible
    assert _run(world)["already_retired"] == 1
    assert _run(world, retire.undo)["undo_syllabi_reactivated"] == 1
    world["extra"].refresh_from_db()
    assert world["extra"].is_active is True


@pytest.mark.django_db
def test_refuses_when_scope_changed(world):
    world["target"]["subject_code"] = "OTHER"
    with pytest.raises(CommandError, match="syllabus_retire_scope_changed"):
        _run(world)
    world["extra"].refresh_from_db()
    assert world["extra"].is_active is True


@pytest.mark.django_db
def test_refuses_when_teacher_would_lose_the_keeper(world):
    Syllabus.objects.filter(pk=world["keeper"].pk).update(is_active=False)
    with pytest.raises(CommandError, match="syllabus_retire_keeper_missing"):
        _run(world)


@pytest.mark.django_db
def test_refuses_when_bound_to_an_active_journal(world):
    Syllabus.objects.filter(pk=world["extra"].pk).update(offering=world["offerings"]["o2"])
    with pytest.raises(CommandError, match="syllabus_retire_bound_to_active_journal"):
        _run(world)
