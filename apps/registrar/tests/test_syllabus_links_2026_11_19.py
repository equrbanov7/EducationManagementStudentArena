"""MR-000562/550: ``fix_syllabus_links_20261119`` — sillabusun kafedrası və fənn bağı (sabit id-lər, geri qaytarıla bilən)."""

from __future__ import annotations

import io
import pathlib

from django.contrib.auth import get_user_model
from django.core.management import call_command

import pytest

from apps.registrar import syllabus_links_2026_11_19 as fixer
from apps.registrar.models import Subject
from apps.syllabus.models import Syllabus
from apps.syllabus.tests.reuse_fixtures import approved_syllabus, build_world

pytestmark = pytest.mark.django_db

WORKFLOW = pathlib.Path(__file__).resolve().parents[3] / ".github" / "workflows" / "prod-data-ops.yml"
PREFIX = "syllabus_links: "


def test_workflow_wiring():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "          - fix_syllabus_links_20261119\n" in text
    assert '[ "$COMMAND" = "fix_syllabus_links_20261119" ]' in text
    assert "|syllabus_links|" in text
    assert "^sylink-[0-9]{8}-[0-9]{6}-[0-9a-f]{4}$" in text


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


def test_apply_and_undo(settings, monkeypatch):
    settings.ACADEMIC_SELFWORK_ENABLED = True
    world = build_world("sylink")
    admin = get_user_model().objects.create_user("sylink_su", "sylink_su@x.test", "pw", is_superuser=True)
    chair_syllabus, _ = approved_syllabus(world, "o1")
    subject_syllabus, _ = approved_syllabus(world, "o2")
    wrong = Subject.objects.create(organization=world["org"], code="WRONG-1", name="VoİP")
    Syllabus.objects.filter(pk=subject_syllabus.pk).update(subject=wrong)
    old_chair = Syllabus.objects.get(pk=chair_syllabus.pk).chair_unit_id
    target_chair = world["other_chair"]
    assert old_chair != target_chair.pk
    monkeypatch.setattr(fixer, "CHAIR_SYLLABI", (str(chair_syllabus.pk),))
    monkeypatch.setattr(fixer, "PHILOSOPHY_CHAIR", str(target_chair.pk))
    monkeypatch.setattr(
        fixer, "SUBJECT_FIXES", ((str(subject_syllabus.pk), str(world["offerings"]["o2"].pk), "WRONG-1"),)
    )

    def call(*extra):
        out = io.StringIO()
        call_command(
            "fix_syllabus_links_20261119", "--org", world["org"].slug, "--actor", admin.username, *extra, stdout=out
        )
        return _parse(out.getvalue())

    dry, _ = call()
    assert dry == {"chair_fixed": "1", "chair_missing": "0", "subject_fixed": "1"}
    assert Syllabus.objects.get(pk=chair_syllabus.pk).chair_unit_id == old_chair
    assert Syllabus.objects.get(pk=subject_syllabus.pk).subject_id == wrong.pk

    applied, batch = call("--apply")
    assert applied["chair_fixed"] == "1" and applied["subject_fixed"] == "1"
    assert batch.startswith("sylink-")
    assert Syllabus.objects.get(pk=chair_syllabus.pk).chair_unit_id == target_chair.pk
    assert Syllabus.objects.get(pk=subject_syllabus.pk).subject_id == world["subject"].pk

    again, _ = call("--apply")
    assert again == {"chair_already": "1", "chair_missing": "0", "subject_already": "1"}

    undone, _ = call("--apply", "--undo", f"--batch={batch}")
    assert undone == {"undone": "2"}
    assert Syllabus.objects.get(pk=chair_syllabus.pk).chair_unit_id == old_chair
    assert Syllabus.objects.get(pk=subject_syllabus.pk).subject_id == wrong.pk


def test_unexpected_subject_is_left_alone(settings, monkeypatch):
    settings.ACADEMIC_SELFWORK_ENABLED = True
    world = build_world("sylink2")
    admin = get_user_model().objects.create_user("sylink2_su", "sylink2_su@x.test", "pw", is_superuser=True)
    syllabus, _ = approved_syllabus(world, "o1")
    other = Subject.objects.create(organization=world["org"], code="OTHER-9", name="Başqa")
    Syllabus.objects.filter(pk=syllabus.pk).update(subject=other)
    monkeypatch.setattr(fixer, "CHAIR_SYLLABI", ())
    monkeypatch.setattr(fixer, "SUBJECT_FIXES", ((str(syllabus.pk), str(world["offerings"]["o1"].pk), "WRONG-1"),))
    out = io.StringIO()
    call_command(
        "fix_syllabus_links_20261119", "--org", world["org"].slug, "--actor", admin.username, "--apply", stdout=out
    )
    counts, _ = _parse(out.getvalue())
    assert counts["skip_subject_unexpected"] == "1"
    assert Syllabus.objects.get(pk=syllabus.pk).subject_id == other.pk
