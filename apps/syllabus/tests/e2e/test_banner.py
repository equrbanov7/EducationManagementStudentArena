"""BANNER: müəllimin «boşaldın» göstərişi İCRA EDİLƏ BİLİRMİ? — ÖLÇÜ."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from django.template.loader import render_to_string
from django.test import RequestFactory

import pytest
from test_real_js_roundtrip import editable  # noqa: F401

from apps.accounts.views.syllabus.editor import build_syllabus_editor_section
from apps.syllabus import services
from apps.syllabus.services.drafts import section_data_map
from apps.syllabus.tests.editor_dom import PANEL_TEMPLATES, shipped_js_path

pytestmark = pytest.mark.django_db
HERE = Path(__file__).resolve().parent


def se_of(editable, version):  # noqa: F811
    request = RequestFactory().get("/profile/", {"section": "syllabus-editor"})
    request.user = editable["teacher"]
    return build_syllabus_editor_section(
        request, organization=editable["org"], version=version
    )["syllabus_editor_section"]


def edit_and_collect(se, edits, tag):
    html = "".join(render_to_string(n, {"se": se}) for n in PANEL_TEMPLATES)
    hf = HERE / f"b_{tag}.html"
    ef = HERE / f"b_{tag}_edits.json"
    of = HERE / f"b_{tag}_out.json"
    hf.write_text(html, encoding="utf-8")
    ef.write_text(json.dumps(edits), encoding="utf-8")
    proc = subprocess.run(
        ["node", str(HERE / "collect_edit.js"), str(hf), str(shipped_js_path()), str(of), str(ef)],
        capture_output=True, text=True, cwd=str(HERE))
    assert proc.returncode == 0, proc.stderr
    return json.loads(of.read_text(encoding="utf-8"))


def test_banner_shrinks_when_the_teacher_does_what_it_says(editable):  # noqa: F811
    version = editable["version"]
    se = se_of(editable, version)
    n0_week, n0_extra = len(se["week_rows"]), se["week_extra_count"]
    n0_slots, n0_sw_extra = len(se["selfwork"]["slots"]), se["selfwork"]["extra_count"]
    print(f"\nƏVVƏL: week sətir={n0_week} (banner artıq={n0_extra}) · "
          f"selfwork yuva={n0_slots} (banner artıq={n0_sw_extra})")

    # Müəllim banner-in dediyini edir: plandan ARTIQ 7 sətri boşaldır.
    result = edit_and_collect(se, {"blankWeekRows": list(range(17, 24)), "blankSelfSlots": [2]}, "pass1")
    print("edit log:", result["log"])
    for sid in ("week", "self"):
        services.save_section(version=version, section_id=sid, data=result["data"][sid],
                              actor=editable["actor"])

    se2 = se_of(editable, version)
    n1_week, n1_extra = len(se2["week_rows"]), se2["week_extra_count"]
    n1_slots, n1_sw_extra = len(se2["selfwork"]["slots"]), se2["selfwork"]["extra_count"]
    print(f"SONRA: week sətir={n1_week} (banner artıq={n1_extra}) · "
          f"selfwork yuva={n1_slots} (banner artıq={n1_sw_extra})")
    print("saxlanılan week.rows sayı:", len(section_data_map(version)["week"]["rows"]))
    print("saxlanılan self.topics sayı:", len(section_data_map(version)["self"]["topics"]))

    assert n1_extra == 0, f"BANNER ƏBƏDİDİR: week artıq {n0_extra} → {n1_extra}"
    assert n1_week == 16, f"cədvəl 16-ya qayıtmadı: {n1_week}"
    assert n1_sw_extra == 0, f"BANNER ƏBƏDİDİR: selfwork artıq {n0_sw_extra} → {n1_sw_extra}"


def test_a_blank_row_in_the_middle_keeps_its_week_number(editable):  # noqa: F811
    """Ortadakı boş sətir YERİNDƏ qalmalıdır — 6-cı həftə 5-ə sürüşməməlidir."""
    version = editable["version"]
    se = se_of(editable, version)
    before6 = se["week_rows"][5]["topic"]
    before7 = se["week_rows"][6]["topic"]
    assert before6 and before7

    result = edit_and_collect(se, {"blankWeekRows": [6]}, "mid")
    services.save_section(version=version, section_id="week", data=result["data"]["week"],
                          actor=editable["actor"])
    se2 = se_of(editable, version)
    print(f"\n6-cı sətir: {se2['week_rows'][5]['topic']!r} (əvvəl {before6!r})")
    print(f"7-ci sətir: {se2['week_rows'][6]['topic']!r} (əvvəl {before7!r})")
    assert se2["week_rows"][5]["topic"] == "", "boş sətir siyahıdan düşdü"
    assert se2["week_rows"][6]["topic"] == before7, "🔴 NÖMRƏLƏMƏ SÜRÜŞDÜ"
    assert len(se2["week_rows"]) == len(se["week_rows"]), "orta boşluq cədvəli qısaltdı"


def test_a_graded_slot_never_leaves_the_tail(editable):  # noqa: F811
    """`graded_count: 3` daşıyan yuva boşaldılsa da quyruqdan DÜŞMÜR."""
    version = editable["version"]
    data = section_data_map(version)["self"]
    data["topics"] = [{"title": "birinci"}, {"title": "", "graded": True, "graded_count": 3}]
    services.save_section(version=version, section_id="self", data=data, actor=editable["actor"])
    se = se_of(editable, version)
    print("\nyuva sayı (qiymətli boş yuva ilə):", len(se["selfwork"]["slots"]))
    assert len(se["selfwork"]["slots"]) == 2, "qiymətlənmiş yuva quyruqdan düşdü — qiymətlər itər"


def test_selfwork_banner_clears_once_the_structure_is_picked(editable):  # noqa: F811
    """Variant seçilməyəndə banner «əvvəlcə struktur seç» deyir — İCRA EDİLİRMİ?"""
    version = editable["version"]
    se = se_of(editable, version)
    print(f"\nvariantsız: yuva={len(se['selfwork']['slots'])} artıq={se['selfwork']['extra_count']}")

    data = section_data_map(version)["self"]
    data["option"] = "2x5"  # müəllim strukturu seçir (2 tapşırıq), 2 mövzu var
    services.save_section(version=version, section_id="self", data=data, actor=editable["actor"])
    se2 = se_of(editable, version)
    print(f"2x5 seçildi: yuva={len(se2['selfwork']['slots'])} artıq={se2['selfwork']['extra_count']}")
    assert se2["selfwork"]["extra_count"] == 0, "struktur seçildi, banner hələ qalır"

    # 1x10 seçilsə 1 yuva planlanır, 2 mövzu var → 1 artıq; onu boşaltmaq banneri bağlamalıdır
    data = section_data_map(version)["self"]
    data["option"] = "1x10"
    services.save_section(version=version, section_id="self", data=data, actor=editable["actor"])
    se3 = se_of(editable, version)
    print(f"1x10 seçildi: yuva={len(se3['selfwork']['slots'])} artıq={se3['selfwork']['extra_count']}")
    assert se3["selfwork"]["extra_count"] == 1

    result = edit_and_collect(se3, {"blankSelfSlots": [2]}, "sw")
    services.save_section(version=version, section_id="self", data=result["data"]["self"],
                          actor=editable["actor"])
    se4 = se_of(editable, version)
    print(f"artıq yuva boşaldıldı: yuva={len(se4['selfwork']['slots'])} artıq={se4['selfwork']['extra_count']}")
    assert se4["selfwork"]["extra_count"] == 0, "🔴 selfwork banneri ƏBƏDİDİR"
