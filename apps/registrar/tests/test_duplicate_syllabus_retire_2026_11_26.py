"""2026-11-26: ``retire_duplicate_syllabus_20261126`` — eyni fənnə ikinci, jurnalsız sillabus passiv + undo (yalnız öz izi)."""

from __future__ import annotations

import pathlib
from collections import Counter

from django.apps import apps
from django.core.management.base import CommandError
from django.test import SimpleTestCase

import pytest

from apps.registrar import duplicate_syllabus_retire_2026_11_26 as retire
from apps.registrar import uiux_syllabus_retire_2026_11_12 as uiux
from apps.syllabus.models import Syllabus
from apps.syllabus.tests.reuse_fixtures import build_world

WORKFLOW = pathlib.Path(__file__).resolve().parents[3] / ".github" / "workflows" / "prod-data-ops.yml"


class WiringTest(SimpleTestCase):
    def test_workflow_wiring(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("          - retire_duplicate_syllabus_20261126\n", text)
        self.assertRegex(text, r"\|retire_duplicate_syllabus_20261126[|)]")
        self.assertIn('[ "$COMMAND" = "retire_duplicate_syllabus_20261126" ]', text)

    def test_target_has_no_keeper(self):
        self.assertEqual(retire.TARGET["keeper_subject_code"], "")
        self.assertNotEqual(retire.RETIRED, uiux.RETIRED)
        from apps.registrar import misattached_syllabus_retire_2026_11_16 as misattached

        self.assertNotEqual(retire.RETIRED, misattached.RETIRED)
        self.assertEqual((retire.TARGET["author"], retire.TARGET["subject_code"]), (11622, "QKU-2416"))

    def test_mr850_extra_targets(self):
        # MR-000850: Rəhim Həsənovun «Etika» (QKU-69) yaz qaralamaları — 4 ayrı dosye, keeper yoxdur.
        self.assertEqual(len({item["syllabus"] for item in retire.EXTRA}), 6)
        expected = {"MR-000850": (9519, "QKU-69"), "MR-000852": (8374, "QKU-588")}
        for item in retire.EXTRA:
            mr = item["reason"][:9]
            self.assertEqual((item["author"], item["subject_code"]), expected[mr])
            self.assertEqual(item["keeper_subject_code"], "")
            self.assertTrue(item["vacant_offering_ok"])


@pytest.fixture
def world():
    value = build_world("duplicate-retire")
    Subject = apps.get_model("registrar", "Subject")
    wrong = Subject.objects.create(organization=value["org"], code="MAL-1", name="Malware analysis")
    dossier = Syllabus.objects.create(
        organization=value["org"], subject=wrong, author=value["teacher"], chair_unit=value["chair"]
    )
    value.update(
        dossier=dossier,
        target={
            "syllabus": str(dossier.pk),
            "author": value["teacher"].pk,
            "subject_code": "MAL-1",
            "keeper_subject_code": "",
        },
    )
    return value


def _run(world, step):
    counts = Counter()
    step(organization=world["org"], actor=world["teacher"], counts=counts, apply=True, target=world["target"])
    return counts


@pytest.mark.django_db
def test_retires_without_keeper_and_undo_restores_only_its_own(world):
    assert _run(world, retire.run)["syllabi_retired"] == 1
    world["dossier"].refresh_from_db()
    assert world["dossier"].is_active is False
    assert _run(world, uiux.undo)["undo_syllabi_reactivated"] == 0  # başqa əmrin izi toxunmur
    assert _run(world, retire.undo)["undo_syllabi_reactivated"] == 1
    world["dossier"].refresh_from_db()
    assert world["dossier"].is_active is True


@pytest.mark.django_db
def test_refuses_when_author_differs(world):
    world["target"]["author"] = world["teacher"].pk + 999
    with pytest.raises(CommandError, match="syllabus_retire_scope_changed"):
        _run(world, retire.run)


@pytest.mark.django_db
def test_default_run_walks_every_target_and_skips_retired(world, monkeypatch):
    Subject = apps.get_model("registrar", "Subject")
    other = Subject.objects.create(organization=world["org"], code="ETK-69", name="Etika")
    second = Syllabus.objects.create(
        organization=world["org"], subject=other, author=world["teacher"], chair_unit=world["chair"]
    )
    extra = {**world["target"], "syllabus": str(second.pk), "subject_code": "ETK-69", "reason": "MR-000850 test"}
    monkeypatch.setattr(retire, "TARGET", world["target"])
    monkeypatch.setattr(retire, "EXTRA", (extra,))
    counts = Counter()
    retire.run(organization=world["org"], actor=world["teacher"], counts=counts, apply=True)
    assert counts["syllabi_retired"] == 2
    counts = Counter()
    retire.run(organization=world["org"], actor=world["teacher"], counts=counts, apply=True)
    assert counts["already_retired"] == 2


@pytest.mark.django_db
def test_vacant_offering_draft_is_retired_but_assigned_one_is_refused(world):
    offering = world["offerings"]["o1"]
    Syllabus.objects.filter(pk=world["dossier"].pk).update(offering=offering)
    world["target"]["vacant_offering_ok"] = True
    with pytest.raises(CommandError, match="syllabus_retire_bound_to_active_journal"):
        _run(world, retire.run)  # müəllimi olan aktiv jurnal qorunur
    type(offering).objects.filter(pk=offering.pk).update(instructor=None)
    assert _run(world, retire.run)["syllabi_retired"] == 1
    del world["target"]["vacant_offering_ok"]
    world["dossier"].refresh_from_db()
    assert world["dossier"].is_active is False
