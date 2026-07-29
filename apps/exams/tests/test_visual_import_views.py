"""Visual-first PDF token-in exam/bank/language save axınlarına inteqrasiyası."""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import ProfileRole
from apps.exams.models import Exam, QuestionBank
from apps.organizations.models import Membership, Organization
from core.constants import OrganizationType

User = get_user_model()


def _raw_questions(count=3):
    return "\n\n".join(
        "\n".join(
            [
                f"{index}. Visual question {index}?",
                f"A) Correct {index}",
                f"B) Wrong {index}",
                f"C) Other {index}",
                f"D) Alternative {index}",
                "Cavab: A",
            ]
        )
        for index in range(1, count + 1)
    )


def _bind_source_indices(token, parsed, **scope):
    for source_index, question in enumerate(parsed):
        question["source_index"] = source_index
        question["has_visual_source"] = True
    return parsed


class VisualImportViewIntegrationTests(TestCase):
    token = "a" * 32

    def setUp(self):
        self.teacher = User.objects.create_user(
            username="visual-import-teacher",
            email="visual-import@example.com",
            password="StrongPass123!",
        )
        self.organization = Organization.objects.create(
            name="Visual Import Org",
            slug="visual-import-org",
            org_type=OrganizationType.SCHOOL,
            owner=self.teacher,
            status="active",
            is_active=True,
        )
        profile = self.teacher.profile
        profile.organization = self.organization
        profile.organization_type = self.organization.org_type
        profile.role = ProfileRole.TEACHER
        profile.save(update_fields=["organization", "organization_type", "role", "updated_at"])
        Membership.objects.update_or_create(
            user=self.teacher,
            organization=self.organization,
            defaults={
                "role": self.organization.roles.get(name="teacher"),
                "is_primary": True,
                "is_active": True,
            },
        )
        self.exam = Exam.objects.create(
            title="Visual Import Exam",
            author=self.teacher,
            organization=self.organization,
            exam_type="test",
            is_active=True,
        )
        self.bank = QuestionBank.objects.create(
            name="Visual Import Bank",
            created_by=self.teacher,
            organization=self.organization,
            default_question_type="test",
        )
        self.client.force_login(self.teacher)
        session = self.client.session
        session["active_organization"] = self.organization.slug
        session.save()

    def _assert_scope(self, scope):
        self.assertEqual(
            scope,
            {
                "owner_id": self.teacher.pk,
                "organization_id": self.organization.pk,
            },
        )

    def test_exam_preview_renders_private_source_image_url(self):
        with patch(
            "apps.exams.views.teacher.question_bank._views_misc.bind_import_manifest",
            side_effect=_bind_source_indices,
        ):
            response = self.client.post(
                reverse("exams:test_question_bank", args=[self.exam.slug]),
                {
                    "action": "preview",
                    "raw_text": _raw_questions(1),
                    "math_token": self.token,
                    "language": "az",
                },
            )

        self.assertEqual(response.status_code, 200)
        expected = reverse(
            "exams:question_import_visual_preview",
            kwargs={"token": self.token, "source_index": 0},
        )
        self.assertContains(response, expected)
        self.assertContains(response, 'class="q-source-preview"', count=1)
        self.assertContains(response, 'class="q-visual-answer"', count=1)
        self.assertContains(response, 'class="q-text sr-only"', count=1)
        self.assertNotContains(response, 'class="options-grid"')

    def test_exam_selected_subset_keeps_original_source_index_for_media(self):
        captured = {}

        def bind(token, parsed, **scope):
            self.assertEqual(token, self.token)
            self._assert_scope(scope)
            return _bind_source_indices(token, parsed, **scope)

        def attach(token, bindings, **scope):
            captured["token"] = token
            captured["bindings"] = list(bindings)
            captured["scope"] = scope
            return len(captured["bindings"])

        with (
            patch("apps.exams.views.teacher.question_bank._views_misc.bind_import_manifest", side_effect=bind),
            patch("apps.exams.views.teacher.question_bank._views_misc.attach_import_media_batch", side_effect=attach),
            patch("apps.exams.views.teacher.question_bank._views_misc.clear_stash") as clear_stash,
            patch("apps.exams.services.difficulty.schedule_ai_question_difficulty_warmup"),
        ):
            response = self.client.post(
                reverse("exams:test_question_bank", args=[self.exam.slug]),
                {
                    "action": "save",
                    "raw_text": _raw_questions(),
                    "math_token": self.token,
                    "selected_indices": "2",
                    "points_payload": "{}",
                    "random_question_count": "1",
                    "default_points": "1",
                    "language": "az",
                },
            )

        self.assertEqual(response.status_code, 302)
        created = self.exam.questions.get()
        self.assertEqual(created.text, "Visual question 2?")
        self.assertEqual(captured["token"], self.token)
        self.assertEqual(captured["bindings"], [(1, created)])
        self._assert_scope(captured["scope"])
        clear_stash.assert_called_once_with(self.token)

    def test_manifest_raw_mismatch_blocks_exam_save(self):
        with (
            patch(
                "apps.exams.views.teacher.question_bank._views_misc.bind_import_manifest",
                side_effect=ValueError("Parsed/manifest sual sayı uyğun deyil"),
            ),
            patch("apps.exams.views.teacher.question_bank._views_misc.attach_import_media_batch") as attach,
            patch("apps.exams.views.teacher.question_bank._views_misc.clear_stash") as clear_stash,
        ):
            response = self.client.post(
                reverse("exams:test_question_bank", args=[self.exam.slug]),
                {
                    "action": "save",
                    "raw_text": _raw_questions(2),
                    "math_token": self.token,
                    "selected_indices": "1,2",
                    "points_payload": "{}",
                    "language": "az",
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.exam.questions.count(), 0)
        self.assertContains(response, "Parsed/manifest sual sayı uyğun deyil")
        attach.assert_not_called()
        clear_stash.assert_not_called()

    def test_bank_bulk_save_attaches_selected_source_and_cleans_token(self):
        captured = {}

        def attach(token, bindings, **scope):
            captured["token"] = token
            captured["bindings"] = list(bindings)
            captured["scope"] = scope
            return len(captured["bindings"])

        with (
            patch(
                "apps.exams.views.teacher.question_library.questions.bind_import_manifest",
                side_effect=_bind_source_indices,
            ),
            patch(
                "apps.exams.views.teacher.question_library._shared.attach_import_media_batch",
                side_effect=attach,
            ),
            patch("apps.exams.views.teacher.question_library.questions.clear_stash") as clear_stash,
        ):
            response = self.client.post(
                reverse("exams:question_bank_bulk_add", args=[self.bank.pk]),
                {
                    "action": "save",
                    "raw_text": _raw_questions(),
                    "math_token": self.token,
                    "selected_indices": "2",
                    "points_payload": "{}",
                    "q_format": "test",
                    "language": "az",
                },
            )

        self.assertEqual(response.status_code, 302)
        created = self.bank.library_questions.get()
        self.assertEqual(created.text, "Visual question 2?")
        self.assertEqual(captured["token"], self.token)
        self.assertEqual(captured["bindings"], [(1, created)])
        self._assert_scope(captured["scope"])
        clear_stash.assert_called_once_with(self.token)

    def test_language_variant_save_attaches_selected_source_and_cleans_token(self):
        captured = {}

        def attach(token, bindings, **scope):
            captured["token"] = token
            captured["bindings"] = list(bindings)
            captured["scope"] = scope
            return len(captured["bindings"])

        with (
            patch("apps.exams.views.teacher.languages.bind_import_manifest", side_effect=_bind_source_indices),
            patch("apps.exams.services.import_media.attach_import_media_batch", side_effect=attach),
            patch("apps.exams.views.teacher.languages.clear_stash") as clear_stash,
        ):
            response = self.client.post(
                reverse("exams:exam_language_manager", args=[self.exam.slug]),
                {
                    "action": "save",
                    "raw_text": _raw_questions(),
                    "math_token": self.token,
                    "selected_indices": "2",
                    "points_payload": "{}",
                    "language": "ru",
                },
            )

        self.assertEqual(response.status_code, 302)
        created = self.exam.questions.get()
        self.assertEqual(created.text, "Visual question 2?")
        self.assertEqual(created.language, "ru")
        self.assertEqual(captured["token"], self.token)
        self.assertEqual(captured["bindings"], [(1, created)])
        self._assert_scope(captured["scope"])
        clear_stash.assert_called_once_with(self.token)
