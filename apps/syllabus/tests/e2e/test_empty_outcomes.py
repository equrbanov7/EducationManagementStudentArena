"""🔴 Nəticəsi OLMAYAN sillabus: «Təlim nəticəsi əlavə et» düyməsi ÖLÜDÜR.

Mənbədə 8,247 başlığın 2,157-sində (26.2 %) heç bir təlim nəticəsi sətri
yoxdur → `out.outcomes = []`.  Şablon `{% for %}` ilə render edir və `{% empty %}`
budağı YOXDUR, `addOutcome` isə MÖVCUD sətri klonlayır — klonlanacaq sətir
olmayanda funksiya səssizcə qayıdır.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from django.contrib.auth import get_user_model
from django.template.loader import render_to_string
from django.test import RequestFactory
from django.utils import timezone

import pytest

from apps.accounts.views.syllabus.editor import build_syllabus_editor_section
from apps.syllabus import services
from apps.syllabus.models import ChangeKind
from apps.syllabus.tests.editor_dom import PANEL_TEMPLATES, shipped_js_path
from apps.syllabus.tests.factories import PLAN_HOURS, activate_member, make_academic_stack, make_offering, make_org

User = get_user_model()
pytestmark = pytest.mark.django_db
HERE = Path(__file__).resolve().parent
EDITOR_JS = shipped_js_path().parent / "syllabus_editor.js"


@pytest.fixture()
def no_outcomes(db):
    org = make_org("no-out-org")
    teacher = User.objects.create_user("no_out_teacher", "no@x.test", "pw")
    stack = make_academic_stack(org, code="NOO101")
    activate_member(org, teacher, "teacher",
                    permissions=["syllabus.view", "syllabus.edit", "syllabus.submit", "grade.input"])
    make_offering(org, stack, teacher)
    actor = services.resolve_actor(teacher, org)
    syllabus, _ = services.import_migrated_version(
        organization=org, subject=stack["subject"], approved_at=timezone.now(),
        author=teacher, chair_unit=stack["chair"], plan_hours=dict(PLAN_HOURS),
        # canlı mənbədəki 2,157 başlığın forması
        section_data={"out": {"outcomes": []}, "week": {"rows": []}},
    )
    version = services.create_next_version(syllabus=syllabus, actor=actor, kind=ChangeKind.MINOR.value)
    request = RequestFactory().get("/profile/", {"section": "syllabus-editor"})
    request.user = teacher
    se = build_syllabus_editor_section(request, organization=org, version=version)["syllabus_editor_section"]
    return se


def test_add_outcome_button_does_nothing_when_there_are_no_outcomes(no_outcomes):
    html = "".join(render_to_string(n, {"se": no_outcomes}) for n in PANEL_TEMPLATES)
    hf = HERE / "noout.html"
    of = HERE / "noout_out.json"
    hf.write_text(html, encoding="utf-8")
    proc = subprocess.run(
        ["node", str(HERE / "regress.js"), str(hf), str(shipped_js_path()), str(EDITOR_JS), str(of)],
        capture_output=True, text=True, cwd=str(HERE))
    assert proc.returncode == 0, proc.stderr
    r = json.loads(of.read_text(encoding="utf-8"))
    print("\nnəticə sətri əvvəl:", r["outcomesBefore"], "· «əlavə et»-dən sonra:", r["outcomesAfter"])
    print("autosave göndərişi:", r["autosavePayloads"])
    assert r["outcomesBefore"] == 0
    assert r["outcomesAfter"] > 0, (
        "🔴 «Təlim nəticəsi əlavə et» HEÇ NƏ ETMİR — nəticəsi olmayan 2,157 "
        "köçürülmüş sillabus (və hər YENİ qaralama) `out` bölməsini heç vaxt "
        "tamamlaya bilmir, yəni təsdiqə GÖNDƏRİLƏ BİLMİR."
    )
