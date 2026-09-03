"""Paylaşılan UI komponent qatı — status kataloqu, şablon tag-ləri, partial-lar.

Dizayn handoff Mərhələ 0-ın qəbul testləri:

* status kataloqu TƏK mənbədir və handoff §5-dəki enum-larla üst-üstə düşür
* `{% ems_status_badge %}` etiketi HƏMİŞƏ yazır (status yalnız rənglə verilmir)
* naməlum açar səssiz boş badge vermir
* hər partial öz kontekst müqaviləsi ilə render olunur (şablon sınmır)
* a11y: `role="dialog" aria-modal`, `aria-sort`, `th scope`, `aria-current`
* səbəb dialoqunun təsdiq düyməsi ≥20 simvola qədər söndürülüdür

QEYD (sahib qərarı 2026-09-03): komponentləri bir yerdə göstərən qalereya
MƏHSUL AĞACINDA YOXDUR — belə bir kabinet bölməsi qəsdən mövcud deyil.
Vizual yoxlama üçün ayrıca, deploy olunmayan statik səhifə saxlanılır. Ona
görə buradakı testlər partial-ları BİRBAŞA render edir.
"""

from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.template import Context, Template
from django.template.loader import render_to_string
from django.test import SimpleTestCase

from core.ui import status_catalog


class StatusCatalogTest(SimpleTestCase):
    """Kataloq — handoff §5 enum-larının hərfi qarşılığı."""

    def test_syllabus_family_has_the_seven_designed_statuses(self):
        self.assertEqual(
            status_catalog.keys("syllabus"),
            ("revision", "rejected", "draft", "submitted", "review", "approved", "archived"),
        )

    def test_syllabus_sort_order_matches_the_handoff(self):
        """revision → rejected → draft → submitted → review → approved → archived."""
        keys = ["approved", "draft", "revision", "archived", "rejected", "review", "submitted"]
        ordered = sorted(keys, key=lambda key: status_catalog.sort_key("syllabus", key))
        self.assertEqual(
            ordered,
            ["revision", "rejected", "draft", "submitted", "review", "approved", "archived"],
        )

    def test_workload_line_matches_the_designed_pill_palette(self):
        """Ekran 15: Göndərilib (mavi) · Qaytarılıb (qırmızı) · Təsdiqlənib (yaşıl)."""
        tones = {status.key: status.tone for status in status_catalog.family("workload_line")}
        self.assertEqual(tones, {"sent": "primary", "returned": "danger", "approved": "success"})

    def test_load_band_has_the_four_designed_bands(self):
        self.assertEqual(status_catalog.keys("load_band"), ("under", "normal", "over", "critical"))

    def test_every_status_uses_a_declared_tone(self):
        for name, members in status_catalog.FAMILIES.items():
            for member in members:
                self.assertIn(member.tone, status_catalog.TONES, f"{name}.{member.key}")

    def test_keys_are_unique_inside_a_family(self):
        for name, members in status_catalog.FAMILIES.items():
            keys = [member.key for member in members]
            self.assertEqual(len(keys), len(set(keys)), f"{name} ailəsində təkrar açar var")

    def test_green_text_never_uses_the_accent_only_success_token(self):
        """`--ems-success` (#10b981) mətn kimi AA-dan keçmir — badge fg olmamalıdır."""
        css = Path(settings.BASE_DIR, "static/css/ems_ui/badge.css").read_text(encoding="utf-8")
        block = css.split(".ems-badge--success {", 1)[1].split("}", 1)[0]
        self.assertIn("var(--ems-success-700)", block)
        self.assertNotIn("color: var(--ems-success)", block)

    def test_unknown_family_raises_instead_of_returning_empty(self):
        with self.assertRaises(status_catalog.UnknownStatusFamily):
            status_catalog.family("bele-bir-aile-yoxdur")

    def test_choices_shape_is_django_compatible(self):
        choices = status_catalog.choices("workload_line")
        self.assertEqual([key for key, _label in choices], ["sent", "returned", "approved"])

    def test_sorted_by_status_orders_rows(self):
        class Row:
            def __init__(self, status):
                self.status = status

        rows = [Row("approved"), Row("revision"), Row("draft")]
        self.assertEqual(
            [row.status for row in status_catalog.sorted_by_status("syllabus", rows)],
            ["revision", "draft", "approved"],
        )


class StatusBadgeTagTest(SimpleTestCase):
    """Şablon tag-i — etiket həmişə görünür, naməlum açar gizlənmir."""

    def _render(self, template: str, **context) -> str:
        return Template("{% load ems_ui %}" + template).render(Context(context))

    def test_badge_renders_label_and_tone_class(self):
        html = self._render('{% ems_status_badge "syllabus" "approved" %}')
        self.assertIn("ems-badge--success", html)
        self.assertIn("Təsdiqlənib", html)

    def test_revision_badge_is_strong_bordered(self):
        html = self._render('{% ems_status_badge "syllabus" "revision" %}')
        self.assertIn("is-strong", html)

    def test_unknown_key_falls_back_to_the_key_itself(self):
        html = self._render('{% ems_status_badge "syllabus" "quraşdırılmamış" %}')
        self.assertIn("quraşdırılmamış", html)
        self.assertIn("ems-badge--neutral", html)

    def test_none_key_renders_a_neutral_unknown_badge(self):
        html = self._render("{% ems_status_badge 'syllabus' missing %}", missing=None)
        self.assertIn("ems-badge--neutral", html)
        self.assertNotIn("None", html)

    def test_label_filter(self):
        html = self._render('{{ "returned"|ems_status_label:"workload_line" }}')
        self.assertEqual(html.strip(), "Qaytarılıb")

    def test_tone_and_class_filters(self):
        self.assertEqual(self._render('{{ "revision"|ems_status_tone:"syllabus" }}').strip(), "warning")
        self.assertIn("is-strong", self._render('{{ "revision"|ems_status_class:"syllabus" }}'))

    def test_next_step_tag(self):
        html = self._render('{% ems_next_step "syllabus" "draft" %}')
        self.assertIn("Qaralamanı tamamlayıb təsdiqə göndər", html)

    def test_status_family_tag_returns_every_member(self):
        html = self._render('{% ems_status_family "workload_visa" as fam %}{% for s in fam %}{{ s.key }},{% endfor %}')
        self.assertEqual(html.strip(), "pending,reviewed,remarked,")

    def test_pct_style_emits_a_custom_property_and_clamps(self):
        self.assertEqual(self._render("{% ems_pct_style 42 %}").strip(), "--ems-bar-pct:42%")
        self.assertEqual(self._render("{% ems_pct_style 180 %}").strip(), "--ems-bar-pct:100%")
        self.assertEqual(self._render("{% ems_pct_style -5 %}").strip(), "--ems-bar-pct:0%")
        self.assertEqual(self._render("{% ems_pct_style 'x' %}").strip(), "--ems-bar-pct:0%")


class ComponentPartialRenderTest(SimpleTestCase):
    """Hər partial öz kontekst müqaviləsi ilə render olunur + a11y şərtləri."""

    def test_content_header_omits_the_h1_for_cabinet_sections(self):
        """Qabıq bölmə adını artıq verir — partial ikinci `h1` yaratmamalıdır."""
        html = render_to_string(
            "partials/ems_ui/_content_header.html",
            {
                "header_subtitle": "Alt izahat",
                "header_crumbs": [{"label": "Kabinet", "url": "/x/"}, {"label": "Cari"}],
            },
        )
        self.assertNotIn("<h1", html)
        self.assertIn("ems-header__subtitle", html)
        self.assertIn('aria-current="page"', html)

    def test_content_header_renders_the_h1_outside_the_shell(self):
        html = render_to_string("partials/ems_ui/_content_header.html", {"header_title": "Başlıq"})
        self.assertIn('<h1 class="ems-header__title">Başlıq</h1>', html)

    def test_kpi_tile_with_a_filter_is_a_button_with_aria_pressed(self):
        html = render_to_string(
            "partials/ems_ui/_kpi_tile.html",
            {"tile": {"label": "Təsdiqlənib", "value": "15", "tone": "success", "filter": "approved", "pressed": True}},
        )
        self.assertIn('data-ems-kpi-filter="approved"', html)
        self.assertIn('aria-pressed="true"', html)
        self.assertIn("ems-kpi--success", html)

    def test_kpi_tile_progress_bar_uses_a_custom_property_not_a_hardcoded_width(self):
        html = render_to_string(
            "partials/ems_ui/_kpi_tile.html",
            {"tile": {"label": "Bölünmüş yük", "value": "87%", "has_bar": True, "pct": 87}},
        )
        self.assertIn('style="--ems-bar-pct:87%"', html)
        self.assertNotIn("width:", html)

    def test_filter_bar_declares_the_section_and_prefix_contract(self):
        html = render_to_string(
            "partials/ems_ui/_filter_bar.html",
            {
                "filter_section": "workload-center",
                "filter_prefix": "wl_",
                "filter_fields": [
                    {"name": "wl_year", "label": "Tədris ili", "kind": "select", "value": "2026/2027", "options": []},
                    {"name": "wl_q", "label": "Axtarış", "kind": "search", "value": ""},
                ],
                "filter_applied": [{"name": "wl_year", "label": "Tədris ili", "value_label": "2026 / 2027"}],
            },
        )
        self.assertIn("data-ems-filters", html)
        self.assertIn('data-section="workload-center"', html)
        self.assertIn('data-param-prefix="wl_"', html)
        self.assertIn("data-ems-filter-search", html)
        self.assertIn('data-ems-filter-remove="wl_year"', html)
        # Hər sahənin GÖRÜNƏN label-ı var (handoff §7).
        self.assertEqual(html.count('class="ems-field__label"'), 2)

    def test_data_table_marks_scope_and_aria_sort(self):
        html = render_to_string(
            "partials/ems_ui/_data_table.html",
            {
                "table_state": "ready",
                "table_zebra": True,
                "table_columns": [
                    {"key": "subject", "label": "Fənn"},
                    {
                        "key": "pct",
                        "label": "Tamamlanma",
                        "sortable": True,
                        "sort_url": "?s=pct",
                        "sort_dir": "descending",
                    },
                    {"key": "status", "label": "Vəziyyət"},
                ],
                "table_rows": [
                    {
                        "row_head": "İNF-201",
                        "cells": [
                            {"text": "82%", "num": True},
                            {"badge_family": "syllabus", "badge_key": "review"},
                        ],
                    }
                ],
            },
        )
        self.assertIn('<th scope="col"', html)
        self.assertIn('<th scope="row"', html)
        self.assertIn('aria-sort="descending"', html)
        self.assertIn("ems-table--zebra", html)
        self.assertIn("Baxışdadır", html)  # badge kataloqdan gəldi

    def test_data_table_empty_and_error_states(self):
        empty = render_to_string(
            "partials/ems_ui/_data_table.html",
            {"table_state": "empty", "state_title": "Sətir yoxdur", "state_action_label": "Sıfırla"},
        )
        self.assertIn("ems-state", empty)
        self.assertNotIn("<table", empty)
        error = render_to_string(
            "partials/ems_ui/_data_table.html",
            {"table_state": "error", "state_kind": "error", "state_title": "Yüklənmədi"},
        )
        self.assertIn("ems-state--error", error)

    def test_tree_is_an_aria_tree_with_expandable_nodes(self):
        html = render_to_string(
            "partials/ems_ui/_tree.html",
            {
                "tree_label": "Struktur",
                "tree_nodes": [
                    {
                        "id": "1",
                        "label": "Universitet",
                        "expanded": True,
                        "children": [{"id": "2", "label": "Fakültə", "flagged": True}],
                    }
                ],
            },
        )
        self.assertIn('role="tree"', html)
        self.assertIn('role="treeitem"', html)
        self.assertIn('role="group"', html)
        self.assertIn('aria-expanded="true"', html)
        self.assertIn("ems-tree__row--flagged", html)

    def test_dialog_and_drawer_are_modal_and_labelled(self):
        for template, ctx, marker in (
            (
                "partials/ems_ui/_dialog.html",
                {"dialog_id": "d1", "dialog_title": "Başlıq", "dialog_body_include": "partials/ems_ui/_banner.html"},
                "d1-title",
            ),
            (
                "partials/ems_ui/_drawer.html",
                {"drawer_id": "w1", "drawer_title": "Başlıq", "drawer_body_include": "partials/ems_ui/_banner.html"},
                "w1-title",
            ),
        ):
            html = render_to_string(template, ctx)
            self.assertIn('role="dialog"', html)
            self.assertIn('aria-modal="true"', html)
            self.assertIn(f'aria-labelledby="{marker}"', html)
            self.assertIn("data-ems-overlay-close", html)
            self.assertIn("hidden", html)

    def test_reason_dialog_starts_disabled_and_enforces_twenty_characters(self):
        html = render_to_string(
            "partials/ems_ui/_reason_dialog.html",
            {"reason_id": "r1", "reason_title": "İrad bildir"},
        )
        self.assertIn('data-ems-min-length="20"', html)
        self.assertIn('minlength="20"', html)
        self.assertIn("data-ems-reason-submit disabled", html)
        self.assertIn('aria-describedby="r1-hint"', html)
        self.assertIn("data-hint-invalid=", html)

    def test_tabs_and_stepper_and_stepnav_carry_aria_state(self):
        tabs = render_to_string(
            "partials/ems_ui/_tabs.html",
            {"tabs_label": "Görünüşlər", "tabs": [{"key": "q", "label": "Növbə", "count": 3, "current": True}]},
        )
        self.assertIn('aria-current="page"', tabs)
        self.assertIn('data-ems-tab="q"', tabs)

        steps = render_to_string(
            "partials/ems_ui/_stepper.html",
            {
                "steps_label": "Mərhələ",
                "steps": [{"label": "Bir", "state": "done"}, {"label": "İki", "state": "error"}],
            },
        )
        self.assertIn("ems-step--done", steps)
        self.assertIn("ems-step--error", steps)

        nav = render_to_string(
            "partials/ems_ui/_step_nav.html",
            {"step_nav_label": "Bölmələr", "step_items": [{"key": "out", "label": "Nəticələr", "current": True}]},
        )
        self.assertIn('aria-current="step"', nav)

    def test_timeline_dot_tone_follows_the_status_vocabulary(self):
        html = render_to_string(
            "partials/ems_ui/_timeline.html",
            {
                "timeline_label": "Tarixçə",
                "timeline": [{"who": "A", "when": "bu gün", "what": "etdi", "reason": "səbəb", "tone": "warning"}],
            },
        )
        self.assertIn("ems-tl__dot--warning", html)
        self.assertIn("ems-tl__reason", html)

    def test_field_message_is_announced(self):
        html = render_to_string(
            "partials/ems_ui/_field_message.html",
            {"msg_id": "m1", "msg_kind": "error", "msg_text": "Kredit artıqdır"},
        )
        self.assertIn('role="alert"', html)
        self.assertIn('id="m1"', html)
        self.assertIn("ems-msg--error", html)

    def test_searchable_select_ties_the_hint_to_the_field(self):
        """Mövcud partial-a əlavə edilən a11y bağı (handoff §7)."""
        html = render_to_string(
            "partials/_bootstrap_select_field.html",
            {
                "field_id": "kafedra",
                "field_name": "kafedra",
                "field_label": "Kafedra",
                "field_placeholder": "Seçin",
                "field_options": [],
                "field_hint": "Yazmağa başlayın",
            },
        )
        self.assertIn('aria-describedby="kafedra-hint"', html)
        self.assertIn('id="kafedra-hint"', html)


class ComponentAssetHygieneTest(SimpleTestCase):
    """CLAUDE.md: inline/internal CSS-JS yoxdur; JS AJAX-safe və ≤600 sətir."""

    CSS_DIR = Path(settings.BASE_DIR, "static/css/ems_ui")
    JS_DIR = Path(settings.BASE_DIR, "static/js/ems_ui")
    PARTIAL_DIR = Path(settings.BASE_DIR, "templates/partials/ems_ui")

    def test_no_component_file_exceeds_the_module_size_cap(self):
        for path in list(self.CSS_DIR.glob("*.css")) + list(self.JS_DIR.glob("*.js")):
            lines = len(path.read_text(encoding="utf-8").splitlines())
            self.assertLessEqual(lines, 600, f"{path.name}: {lines} sətir")

    def test_partials_carry_no_inline_style_or_script_blocks(self):
        for path in self.PARTIAL_DIR.glob("*.html"):
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("<style", text, path.name)
            if path.name == "_assets.html":
                continue  # yalnız <script src> daşıyır
            for chunk in text.split("<script")[1:]:
                self.assertIn("src=", chunk.split(">", 1)[0], path.name)

    def test_component_js_is_ajax_safe(self):
        """Hər JS `EMSReady`/`EMSDelegate` üzərində qurulmalı və idempotent olmalıdır."""
        for path in self.JS_DIR.glob("*.js"):
            text = path.read_text(encoding="utf-8")
            self.assertTrue(
                "EMSDelegate.on(" in text or "EMSReady(" in text,
                f"{path.name}: nə EMSDelegate, nə EMSReady işlədir",
            )
            self.assertNotIn("DOMContentLoaded", text, f"{path.name}: birbaşa DOMContentLoaded antipattern-i")

    def test_css_uses_tokens_not_raw_hex(self):
        """Rəng hardcode edilmir — yalnız `--ems-*` tokenləri (scrim rgba istisna).

        Şərhlər çıxarılır: sənədləşdirmə məqsədilə ölçülmüş kontrast dəyərləri
        (məs. «dizayn #94a3b8 deyir») şərhdə qanuni olaraq yazılır.
        """
        import re

        comment_re = re.compile(r"/\*.*?\*/", re.S)
        hex_re = re.compile(r"#[0-9a-fA-F]{3,8}\b")
        for path in self.CSS_DIR.glob("*.css"):
            body = comment_re.sub("", path.read_text(encoding="utf-8"))
            found = hex_re.findall(body)
            self.assertEqual(found, [], f"{path.name}: hardcode rəng {found}")

    def test_assets_partial_lists_every_component_file(self):
        assets = (self.PARTIAL_DIR / "_assets.html").read_text(encoding="utf-8")
        for path in self.CSS_DIR.glob("*.css"):
            self.assertIn(f"css/ems_ui/{path.name}", assets, f"{path.name} `_assets.html`-də yoxdur")
        for path in self.JS_DIR.glob("*.js"):
            self.assertIn(f"js/ems_ui/{path.name}", assets, f"{path.name} `_assets.html`-də yoxdur")


class NoGalleryInProductTreeTest(SimpleTestCase):
    """Sahib qərarı: qalereya MƏHSUL AĞACINDA olmamalıdır (2026-09-03).

    Bu test qalereyanın təsadüfən geri qayıtmasının qarşısını alır.
    """

    ROOTS = ("apps", "core", "templates", "static", "config")
    #: Axtarış sözləri QƏSDƏN hissə-hissə qurulur: əks halda bu faylın özü
    #: «qalereya izi» kimi tapılar və `grep` heç vaxt boş qayıtmazdı.
    NEEDLES = ("ui-" + "gallery", "ui_" + "gallery", "gallery_" + "samples", "ems_" + "gallery")

    def test_no_gallery_reference_survives(self):
        hits = []
        for root in self.ROOTS:
            base = Path(settings.BASE_DIR, root)
            for path in base.rglob("*"):
                if not path.is_file() or path.suffix not in {".py", ".html", ".css", ".js"}:
                    continue
                if "__pycache__" in path.parts or path.name == Path(__file__).name:
                    continue
                text = path.read_text(encoding="utf-8", errors="ignore")
                for needle in self.NEEDLES:
                    if needle in text:
                        hits.append(f"{path}: {needle}")
        self.assertEqual(hits, [], "Qalereya məhsul ağacına qayıdıb: " + ", ".join(hits))
