"""REGRESSİYA: `<textarea>` çevirməsi redaktoru pozdumu? (ƏSL editor JS)"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from django.template.loader import render_to_string
from django.test import RequestFactory

import pytest
from test_real_js_roundtrip import editable  # noqa: F401

from apps.accounts.views.syllabus.editor import build_syllabus_editor_section
from apps.syllabus.tests.editor_dom import PANEL_TEMPLATES, shipped_js_path

pytestmark = pytest.mark.django_db
HERE = Path(__file__).resolve().parent
EDITOR_JS = shipped_js_path().parent / "syllabus_editor.js"


@pytest.fixture()
def report(editable):
    request = RequestFactory().get("/profile/", {"section": "syllabus-editor"})
    request.user = editable["teacher"]
    se = build_syllabus_editor_section(
        request, organization=editable["org"], version=editable["version"]
    )["syllabus_editor_section"]
    html = "".join(render_to_string(n, {"se": se}) for n in PANEL_TEMPLATES)
    hf = HERE / "r.html"; of = HERE / "r_out.json"
    hf.write_text(html, encoding="utf-8")
    proc = subprocess.run(
        ["node", str(HERE / "regress.js"), str(hf), str(shipped_js_path()), str(EDITOR_JS), str(of)],
        capture_output=True, text=True, cwd=str(HERE))
    assert proc.returncode == 0, proc.stderr
    data = json.loads(of.read_text(encoding="utf-8"))
    print("\n" + json.dumps(data, ensure_ascii=False, indent=1)[:2500])
    return data


def test_no_form_so_enter_cannot_submit(report):
    assert report["formCount"] == 0


def test_add_outcome_clone_is_empty_not_a_duplicate(report):
    assert report["cloneTag"] == "textarea"
    assert report["outcomesAfter"] == report["outcomesBefore"] + 1
    assert report["cloneValue"] == "", "🔴 klon köhnə mətni daşıyır (defaultValue tələsi)"
    assert report["cloneCollected"][-1] == "", "🔴 toplayıcı klonu dublikat kimi göndərir"
    assert report["cloneCollected"][0] != "", "birinci nəticə itdi"


def test_tn_tags_are_renumbered_after_add(report):
    assert report["tags"] == [f"TN{i}" for i in range(1, len(report["tags"]) + 1)]


def test_textarea_input_still_routes_to_its_section(report):
    assert report["sectionOfTextarea"] == "out"


def test_clear_button_empties_the_textarea(report):
    assert report["slotTitleBefore"], "yuva mətni yox idi"
    assert report["slotTitleAfter"] == ""


def test_autosave_fired(report):
    assert report["autosavePayloads"] >= 1


def test_add_outcome_is_impossible_when_the_list_is_empty(report):
    """⚠️ `addOutcome` NÜMUNƏ sətri klonlayır — sətir yoxdursa heç nə etmir."""
    assert report["emptyPanelSampleFound"] is False, (
        "boş panel nümunə sətri render edir (yaxşı olardı)"
    )
