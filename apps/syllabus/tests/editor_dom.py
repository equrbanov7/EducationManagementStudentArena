"""Redaktorun HƏQİQİ DOM-undan autosave gövdəsini quran test köməkçisi.

Niyə belə
=========
Bu qovluqdakı «məzmun itmir» qapı testləri süni TAM yük göndərsə, heç nə
qorumazdı: itki məhz ondan yaranırdı ki, **brauzerdəki toplayıcı** mənbədən DAR
gövdə göndərirdi.  Ona görə burada:

1. ``accounts.views.syllabus.editor.build_syllabus_editor_section`` ilə redaktorun
   ƏSL context-i qurulur;
2. redaktorun ƏSL şablon parçaları (``_editor_plan.html``, ``_editor_final.html``)
   render olunur;
3. alınan HTML ``lxml`` ilə oxunub ``syllabus_editor_fields.js``-in seçiciləri
   ilə BİR-BİR eyni qaydada toplanır.

Yəni şablondan bir çip/sətir/yuva düşsə və ya toplayıcının qaydası pozulsa, test
çökür — köçürülmüş məzmunun qorunması «kod oxunuşu» yox, İCRA OLUNAN qapıdır.

⚠️ Brauzer davranışı da təqlid olunur: ``<select>``-də heç bir ``selected``
yoxdursa brauzer BİRİNCİ variantı göstərir və autosave onu göndərir.  Məhz bu
səbəbdən mənbədəki 6 saatlıq sətir «0» kimi geri yazıla bilərdi.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from django.apps import apps as django_apps
from django.template.loader import render_to_string
from django.test import RequestFactory

import lxml.html

from apps.accounts.views.syllabus.editor import build_syllabus_editor_section

#: `syllabus_editor_fields.js` — `HOUR_KINDS`.
HOUR_KINDS = ("lecture", "seminar", "lab")

#: GÖNDƏRİLƏN toplayıcı faylı.  Bu modul onun güzgüsüdür; sürüşməni
#: `test_editor_shipped_js` barmaq izi ilə tutur.
SHIPPED_JS_RELATIVE = "static/accounts/js/profile/syllabus_editor_fields.js"
CONTRACT_BEGIN = "@collector-contract:begin"
CONTRACT_END = "@collector-contract:end"

#: HTML-in «value sanitization algorithm»-i `<input>` dəyərindən məhz bu iki
#: simvolu SİLİR (boşluqla əvəz etmir).  Brauzer probe-u ilə ölçülüb:
#: `<input value="a\nb">.value === "ab"`, `<textarea>` və `data-*` atributu isə
#: `\n`-i (və abzas boş sətrini) SAXLAYIR.
INPUT_STRIPPED_CHARS = ("\r", "\n")


def shipped_js_path() -> Path:
    return Path(django_apps.get_app_config("accounts").path) / SHIPPED_JS_RELATIVE


def shipped_collector_source() -> str:
    """Göndərilən JS-in TOPLAYICI blokunu (sentinel-lər arası) qaytarır."""
    text = shipped_js_path().read_text(encoding="utf-8")
    start = text.index(CONTRACT_BEGIN)
    end = text.index(CONTRACT_END)
    if end <= start:
        raise AssertionError("collector-contract sentinel-ləri tərs sıradadır")
    return text[start:end]


def shipped_collector_digest() -> str:
    return hashlib.sha256(shipped_collector_source().encode("utf-8")).hexdigest()


#: Redaktorun bölmə panellərini daşıyan şablon parçaları.
PANEL_TEMPLATES = (
    "accounts/profile/sections/syllabus/_editor_basics.html",
    "accounts/profile/sections/syllabus/_editor_plan.html",
    "accounts/profile/sections/syllabus/_editor_final.html",
)


def _has_class(node, name: str) -> bool:
    return name in (node.get("class") or "").split()


def _value(node) -> str:
    """`node.value` — BRAUZERİN davranışı ilə eyni (atribut dəyəri ilə YOX).

    ``<select>``: ``selected`` işarəli variant, yoxdursa BİRİNCİ variant (brauzer
    məhz belə edir).

    ``<input>``: ``value`` atributu **value sanitization algorithm-dən keçir** —
    CR və LF simvolları SİLİNİR (boşluqla əvəz olunmur).  Bu addımın modelə
    salınmaması güzgünün ikinci qapısızlığı idi: `collect_out` sadəcə əlavə
    edilsəydi, test xam atributu oxuyub YAŞIL qalar, göndərilən JS isə
    köçürülmüş 4,790 sillabusun sətir strukturunu itirərdi.

    ``<textarea>``: mətn olduğu kimi (yalnız açılış teqindən dərhal sonrakı
    TƏK sətir sonu — HTML parserinin qaydası — atılır).
    """
    if node is None:
        return ""
    tag = node.tag
    if tag == "select":
        options = node.xpath(".//option")
        if not options:
            return ""
        chosen = [option for option in options if option.get("selected") is not None]
        return (chosen[0] if chosen else options[0]).get("value") or ""
    if tag == "textarea":
        text = node.text or ""
        return text[1:] if text.startswith("\n") else text
    raw = node.get("value") or ""
    if tag == "input":
        for char in INPUT_STRIPPED_CHARS:
            raw = raw.replace(char, "")
    return raw


def _prose_lines(value) -> list:
    """`toProseLines` — abzas fasiləsi qorunur (boş sətir MÖVQE daşıyır)."""
    kept: list = []
    for raw in str(value or "").split("\n"):
        line = raw.strip()
        if line:
            kept.append(line)
        elif kept and kept[-1]:
            kept.append("")
    while kept and not kept[-1]:
        kept.pop()
    return kept


def _plain_fields(box) -> dict:
    """`plainFields` — `data-field` daşıyan hər input → {ad: dəyər}."""
    if box is None:
        return {}
    return {node.get("data-field"): _value(node) for node in box.xpath(".//*[@data-field]")}


def _assign(target: dict, fields: dict, keys) -> dict:
    """`assign` — açar HƏQİQƏTƏN varsa köçürülür (yoxdursa UYDURULMUR)."""
    for key in keys:
        if key in fields:
            target[key] = fields[key]
    return target


def _int(value) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return 0


def _carried(node) -> dict:
    """`carried()` — sətrin/yuvanın `data-extra` JSON-u (DOM-un idarə etmədiyi açarlar)."""
    raw = node.get("data-extra") or ""
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except ValueError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def render_editor_dom(*, user, organization, version, step: str = "info"):
    """Redaktorun panel HTML-ini render edib parse olunmuş kök qaytarır."""
    request = RequestFactory().get("/profile/", {"section": "syllabus-editor", "step": step})
    request.user = user
    context = build_syllabus_editor_section(request, organization=organization, version=version)
    se = context["syllabus_editor_section"]
    assert se["view_state"] == "normal", f"redaktor redaktə rejimində deyil: {se['view_state']}"
    html = "".join(render_to_string(name, {"se": se}) for name in PANEL_TEMPLATES)
    return lxml.html.fromstring(f"<div>{html}</div>"), se


def panel(root, section_id: str):
    """`panel(el, id)` — `[data-syl-panel='<id>']`."""
    found = root.xpath(f"//*[@data-syl-panel='{section_id}']")
    return found[0] if found else None


# ── Bölmə toplayıcıları — `syllabus_editor_fields.js` ilə SƏTİR-SƏTİR eyni ──


def collect_method(root) -> dict:
    """`collectMethod` — yalnız `.is-on` çipləri + `data-field` sahələri."""
    box = panel(root, "method")
    methods = []
    if box is not None:
        for node in box.xpath(".//*[@data-syl-method]"):
            if _has_class(node, "is-on"):
                methods.append(node.get("data-syl-method"))
    data = {"methods": methods}
    if box is not None:
        for node in box.xpath(".//*[@data-field='note']"):
            data["note"] = _value(node)
    return data


def collect_week(root) -> dict:
    """`collectWeek` — sətir `data-extra`-dan qurulur, DOM açarları üstələyir."""
    box = panel(root, "week")
    rows = []
    if box is None:
        return {"rows": rows}
    for tr in box.xpath(".//*[@data-syl-week-row]"):
        row = _carried(tr)
        topic = tr.xpath(".//*[@data-week='topic']")
        outcome = tr.xpath(".//*[@data-week='outcome']")
        row["topic"] = _value(topic[0] if topic else None).strip()
        row["outcome"] = _value(outcome[0] if outcome else None).strip()
        for kind in HOUR_KINDS:
            cell = tr.xpath(f".//*[@data-week='{kind}']")
            row[kind] = _int(_value(cell[0] if cell else None))
        rows.append(row)
    return {"rows": rows}


def collect_self(root) -> dict:
    """`collectSelf` — yuvalar + arxiv sətirləri, hər ikisi DOM-dan."""
    box = panel(root, "self")
    topics, archived = [], []
    option = ""
    if box is not None:
        active = [n for n in box.xpath(".//*[@data-syl-selfwork]") if _has_class(n, "is-on")]
        option = active[0].get("data-syl-selfwork") if active else ""
        for slot in box.xpath(".//*[@data-syl-slot]"):
            topic = _carried(slot)
            title = slot.xpath(".//*[@data-selfwork-title]")
            topic["title"] = _value(title[0] if title else None).strip()
            topic["graded"] = slot.get("data-graded") == "1"
            topic["graded_count"] = _int(slot.get("data-graded-count"))
            topics.append(topic)
        for row in box.xpath(".//*[@data-syl-archived-row]"):
            entry = _carried(row)
            entry["title"] = row.get("data-title") or ""
            entry["note"] = row.get("data-note") or ""
            archived.append(entry)
    return {"option": option, "topics": topics, "archived": archived}


def collect_info(root) -> dict:
    """`collectInfo` — yalnız panelin ÖZ `data-field` input-ları."""
    return _plain_fields(panel(root, "info"))


def collect_desc(root) -> dict:
    """`collectDesc` — iki `<textarea>`."""
    data = _plain_fields(panel(root, "desc"))
    return {"description": data.get("description") or "", "goal": data.get("goal") or ""}


def collect_out(root) -> dict:
    """`collectOut` — `[data-outcome]` elementlərinin dəyəri.

    ⚠️ Bu toplayıcı güzgüdə ÜMUMİYYƏTLƏ YOX idi, ona görə redaktorun ən böyük
    itki yolu (4,790 sillabus) heç vaxt sınaq səthinə düşməmişdi.
    """
    box = panel(root, "out")
    outcomes = []
    if box is not None:
        for node in box.xpath(".//*[@data-outcome]"):
            outcomes.append(_value(node).strip())
    return {"outcomes": outcomes}


def collect_assess(root) -> dict:
    """`collectAssess` — bal yalnız sürüşdürücüyə TOXUNULUBSA, `note` input VARSA.

    ⚠️ Toxunma bayrağı (``data-touched="1"``) redaktorun ``input``/``change``
    hadisəsində qoyulur.  Render olunmuş DOM-da o YOXDUR, yəni bu güzgü
    «müəllim toxunmadı» halını modelləyir: bal açarları göndərilmir və serverin
    bölgüsü toxunulmaz qalır.  Əvvəllər açarlar həmişə gedirdi və köçürmənin
    «bölgü yoxdur» yazısı (``midterm: 0, project: 0``) müəllimin ilk
    saxlamasında ``project: 30``-a çevrilirdi.
    """
    box = panel(root, "assess")
    data: dict = {}
    if box is None:
        return data
    sliders = box.xpath(".//*[@data-syl-midterm]")
    if sliders and sliders[0].get("data-touched") == "1":
        midterm = _int(sliders[0].get("value"))
        data["midterm"] = midterm
        data["project"] = max(0, _int(sliders[0].get("data-flex")) - midterm)
    return _assign(data, _plain_fields(box), ["note"])


def collect_lit(root) -> dict:
    """`collectLit` — `data-field-lines` sahələri, ABZAS FASİLƏSİ QORUNUR."""
    box = panel(root, "lit")
    out = {"primary": [], "additional": []}
    if box is None:
        return out
    for node in box.xpath(".//*[@data-field-lines]"):
        out[node.get("data-field-lines")] = _prose_lines(_value(node))
    return out


#: Bölmə → toplayıcı.  JS-dəki `COLLECTORS` xəritəsi ilə AÇAR-AÇAR eyni
#: olmalıdır; bərabərliyi `test_editor_shipped_js` yoxlayır.  Əvvəllər burada
#: cəmi üç giriş vardı (`method`/`week`/`self`), yəni `out`, `desc`, `lit`,
#: `info`, `assess` üçün heç bir icra olunan qapı YOX idi.
COLLECTORS = {
    "info": collect_info,
    "desc": collect_desc,
    "out": collect_out,
    "week": collect_week,
    "method": collect_method,
    "assess": collect_assess,
    "self": collect_self,
    "lit": collect_lit,
}


def collect(root, section_id: str) -> dict:
    return COLLECTORS[section_id](root)


__all__ = [
    "COLLECTORS",
    "CONTRACT_BEGIN",
    "CONTRACT_END",
    "HOUR_KINDS",
    "INPUT_STRIPPED_CHARS",
    "collect",
    "collect_assess",
    "collect_desc",
    "collect_info",
    "collect_lit",
    "collect_method",
    "collect_out",
    "collect_self",
    "collect_week",
    "panel",
    "render_editor_dom",
    "shipped_collector_digest",
    "shipped_collector_source",
    "shipped_js_path",
]
