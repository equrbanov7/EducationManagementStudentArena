"""Həssas media URL-ləri object-storage origin-i sızdırmamalıdır."""

from types import SimpleNamespace

from django.test import SimpleTestCase, override_settings

from apps.exams.services.question_delivery import _storage_url
from apps.exams.services.question_snapshot import _media_url
from core.media_urls import protected_media_url


class PrivateMediaUrlTests(SimpleTestCase):
    @override_settings(
        MEDIA_URL="/media/",
        OBJECT_STORAGE_ENABLED=True,
    )
    def test_question_media_always_uses_application_rbac_route(self):
        value = SimpleNamespace(name="question_media/exam_7/q_8/formula 1.png")
        expected = "/media/question_media/exam_7/q_8/formula%201.png"

        self.assertEqual(protected_media_url(value), expected)
        self.assertEqual(_media_url(value.name), expected)
        self.assertEqual(_storage_url(value.name), expected)
        self.assertNotIn("amazonaws", protected_media_url(value))

    def test_empty_and_traversal_names_fail_closed(self):
        self.assertEqual(protected_media_url(""), "")
        self.assertEqual(protected_media_url("../secret.pdf"), "")
