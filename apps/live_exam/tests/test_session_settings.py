from django.test import SimpleTestCase

from apps.live_exam.session_settings import default_session_settings, normalize_session_settings


class LiveSessionSettingsDefaultsTest(SimpleTestCase):
    def test_show_questions_on_devices_is_enabled_by_default(self):
        self.assertTrue(default_session_settings()["show_questions_on_devices"])
        self.assertTrue(normalize_session_settings({})["show_questions_on_devices"])

    def test_show_questions_on_devices_can_still_be_disabled_explicitly(self):
        settings = normalize_session_settings({"show_questions_on_devices": False})

        self.assertFalse(settings["show_questions_on_devices"])
