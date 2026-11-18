"""MR-000537: ``remove_colloquium_note_20261118`` — qiymətləndirmə qeydindən «colloquium» cümlələri silinir."""

from __future__ import annotations

import io
import pathlib
import re

from django.contrib.auth import get_user_model
from django.core.management import call_command

import pytest

from apps.registrar import colloquium_note_2026_11_18 as cleaner
from apps.syllabus.models import SyllabusSection
from apps.syllabus.tests.reuse_fixtures import approved_syllabus, build_world

pytestmark = pytest.mark.django_db

WORKFLOW = pathlib.Path(__file__).resolve().parents[3] / ".github" / "workflows" / "prod-data-ops.yml"
PREFIX = "colloquium_note: "
NOTE = (
    "The total of the points awarded for the current assessment, which consists of seminars and colloquiums "
    "(0–10 points), independent work (0–10 points), determines the final grade. The current grade plus the "
    "interim grade equals the final grade. Colloquiums take place three times a semester. Every colloquium "
    "receives a score between 0 and 10. The colloquium is required.\nAttendance is checked every lesson."
)


def test_strip_keeps_other_sentences():
    cleaned, removed = cleaner.strip_colloquium(NOTE)
    assert removed == 4
    assert "olloquium" not in cleaned
    assert "The current grade plus the interim grade equals the final grade." in cleaned
    assert "Attendance is checked every lesson." in cleaned


def test_workflow_wiring():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "          - remove_colloquium_note_20261118\n" in text
    assert '[ "$COMMAND" = "remove_colloquium_note_20261118" ]' in text
    assert "|colloquium_note|" in text
    assert "^colloq-[0-9]{8}-[0-9]{6}-[0-9a-f]{4}$" in text


def _parse(text):
    counts, batch = {}, ""
    for line in text.splitlines():
        if not line.startswith(PREFIX) or "mode=" in line:
            continue
        body = line[len(PREFIX) :]
        if body.startswith("batch="):
            batch = body.split("=", 1)[1]
            continue
        counts.update(pair.split("=", 1) for pair in body.split())
    return counts, batch


def test_apply_and_undo(settings, monkeypatch):
    settings.ACADEMIC_SELFWORK_ENABLED = True
    world = build_world("colloq")
    admin = get_user_model().objects.create_user("colloq_su", "colloq_su@x.test", "pw", is_superuser=True)
    syllabus, version = approved_syllabus(world, "o1")
    row = SyllabusSection.objects.get(version=version, section_id="assess")
    SyllabusSection.objects.filter(pk=row.pk).update(data={**(row.data or {}), "note": NOTE})
    monkeypatch.setattr(cleaner, "VERSIONS", (str(version.pk),))
    monkeypatch.setattr(cleaner, "AUTHOR_ID", syllabus.author_id)

    def call(*extra):
        out = io.StringIO()
        call_command(
            "remove_colloquium_note_20261118", "--org", world["org"].slug, "--actor", admin.username, *extra, stdout=out
        )
        return _parse(out.getvalue())

    dry, _ = call()
    assert dry["sentences_removed"] == "4"
    assert SyllabusSection.objects.get(pk=row.pk).data["note"] == NOTE

    applied, batch = call("--apply")
    assert re.match(r"^colloq-\d{8}-\d{6}-[0-9a-f]{4}$", batch)
    note = SyllabusSection.objects.get(pk=row.pk).data["note"]
    assert "olloquium" not in note and "Attendance is checked every lesson." in note

    again, _ = call("--apply")
    assert again["skip_no_colloquium"] == "1"

    undone, _ = call("--apply", "--undo", "--batch", batch)
    assert undone["undone"] == "1"
    assert SyllabusSection.objects.get(pk=row.pk).data["note"] == NOTE
