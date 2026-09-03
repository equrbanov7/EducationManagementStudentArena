"""QAPI: «+ Təlim nəticəsi əlavə et» düyməsinin ÖLÜ olduğu hal.

Nə idi
======
``addOutcome`` (göndərilən ``syllabus_editor.js``) sətri MÖVCUD sətri
klonlayaraq əlavə edirdi, şablonda (``_editor_basics.html``) isə ``{% empty %}``
budağı YOXDUR.  ``out.outcomes == []`` olanda 0 sətir render olunur → klon
mənbəyi tapılmır → funksiya səssizcə qayıdır → **düymə heç nə etmir**.

Miqyas (köçürmə mənbəyində ölçülüb): 8,247 başlığın 2,157-si (26.2%) məhz bu
formadadır, üstəlik HƏR yeni qaralama da (``blank_section_data`` →
``outcomes: []``).  ``out`` qayda bölməsi olduğuna görə (``MIN_OUTCOMES = 3``)
tamamlanma 100%-ə çatmır, yəni həmin sillabuslar təsdiqə GÖNDƏRİLƏ BİLMİRDİ.

Düzəliş: klon mənbəyi yoxdursa sətir ``EMSSyllabusFields.makeOutcomeRow`` ilə
SIFIRDAN qurulur.

Bu faylın qapıları
==================
Testlər node/jsdom TƏLƏB ETMİR (CI-da yoxdur) — iki müstəqil qat yoxlanılır:

1. **Render qatı** — nəticəsiz sillabusda panel həqiqətən 0 sətir verir, amma
   düymə və JS-in yeganə MƏTN MƏNBƏYİ (``data-t-placeholder``) yerindədir.
2. **Mətn-müqavilə qatı** — göndərilən JS-də klon-yoxdursa-qayıt budağı geri
   qayıtmır və qurucu şablon sətrinin BÜTÜN çəngəllərini yaradır.

Brauzerdə uçdan-uca icra (jsdom) qəsdən repodan kənardadır; sübutu və
təkrar-icra resepti ``docs/frontend/SILLABUS_REDAKTOR_QALAN_IS.md``-dədir.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.utils import timezone

import pytest

from apps.syllabus import services
from apps.syllabus.constants import MIN_OUTCOMES, SectionKey
from apps.syllabus.models import ChangeKind
from apps.syllabus.tests.editor_dom import render_editor_dom, shipped_js_path
from apps.syllabus.tests.factories import (
    PLAN_HOURS,
    activate_member,
    make_academic_stack,
    make_offering,
    make_org,
)

User = get_user_model()
pytestmark = pytest.mark.django_db

PERMS = ["syllabus.view", "syllabus.edit", "syllabus.submit", "grade.input"]

#: Şablonun (`_editor_basics.html`) bir nəticə sətrində daşıdığı çəngəllər.
#: Qurucu bunların HAMISINI verməlidir, əks halda əlavə edilən sətir
#: toplayıcıya (`collectOut`), etiketləməyə (`retagOutcomes`) və ya silmə
#: düyməsinə görünməz olur.
ROW_HOOKS = ("data-syl-outcome", "data-syl-outcome-tag", "data-outcome", "data-syl-outcome-remove")


def _editor_js_source() -> str:
    return (shipped_js_path().parent / "syllabus_editor.js").read_text(encoding="utf-8")


def _fields_js_source() -> str:
    return shipped_js_path().read_text(encoding="utf-8")


def _function_body(source: str, name: str) -> str:
    """``function <name>(`` başlığından mötərizə balansı ilə gövdəni kəsir."""
    start = source.index(f"function {name}(")
    open_brace = source.index("{", start)
    depth = 0
    for index in range(open_brace, len(source)):
        char = source[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return source[open_brace : index + 1]
    raise AssertionError(f"{name} gövdəsi bağlanmadı")


def _make_version(*, outcomes):
    org = make_org("add-outcome-org")
    teacher = User.objects.create_user("add_outcome_teacher", "addout@x.test", "pw")
    stack = make_academic_stack(org, code="AOC101")
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
        section_data={SectionKey.OUT.value: {"outcomes": list(outcomes)}},
    )
    version = services.create_next_version(syllabus=syllabus, actor=actor, kind=ChangeKind.MINOR.value)
    root, _se = render_editor_dom(user=teacher, organization=org, version=version)
    return root


# ── 1. Render qatı ────────────────────────────────────────────────────────
def test_empty_outcomes_panel_has_no_clone_source_but_keeps_the_button(db):
    """Klon mənbəyi YOXDUR — məhz bu, ölü düymənin ilkin şərti idi."""
    root = _make_version(outcomes=[])
    assert root.xpath("//*[@data-syl-outcome]") == []
    assert root.xpath("//*[@data-syl-outcome-add]"), "«əlavə et» düyməsi render olunmur"


def test_empty_outcomes_box_still_carries_the_placeholder_text(db):
    """Qurucu MƏTN YAZMIR — yer tutucunu yalnız bu atributdan ala bilər.

    Atribut boşalsa əlavə edilən sətir dörd dildə də yer tutucusuz qalar.
    """
    root = _make_version(outcomes=[])
    box = root.xpath("//*[@data-syl-outcomes]")[0]
    assert (box.get("data-t-placeholder") or "").strip()
    assert (box.get("data-t-label") or "").strip()
    assert (box.get("data-t-remove") or "").strip()


def test_rendered_row_hooks_match_the_javascript_constructor(db):
    """Şablon sətri ilə JS qurucusu EYNİ çəngəlləri daşıyır."""
    root = _make_version(outcomes=["A" * 20, "B" * 20, "C" * 20])
    rows = root.xpath("//*[@data-syl-outcome]")
    assert len(rows) == MIN_OUTCOMES
    rendered = rows[0]
    for hook in ROW_HOOKS:
        assert rendered.xpath(f".//*[@{hook}]") or rendered.get(hook) is not None, hook

    builder = _function_body(_fields_js_source(), "makeOutcomeRow")
    for hook in ROW_HOOKS:
        assert hook in builder, f"qurucu `{hook}` çəngəlini vermir"
    # Sətir sonu daşıya bilən sahə — `<input>` OLMAZ (bax test_editor_shipped_js).
    assert 'createElement("textarea")' in builder
    assert 'createElement("input")' not in builder
    assert 'getAttribute("data-t-placeholder")' in builder


# ── 2. Mətn-müqavilə qatı ─────────────────────────────────────────────────
def test_add_outcome_no_longer_bails_out_when_there_is_no_sample_row(db):
    """Klon-yoxdursa-qayıt budağı geri qayıtmamalıdır."""
    body = _function_body(_editor_js_source(), "addOutcome")
    assert "!sample" not in body, (
        "🔴 `addOutcome` yenidən klon mənbəyi olmayanda qayıdır — nəticəsiz "
        "2,157 köçürülmüş sillabusda və HƏR yeni qaralamada düymə ölü olur."
    )
    assert "makeOutcomeRow" in body, "klon mənbəyi olmayanda ehtiyat qurucu çağırılmır"


def test_field_module_exports_the_row_constructor(db):
    """Qurucu görüntü modulundadır və redaktora AÇILIR."""
    source = _fields_js_source()
    assert "function makeOutcomeRow(" in source
    assert "makeOutcomeRow: makeOutcomeRow," in source
