"""QAPI: GÖNDƏRİLƏN JS toplayıcısı — emulyator deyil.

Niyə bu fayl var
================
``apps/syllabus/tests/editor_dom.py`` ``syllabus_editor_fields.js``-in Python-da
YENİDƏN YAZILMIŞ nüsxəsidir.  İkisini sinxron saxlayan heç nə yox idi, nəticə
ölçülüb: göndərilən JS-də hər iki ``carried()`` çağırışı orijinal səhvə
qaytarıldıqda **7 testin 7-si də YAŞIL qaldı** — yəni köçürülmüş məzmunu
qoruyan düzəlişlərin ƏSL İCRA YERİ qapısız idi.

Qapısızlıq İKİ müstəqil qatdan ibarət idi:

1. **Güzgünün yarısı ümumiyyətlə yox idi.**  ``COLLECTORS`` cəmi üç giriş
   daşıyırdı (``method``/``week``/``self``); ``out``, ``desc``, ``lit``,
   ``info``, ``assess`` üçün heç bir icra olunan yoxlama YOX idi.  Ən böyük
   itki yolu (``out.outcomes``, 4,790 sillabus) məhz o boşluqda yaşayırdı.
2. **Qalan yarısı brauzeri təqlid etmirdi.**  ``_value`` ``<input>`` üçün XAM
   ``value`` atributunu qaytarırdı; brauzerin CR/LF silən «value sanitization
   algorithm»-i modelə salınmamışdı.  Bu halda ``collect_out`` sadəcə əlavə
   edilsə belə test yaşıl qalar, göndərilən JS isə data itirərdi.

Bu modul hər iki qatı bağlayır:

* **Barmaq izi (drift qapısı).**  Göndərilən faylın ``@collector-contract``
  sentinel-ləri arasındakı blokun SHA-256-sı burada BƏRKİDİLİB.  Blokda bir
  bayt dəyişsə qapı çökür və commit müəllifi güzgünü də yeniləməyə məcbur olur.
  Barmaq izini «sadəcə yeniləmək» icazəlidir — şüursuz sürüşmə isə artıq
  MÜMKÜN DEYİL.
* **Mətn-müqavilə.**  Keçmişdə sübutlu şəkildə pozulan hər qayda ayrıca
  yoxlanılır (``carried()``, ``data-extra``-dan başlamaq, uydurulmayan açar,
  abzas fasiləsi), ona görə çökmə mesajı «hash dəyişdi»-dən daha dəqiqdir.
* **Render qapısı.**  Sətir sonu UDAN elementə çox sətirli dəyər verilməsi
  qadağandır: render olunan hər ``<input>`` sətir ayırıcısına qarşı yoxlanılır.
"""

from __future__ import annotations

import re

from django.contrib.auth import get_user_model
from django.utils import timezone

import pytest

from apps.syllabus import services
from apps.syllabus.constants import SectionKey
from apps.syllabus.models import ChangeKind
from apps.syllabus.tests.editor_dom import (
    COLLECTORS,
    render_editor_dom,
    shipped_collector_digest,
    shipped_collector_source,
)
from apps.syllabus.tests.factories import PLAN_HOURS, activate_member, make_academic_stack, make_offering, make_org

User = get_user_model()
pytestmark = pytest.mark.django_db

PERMS = ["syllabus.view", "syllabus.edit", "syllabus.submit", "grade.input"]

#: Göndərilən toplayıcı blokunun BƏRKİDİLMİŞ barmaq izi.
#:
#: ⚠️ Bu sabiti yeniləmək = «güzgünü (``editor_dom.py``) da nəzərdən keçirdim»
#: demək.  Yalnız həmin nəzərdən keçirmə ilə birlikdə dəyişdirin.
CONTRACT_DIGEST = "9f3dfc2e329496c143e8fc32fc8d962e18c700bda8b59e5dd9a629e90a20e725"

#: Unicode-un sətir ayırıcıları — ``str.splitlines`` onların HAMISINI bölür,
#: yəni köçürmə təmizləyicisi hamısını ``\n``-ə çevirir.  Ona görə hədəfdə
#: yoxlanılası yeganə simvol ``\n`` deyil.
LINE_SEPARATORS = "\n\r  \v\f\x85"

#: Sətir sonu daşıya bilən, ona görə ``<textarea>`` OLMALI olan sahələr.
MULTILINE_CONTROLS = ("data-outcome", "data-selfwork-title")

MIGRATED_SECTIONS = {
    SectionKey.OUT.value: {"outcomes": ["TN1. birinci\nTN2. ikinci", "üçüncü nəticə"]},
    SectionKey.SELF.value: {
        "option": "",
        "topics": [{"title": "Avropanın birləşməsi.\nİkinci mərhələ."}],
        "archived": [],
    },
    SectionKey.LIT.value: {"primary": ["1. birinci mənbə\n2. ikinci mənbə\n\nElektron:\n3. üçüncü"]},
    SectionKey.DESC.value: {"description": "Birinci abzas.\n\nİkinci abzas.", "goal": ""},
    SectionKey.METHOD.value: {"methods": ["1. mühazirə\n2. seminar"], "note": ""},
    SectionKey.ASSESS.value: {"midterm": 0, "project": 0, "note": "Qayda mətni.\nİkinci sətir."},
    SectionKey.WEEK.value: {
        # ⚠️ Mövzu QƏSDƏN tək sətirdir: köçürmə orada ``clean_text`` işlədir
        # (mənbədə 131,056 sətrin heç birində sətir sonu yoxdur), ona görə
        # ``<input>`` heç nə itirmir.  Fərziyyə deyil — aşağıdakı render qapısı
        # köhnə mövzu çox sətirli olan gün DƏRHAL çökür.
        "rows": [{"topic": "birinci mövzu", "lecture": 2, "seminar": 0, "lab": 0, "outcome": "", "practical": 2}]
    },
}


@pytest.fixture()
def migrated(db):
    org = make_org("shipped-js-org")
    teacher = User.objects.create_user("shipped_js_teacher", "shipped@x.test", "pw")
    stack = make_academic_stack(org, code="SJS101")
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
        section_data=MIGRATED_SECTIONS,
    )
    version = services.create_next_version(syllabus=syllabus, actor=actor, kind=ChangeKind.MINOR.value)
    root, se = render_editor_dom(user=teacher, organization=org, version=version)
    return {"root": root, "se": se}


# ── 1. Drift qapısı: göndərilən blokun barmaq izi ──────────────────────────
def test_shipped_collector_block_digest_is_pinned():
    """Blokda bir bayt dəyişsə bu test çökür — güzgü yenidən baxılmalıdır."""
    assert shipped_collector_digest() == CONTRACT_DIGEST, (
        "syllabus_editor_fields.js-in toplayıcı bloku dəyişdi. "
        "apps/syllabus/tests/editor_dom.py güzgüsünü də yeniləyin, sonra "
        "CONTRACT_DIGEST sabitini yeni barmaq izi ilə əvəz edin."
    )


def test_every_editor_section_has_a_mirrored_collector():
    """JS-dəki `COLLECTORS` açarları ilə güzgüdəki xəritə AÇAR-AÇAR eynidir.

    Bu, birinci qapısızlığın birbaşa qapısıdır: güzgüdə cəmi 3 giriş vardı,
    göndərilən JS-də isə 8 — fərq beş bölmənin sınaqsız qalması demək idi.
    """
    source = shipped_collector_source()
    block = re.search(r"var COLLECTORS = \{(.+?)\};", source, re.S)
    assert block, "göndərilən JS-də `COLLECTORS` xəritəsi tapılmadı"
    shipped_keys = set(re.findall(r"(\w+)\s*:\s*collect\w+", block.group(1)))
    assert shipped_keys == set(COLLECTORS), f"güzgü sürüşdü: {shipped_keys ^ set(COLLECTORS)}"


# ── 2. Mətn-müqavilə: keçmişdə POZULMUŞ hər qayda ─────────────────────────
def _body(source: str, name: str) -> str:
    """Adı verilən funksiyanın gövdəsi (növbəti `function`-a qədər)."""
    start = source.index(f"function {name}(")
    tail = source.find("\n    function ", start + 1)
    return source[start : tail if tail != -1 else len(source)]


@pytest.mark.parametrize(
    ("collector", "node"),
    [("collectWeek", "tr"), ("collectSelf", "slot"), ("collectSelf", "row")],
)
def test_row_collectors_start_from_the_carried_keys(collector, node):
    """Sətir/yuva/arxiv lüğəti SIFIRDAN qurulmur — `carried()`-dən başlayır.

    Düşmən baxışı məhz bu iki çağırışı geri qaytarıb 7/7 yaşıl aldı.
    """
    assert f"carried({node})" in _body(shipped_collector_source(), collector)


def test_literature_collector_preserves_paragraph_breaks():
    source = shipped_collector_source()
    assert "toProseLines(text(node))" in _body(source, "collectLit")
    prose = _body(source, "toProseLines")
    # Boş sətri MÖVQE kimi saxlayan budaq mütləq olmalıdır.
    assert 'kept.push("")' in prose
    assert ".filter(" not in prose, "boş sətirlər yenidən atılır"


def test_outcome_collector_reads_the_outcome_controls():
    assert '"[data-outcome]"' in _body(shipped_collector_source(), "collectOut")


def test_assess_collector_does_not_invent_the_note_key():
    """`note` üçün input YOXDURSA açar GÖNDƏRİLMİR (5,893 sillabusun mətni)."""
    body = _body(shipped_collector_source(), "collectAssess")
    assert 'assign(data, plainFields(box), ["note"])' in body
    assert 'note: ""' not in body


def test_assess_collector_writes_scores_only_after_the_slider_was_touched():
    """Bal açarları MÜƏLLİMİN ƏMƏLİ olmadan göndərilmir.

    Ölçülmüş itki yolu: köçürmə ``midterm: 0, project: 0`` (= «bölgü YOXDUR»)
    yazır; müəllim «Qiymətləndirmə» addımına keçib sürüşdürücüyə TOXUNMADAN
    «Qaralama saxla» basanda toplayıcı ``project: 30`` göndərirdi və tələbənin
    sənədinə heç kimin yazmadığı bal qaydası düşürdü.  Şərt `data-touched`
    bayrağıdır — 0 seçmək də toxunmaqdır, ona görə silmə niyyəti qorunur.
    """
    body = _body(shipped_collector_source(), "collectAssess")
    assert (
        'slider.getAttribute("data-touched") === "1"' in body
    ), "toxunma şərti itdi: bal açarları yenidən müəllim toxunmadan göndərilir"
    assert "data.project" in body and body.index("data-touched") < body.index("data.project")


# ── 3. Render qapısı: sətir sonu UDAN elementə çox sətirli dəyər YOX ───────
def test_no_single_line_control_carries_a_line_break(migrated):
    """Bütün sinfi bağlayan qapı — bu gün və gələcəkdə.

    HTML-in «value sanitization algorithm»-i ``<input>``-in dəyərindən CR/LF-i
    SİLİR.  Yəni çox sətirli dəyəri ``<input>``-ə render etmək = ilk
    avtosaxlamada sətir strukturunu itirmək.  Qapı elementə görə deyil,
    DƏYƏRƏ görə işləyir: hansı sahənin bir gün çox sətirli olacağını
    fərziyyə ilə deyil, render ilə bilirik.
    """
    offenders = [
        (node.get("data-week") or node.get("data-field") or node.get("name") or node.get("id"), node.get("value"))
        for node in migrated["root"].xpath("//input")
        if any(char in (node.get("value") or "") for char in LINE_SEPARATORS)
    ]
    assert offenders == [], f"sətir sonu udan `<input>`-lər: {offenders}"


@pytest.mark.parametrize("attribute", MULTILINE_CONTROLS)
def test_multiline_fields_render_as_textarea(migrated, attribute):
    nodes = migrated["root"].xpath(f"//*[@{attribute}]")
    assert nodes, f"[{attribute}] render olunmadı"
    assert {node.tag for node in nodes} == {"textarea"}
