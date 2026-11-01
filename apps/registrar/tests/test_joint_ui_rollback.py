"""The normal journal remains the default, without altering any stored journal."""

from types import SimpleNamespace
from unittest.mock import patch

from django.test import RequestFactory, SimpleTestCase, override_settings
from django.urls import reverse

from apps.registrar import joint_journal_list, joint_journal_ui, joint_journal_views


@override_settings(REGISTRAR_JOINT_JOURNAL_UI_ENABLED=False)
class JointUIRollbackTests(SimpleTestCase):
    def test_default_projection_preserves_original_unsplit_queryset_without_reading_it(self):
        original = object()
        with patch.object(joint_journal_list, "selections", side_effect=AssertionError("must not project")):
            result = joint_journal_list.project(original, organization=None, user=None, selected_kind="")
        self.assertIs(result, original)

    def test_old_combined_bookmark_returns_to_existing_journal_list(self):
        request = RequestFactory().get("/unused?teacher=8425")
        request.user = SimpleNamespace(is_authenticated=True)
        with patch.object(joint_journal_views.joint_journal, "resolve", side_effect=AssertionError("no lookup")):
            response = joint_journal_views.detail(request, "unused", "lecture")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("registrar:journal_list") + "?teacher=8425")

    def test_invalid_teacher_query_is_not_forwarded(self):
        request = RequestFactory().get("/unused?teacher=https://untrusted.example/")
        request.user = SimpleNamespace(is_authenticated=True)
        response = joint_journal_views.detail(request, "unused", "lecture")
        self.assertEqual(response.url, reverse("registrar:journal_list"))

    @override_settings(REGISTRAR_JOINT_JOURNAL_UI_ENABLED="true")
    def test_string_flag_cannot_accidentally_enable_combined_ui(self):
        self.assertFalse(joint_journal_ui.enabled())

    @override_settings(REGISTRAR_JOINT_JOURNAL_UI_ENABLED=True)
    def test_explicit_reviewed_opt_in_is_available_for_hidden_ui_tests(self):
        self.assertTrue(joint_journal_ui.enabled())
