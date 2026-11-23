"""MR-000681: ``fix_syllabus_chairs_20261123`` — sillabusun kafedrası jurnalın dərs yükü kafedrasına (geri qaytarıla bilən)."""

from __future__ import annotations

import io
import pathlib

from django.contrib.auth import get_user_model
from django.core.management import call_command

import pytest

from apps.registrar import offering_chairs
from apps.syllabus.models import Syllabus
from apps.syllabus.tests.reuse_fixtures import approved_syllabus, build_world

pytestmark = pytest.mark.django_db

WORKFLOW = pathlib.Path(__file__).resolve().parents[3] / ".github" / "workflows" / "prod-data-ops.yml"
PREFIX = "syllabus_chairs: "


def test_workflow_wiring():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "          - fix_syllabus_chairs_20261123\n" in text
    assert '[ "$COMMAND" = "fix_syllabus_chairs_20261123" ]' in text
    assert "|syllabus_chairs|" in text
    assert "^sychair-[0-9]{8}-[0-9]{6}-[0-9a-f]{4}$" in text


def _parse(text):
    counts, batch = {}, ""
    for line in text.splitlines():
        if not line.startswith(PREFIX) or "mode=" in line:
            continue
        body = line[len(PREFIX) :]
        if body.startswith("batch="):
            batch = body.split("=", 1)[1]
            continue
        counts.update(pair.split("=", 1) for pair in body.split() if "=" in pair)
    return counts, batch


def test_single_load_chair_wins_ambiguous_untouched_and_undo(settings, monkeypatch):
    settings.ACADEMIC_SELFWORK_ENABLED = True
    world = build_world("sychair")
    admin = get_user_model().objects.create_user("sychair_su", "sychair_su@x.test", "pw", is_superuser=True)
    fixed, _ = approved_syllabus(world, "o1")
    ambiguous, _ = approved_syllabus(world, "o2")
    old_fixed = Syllabus.objects.get(pk=fixed.pk).chair_unit_id
    old_ambiguous = Syllabus.objects.get(pk=ambiguous.pk).chair_unit_id
    target = world["other_chair"]
    assert old_fixed != target.pk
    offerings = world["offerings"]

    def fake_official(queryset, organization_id):
        return {
            offerings["o1"].pk: frozenset({str(target.pk)}),
            offerings["o2"].pk: frozenset({str(target.pk), str(old_ambiguous)}),
        }

    monkeypatch.setattr(offering_chairs, "official_offering_chairs", fake_official)

    def call(*extra):
        out = io.StringIO()
        call_command(
            "fix_syllabus_chairs_20261123", "--org", world["org"].slug, "--actor", admin.username, *extra, stdout=out
        )
        return _parse(out.getvalue())

    dry, _ = call()
    assert dry == {"candidates": "1", "chair_fixed": "1"}
    assert Syllabus.objects.get(pk=fixed.pk).chair_unit_id == old_fixed  # dry-run geri qaytarılır

    applied, batch = call("--apply")
    assert applied["chair_fixed"] == "1" and batch.startswith("sychair-")
    assert Syllabus.objects.get(pk=fixed.pk).chair_unit_id == target.pk
    assert Syllabus.objects.get(pk=ambiguous.pk).chair_unit_id == old_ambiguous  # iki kafedra — toxunulmur

    again, _ = call("--apply")
    assert again.get("candidates") == "0"  # idempotent

    undone, _ = call("--apply", "--undo", "--batch", batch)
    assert undone == {"undone": "1"}
    assert Syllabus.objects.get(pk=fixed.pk).chair_unit_id == old_fixed
