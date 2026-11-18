"""Sahib 2026-11-18: boş həftəlik planlı BAZA sillabus müəllimin öz təsdiqlənmiş planı ilə (``fill_base_syllabus_weeks``).

Dünya (``reuse_fixtures``): müəllimin o1 (101A, plan 30/16/14) jurnalının öz təsdiqlənmiş sillabusu var; o2/o4 (eyni
saat) jurnallarının öz dosyesi yoxdur və müəllimin semestrsiz baza dosyesinə düşür — onun həftəlik planı boşdur.
"""

from __future__ import annotations

import io
import pathlib
import re

from django.core.management import call_command

import pytest

from apps.registrar import base_syllabus_weeks_2026_11_18 as filler
from apps.registrar.models import CourseOffering
from apps.syllabus import services
from apps.syllabus.models import Syllabus, SyllabusSection, SyllabusVersion
from apps.syllabus.tests.reuse_fixtures import approved_syllabus, build_world

pytestmark = pytest.mark.django_db

WORKFLOW = pathlib.Path(__file__).resolve().parents[3] / ".github" / "workflows" / "prod-data-ops.yml"
PREFIX = "base_weeks: "
EMPTY_ROWS = [{"topic": "", "outcome": "", "lecture": 0, "seminar": 0, "lab": 0} for _ in range(16)]


@pytest.fixture()
def world(settings):
    settings.ACADEMIC_SELFWORK_ENABLED = True
    from django.contrib.auth import get_user_model

    data = build_world("basewk")
    data["owner"] = get_user_model().objects.create_user("basewk_su", "basewk_su@x.test", "pw", is_superuser=True)
    return data


def _make_base(world):
    """o2 üçün təsdiqlənmiş dosye → baza (semestrsiz, açılışsız), həftəlik planı boş, plan saatı yox."""
    base, version = approved_syllabus(world, "o2")
    Syllabus.objects.filter(pk=base.pk).update(offering=None, period=None)
    SyllabusSection.objects.filter(version=version, section_id="week").update(data={"rows": EMPTY_ROWS})
    SyllabusVersion.objects.filter(pk=version.pk).update(plan_hours={})
    return base, version


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


def _call(world, *extra):
    out = io.StringIO()
    call_command(
        "fill_base_syllabus_weeks_20261118",
        "--org",
        world["org"].slug,
        "--actor",
        world["owner"].username,
        *extra,
        stdout=out,
    )
    return _parse(out.getvalue())


def _week(version):
    return SyllabusSection.objects.get(version=version, section_id="week").data["rows"]


def test_workflow_wiring():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "          - fill_base_syllabus_weeks_20261118\n" in text
    assert '[ "$COMMAND" = "fill_base_syllabus_weeks_20261118" ]' in text
    assert "|base_weeks|" in text
    assert "^basewk-[0-9]{8}-[0-9]{6}-[0-9a-f]{4}$" in text


def test_dry_run_apply_and_undo(world):
    source, source_version = approved_syllabus(world, "o1")
    base, version = _make_base(world)
    CourseOffering.objects.filter(pk=world["offerings"]["o3"].pk).update(is_active=False)  # saatı fərqli jurnal
    offering = CourseOffering.objects.select_related("organization").get(pk=world["offerings"]["o2"].pk)
    assert services.syllabus_for_offering_obj(offering).pk == base.pk

    dry, batch = _call(world)
    assert (dry["filled"], dry["journals_covered"]) == ("1", "2")
    assert batch == ""
    assert _week(version) == EMPTY_ROWS

    applied, batch = _call(world, "--apply")
    assert applied["filled"] == "1"
    assert re.match(r"^basewk-\d{8}-\d{6}-[0-9a-f]{4}$", batch)
    rows = _week(version)
    version.refresh_from_db()
    assert version.plan_hours == {"lecture": 30, "seminar": 16, "lab": 14}
    assert len(rows) == 15  # ceil(30 / 2) — artıq boş sətir yoxdur
    assert all(row["topic"] for row in rows)
    assert [r["topic"] for r in rows] == [r["topic"] for r in _week(source_version)][: len(rows)]
    assert sum(int(r.get("lecture") or 0) for r in rows) == 30
    assert sum(int(r.get("seminar") or 0) for r in rows) == 16
    assert version.status == "approved"

    again, _ = _call(world, "--apply")
    assert again.get("filled") is None and again["skip_has_topics"] == "1"

    undone, _ = _call(world, "--apply", "--undo", "--batch", batch)
    assert undone["undone"] == "1"
    assert _week(version) == EMPTY_ROWS
    version.refresh_from_db()
    assert version.plan_hours == {}


def test_mixed_hours_are_left_alone(world):
    approved_syllabus(world, "o1")
    _base, version = _make_base(world)  # o2/o3/o4 bazaya düşür, o3-ün saatı fərqlidir
    applied, _ = _call(world, "--apply")
    assert applied["skip_hours_mixed"] == "1"
    assert _week(version) == EMPTY_ROWS


def test_no_source_without_teachers_topics(world):
    _base, version = _make_base(world)
    CourseOffering.objects.filter(pk=world["offerings"]["o3"].pk).update(is_active=False)
    applied, _ = _call(world, "--apply")
    assert applied["skip_no_source"] == "1"
    assert _week(version) == EMPTY_ROWS


def test_module_exports():
    assert filler.RESOURCE.startswith("registrar.")
