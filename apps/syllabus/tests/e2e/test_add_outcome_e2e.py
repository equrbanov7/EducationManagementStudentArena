"""UÇDAN-UCA: «+ Təlim nəticəsi əlavə et» → 3 nəticə → 100% → təsdiqə göndər.

Sürücü GÖNDƏRİLƏN JS-dir (jsdom), serverin RENDER ETDİYİ panellər üzərində;
autosave gövdəsi isə HƏQİQİ HTTP uclarına göndərilir
(`accounts:syllabus_section_save`, `accounts:syllabus_action`).
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from django.contrib.auth import get_user_model
from django.template.loader import render_to_string
from django.test import Client, RequestFactory
from django.urls import reverse
from django.utils import timezone

import pytest

from apps.accounts.views.syllabus.editor import build_syllabus_editor_section
from apps.syllabus import services
from apps.syllabus.constants import (
    LESSON_HOUR_KINDS,
    MIN_FILLED_WEEKS,
    SELFWORK_OPTIONS,
    WEEK_ROWS,
    SectionKey,
)
from apps.syllabus.models import ChangeKind, SyllabusVersion
from apps.syllabus.tests.editor_dom import PANEL_TEMPLATES, shipped_js_path
from apps.syllabus.tests.factories import (
    PLAN_HOURS,
    activate_member,
    make_academic_stack,
    make_offering,
    make_org,
)

User = get_user_model()
pytestmark = pytest.mark.django_db
HERE = Path(__file__).resolve().parent
EDITOR_JS = shipped_js_path().parent / "syllabus_editor.js"
PERMS = ["syllabus.view", "syllabus.edit", "syllabus.submit", "grade.input"]

OUTCOME_TEXTS = [
    "Alqoritmin mürəkkəbliyini O notasiyası ilə qiymətləndirir",
    "Verilənlər strukturunu məsələyə uyğun seçir və əsaslandırır",
    "Test yazaraq həllin düzgünlüyünü sübut edir",
]


def _panels_html(user, org, version, step="out"):
    request = RequestFactory().get("/profile/", {"section": "syllabus-editor", "step": step})
    request.user = user
    se = build_syllabus_editor_section(request, organization=org, version=version)["syllabus_editor_section"]
    assert se["view_state"] == "normal", se["view_state"]
    return "".join(render_to_string(name, {"se": se}) for name in PANEL_TEMPLATES)


def _drive(html, texts, stem):
    hf, tf, of = HERE / f"{stem}.html", HERE / f"{stem}_texts.json", HERE / f"{stem}_out.json"
    hf.write_text(html, encoding="utf-8")
    tf.write_text(json.dumps(texts, ensure_ascii=False), encoding="utf-8")
    proc = subprocess.run(
        ["node", str(HERE / "add_outcome_e2e.js"), str(hf), str(shipped_js_path()),
         str(EDITOR_JS), str(tf), str(of)],
        capture_output=True, text=True, cwd=str(HERE),
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(of.read_text(encoding="utf-8"))


def _save(client, version, section_id, data):
    row = version.sections.get(section_id=section_id)
    return client.post(
        reverse("accounts:syllabus_section_save", args=[version.pk]),
        data=json.dumps({"section": section_id, "data": data, "revision": row.revision}),
        content_type="application/json",
    )


def _rest_of_sections(plan):
    base = {k: plan.get(k, 0) // MIN_FILLED_WEEKS for k in LESSON_HOUR_KINDS}
    rest = {k: plan.get(k, 0) - base[k] * MIN_FILLED_WEEKS for k in LESSON_HOUR_KINDS}
    rows = []
    for i in range(WEEK_ROWS):
        if i >= MIN_FILLED_WEEKS:
            rows.append({"topic": "", **{k: 0 for k in LESSON_HOUR_KINDS}, "outcome": ""})
            continue
        hours = {k: base[k] + (rest[k] if i == 0 else 0) for k in LESSON_HOUR_KINDS}
        rows.append({"topic": f"{i + 1}-ci həftənin mövzusu", **hours, "outcome": f"TN{(i % 3) + 1}"})
    option = sorted(SELFWORK_OPTIONS)[0]
    return {
        "info": {"teacher": "Müəllim Adı", "office_hours": "Bazar ertəsi 14:00-16:00", "prerequisites": ""},
        "desc": {"description": "F" * 130, "goal": "M" * 70},
        "week": {"rows": rows},
        "method": {"methods": ["lecture", "discussion"], "note": ""},
        "self": {
            "option": option,
            "topics": [{"title": f"Sərbəst iş mövzusu {n + 1}"} for n in range(SELFWORK_OPTIONS[option]["count"])],
            "archived": [],
        },
        "lit": {"primary": ["Birinci mənbə kitabı", "İkinci mənbə kitabı"],
                "additional": ["Əlavə mənbə kitabı"]},
    }


@pytest.fixture()
def fresh(db):
    org = make_org("e2e-addout")
    teacher = User.objects.create_user("e2e_addout_teacher", "e2e@x.test", "pw12345!")
    stack = make_academic_stack(org, code="AOE101")
    activate_member(org, teacher, "teacher", permissions=PERMS)
    offering = make_offering(org, stack, teacher)
    client = Client()
    client.force_login(teacher)
    session = client.session
    session["active_organization_id"] = str(org.pk)
    session.save()
    return {"org": org, "teacher": teacher, "stack": stack, "offering": offering, "client": client}


def test_new_draft_button_fills_the_out_section(fresh):
    """YENİ qaralama (`blank_section_data` → `outcomes: []`) — düymə işləyir."""
    org, teacher, client = fresh["org"], fresh["teacher"], fresh["client"]
    resp = client.post(
        reverse("accounts:syllabus_action"),
        data=json.dumps({"action": "create", "offering": str(fresh["offering"].pk)}),
        content_type="application/json",
    )
    assert resp.status_code == 200, resp.content
    version = SyllabusVersion.objects.get(pk=resp.json()["version"])
    print("\n[YENİ QARALAMA]", version.label, "· plan_hours =", version.plan_hours)
    assert services.section_data_map(version)[SectionKey.OUT.value] == {"outcomes": []}

    report = _drive(_panels_html(teacher, org, version), OUTCOME_TEXTS, "fresh")
    print("  nəticə sətri — əvvəl:", report["before"], "· sonra:", report["after"], "· etiketlər:", report["tags"])
    print("  autosave gövdəsi:", json.dumps(report["lastOutPayload"]["data"], ensure_ascii=False))
    assert report["before"] == 0 and report["addButtonFound"] is True
    assert report["after"] == 3
    assert all(step["tag"] == "textarea" for step in report["steps"]), report["steps"]
    assert report["tags"] == ["TN1", "TN2", "TN3"]
    assert report["collected"]["outcomes"] == OUTCOME_TEXTS
    assert all(report["placeholders"]), "yer tutucu mətn itdi (dörd dil)"

    resp = _save(client, version, "out", report["lastOutPayload"]["data"])
    assert resp.status_code == 200, resp.content
    body = resp.json()
    print("  server: out bölməsi =", body["completion"]["sections"]["out"])
    assert services.section_data_map(version)[SectionKey.OUT.value]["outcomes"] == OUTCOME_TEXTS

    for section_id, data in _rest_of_sections(version.plan_hours or {}).items():
        resp = _save(client, version, section_id, data)
        assert resp.status_code == 200, (section_id, resp.content)
        body = resp.json()
    print("  tamamlanma:", body["completion"]["percent"], "%", "·", body["completion"]["sections"])
    print("  qalan çatışmazlıq:", body["completion"]["issues"])
    assert body["completion"]["sections"]["out"] is True, "«out» hələ də bağlıdır"

    # ⚠️ AYRI, MÜSTƏQİL BLOKER (bu tapşırığın hədəfi DEYİL, sənədləşdirilib):
    # `_do_create` versiyanı `plan_hours={}` ilə açır → `week` qaydası saat
    # cəmini 0 gözləyir, amma 14 mövzunun hər biri saat tələb edir → ziddiyyət.
    assert body["completion"]["sections"]["week"] is False
    assert [i["code"] for i in body["completion"]["issues"]] == ["week.topic_without_hours"]
    assert body["completion"]["percent"] == 88


def test_migrated_empty_outcomes_reaches_100_and_submits(fresh):
    """Mövcud 2,157 köçürülmüş sillabus: düymə → 3 nəticə → 100% → GÖNDƏRİLDİ."""
    org, teacher, client, stack = fresh["org"], fresh["teacher"], fresh["client"], fresh["stack"]
    actor = services.resolve_actor(teacher, org)
    syllabus, _ = services.import_migrated_version(
        organization=org, subject=stack["subject"], approved_at=timezone.now(),
        author=teacher, chair_unit=stack["chair"], plan_hours=dict(PLAN_HOURS),
        section_data={"out": {"outcomes": []}, "week": {"rows": []}},
    )
    version = services.create_next_version(syllabus=syllabus, actor=actor, kind=ChangeKind.MINOR.value)
    print("\n[KÖÇÜRÜLMÜŞ]", version.label, "· plan_hours =", version.plan_hours)
    assert services.section_data_map(version)[SectionKey.OUT.value] == {"outcomes": []}

    report = _drive(_panels_html(teacher, org, version), OUTCOME_TEXTS, "migrated")
    print("  nəticə sətri — əvvəl:", report["before"], "· sonra:", report["after"], "· etiketlər:", report["tags"])
    assert report["before"] == 0
    assert report["after"] == 3
    assert report["collected"]["outcomes"] == OUTCOME_TEXTS

    resp = _save(client, version, "out", report["lastOutPayload"]["data"])
    assert resp.status_code == 200, resp.content
    for section_id, data in _rest_of_sections(version.plan_hours or {}).items():
        resp = _save(client, version, section_id, data)
        assert resp.status_code == 200, (section_id, resp.content)
        body = resp.json()
    print("  tamamlanma:", body["completion"]["percent"], "% ·", body["completion"]["sections"])
    assert body["completion"]["percent"] == 100, body["completion"]["issues"]

    resp = client.post(
        reverse("accounts:syllabus_action"),
        data=json.dumps({"action": "submit", "version": str(version.pk)}),
        content_type="application/json",
    )
    assert resp.status_code == 200, resp.content
    version.refresh_from_db()
    print("  STATUS:", version.status)
    assert version.status == "submitted"
