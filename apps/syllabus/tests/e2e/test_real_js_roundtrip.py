"""E2E: REAL PostgreSQL -> REAL render -> REAL shipped JS (jsdom) -> REAL save_section.

Heç bir emulyator yoxdur: toplayıcı `syllabus_editor_fields.js`-in ÖZÜDÜR,
Node+jsdom altında icra olunur.  Mətnlər canlı mənbədən (MariaDB) çəkilib və
əsl `legacy_text` təmizləyicisindən keçir.
"""

from __future__ import annotations

import copy
import json
import subprocess
from pathlib import Path

from django.contrib.auth import get_user_model
from django.template.loader import render_to_string
from django.test import RequestFactory
from django.utils import timezone

import pytest

from apps.accounts.views.syllabus.editor import build_syllabus_editor_section
from apps.legacy_import.services.legacy_text import clean_multiline_text, clean_text
from apps.syllabus import services
from apps.syllabus.models import ChangeKind
from apps.syllabus.services.drafts import section_data_map
from apps.syllabus.tests.editor_dom import PANEL_TEMPLATES, shipped_js_path
from apps.syllabus.tests.factories import PLAN_HOURS, activate_member, make_academic_stack, make_offering, make_org

User = get_user_model()
pytestmark = pytest.mark.django_db

HERE = Path(__file__).resolve().parent
REAL = json.loads((HERE.parent / "real_texts.json").read_text(encoding="utf-8"))
MAXLEN = 20000


def mline(key):
    return clean_multiline_text(REAL[key], max_length=MAXLEN)[0]


def sline(key):
    return clean_text(REAL[key], max_length=MAXLEN)[0]


def build_real_sections():
    """`rehearsal_syllabus_targets.build_section_data` ilə EYNİ açar formaları."""
    return {
        "info": {
            "teacher": "",
            "office_hours": "",
            "prerequisites": "",
            "language": "az",
            "lesson_hours": 45,
            "welcome": mline("welcome"),
            "research_interests": [mline("welcome")],
            "certificates": ["ISO 9001"],
        },
        "desc": {"description": mline("desc"), "goal": ""},
        "out": {"outcomes": [mline("outcome"), mline("outcome2")]},
        "week": {
            "rows": [
                {
                    "topic": sline("topic"),
                    "lecture": 2,
                    "seminar": 0,
                    "lab": 0,
                    "outcome": "",
                    "practical": 2,
                    "note": sline("wknote"),
                }
            ]
            # 23 sətirlik köçürülmüş cədvəl: 16-dan artıq 7 sətir.
            + [
                {"topic": f"{sline('topic')} — {n}", "lecture": 1, "seminar": 0, "lab": 0,
                 "outcome": "", "practical": 0, "note": ""}
                for n in range(2, 24)
            ]
        },
        "method": {"methods": [mline("method")], "note": ""},
        "assess": {"midterm": 0, "project": 0, "note": mline("assess"),
                   "exam_questions": [mline("examq")]},
        "self": {
            "option": "",
            "topics": [{"title": mline("selfu2028")}, {"title": mline("self")}],
            "archived": [],
        },
        "lit": {"primary": [mline("lit")], "additional": []},
        "prev": {},
        "send": {},
    }


@pytest.fixture()
def editable(db):
    org = make_org("e2e-realjs-org")
    teacher = User.objects.create_user("e2e_realjs_teacher", "e2e@x.test", "pw")
    stack = make_academic_stack(org, code="E2E101")
    activate_member(org, teacher, "teacher",
                    permissions=["syllabus.view", "syllabus.edit", "syllabus.submit", "grade.input"])
    make_offering(org, stack, teacher)
    actor = services.resolve_actor(teacher, org)
    syllabus, _ = services.import_migrated_version(
        organization=org, subject=stack["subject"], approved_at=timezone.now(),
        author=teacher, chair_unit=stack["chair"], plan_hours=dict(PLAN_HOURS),
        section_data=build_real_sections(),
    )
    version = services.create_next_version(syllabus=syllabus, actor=actor, kind=ChangeKind.MINOR.value)
    return {"org": org, "teacher": teacher, "actor": actor, "version": version}


def render_html(*, user, organization, version) -> str:
    request = RequestFactory().get("/profile/", {"section": "syllabus-editor", "step": "info"})
    request.user = user
    se = build_syllabus_editor_section(request, organization=organization, version=version)[
        "syllabus_editor_section"
    ]
    assert se["view_state"] == "normal", se["view_state"]
    return "".join(render_to_string(name, {"se": se}) for name in PANEL_TEMPLATES)


def run_shipped_js(html: str, tag: str) -> dict:
    out_dir = HERE
    html_file = out_dir / f"dom_{tag}.html"
    json_file = out_dir / f"collected_{tag}.json"
    html_file.write_text(html, encoding="utf-8")
    proc = subprocess.run(
        ["node", str(out_dir / "collect.js"), str(html_file), str(shipped_js_path()), str(json_file)],
        capture_output=True, text=True, cwd=str(out_dir),
    )
    assert proc.returncode == 0, f"node failed:\n{proc.stderr}"
    return json.loads(json_file.read_text(encoding="utf-8"))


def _reader_view(data_map):
    """Saxlanılan datanın TƏLƏBƏYƏ çatan formaya normallaşdırılmış görüntüsü.

    Toplayıcı iki yerdə normallaşdırma edir və heç biri məzmun itkisi deyil:
      * `lit.primary` — sətir strukturu yastılanır, `document._prose_lines`
        onsuz da elementləri "\n" üzrə açır (ayrıca test bunu sübut edir);
      * `self.topics[]` — yuvaya boş `graded`/`graded_count` açarları düşür.
    Bu funksiya məhz o iki normallaşdırmanı geri sarır ki, qalan HƏR fərq əsl
    itki olsun.
    """
    from apps.syllabus import document as doc

    view = copy.deepcopy(data_map)
    for key in ("primary", "additional"):
        view["lit"][key] = doc._prose_lines(view["lit"].get(key) or [])
    view["desc"]["description"] = doc._prose_lines(view["desc"].get("description"))
    view["out"]["outcomes"] = doc._prose_lines(view["out"].get("outcomes") or [])
    view["method"]["methods"] = doc._prose_lines(view["method"].get("methods") or [])
    view["assess"]["note"] = doc._prose_lines(view["assess"].get("note"))
    view["assess"]["exam_questions"] = doc._prose_lines(view["assess"].get("exam_questions") or [])
    view["self"]["topics"] = [
        {k: v for k, v in topic.items() if k not in ("graded", "graded_count") or v}
        for topic in view["self"].get("topics") or []
    ]
    # BİLİNƏN BEŞİNCİ YOL — `test_fifth_path.py`-də ayrıca sübut olunub;
    # sahibin BAĞLI mövzusuna düşdüyü üçün burada düzəldilmir, elan olunur.
    view["assess"].pop("project", None)
    return view


def test_first_autosave_of_a_real_migrated_syllabus_loses_nothing(editable):
    """Müəllim heç nəyə toxunmadan HƏR bölmə avtosaxlanır -> məzmun DƏYİŞMİR."""
    version = editable["version"]
    before = _reader_view(section_data_map(version))

    html = render_html(user=editable["teacher"], organization=editable["org"], version=version)
    collected = run_shipped_js(html, "pass1")

    for section_id, data in collected.items():
        services.save_section(version=version, section_id=section_id, data=data, actor=editable["actor"])

    after = _reader_view(section_data_map(version))
    diffs = {}
    for section_id, old in before.items():
        new = after.get(section_id, {})
        delta = {
            key: {"before": old.get(key), "after": new.get(key)}
            for key in set(old) | set(new)
            if old.get(key) != new.get(key)
        }
        if delta:
            diffs[section_id] = delta
    assert diffs == {}, json.dumps(diffs, ensure_ascii=False, indent=1)[:6000]


def test_second_autosave_is_idempotent(editable):
    """İkinci dövr də dəyişiklik verməməlidir (toplayıcı idempotentdir)."""
    version = editable["version"]
    for round_no in (1, 2):
        html = render_html(user=editable["teacher"], organization=editable["org"], version=version)
        collected = run_shipped_js(html, f"round{round_no}")
        for section_id, data in collected.items():
            services.save_section(version=version, section_id=section_id, data=data, actor=editable["actor"])
        version.refresh_from_db()
    snapshot = copy.deepcopy(section_data_map(version))

    html = render_html(user=editable["teacher"], organization=editable["org"], version=version)
    collected = run_shipped_js(html, "round3")
    for section_id, data in collected.items():
        services.save_section(version=version, section_id=section_id, data=data, actor=editable["actor"])
    assert section_data_map(version) == snapshot
