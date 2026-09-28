"""Audit 2026-09-28 FQ-TEST-1: göndərilən sillabus toplayıcısı ƏSL DOM-da (jsdom).

`tests/js/collect_shipped.js` qoşqusu indiyə qədər heç bir test/CI tərəfindən
çağırılmırdı. Bu test onu işə salır: redaktorun ƏSL şablon parçaları render
olunur, `syllabus_editor_fields.js` OLDUĞU KİMİ jsdom-da icra olunur və nəticə
həm məzmun baxımından (çox sətirli dəyərlər itmir), həm də Python güzgüsü
(`apps/syllabus/tests/editor_dom.collect`) ilə müqayisə olunur — güzgü brauzer
semantikasından sürüşərsə test qırılır.

Node + `tests/js/node_modules` (``npm ci``) yoxdursa test ÖTÜRÜLÜR; CI-nin
`js-tests` job-u ``EMS_REQUIRE_JSDOM=1`` qoyur ki, orada ötürülmə xəta olsun.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

from django.contrib.auth import get_user_model
from django.template.loader import render_to_string
from django.test import RequestFactory
from django.utils import timezone

import pytest

from apps.accounts.views.syllabus.editor import build_syllabus_editor_section
from apps.syllabus import services
from apps.syllabus.constants import SectionKey
from apps.syllabus.models import ChangeKind
from apps.syllabus.tests.editor_dom import PANEL_TEMPLATES, collect, render_editor_dom, shipped_js_path
from apps.syllabus.tests.factories import PLAN_HOURS, activate_member, make_academic_stack, make_offering, make_org

User = get_user_model()
pytestmark = pytest.mark.django_db

HARNESS_DIR = Path(__file__).resolve().parent / "js"
HARNESS = HARNESS_DIR / "collect_shipped.js"
PERMS = ["syllabus.view", "syllabus.edit", "syllabus.submit", "grade.input"]

MULTILINE_OUTCOMES = [
    "TN1. alqoritmin mürəkkəbliyini O notasiyası ilə qiymətləndirir\n2. məsələyə uyğun strukturu seçir",
    "təhlilin nəticəsini yazılı şəkildə əsaslandırır",
]
MULTILINE_METHODS = [
    "1. mühazirə\n2. mövzunun müzakirəsi və diskussiya",
    "video materiallardan istifadə",
]
LITERATURE = ["1. Kormen T. Alqoritmlərə giriş\n\nElektron resurslar:\n2. Knuth D. TAOCP"]


def _require_jsdom():
    node = shutil.which("node")
    ready = node and (HARNESS_DIR / "node_modules" / "jsdom").is_dir()
    if ready:
        return node
    message = "node + tests/js/node_modules (npm ci) tələb olunur"
    if os.environ.get("EMS_REQUIRE_JSDOM") == "1":
        pytest.fail(message)
    pytest.skip(message)


def _run_harness(node, *, html: str, sections: list[str]) -> dict:
    job = json.dumps({"html": html, "jsPath": str(shipped_js_path()), "sections": sections})
    proc = subprocess.run(
        [node, str(HARNESS)], input=job, capture_output=True, text=True, cwd=str(HARNESS_DIR), check=False, timeout=60
    )
    assert proc.returncode == 0, f"jsdom qoşqusu çökdü: {proc.stderr}"
    result = json.loads(proc.stdout)
    assert result["ok"] is True
    return result


@pytest.fixture()
def draft():
    org = make_org("jsdom-org")
    teacher = User.objects.create_user("jsdom_teacher", "jsdom@x.test", "pw")
    stack = make_academic_stack(org, code="JSD101")
    activate_member(org, teacher, "teacher", permissions=PERMS)
    make_offering(org, stack, teacher)
    actor = services.resolve_actor(teacher, org)
    syllabus, _ = services.import_migrated_version(
        organization=org,
        subject=stack["subject"],
        approved_at=timezone.now(),
        author=teacher,
        chair_unit=stack["chair"],
        plan_hours=dict(PLAN_HOURS),
        section_data={
            SectionKey.OUT.value: {"outcomes": list(MULTILINE_OUTCOMES)},
            SectionKey.METHOD.value: {"methods": list(MULTILINE_METHODS), "note": "qeyd"},
            SectionKey.LIT.value: {"primary": list(LITERATURE)},
        },
    )
    version = services.create_next_version(syllabus=syllabus, actor=actor, kind=ChangeKind.MINOR.value)
    return {"org": org, "teacher": teacher, "version": version}


def _panels_html(draft) -> str:
    request = RequestFactory().get("/profile/", {"section": "syllabus-editor", "step": "info"})
    request.user = draft["teacher"]
    context = build_syllabus_editor_section(request, organization=draft["org"], version=draft["version"])
    se = context["syllabus_editor_section"]
    return "".join(render_to_string(name, {"se": se}) for name in PANEL_TEMPLATES)


SECTIONS = [
    SectionKey.INFO.value,
    SectionKey.DESC.value,
    SectionKey.OUT.value,
    SectionKey.WEEK.value,
    SectionKey.METHOD.value,
    SectionKey.SELF.value,
    SectionKey.LIT.value,
]


def test_shipped_collector_keeps_multiline_migrated_values_in_a_real_dom(draft):
    node = _require_jsdom()
    result = _run_harness(node, html=_panels_html(draft), sections=SECTIONS)
    data = result["data"]
    assert "collect" in result["api"]
    assert data["out"]["outcomes"] == MULTILINE_OUTCOMES, "çox sətirli təlim nəticəsi brauzerdə itdi"
    assert data["method"]["methods"] == MULTILINE_METHODS
    assert "" in data["lit"]["primary"], "ədəbiyyatın abzas fasiləsi brauzerdə itdi"


def test_python_mirror_matches_the_shipped_collector(draft):
    """`editor_dom.collect` (Python güzgüsü) ƏSL brauzer nəticəsi ilə eyni olmalıdır."""
    node = _require_jsdom()
    result = _run_harness(node, html=_panels_html(draft), sections=SECTIONS)
    for section_id in SECTIONS:
        root, _se = render_editor_dom(
            user=draft["teacher"], organization=draft["org"], version=draft["version"], step=section_id
        )
        assert result["data"][section_id] == collect(root, section_id), section_id
