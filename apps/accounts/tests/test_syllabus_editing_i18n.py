"""Avtomatik təsdiq redaktorunun real şablonu EN/RU/TR/DE-də Azərbaycan dilinə geri düşmür."""

from django.template.loader import render_to_string
from django.test import SimpleTestCase
from django.utils.translation import override, pgettext


class SyllabusEditingI18nTests(SimpleTestCase):
    # İstifadəçinin gördüyü əsas iki məna hər dildə: məsləhət saatı məcburi deyil,
    # saxlanmış düzəliş sillabusu təsdiqlənmiş vəziyyətdə saxlayır.
    LABELS = {
        "en": (
            "Consultation hours (optional)",
            "Save changes",
            "Changes are saved automatically and remain approved.",
            "The syllabus remains approved when changes are saved.",
            "Approve syllabus",
            "The syllabus will be approved automatically.",
            "Confirming automatically approves the syllabus",
            "Confirming approves the syllabus immediately.",
            "Changes are approved automatically",
            "Edit",
        ),
        "ru": (
            "Часы консультаций (необязательно)",
            "Сохранить изменения",
            "Изменения сохраняются автоматически и остаются утверждёнными.",
            "После сохранения изменений силлабус остаётся утверждённым.",
            "Утвердить силлабус",
            "Силлабус будет утверждён автоматически.",
            "После подтверждения силлабус автоматически утверждается",
            "После подтверждения силлабус сразу утверждается автоматически",
            "Изменения утверждаются автоматически",
            "Редактировать",
        ),
        "tr": (
            "Danışmanlık saatleri (isteğe bağlı)",
            "Değişiklikleri kaydet",
            "Değişiklikler otomatik kaydedilir ve onaylı kalır.",
            "Değişiklikler kaydedildiğinde izlence onaylı kalır.",
            "İzlenceyi onayla",
            "İzlence otomatik onaylanacaktır.",
            "Onayladığınızda izlence otomatik onaylanır",
            "Onayladığınızda izlence hemen otomatik onaylanır.",
            "Değişiklikler otomatik onaylanır",
            "Düzenle",
        ),
        "de": (
            "Sprechstunden (optional)",
            "Änderungen speichern",
            "Änderungen werden automatisch gespeichert und bleiben genehmigt.",
            "Der Lehrplan bleibt nach dem Speichern genehmigt.",
            "Lehrplan genehmigen",
            "Der Lehrplan wird automatisch genehmigt.",
            "Nach der Bestätigung wird der Lehrplan automatisch genehmigt",
            "Nach der Bestätigung wird der Lehrplan sofort genehmigt",
            "Änderungen werden automatisch genehmigt",
            "Bearbeiten",
        ),
    }

    @staticmethod
    def _render(status):
        return render_to_string(
            "accounts/profile/sections/_syllabus_editor.html",
            {
                "allowed_sections": {"syllabus-editor"},
                "active_section": "syllabus-editor",
                "profile_base_url": "/accounts/profile/",
                "syllabus_editor_section": {
                    "header": {"status_key": status},
                    "readonly": False,
                    "approval_required": False,
                    "can_submit": True,
                    "panels": {},
                    "nav": [],
                    "urls": {},
                    "reuse": {},
                    "shares": {},
                },
            },
        )

    def test_approved_editor_renders_localized_optional_hours_and_save_state(self):
        for language, expected in self.LABELS.items():
            with self.subTest(language=language), override(language):
                html = self._render("approved")
                for text in expected[:4]:
                    self.assertIn(text, html)
                self.assertNotIn("Məsləhət saatı (istəyə bağlı)", html)
                self.assertNotIn("Dəyişiklikləri saxla", html)
                self.assertNotIn("Düzəlişlər avtomatik saxlanılır", html)
                self.assertIn('data-status="approved"', html)
                self.assertEqual(pgettext("accounts.syllabus", "Düzəlişlər avtomatik təsdiqlənir"), expected[8])
                self.assertEqual(pgettext("accounts.syllabus", "Redaktə et"), expected[9])

    def test_draft_editor_renders_localized_automatic_approval_dialog(self):
        for language, expected in self.LABELS.items():
            with self.subTest(language=language), override(language):
                html = self._render("draft")
                for text in expected[4:8]:
                    self.assertIn(text, html)
                self.assertNotIn("Sillabusu təsdiqlə", html)
                self.assertNotIn("Sillabus avtomatik təsdiqlənəcək", html)
                self.assertIn('data-t-submit-body="', html)
