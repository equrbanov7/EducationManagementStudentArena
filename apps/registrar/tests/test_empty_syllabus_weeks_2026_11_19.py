"""Sahib 2026-11-19: boş həftəlik planlı sillabuslar bütün formalar üzrə (``fill_empty_syllabus_weeks_20261119``).

Dünya (``reuse_fixtures``): müəllimin o1/o2/o4 jurnalları plan 30/16/14, o3 — 30/30; ikinci müəllimin o5 jurnalı
30/16/14.  o1-in təsdiqlənmiş sillabusu mövzuludur — jurnalın ehtiyat mənbəyi odur.
"""

from __future__ import annotations

import io
import pathlib
import re

from django.core.management import call_command

import pytest

from apps.registrar import empty_syllabus_weeks_2026_11_19 as filler
from apps.registrar.models import CourseOffering
from apps.syllabus import services
from apps.syllabus.models import Syllabus, SyllabusSection, SyllabusVersion
from apps.syllabus.tests.factories import PLAN_HOURS
from apps.syllabus.tests.reuse_fixtures import approved_syllabus, build_world
from apps.syllabus.week_plan import expected_week_rows

pytestmark = pytest.mark.django_db

WORKFLOW = pathlib.Path(__file__).resolve().parents[3] / ".github" / "workflows" / "prod-data-ops.yml"
PREFIX = "empty_weeks: "
IDS_PREFIX = "empty_weeks_ids: "
EMPTY_ROWS = [{"topic": "", "outcome": "", "lecture": 0, "seminar": 0, "lab": 0} for _ in range(16)]


@pytest.fixture()
def world(settings):
    settings.ACADEMIC_SELFWORK_ENABLED = True
    from django.contrib.auth import get_user_model

    data = build_world("emptywk")
    data["owner"] = get_user_model().objects.create_user("emptywk_su", "emptywk_su@x.test", "pw", is_superuser=True)
    return data


def _empty(version):
    SyllabusSection.objects.filter(version=version, section_id="week").update(data={"rows": EMPTY_ROWS})
    SyllabusVersion.objects.filter(pk=version.pk).update(plan_hours={})


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
        "fill_empty_syllabus_weeks_20261119",
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
    assert "          - fill_empty_syllabus_weeks_20261119\n" in text
    assert '[ "$COMMAND" = "fill_empty_syllabus_weeks_20261119" ]' in text
    assert "|empty_weeks|empty_weeks_ids|" in text
    assert "^emptywk-[0-9]{8}-[0-9]{6}-[0-9a-f]{4}$" in text


def test_own_dossier_filled_and_undone(world):
    _source, source_version = approved_syllabus(world, "o1")
    own, version = approved_syllabus(world, "o2")
    _empty(version)
    offering = CourseOffering.objects.select_related("organization").get(pk=world["offerings"]["o2"].pk)
    assert services.syllabus_for_offering_obj(offering).pk == own.pk

    dry, batch, ids = _call(world)
    assert (dry["found_a_own"], dry["filled_a_own"], dry["healthy"]) == ("1", "1", "1")
    assert all(re.fullmatch(r"[a-z_]+", key) and value.isdigit() for key, value in dry.items())
    assert ids["filled_a_own"] == [str(version.pk)]
    assert batch == ""
    assert _week(version) == EMPTY_ROWS

    applied, batch, _ids = _call(world, "--apply")
    assert applied["filled_a_own"] == "1"
    assert re.match(r"^emptywk-\d{8}-\d{6}-[0-9a-f]{4}$", batch)
    rows = _week(version)
    version.refresh_from_db()
    assert version.plan_hours == PLAN_HOURS
    assert len(rows) == expected_week_rows(PLAN_HOURS) == 15
    assert [row["topic"] for row in rows] == [row["topic"] for row in _week(source_version)][: len(rows)]
    assert all(row["topic"] for row in rows)
    assert sum(int(row.get("lecture") or 0) for row in rows) == PLAN_HOURS["lecture"]
    assert sum(int(row.get("seminar") or 0) for row in rows) == PLAN_HOURS["seminar"]
    assert version.status == "approved"

    again, _batch, _ids = _call(world, "--apply")
    assert again.get("filled_a_own") is None and again["healthy"] == "2"

    undone, _batch, _ids = _call(world, "--apply", "--undo", "--batch", batch)
    assert undone["undone"] == "1"
    assert _week(version) == EMPTY_ROWS
    version.refresh_from_db()
    assert version.plan_hours == {}


def test_shared_semester_dossier_with_two_teachers_is_skipped(world):
    semester, version = approved_syllabus(world, "o1")
    Syllabus.objects.filter(pk=semester.pk).update(offering=None)  # fənn + semestr dosyesi
    _empty(version)
    offering = CourseOffering.objects.select_related("organization").get(pk=world["offerings"]["o5"].pk)
    assert services.syllabus_for_offering_obj(offering).pk == semester.pk  # ikinci müəllimin jurnalı da ona düşür

    applied, _batch, ids = _call(world, "--apply")
    assert applied["found_b_semester"] == "1"
    assert applied["skip_teachers_mixed"] == "1"
    assert applied.get("filled_b_semester") is None
    assert ids["skip_teachers_mixed"] == [str(version.pk)]
    assert _week(version) == EMPTY_ROWS


def test_plan_with_topics_untouched_and_missing_hours_added(world):
    _syllabus, healthy = approved_syllabus(world, "o1")
    before = _week(healthy)
    _other, no_hours = approved_syllabus(world, "o2")
    SyllabusVersion.objects.filter(pk=no_hours.pk).update(plan_hours={})
    topics = [row["topic"] for row in _week(no_hours)]

    applied, _batch, _ids = _call(world, "--apply")
    assert applied["healthy"] == "1"
    assert (applied["found_c_no_plan_hours"], applied["fixed_c_no_plan_hours"]) == ("1", "1")
    assert _week(healthy) == before
    no_hours.refresh_from_db()
    assert no_hours.plan_hours == PLAN_HOURS
    assert [row["topic"] for row in _week(no_hours)] == topics


def test_open_draft_is_not_touched(world):
    approved_syllabus(world, "o1")
    own, version = approved_syllabus(world, "o2")
    _empty(version)
    draft = services.create_next_version(
        syllabus=own, actor=services.resolve_actor(world["teacher"], world["org"]), kind="minor"
    )
    _empty(draft)

    applied, _batch, _ids = _call(world, "--apply")
    assert applied["skip_open_draft"] == "1"
    assert _week(version) == EMPTY_ROWS
    assert _week(draft) == EMPTY_ROWS


def test_module_exports():
    assert filler.RESOURCE.startswith("registrar.")
