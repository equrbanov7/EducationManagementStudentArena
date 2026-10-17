"""Sahib 2026-10-10: AI köməkçi düyməsi — gizlətmək, sürüşdürmək, RİM açarı.

«AI buttonu gizlətmə, yerini dəyişmək və s. də olsun — bəzən hansısa button üstündə dayana bilir».
JS davranışı (sürüşdürmə həddi, yapışma, sıxma, gizlət/qaytar, klaviatura) jsdom-dadır:
``tests/js/ai_assistant_fab.test.js``. Burada şablon müqaviləsi və qlobal açar:

* açar YANILI (defolt): düymə istifadəçi açarı ilə (``data-pref-key``); bərpa nişanı, paneldəki «Gizlət» və
  menyu açarı ``hidden`` render olunur (yalnız skript aktivləşdirir); fab modulu ``ai_assistant.js``-dən əvvəl;
* açar SÖNDÜRÜLÜ (RİM «Sistem tənzimləmələri» və ya mühit): heç kimə nə düymə, nə üslub, nə skript;
  yenidən yandıranda hər şey qayıdır (geri dönən qərar).
"""

from __future__ import annotations

import re
from pathlib import Path

from django.apps import apps
from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from core import runtime_settings

ROOT = Path(__file__).resolve().parents[2]
LOCMEM = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "ai-fab"}}
CACHE_BUSTER = "?v=20261010-wp5ai"
MAIN_BUSTER = "?v=20261017-fixg"  # ai_assistant.js (ai_assistant_fab.js hələ köhnə tokendədir)
WIDGET_MARKERS = (
    'id="ai-fab"',
    'id="ai-bot-btn"',
    'id="ai-fab-restore"',
    'id="ai-chat-panel"',
    "data-ai-fab-toggle",
    "js/ai_assistant.js",
    "js/ai_assistant_fab.js",
    "css/ai_assistant.css",
)
HIDDEN_ATTR = re.compile(r"\shidden[\s>]")


def _tag(html: str, marker: str) -> str:
    match = re.search(r"<[a-z]+\b[^>]*" + re.escape(marker) + r"[^>]*>", html)
    assert match, marker
    return match.group(0)


def _page(client, user=None) -> str:
    if user is not None:
        client.force_login(user)
    response = client.get(reverse("about"))
    assert response.status_code == 200, response.status_code
    return response.content.decode()


class AiFabMarkupTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user("ai_fab_user", "ai_fab@example.com", "pw-ai-fab-1")

    def test_root_carries_the_per_user_pref_key_and_texts(self):
        html = _page(self.client, self.user)
        root = _tag(html, 'id="ai-fab"')
        self.assertIn(f'data-pref-key="ems.aiFab.v1:{self.user.id}"', root)
        for attr in ("hidden-message", "undo-label", "moved-left", "moved-right", "moved-up", "moved-down"):
            self.assertRegex(root, rf'data-{attr}="[^"]+"', attr)

    def test_button_has_keyboard_hint_live_region_and_corner_hide(self):
        html = _page(self.client, self.user)
        self.assertIn('aria-describedby="ai-fab-hint"', _tag(html, 'id="ai-bot-btn"'))
        self.assertRegex(html, r'<span id="ai-fab-hint" class="visually-hidden">[^<]*Alt[^<]*</span>')
        self.assertIn('<span id="ai-fab-live" class="visually-hidden" aria-live="polite"></span>', html)
        button = html[html.index('id="ai-bot-btn"') : html.index("</button>", html.index('id="ai-bot-btn"'))]
        self.assertIn('data-ai-fab-hide aria-hidden="true"', button)

    def test_restore_tab_panel_hide_and_menu_switch_render_hidden(self):
        html = _page(self.client, self.user)
        restore = _tag(html, 'id="ai-fab-restore"')
        self.assertRegex(restore, HIDDEN_ATTR)
        self.assertIn('aria-label="AI köməkçini göstər"', restore)
        self.assertIn('<span class="ai-fab-restore__text">AI köməkçi</span>', html)

        hide = _tag(html, 'id="ai-chat-hide"')
        self.assertRegex(hide, HIDDEN_ATTR)
        self.assertIn('aria-label="AI köməkçini gizlət"', hide)
        header = html[html.index('<header class="ai-chat-header">') :]
        header = header[: header.index("</header>")]
        self.assertLess(header.index('id="ai-chat-hide"'), header.index('id="ai-chat-close"'))

        toggle = _tag(html, "data-ai-fab-toggle")
        self.assertRegex(toggle, HIDDEN_ATTR)
        self.assertIn('role="switch"', toggle)
        self.assertIn('aria-checked="true"', toggle)
        menu = html[html.index('<div class="blog-header__user-menu">') :]
        self.assertLess(menu.index("data-ai-fab-toggle"), menu.index('class="blog-header__user-menu-form"'))

    def test_fab_module_loads_before_the_widget_script(self):
        html = _page(self.client, self.user)
        self.assertLess(
            html.index("js/ai_assistant_fab.js" + CACHE_BUSTER), html.index("js/ai_assistant.js" + MAIN_BUSTER)
        )
        self.assertIn("css/ai_assistant.css" + CACHE_BUSTER, html)

    def test_anonymous_visitor_gets_no_button_or_switch(self):
        html = _page(self.client)
        self.assertNotIn('id="ai-bot-btn"', html)
        self.assertNotIn("data-ai-fab-toggle", html)

    @override_settings(AI_ASSISTANT_BUTTON=False)
    def test_global_switch_off_renders_nothing_for_anyone(self):
        html = _page(self.client, self.user)
        for marker in WIDGET_MARKERS:
            self.assertNotIn(marker, html, marker)


@override_settings(RUNTIME_SETTINGS_ENABLED=True, CACHES=LOCMEM)
class AiFabRuntimeSwitchTests(TestCase):
    """RİM «Sistem tənzimləmələri» → «AI köməkçi düyməsi»: söndür → heç kimdə yoxdur; yandır → qayıdır."""

    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user("ai_fab_rim", "ai_fab_rim@example.com", "pw-ai-fab-2")

    def setUp(self):
        # Model ``core.runtime_settings`` kimi tətbiq reyestrindən götürülür (accounts-a birbaşa import yoxdur).
        self.setting_model = apps.get_model("accounts", "RuntimeSetting")
        self.setting_model.objects.all().delete()
        runtime_settings.invalidate()

    def tearDown(self):
        runtime_settings.invalidate()

    def test_switch_off_hides_everything_and_switching_back_restores_it(self):
        self.setting_model.objects.create(key="ai.assistant_button", value=False)
        runtime_settings.invalidate()
        html = _page(self.client, self.user)
        for marker in WIDGET_MARKERS:
            self.assertNotIn(marker, html, marker)

        self.setting_model.objects.filter(key="ai.assistant_button").delete()
        runtime_settings.invalidate()
        html = _page(self.client)
        for marker in WIDGET_MARKERS:
            self.assertIn(marker, html, marker)


class AiFabBaseTemplateTests(SimpleTestCase):
    """İmtahan/sorğu səhifələri hər iki bloku boşaldır — fab skripti də blokun içindədir, orada yüklənmir."""

    def test_both_scripts_and_the_partial_sit_inside_the_switched_blocks(self):
        base = (ROOT / "templates/base.html").read_text(encoding="utf-8")
        js_block = re.search(r"\{% block ai_assistant_js %\}(.*?)\{% endblock %\}", base, re.S).group(1)
        self.assertIn("{% if academic_rules.ai_button %}", js_block)
        self.assertIn("js/ai_assistant_fab.js", js_block)
        self.assertIn("js/ai_assistant.js", js_block)
        widget_block = re.search(r"\{% block ai_assistant %\}(.*?)\{% endblock %\}", base, re.S).group(1)
        self.assertIn("{% if academic_rules.ai_button %}", widget_block)
        self.assertIn('{% include "partials/_ai_assistant.html" %}', widget_block)
        for rel in (
            "apps/exams/templates/exams/student/take_exam.html",
            "apps/surveys/templates/surveys/base_survey.html",
        ):
            source = (ROOT / rel).read_text(encoding="utf-8")
            self.assertIn("{% block ai_assistant_js %}{% endblock %}", source, rel)
