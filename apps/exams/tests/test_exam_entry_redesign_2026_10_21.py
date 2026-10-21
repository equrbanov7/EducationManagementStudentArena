"""İmtahan zalı giriş + qaydalar modalı + gözləmə otağı — redizayn (sahib 2026-10-21).

Sahib: «Burda yuxarı-aşağı scroll var, onu düzəltmək lazımdır; dil əlavəsi yerində düzəltmək lazımdır; rəng tonu
sistemin özünə uyğun redesign et; içəri keçid gözləmə yerini redesign et ki, normal görüntü olsun.»

* Giriş: növə görə başlıq, rəsmi loqo, saytın ORTAQ dil seçicisi (yuxarı zolaqda), PIN sahəsinin atributları,
  xəta (role=alert) və «açar söndürülüb» (role=status, forma yoxdur) halları.
* Modal: dialoq semantikası, sabit alt zolaq (təsdiq + düymələr), arxa plan `inert`.
* Gözləmə otağı: JS müqaviləsi (id/data-*), `data-phase`, aria-live vəziyyət mətni, növ nişanı, tələbə.
* Dil seçici: dillər `settings.LANGUAGES`-dən — hər kod giriş, gözləmə otağı və bildiriş səhifələrində görünür;
  sistemə yeni dil əlavə olunanda avtomatik çıxır (şablonda sabit siyahı yoxdur).
* CSS: scroll kök səbəbinin düzəlişi (main.css 110px padding sıfırlanır) və xam hex rəng yoxdur.
"""

from __future__ import annotations

import re
from pathlib import Path

from django.conf import settings
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils.html import escape

from apps.exams.models import FinalExamTicket
from apps.exams.tests.test_audit_2026_09_13_exam_integrity import LOCMEM_CACHE
from apps.exams.tests.test_examaccess_2026_10_13 import EXTERNAL_IP, NETWORK_ON
from apps.exams.tests.test_midterm_center_2026_10_20 import (
    CENTER_OFF,
    CENTER_ON,
    FINAL_PIN,
    MIDTERM_PIN,
    PC1_IP,
    _CenterFixture,
)

CSS_DIR = Path(settings.BASE_DIR) / "apps" / "exams" / "static" / "exams" / "css" / "final_center"
SET_LANGUAGE_URL = reverse("set_language")


def _assert_all_languages(testcase, response):
    """settings.LANGUAGES-dəki HƏR dil seçicidə bir set_language forması kimi var."""
    html = response.content.decode()
    testcase.assertIn("language-switcher--floating", html)
    testcase.assertIn(f'action="{SET_LANGUAGE_URL}"', html)
    for code, name in settings.LANGUAGES:
        testcase.assertIn(f'name="language" value="{code}"', html, code)
        testcase.assertIn(f'<span class="language-switcher__option-code">{code.upper()}</span>', html, code)
        # Ad dilin ÖZ adıdır (settings.LANGUAGES, login səhifəsinin seçicisi kimi).
        testcase.assertIn(f'<span class="language-switcher__option-label">{escape(name)}</span>', html, code)


@override_settings(CACHES=LOCMEM_CACHE, **CENTER_ON)
class ExamEntryRedesignTests(_CenterFixture, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls._build("rd1021")

    def _get(self, url_name, client=None):
        return (client or Client()).get(reverse(url_name), REMOTE_ADDR=PC1_IP)

    def test_final_entry_has_brand_title_language_switcher_and_pin_field(self):
        response = self._get("exams:final_exam_entry")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Final imtahan girişi")
        self.assertContains(response, "brand/wcu-official-lockup.svg")
        # Saytın ortaq dil seçicisi (floating) yuxarı zolaqda — öz «AZ/EN/RU» həb zolağı yoxdur.
        self.assertContains(response, 'class="fexc-topbar"')
        self.assertContains(response, "language-switcher--floating")
        self.assertContains(response, f'action="{SET_LANGUAGE_URL}"')
        self.assertNotContains(response, "fexc-langbar-pill")
        _assert_all_languages(self, response)
        # Forma və PIN sahəsi dəyişməyib.
        self.assertContains(response, 'action="/exams/final/"')
        self.assertContains(response, 'autocomplete="off"')
        self.assertContains(response, 'name="username"')
        self.assertContains(response, 'name="pin"')
        self.assertContains(response, 'inputmode="numeric"')
        self.assertContains(response, 'autocomplete="one-time-code"')
        self.assertContains(response, 'aria-describedby="fexc-pin-hint"')
        self.assertContains(response, "csrfmiddlewaretoken")
        self.assertContains(response, "final_center/student.css")
        self.assertNotContains(response, "final_center/student_gate.css")
        self.assertNotContains(response, "data-fexc-gate-backdrop")

    def test_midterm_entry_uses_midterm_title_only(self):
        response = self._get("exams:midterm_exam_entry")
        self.assertContains(response, "Midterm imtahan girişi")
        self.assertNotContains(response, "Final imtahan girişi")
        self.assertContains(response, 'action="/exams/midterm/"')
        _assert_all_languages(self, response)

    def test_language_list_follows_settings_languages(self):
        """Sistemə dil əlavə olunanda seçicidə avtomatik görünür; çıxarılan dil görünmür."""
        languages = [("az", "Azərbaycan dili"), ("en", "English"), ("de", "Deutsch"), ("fr", "Français")]
        with self.settings(LANGUAGES=languages):
            response = self._get("exams:final_exam_entry")
        self.assertContains(response, 'name="language" value="fr"')
        self.assertContains(response, "Français")
        self.assertContains(response, 'name="language" value="de"')
        self.assertNotContains(response, 'name="language" value="ru"')
        self.assertNotContains(response, 'name="language" value="tr"')

    def test_wrong_pin_shows_error_alert_and_keeps_username(self):
        response = Client().post(
            reverse("exams:final_exam_entry"),
            {"username": self.student.username, "pin": "00000000"},
            REMOTE_ADDR=PC1_IP,
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'class="fexc-alert fexc-alert-error" role="alert"')
        self.assertContains(response, "aktiv final imtahanınız yoxdur")
        self.assertContains(response, f'value="{self.student.username}"')

    def test_wrong_kind_pin_points_to_the_right_page(self):
        response = Client().post(
            reverse("exams:midterm_exam_entry"),
            {"username": self.student.username, "pin": FINAL_PIN},
            REMOTE_ADDR=PC1_IP,
        )
        self.assertContains(response, "fexc-alert-error")
        self.assertContains(response, "/exams/final/ ünvanından daxil olun")

    def test_gate_modal_is_a_dialog_with_fixed_footer_and_inert_background(self):
        client, response = self._login("exams:final_exam_entry", FINAL_PIN)
        self.assertEqual(response.status_code, 302)
        modal = self._get("exams:final_exam_entry", client)
        self.assertTrue(modal.context["show_gate_modal"])
        self.assertContains(modal, "final_center/student_gate.css")
        self.assertContains(modal, 'role="dialog" aria-modal="true" aria-labelledby="fexc-modal-title"')
        self.assertContains(modal, 'class="fexc-shell fexc-shell--entry" inert aria-hidden="true"')
        self.assertContains(modal, 'class="fexc-gate-body"')
        foot = modal.content.decode().split('class="fexc-gate-foot"', 1)[1]
        self.assertIn('name="accept_rules"', foot)
        self.assertIn('name="action" value="back"', foot)
        self.assertIn('name="action" value="confirm"', foot)
        self.assertIn("formnovalidate", foot)
        self.assertContains(modal, "İmtahan qaydaları")
        self.assertContains(modal, "Final imtahanı")

    def test_waiting_room_markup_contract_and_accessibility(self):
        client, response = self._login("exams:midterm_exam_entry", MIDTERM_PIN)
        self.assertEqual(response.status_code, 302)
        confirm = self._enter_waiting(client)
        ticket = FinalExamTicket.objects.get(exam=self.midterm, student=self.student)
        waiting = client.get(confirm["Location"], REMOTE_ADDR=PC1_IP)
        self.assertEqual(waiting.status_code, 200)
        html = waiting.content.decode()
        # JS müqaviləsi (waiting_room.js) dəyişməyib.
        for marker in (
            'id="fexc-waiting-root"',
            f'data-state-url="{reverse("exams:final_ticket_state", args=[ticket.pk])}"',
            f'data-begin-url="{reverse("exams:final_exam_begin", args=[ticket.pk])}"',
            'data-entry-url="/exams/midterm/"',
            'data-session-active="0"',
            'id="fexc-conn-state" data-state="connecting"',
            'id="fexc-manual-start" hidden',
            f'action="{reverse("exams:final_exam_cancel", args=[ticket.pk])}" class="fexc-cancel-form"',
        ):
            self.assertIn(marker, html)
        self.assertIn('data-phase="waiting"', html)
        self.assertRegex(html, r'id="fexc-wait-message" role="status" aria-live="polite"')
        self.assertIn("Midterm imtahanı", html)
        self.assertIn("fexc-kind fexc-kind--midterm", html)
        self.assertIn(self.student.username, html)
        self.assertIn("brand/wcu-official-mark.png", html)
        _assert_all_languages(self, waiting)
        self.assertIn("final_center/student_waiting.css", html)
        self.assertIn("nəzarətçi imtahanı başladanda imtahan avtomatik açılacaq", html)
        self.assertIn(self.room.name, html)


@override_settings(CACHES=LOCMEM_CACHE, **CENTER_OFF)
class ExamEntryRedesignKeyOffTests(_CenterFixture, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls._build("rd1021off")

    def test_midterm_key_off_is_an_info_notice_without_form(self):
        response = Client().get(reverse("exams:midterm_exam_entry"), REMOTE_ADDR=PC1_IP)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'class="fexc-alert fexc-alert-info" role="status"')
        self.assertNotContains(response, "fexc-alert-error")
        self.assertNotContains(response, 'name="pin"')
        _assert_all_languages(self, response)


@override_settings(CACHES=LOCMEM_CACHE, **CENTER_ON, **NETWORK_ON)
class ExamEntryRedesignNoticeTests(TestCase):
    def test_network_blocked_notice_has_language_switcher(self):
        response = Client().get(reverse("exams:final_exam_entry"), REMOTE_ADDR=EXTERNAL_IP)
        self.assertEqual(response.status_code, 403)
        self.assertTemplateUsed(response, "exams/student/exam_network_blocked.html")
        _assert_all_languages(self, response)
        self.assertContains(response, "css/language-switcher.css", status_code=403)
        self.assertContains(response, "bootstrap.bundle.min.js", status_code=403)
        self.assertContains(response, "js/language_switcher.js", status_code=403)


class ExamEntryRedesignCssTests(TestCase):
    def test_scroll_root_cause_is_fixed_without_hiding_overflow(self):
        css = re.sub(r"/\*.*?\*/", "", (CSS_DIR / "student.css").read_text(encoding="utf-8"), flags=re.S)
        # main.css-in AI FAB boşluğu (110px) zal səhifələrində sıfırlanır; qabıq 100dvh.
        self.assertRegex(css, r"#main-content:has\(> \.fexc-shell\)\s*\{\s*padding-bottom:\s*0;")
        self.assertIn("min-height: 100dvh;", css)
        self.assertNotRegex(css, r"overflow\s*:\s*hidden")
        # Köhnə `position: fixed` dil zolağı yoxdur.
        self.assertNotIn("fexc-langbar", css)

    def test_redesigned_css_uses_design_tokens_only(self):
        for name in ("student.css", "student_gate.css", "student_waiting.css", "student_notice.css"):
            css = (CSS_DIR / name).read_text(encoding="utf-8")
            code = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
            self.assertIsNone(re.search(r"#[0-9a-fA-F]{3,8}\b", code), name)
            self.assertNotIn("rgba(", code, name)
            self.assertLessEqual(len(css.splitlines()), 600, name)
