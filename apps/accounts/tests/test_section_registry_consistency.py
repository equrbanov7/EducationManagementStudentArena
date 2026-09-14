"""Şablonun AJAX bölmə siyahısı ilə backend qeydiyyatı UYĞUN olmalıdır.

2026-08-27 QA süpürgəsi belə bir sinif xəta tapdı: ``profile.html``-in
``data-ajax-sections`` atributunda ``unit-exams`` və ``superadmin-org-inspector``
VAR idi, ``sections_api.SECTION_PARTIALS``-da isə YOX.  Nəticədə dekan menyuda
«Bölmə imtahanları»nı görürdü, klikləyəndə ön tərəf fraqment sorğusu atırdı və
``_ensure_section_allowed`` 403 qaytarırdı.

Tələ məhz ona görə uzun müddət gizli qaldı ki, **tam səhifə yolu**
(``/accounts/profile/?section=unit-exams``) işləyirdi — yalnız AJAX yolu sınırdı.

Bu modul iki istiqamətdə uyğunluğu kilidləyir ki, siyahılar bir daha ayrılmasın.
"""

from __future__ import annotations

import re
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

from apps.accounts.views.profile.sections_api import AJAX_SAFE_SECTIONS, SECTION_PARTIALS

_PROFILE_TEMPLATE = Path(settings.BASE_DIR) / "apps/accounts/templates/accounts/profile.html"
_AJAX_ATTR = re.compile(r'data-ajax-sections="([^"]+)"')


def _template_ajax_sections() -> set[str]:
    match = _AJAX_ATTR.search(_PROFILE_TEMPLATE.read_text(encoding="utf-8"))
    assert match is not None, "profile.html-də `data-ajax-sections` atributu tapılmadı"
    return {name.strip() for name in match.group(1).split(",") if name.strip()}


class SectionRegistryConsistencyTest(SimpleTestCase):
    def test_every_ajax_section_has_a_registered_partial(self):
        """Şablon AJAX ilə yükləyəcəyini deyirsə, backend onu tanımalıdır."""
        missing = sorted(_template_ajax_sections() - set(SECTION_PARTIALS))
        self.assertEqual(
            missing,
            [],
            "Bu bölmələr `data-ajax-sections`-dadır, amma `SECTION_PARTIALS`-da yoxdur — "
            "menyuda görünəcək, klikləndikdə isə 403 verəcək: " + ", ".join(missing),
        )

    def test_every_ajax_section_is_marked_ajax_safe(self):
        """Fraqment endpoint-i `AJAX_SAFE_SECTIONS`-ı ayrıca yoxlayır."""
        missing = sorted(_template_ajax_sections() - set(AJAX_SAFE_SECTIONS))
        self.assertEqual(
            missing,
            [],
            "Bu bölmələr `data-ajax-sections`-dadır, amma `AJAX_SAFE_SECTIONS`-da yoxdur "
            "(yəni fraqment endpoint-i onları rədd edəcək): " + ", ".join(missing),
        )

    def test_ajax_safe_sections_are_a_subset_of_registered_partials(self):
        """`AJAX_SAFE_SECTIONS`-da şablonu olmayan ad qalmasın."""
        orphan = sorted(set(AJAX_SAFE_SECTIONS) - set(SECTION_PARTIALS))
        self.assertEqual(
            orphan,
            [],
            "AJAX-safe elan olunub, amma partial şablonu qeydiyyatda yoxdur: " + ", ".join(orphan),
        )

    def test_registered_partial_templates_exist_on_disk(self):
        """Qeydiyyatdakı hər şablon yolu HƏQİQƏTƏN mövcud olsun."""
        template_dirs = [Path(settings.BASE_DIR) / "apps/accounts/templates"]
        template_dirs += [Path(directory) for directory in settings.TEMPLATES[0].get("DIRS", [])]
        missing = []
        for section, template_name in sorted(SECTION_PARTIALS.items()):
            if not any((directory / template_name).is_file() for directory in template_dirs):
                missing.append(f"{section} → {template_name}")
        self.assertEqual(missing, [], "Qeydiyyatda olan, amma diskdə tapılmayan şablonlar: " + ", ".join(missing))

    def test_every_ajax_safe_section_is_listed_in_template(self):
        """Əks istiqamət (frontend auditi 2026-09-13, F14): server ⊆ şablon.

        `rim-center` `AJAX_SAFE_SECTIONS`-da idi, amma `data-ajax-sections`-da YOX —
        nəticədə həmin bölmə həmişə tam səhifə yüklənirdi (SPA keçidi itirdi) və
        heç bir test bunu görmürdü, çünki yalnız şablon ⊆ server yoxlanılırdı.
        Qəsdən tam səhifə qalan bölmə `data-force-navigation` ilə işarələnir və
        `AJAX_SAFE_SECTIONS`-dan çıxarılmalıdır — siyahılar EYNİ olmalıdır.
        """
        missing = sorted(set(AJAX_SAFE_SECTIONS) - _template_ajax_sections())
        self.assertEqual(
            missing,
            [],
            "Bu bölmələr `AJAX_SAFE_SECTIONS`-dadır, amma `profile.html` `data-ajax-sections`-da yoxdur — "
            "klient onları həmişə tam səhifə yükləyəcək: " + ", ".join(missing),
        )


# ---------------------------------------------------------------------------
# 2026-09-14 (W3 `w3sweep` brauzer süpürgəsi): bölmənin İÇİNDƏKİ fraqment
# naviqasiyası (`data-ems-filters` + `data-section`, `data-profile-ajax-form`,
# `data-profile-ajax-link`) `EMSProfileLoadSection`/`tryAjaxLoadSection`-a gedir;
# bölmə `AJAX_SAFE_SECTIONS`-da deyilsə yükləyici `false` qaytarır və çağıranlar
# nəticəni yoxlamadığı üçün klik SƏSSİZ udulurdu. Loader-ə tam-səhifə fallback
# əlavə edildi, amma dizayn niyyəti «panel yerində yenilənsin»dir — ona görə
# belə şablonu olan bölmə AJAX-safe siyahısında OLMALIDIR.
# ---------------------------------------------------------------------------

_TEMPLATE_DIRS: list[Path] = [Path(settings.BASE_DIR) / "apps/accounts/templates"]
_TEMPLATE_DIRS += [Path(directory) for directory in settings.TEMPLATES[0].get("DIRS", [])]
_TEMPLATE_DIRS += sorted(Path(settings.BASE_DIR).glob("apps/*/templates"))

_INCLUDE_RE = re.compile(r"{%\s*include\s+\"([^\"]+)\"")
_BLOCK_COMMENT_RE = re.compile(r"{%\s*comment\s*%}.*?{%\s*endcomment\s*%}", re.S)
_LINE_COMMENT_RE = re.compile(r"{#.*?#}", re.S)
_FRAGMENT_NAV_MARKERS = (
    "data-ems-filters",
    "data-profile-ajax-form",
    "data-profile-ajax-link",
    "data-section-fragment",
)


def _find_template(name: str) -> Path | None:
    for directory in _TEMPLATE_DIRS:
        candidate = directory / name
        if candidate.is_file():
            return candidate
    return None


def _strip_template_comments(text: str) -> str:
    return _LINE_COMMENT_RE.sub("", _BLOCK_COMMENT_RE.sub("", text))


def _collect_template_tree(name: str, seen: dict[Path, str]) -> None:
    """Şablonu və (rekursiv) statik `{% include "…" %}`-lərini toplayır."""
    path = _find_template(name)
    if path is None or path in seen:
        return
    text = _strip_template_comments(path.read_text(encoding="utf-8"))
    seen[path] = text
    for match in _INCLUDE_RE.finditer(text):
        _collect_template_tree(match.group(1), seen)


def _fragment_nav_markers_in_section(template_name: str) -> list[str]:
    tree: dict[Path, str] = {}
    _collect_template_tree(template_name, tree)
    base = Path(settings.BASE_DIR)
    hits: list[str] = []
    for path, text in tree.items():
        for marker in _FRAGMENT_NAV_MARKERS:
            if marker in text:
                hits.append(f"{path.relative_to(base).as_posix()} → {marker}")
    return sorted(hits)


class SectionFragmentNavigationRequiresAjaxSafeTest(SimpleTestCase):
    def test_sections_with_in_panel_fragment_navigation_are_ajax_safe(self):
        """Fraqment naviqasiyası olan bölmə `AJAX_SAFE_SECTIONS`-da olmalıdır."""
        offenders: list[str] = []
        for section, template_name in sorted(SECTION_PARTIALS.items()):
            if section in AJAX_SAFE_SECTIONS:
                continue
            hits = _fragment_nav_markers_in_section(template_name)
            if hits:
                offenders.append(f"{section}: " + "; ".join(hits))
        self.assertEqual(
            offenders,
            [],
            "Bu bölmələr panel içində fraqment naviqasiyası işlədir, amma AJAX-safe deyil — "
            "ya `AJAX_SAFE_SECTIONS` + `data-ajax-sections`-a əlavə edin (skript "
            "`[data-profile-section-panel]` içində, `defer`, EMSReady), ya da linkləri "
            "tam səhifə edin:\n" + "\n".join(offenders),
        )

    def test_scanner_sees_the_three_full_page_exam_sections(self):
        """Süpürgənin hədəf üçlüyü (`journal-close`, `kollokvium-windows`,
        `exam-center-stats`) hələ də tam-səhifə bölmədir və şablon ağacı oxunur —
        skaner boş qayıdıb «hər şey qaydasındadır» deməsin."""
        for section in ("journal-close", "kollokvium-windows", "exam-center-stats"):
            with self.subTest(section=section):
                self.assertIn(section, SECTION_PARTIALS)
                tree: dict[Path, str] = {}
                _collect_template_tree(SECTION_PARTIALS[section], tree)
                self.assertGreaterEqual(len(tree), 1, section)

    def test_scanner_detects_marker_in_included_partial(self):
        """Markerlər daxil edilən partial-larda da tapılır (rekursiya işləyir)."""
        hits = _fragment_nav_markers_in_section(SECTION_PARTIALS["pending-answers"])
        self.assertTrue(
            any("data-ems-filters" in hit for hit in hits),
            "`_pending_answers_content.html`-dəki `data-ems-filters` tapılmalı idi: %r" % (hits,),
        )
