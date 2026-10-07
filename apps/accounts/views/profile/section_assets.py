"""Kabinet bölmə asset-ləri — YALNIZ render olunan bölmənin CSS/JS-i (perf 2026-10-07).

PROBLEM
-------
Bölmə CSS-i (`profile/_section_assets.html`) və JS-i (`profile.html`) əvvəl
`allowed_sections` ilə şərtlənirdi: SPA istənilən icazəli bölməyə keçə bilər deyə
İLK açılışda hamısı yüklənirdi. Tələbə kabinetinin «Ana səhifə»si 115 asset
(1.6 MB xam / 409 KB gzip) çəkirdi — açılmamış jurnal, cədvəl, apellyasiya,
müraciət üslubları, Chart.js (200 KB) və ölü statistika paketi daxil.

HƏLL
----
* Bölmə qrupları `asset_sections` ilə şərtlənir = render olunan bölmə + onun
  `SECTION_ASSET_BORROWS`-dakı İCAZƏLİ qonşuları (bölmə başqa bölmənin faylındakı
  qaydanı/skripti işlədirsə). Borc yalnız icazə varsa tətbiq olunur — yəni əvvəl
  həmin istifadəçidə yüklənən fayl indi də (lazım olan bölmədə) yüklənir.
* Tam səhifə: `{% profile_section_css %}` / `{% profile_section_js "pre"|"post" %}`
  (``templatetags/profile_shell.py``) şablonları köhnə yerlərində render edir.
* AJAX: `profile_section_fragment` cavabında `assets` (``section_assets_payload``) —
  `section_assets.js` çatışmayan CSS-i kaskad sırası ilə `<head>`-ə, JS-i ardıcıl
  və bir dəfə qoşur, sonra panel swap olunur (köhnə AJAX semantikası: skript panel
  DOM-a düşməzdən əvvəl icra olunur, swap-dan sonra `profile:section:loaded`).
* Qabıq qrupları (`allowed_sections`) dəyişməyib: qabıqdakı modallar, superadmin
  üslubları, `ns.register` / tək `DOMContentLoaded` skriptləri.

Siyahılar yalnız `asset_sections`/`allowed_sections`-dan asılıdır — proses daxilində
keşlənir (DEBUG-da yox: şablon dəyişikliyi dərhal görünsün).
"""

from __future__ import annotations

import re
from html.parser import HTMLParser
from typing import Iterable

from django.conf import settings
from django.template.loader import get_template, render_to_string
from django.templatetags.static import static

CSS_TEMPLATE = "accounts/profile/_section_assets.html"
JS_TEMPLATE = "accounts/profile/_section_scripts.html"
JS_PHASES = ("pre", "post")
UNKNOWN_CSS_ORDER = 100_000

_TOF_CORE = ("chair-profile", "org-structure-tree", "programs-registry", "subject-catalog")
_TOF_PLAN = ("curriculum-editor", "groups-registry", "semester-opening")

#: Bölmə → asset-lərini də yükləyəcəyi (icazəli) bölmələr. Mənbə: 2026-10-07 selektor /
#: hook auditi — bölmənin şablon ağacı (və JS-i) başqa bölmənin faylındakı sinfi və ya
#: `data-*` hook-u işlədir. Yeni çarpaz asılılıq yarananda buraya yazın.
SECTION_ASSET_BORROWS: dict[str, tuple[str, ...]] = {
    # registrar «embed» qaydaları (`.profile-section--registrar-embed …`) transcript.css-dədir;
    # `.journal-page` əsası journal.css-də; `.sgx-*` (cədvəl modalı/çipləri) schedule.css-də.
    "academic-calendar": ("my-transcript", "my-journal", "journal-close", "analytics"),
    "analytics": ("my-transcript",),
    "my-journal": ("my-transcript", "my-schedule", "schedule-manage"),
    "journal-close": ("my-schedule", "schedule-manage"),
    # cədvəl ↔ jurnal: `.sjx-*`, `.corr-hist-*`, `.sylv-*`; redaktor hook-ları (`data-sedit-*`).
    "my-schedule": ("my-transcript", "my-journal", "journal-close", "schedule-manage"),
    "schedule-manage": ("my-journal", "journal-close"),
    # tədris şöbəsi: `.tof` / `.tof-pane` / `.tof-split` teaching_office.css-də,
    # `.tof-chip*` / `.tof-pane__hint` / `.ems-*.is-warning` teaching_office_plan.css-də.
    "curriculum-editor": _TOF_CORE,
    "groups-registry": _TOF_CORE,
    "semester-opening": _TOF_CORE,
    "chair-profile": _TOF_PLAN,
    "org-structure-tree": _TOF_PLAN,
    "exam-score-entry": _TOF_PLAN,
    "my-workload": _TOF_CORE,
    "org-faculties": _TOF_CORE,
    "org-kafedras": _TOF_CORE,
    "teaching-handover": _TOF_CORE,
    "workload-center": _TOF_CORE,
    "workload-distribution": _TOF_CORE,
    "workload-overview": _TOF_CORE,
    "workload-visa": _TOF_CORE,
    "workload-approval": _TOF_CORE + _TOF_PLAN,
    # apellyasiya idarəsi apellyasiya paketinin üslub/skriptini işlədir (şərtdə yox idi).
    "manage-appeals": ("my-appeals", "appeal-stats"),
    # kataloqlar ↔ reyestr: `.psm*` (tələbə çekməcəsi), hesab dayandırma sahələri.
    "people-teachers": ("people-students", "student-admission", "student-registry"),
    "people-students": ("student-admission", "student-registry"),
    "student-registry": ("people-students", "people-teachers"),
    # sillabus ailəsi ortaq primitivləri və modal hook-larını bölüşür.
    "syllabus-editor": ("syllabus-list", "syllabus-review"),
    "syllabus-list": ("syllabus-review",),
    "syllabus-review": ("syllabus-list",),
    # rol dialoqları (`data-roles-root`) icazə redaktorunda da var.
    "permission-editor": ("manage-roles", "role-assignment"),
}

_STATIC_CSS_IN_SOURCE = re.compile(r"""{%\s*static\s+['"]([^'"]+\.css)['"]\s*%}""")
_CACHE_LIMIT = 2048  # (bölmə dəsti × icazə dəsti) kombinasiyaları — rol sayı ilə məhduddur
_cache: dict[tuple, object] = {}


def asset_sections_for(section: str | None, allowed_sections: Iterable[str] | None) -> frozenset[str]:
    """Render olunan bölmə + onun icazəli borc qonşuları."""
    allowed = set(allowed_sections or ())
    keys = {section} if section else set()
    keys.update(other for other in SECTION_ASSET_BORROWS.get(section or "", ()) if other in allowed)
    return frozenset(keys)


class _AssetCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.css: list[str] = []
        self.js: list[str] = []

    def handle_starttag(self, tag, attrs):
        attr = dict(attrs)
        if tag == "link" and (attr.get("rel") or "").lower() == "stylesheet" and attr.get("href"):
            self.css.append(attr["href"])
        elif tag == "script" and attr.get("src"):
            self.js.append(attr["src"])


def _unique(items: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(items))


def _memo(key: tuple, build):
    if settings.DEBUG:
        return build()
    if key not in _cache:
        if len(_cache) >= _CACHE_LIMIT:
            _cache.clear()
        _cache[key] = build()
    return _cache[key]


def _collect(template_name: str, context: dict) -> _AssetCollector:
    collector = _AssetCollector()
    collector.feed(render_to_string(template_name, context))
    collector.close()
    return collector


def _css_source_order() -> dict[str, int]:
    """`static()` URL → şablondakı ilk mövqe (kaskad sırası)."""

    def build():
        source = get_template(CSS_TEMPLATE).template.source
        order: dict[str, int] = {}
        for index, path in enumerate(_STATIC_CSS_IN_SOURCE.findall(source)):
            order.setdefault(static(path), index)
        return order

    return _memo(("css-order",), build)


def section_css(asset_sections: frozenset[str], allowed_sections: Iterable[str] | None) -> list[dict]:
    """Bölmə + qabıq CSS-i kaskad sırası ilə: ``[{"href": …, "order": int}]``."""
    allowed = frozenset(allowed_sections or ())

    def build():
        hrefs = _collect(CSS_TEMPLATE, {"asset_sections": asset_sections, "allowed_sections": allowed}).css
        order = _css_source_order()
        return [{"href": href, "order": order.get(href.split("?", 1)[0], UNKNOWN_CSS_ORDER)} for href in _unique(hrefs)]

    return _memo(("css", asset_sections, allowed), build)


def section_js(asset_sections: frozenset[str], allowed_sections: Iterable[str] | None, phase: str) -> list[str]:
    """`_section_scripts.html`-in `phase` hissəsinin `src`-ləri (sıra saxlanılır)."""
    if phase not in JS_PHASES:
        raise ValueError(f"unknown asset phase: {phase!r}")
    allowed = frozenset(allowed_sections or ())

    def build():
        context = {"asset_sections": asset_sections, "allowed_sections": allowed, "asset_phase": phase}
        return _unique(_collect(JS_TEMPLATE, context).js)

    return _memo(("js", phase, asset_sections, allowed), build)


def section_assets_payload(section: str, allowed_sections: Iterable[str] | None) -> dict:
    """AJAX fraqmenti üçün: bölmənin (və qabığın) CSS/JS siyahısı — klient çatışmayanı yükləyir."""
    asset_sections = asset_sections_for(section, allowed_sections)
    js = _unique([src for phase in JS_PHASES for src in section_js(asset_sections, allowed_sections, phase)])
    return {"css": section_css(asset_sections, allowed_sections), "js": js}


__all__ = [
    "SECTION_ASSET_BORROWS",
    "asset_sections_for",
    "section_assets_payload",
    "section_css",
    "section_js",
]
