"""MR-000647: ``fix_syllabus_author_20261123`` — sillabusun müəllifi jurnalın müəllimi (sabit id, geri qaytarıla bilən)."""

from __future__ import annotations

import io
import pathlib

from django.contrib.auth import get_user_model
from django.core.management import call_command

import pytest

from apps.registrar import syllabus_author_2026_11_23 as fixer
from apps.syllabus.models import Syllabus
from apps.syllabus.tests.reuse_fixtures import approved_syllabus, build_world

pytestmark = pytest.mark.django_db

WORKFLOW = pathlib.Path(__file__).resolve().parents[3] / ".github" / "workflows" / "prod-data-ops.yml"
PREFIX = "syllabus_author: "


def test_workflow_wiring():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "          - fix_syllabus_author_20261123\n" in text
    assert '[ "$COMMAND" = "fix_syllabus_author_20261123" ]' in text
    assert "|syllabus_author|" in text
    assert "^syauth-[0-9]{8}-[0-9]{6}-[0-9a-f]{4}$" in text


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


def _call(world, admin, *extra):
    out = io.StringIO()
    call_command(
        "fix_syllabus_author_20261123", "--org", world["org"].slug, "--actor", admin.username, *extra, stdout=out
    )
    return _parse(out.getvalue())


def test_apply_and_undo(settings, monkeypatch):
    settings.ACADEMIC_SELFWORK_ENABLED = True
    world = build_world("syauth")
    admin = get_user_model().objects.create_user("syauth_su", "syauth_su@x.test", "pw", is_superuser=True)
    syllabus, _ = approved_syllabus(world, "o1")
    other = world["teacher2"]
    Syllabus.objects.filter(pk=syllabus.pk).update(author=other)
    offering = world["offerings"]["o1"]
    monkeypatch.setattr(fixer, "FIXES", ((str(syllabus.pk), str(offering.pk), world["teacher"].pk),))

    dry, _ = _call(world, admin)
    assert dry == {"author_fixed": "1"}
    assert Syllabus.objects.get(pk=syllabus.pk).author_id == other.pk

    applied, batch = _call(world, admin, "--apply")
    assert applied == {"author_fixed": "1"}
    assert batch.startswith("syauth-")
    assert Syllabus.objects.get(pk=syllabus.pk).author_id == world["teacher"].pk

    again, _ = _call(world, admin, "--apply")
    assert again == {"already": "1"}

    undone, _ = _call(world, admin, "--apply", "--undo", f"--batch={batch}")
    assert undone == {"undone": "1"}
    assert Syllabus.objects.get(pk=syllabus.pk).author_id == other.pk


def test_unexpected_teacher_is_left_alone(settings, monkeypatch):
    settings.ACADEMIC_SELFWORK_ENABLED = True
    world = build_world("syauth2")
    admin = get_user_model().objects.create_user("syauth2_su", "syauth2_su@x.test", "pw", is_superuser=True)
    syllabus, _ = approved_syllabus(world, "o1")
    offering = world["offerings"]["o1"]
    monkeypatch.setattr(fixer, "FIXES", ((str(syllabus.pk), str(offering.pk), world["teacher2"].pk),))
    counts, _ = _call(world, admin, "--apply")
    assert counts == {"skip_unexpected": "1"}
    assert Syllabus.objects.get(pk=syllabus.pk).author_id == world["teacher"].pk
