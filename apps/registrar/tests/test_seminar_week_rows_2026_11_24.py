"""Sahib 2026-11-24: seminar saatı «mühazirə» kimi yazılmış həftəlik plan (``fix_seminar_week_rows_20261124``).

Hal: plan 30 mühazirə + 15 seminar, sətirlərdə 23 mövzu — 22×2 + 1 = 45 saat mühazirə, seminar 0.  Son 8 sətir
(15 saat) seminara keçməlidir.
"""

from __future__ import annotations

import io
import pathlib
import re

from django.core.management import call_command

import pytest

from apps.registrar import seminar_week_rows_2026_11_24 as fixer
from apps.syllabus.models import SyllabusSection, SyllabusVersion
from apps.syllabus.tests.reuse_fixtures import approved_syllabus, build_world

pytestmark = pytest.mark.django_db

WORKFLOW = pathlib.Path(__file__).resolve().parents[3] / ".github" / "workflows" / "prod-data-ops.yml"
PREFIX = "seminar_weeks: "
IDS_PREFIX = "seminar_weeks_ids: "
PLAN = {"lecture": 30, "seminar": 15}


def _row(index, lecture=0, seminar=0, lab=0):
    return {"topic": f"Mövzu {index}", "outcome": "", "lecture": lecture, "seminar": seminar, "lab": lab}


def _misplaced_rows():
    return [_row(i + 1, lecture=2) for i in range(22)] + [_row(23, lecture=1)]


@pytest.fixture()
def world(settings):
    settings.ACADEMIC_SELFWORK_ENABLED = True
    from django.contrib.auth import get_user_model

    data = build_world("semwk")
    data["owner"] = get_user_model().objects.create_user("semwk_su", "semwk_su@x.test", "pw", is_superuser=True)
    return data


def _set(version, rows, plan):
    SyllabusSection.objects.filter(version=version, section_id="week").update(data={"rows": rows})
    SyllabusVersion.objects.filter(pk=version.pk).update(plan_hours=plan)


def _week(version):
    return SyllabusSection.objects.get(version=version, section_id="week").data["rows"]


def _parse(text):
    counts, batch, ids = {}, "", {}
    for line in text.splitlines():
        if line.startswith(IDS_PREFIX):
            key, value = line[len(IDS_PREFIX) :].split("=", 1)
            ids.setdefault(key, []).append(value)
            continue
        if not line.startswith(PREFIX) or "mode=" in line:
            continue
        body = line[len(PREFIX) :]
        if body.startswith("batch="):
            batch = body.split("=", 1)[1]
            continue
        counts.update(pair.split("=", 1) for pair in body.split())
    return counts, batch, ids


def _call(world, *extra):
    out = io.StringIO()
    call_command(
        "fix_seminar_week_rows_20261124",
        "--org",
        world["org"].slug,
        "--actor",
        world["owner"].username,
        *extra,
        stdout=out,
    )
    return _parse(out.getvalue())


def test_workflow_wiring():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "          - fix_seminar_week_rows_20261124\n" in text
    assert '[ "$COMMAND" = "fix_seminar_week_rows_20261124" ]' in text
    assert "|seminar_weeks|seminar_weeks_ids|" in text
    assert "^semwk-[0-9]{8}-[0-9]{6}-[0-9a-f]{4}$" in text


def test_shape_detection():
    rows, carrier, missing, moved = fixer.misplaced_fix(_misplaced_rows(), PLAN)
    assert (carrier, missing, moved) == ("lecture", "seminar", 8)
    assert sum(r["lecture"] for r in rows) == 30 and sum(r["seminar"] for r in rows) == 15
    assert [r["topic"] for r in rows] == [r["topic"] for r in _misplaced_rows()]
    assert all(r["lecture"] == 0 and r["seminar"] for r in rows[15:])
    # Seminar artıq varsa, cəm uyğun gəlmirsə və ya quyruqda başqa növ varsa — toxunulmur.
    healthy = [_row(i + 1, lecture=2, seminar=2 if i < 8 else 0) for i in range(15)]
    assert fixer.misplaced_fix(healthy, PLAN) is None
    assert fixer.misplaced_fix(_misplaced_rows()[:-1], PLAN) is None
    mixed = _misplaced_rows()
    mixed[20]["lab"] = 2
    assert fixer.misplaced_fix(mixed, PLAN) is None
    assert fixer.misplaced_fix(_misplaced_rows(), {}) is None


def test_fix_dry_run_apply_undo(world):
    _syllabus, version = approved_syllabus(world, "o1")
    _set(version, _misplaced_rows(), PLAN)

    dry, batch, ids = _call(world)
    assert dry["fix_approved_lecture_to_seminar"] == "1" and dry["rows_moved"] == "8"
    assert all(re.fullmatch(r"[a-z_]+", key) and value.isdigit() for key, value in dry.items())
    assert ids["fix_approved_lecture_to_seminar"] == [str(version.pk)]
    assert batch == ""
    assert _week(version) == _misplaced_rows()

    applied, batch, _ids = _call(world, "--apply")
    assert applied["fix_approved_lecture_to_seminar"] == "1"
    assert re.match(r"^semwk-\d{8}-\d{6}-[0-9a-f]{4}$", batch)
    rows = _week(version)
    assert len(rows) == 23
    assert sum(r["lecture"] for r in rows) == 30 and sum(r["seminar"] for r in rows) == 15
    version.refresh_from_db()
    assert version.status == "approved" and version.plan_hours == PLAN

    again, _batch, _ids = _call(world, "--apply")
    assert again.get("fix_approved_lecture_to_seminar") is None

    undone, _batch, _ids = _call(world, "--apply", "--undo", "--batch", batch)
    assert undone["undone"] == "1"
    assert _week(version) == _misplaced_rows()


def test_plan_from_journal_when_version_empty(world, monkeypatch):
    _syllabus, version = approved_syllabus(world, "o1")
    _set(version, _misplaced_rows(), {})
    monkeypatch.setattr("apps.registrar.plan_hours.plan_hours_for_offering", lambda offering: dict(PLAN))

    applied, _batch, _ids = _call(world, "--apply")
    assert applied["fix_approved_lecture_to_seminar"] == "1"
    assert applied["plan_hours_from_journal"] == "1"
    version.refresh_from_db()
    assert version.plan_hours == PLAN
    assert sum(r["seminar"] for r in _week(version)) == 15
