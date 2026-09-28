"""Audit 2026-09-28 — iş paketi G (frontend / a11y / i18n) reqressiya qoruyucuları.

* FQ-FE-1 — bildiriş silmə düymələri CSP-nin blokladığı `onclick=confirm` əvəzinə
  `data-ems-confirm` (csp_event_handlers.js → EMSConfirm) daşıyır.
* FQ-FE-3 — əl ilə yazılmış JSON i18n bloklarında hər `{% trans %}` `|escapejs`-dən keçir.
* FQ-FE-4 — kurs panelinin elementləri (labs/assignments/projects/courses/notifications
  JS-i) native `alert()` işlətmir.
* FQ-A11Y-1 — xəta səhifələrinin `<html lang>` aktiv dili göstərir (500 daxil).
* Agent D follow-up — canlı sessiya yaratma POST formu ilə; ViewAs blok siyahısında
  silinmiş OTP API adları yoxdur.
"""

import json
import re
from pathlib import Path

from django.conf import settings
from django.template import Context, Template
from django.template.loader import render_to_string
from django.test import SimpleTestCase
from django.urls import NoReverseMatch, reverse
from django.utils import translation

BASE = Path(settings.BASE_DIR)

_NATIVE_ALERT = re.compile(r"(?<![\w.$])(?:window\.)?alert\(")

# Allowlist boşdur: əvvəl burada olan 3 ölü fayl (heç bir şablon yükləmirdi) 2026-09-28 silindi.
ALERT_ALLOWLIST: dict[str, str] = {}

ALERT_SCOPES = (
    "apps/labs/static",
    "apps/assignments/static",
    "apps/projects/static",
    "apps/courses/static",
    "apps/notifications/static",
)


def _strip_js_comments(text):
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("//"))


class NotificationDeleteConfirmTest(SimpleTestCase):
    TEMPLATES = (
        "apps/notifications/templates/notifications/notification_list.html",
        "apps/notifications/templates/notifications/notification_detail.html",
    )

    def test_delete_uses_ems_confirm_not_inline_handler(self):
        for rel in self.TEMPLATES:
            source = (BASE / rel).read_text(encoding="utf-8")
            with self.subTest(template=rel):
                self.assertNotRegex(source, r"\son[a-z]+\s*=")
                self.assertIn('data-ems-confirm="{% trans "Delete this notification?" %}"', source)


class JsonI18nEscapeTest(SimpleTestCase):
    BLOCKS = (
        ("apps/accounts/templates/accounts/profile/sections/_people_directory.html", 'id="people-detail-i18n-'),
        ("apps/accounts/templates/accounts/register.html", 'id="register-i18n-data"'),
    )

    def _block(self, rel, marker):
        source = (BASE / rel).read_text(encoding="utf-8")
        start = source.index(marker)
        start = source.index(">", start) + 1
        return source[start : source.index("</script>", start)]

    def test_every_trans_in_json_block_is_escapejs(self):
        for rel, marker in self.BLOCKS:
            block = self._block(rel, marker)
            tags = re.findall(r"\{% trans [^%]*%\}", block)
            with self.subTest(template=rel):
                self.assertGreater(len(tags), 10)
                self.assertEqual([t for t in tags if "|escapejs" not in t], [])

    def test_quotes_and_backslashes_keep_json_valid(self):
        for rel, marker in self.BLOCKS:
            block = self._block(rel, marker)
            # İlk trans-ı qəsdən «pis» literal ilə əvəz edirik: tərcümə `"`, `\` və
            # sətir sonu daşısa belə JSON.parse sınmamalıdır.
            first = re.search(r"\{% trans '([^']*)'\|escapejs", block)
            hostile = block.replace(first.group(0), "{% trans 'a\"b\\\\c'|escapejs", 1)
            rendered = Template("{% load i18n %}" + hostile).render(Context({"people_section": {"kind": "x"}}))
            with self.subTest(template=rel), translation.override("az"):
                data = json.loads(rendered)
                self.assertEqual(list(data.values())[0], 'a"b\\c')


class NativeAlertGuardTest(SimpleTestCase):
    def test_course_item_js_has_no_native_alert(self):
        offenders = {}
        for scope in ALERT_SCOPES:
            for path in sorted((BASE / scope).rglob("*.js")):
                rel = path.relative_to(BASE).as_posix()
                if rel in ALERT_ALLOWLIST or "/vendor/" in rel:
                    continue
                text = _strip_js_comments(path.read_text(encoding="utf-8", errors="ignore"))
                hits = [text.count("\n", 0, m.start()) + 1 for m in _NATIVE_ALERT.finditer(text)]
                if hits:
                    offenders[rel] = hits
        self.assertEqual(offenders, {}, "Native alert() → EMSToast.show(msg, 'error') işlədin.")

    def test_allowlisted_files_are_really_dead(self):
        templates = [p for root in ("apps", "templates") for p in (BASE / root).rglob("*.html")]
        corpus = "\n".join(p.read_text(encoding="utf-8", errors="ignore") for p in templates)
        for rel in ALERT_ALLOWLIST:
            static_path = rel.split("/static/", 1)[1]
            with self.subTest(file=rel):
                self.assertNotIn(static_path, corpus)


class ErrorPageLangTest(SimpleTestCase):
    def test_error_pages_follow_active_language(self):
        for name in ("400", "403", "404", "500", "network_zone"):
            for lang in ("en", "ru"):
                with self.subTest(page=name, lang=lang), translation.override(lang):
                    html = render_to_string(f"errors/{name}.html")
                    self.assertIn(f'<html lang="{lang}">', html)

    def test_500_without_request_context_falls_back_gracefully(self):
        with translation.override(None):
            html = render_to_string("errors/500.html")
        self.assertRegex(html, r'<html lang="[a-z-]+">')


class LiveSessionStartIsPostTest(SimpleTestCase):
    SCRIPT = "apps/exams/static/exams/js/teacher_exam_detail.js"

    def test_start_and_new_session_submit_post_form(self):
        source = (BASE / self.SCRIPT).read_text(encoding="utf-8")
        live_block = source.split("initQuestionLazyLoading", 1)[0]
        self.assertIn('form.method = "post"', live_block)
        self.assertIn('"csrfmiddlewaretoken"', live_block)
        self.assertIn('"force_new"', live_block)
        self.assertIn("submitStartForm(targetUrl, true)", live_block)
        # GET naviqasiya yalnız «mövcud sessiyaya qayıt» düyməsində qalır (sessiya yaratmır).
        self.assertEqual(live_block.count("window.location.href = targetUrl"), 1)

    def test_template_busts_cache(self):
        template = (BASE / "apps/exams/templates/exams/teacher/teacher_exam_detail.html").read_text(encoding="utf-8")
        self.assertIn("teacher_exam_detail.js' %}?v=20260928-live-post", template)


class ViewAsBlockedNamesTest(SimpleTestCase):
    def test_blocked_url_names_do_not_reference_removed_routes(self):
        from apps.accounts.middleware import ViewAsMiddleware

        for name in ("accounts:send_otp_api", "accounts:verify_otp_api", "accounts:resend_otp_api"):
            self.assertNotIn(name, ViewAsMiddleware.BLOCKED_URL_NAMES)
        for name in ViewAsMiddleware.BLOCKED_URL_NAMES:
            with self.subTest(name=name):
                try:
                    reverse(name)
                except NoReverseMatch as exc:  # arqument tələb edən ad — mövcuddur
                    self.assertIn("arguments", str(exc))
