"""Sual göndərişi axınında visual-first manifestin qorunması testləri."""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from apps.exams.models import QuestionSubmission, StudentGroup
from apps.exams.services.question_submission import (
    accept_submission,
    resubmit_question_set,
    submit_question_set,
)
from apps.exams.tests.test_question_submission import VALID_TEXT, _Base

User = get_user_model()


def _bind_source_indices(_token, parsed, **_scope):
    for source_index, question in enumerate(parsed):
        question["source_index"] = source_index
    return parsed


class QuestionSubmissionVisualViewTests(_Base):
    token = "a" * 32

    def test_workbench_visual_preview_is_owner_scoped(self):
        url = reverse(
            "exams:question_import_visual_preview",
            kwargs={"token": self.token, "source_index": 4},
        )

        def render_preview(_token, _source_index, *, owner_id, organization_id):
            self.assertEqual(organization_id, self.org.pk)
            if owner_id != self.teacher.pk:
                raise PermissionDenied
            return b"\x89PNG\r\n\x1a\npreview"

        with patch(
            "apps.exams.views.teacher.submission_media.render_stashed_question_preview",
            side_effect=render_preview,
        ) as render:
            owner_response = self._client_for(self.teacher).get(url)
            denied_response = self._client_for(self.exam_center).get(url)

        self.assertEqual(owner_response.status_code, 200)
        self.assertEqual(owner_response["Cache-Control"], "private, no-store")
        self.assertEqual(denied_response.status_code, 404)
        self.assertEqual(render.call_count, 2)

    def test_selected_visual_question_keeps_source_index_and_token(self):
        group = StudentGroup.objects.create(
            teacher=self.teacher,
            organization=self.org,
            name="Vizual qrup",
        )
        subject = self._subject(name="Riyaziyyat", code="RIY101", group=group)
        client = self._client_for(self.teacher)

        with patch(
            "apps.exams.services.import_media.bind_import_manifest",
            side_effect=_bind_source_indices,
        ):
            response = client.post(
                reverse("exams:question_submission_create"),
                {
                    "action": "save",
                    "title": "Vizual göndəriş",
                    "subject": str(subject.pk),
                    "exam_kind": "final",
                    "group_id": str(group.pk),
                    "language": "az",
                    "raw_text": VALID_TEXT,
                    "math_token": self.token,
                    "selected_indices": "2",
                    "points_payload": '{"2": "4"}',
                },
            )

        self.assertEqual(response.status_code, 302)
        submission = QuestionSubmission.objects.get(title="Vizual göndəriş")
        self.assertEqual(submission.import_token, self.token)
        self.assertEqual(submission.question_count, 1)
        self.assertEqual(submission.parsed_snapshot[0]["source_index"], 1)
        self.assertEqual(submission.parsed_snapshot[0]["points"], 4)

    def test_manifest_mismatch_blocks_submission_save(self):
        group = StudentGroup.objects.create(
            teacher=self.teacher,
            organization=self.org,
            name="Uyğunsuz qrup",
        )
        client = self._client_for(self.teacher)

        with patch(
            "apps.exams.services.import_media.bind_import_manifest",
            side_effect=ValueError("Parsed/manifest məzmunu uyğun deyil"),
        ):
            response = client.post(
                reverse("exams:question_submission_create"),
                {
                    "action": "save",
                    "title": "Uyğunsuz göndəriş",
                    "subject": "Riyaziyyat",
                    "group_id": str(group.pk),
                    "language": "az",
                    "raw_text": VALID_TEXT,
                    "math_token": self.token,
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Parsed/manifest məzmunu uyğun deyil")
        self.assertFalse(QuestionSubmission.objects.filter(title="Uyğunsuz göndəriş").exists())

    def test_visual_upload_uses_canonical_manifest_text(self):
        group = StudentGroup.objects.create(
            teacher=self.teacher,
            organization=self.org,
            name="Upload qrup",
        )
        subject = self._subject(name="Riyaziyyat", code="RIY101", group=group)
        client = self._client_for(self.teacher)
        uploaded = SimpleUploadedFile("questions.png", b"not-decoded-in-view", content_type="image/png")

        with (
            patch(
                "apps.exams.views.teacher.submission_workbench.prepare_question_upload",
                return_value=(VALID_TEXT, self.token),
            ) as prepare,
            patch(
                "apps.exams.services.import_media.bind_import_manifest",
                side_effect=_bind_source_indices,
            ),
        ):
            response = client.post(
                reverse("exams:question_submission_create"),
                {
                    "action": "save",
                    "title": "Upload göndərişi",
                    "subject": str(subject.pk),
                    "exam_kind": "final",
                    "group_id": str(group.pk),
                    "language": "az",
                    "raw_text": "köhnə mətn",
                    "upload_file": uploaded,
                },
            )

        self.assertEqual(response.status_code, 302)
        submission = QuestionSubmission.objects.get(title="Upload göndərişi")
        self.assertEqual(submission.raw_text, VALID_TEXT)
        self.assertEqual(submission.import_token, self.token)
        prepare.assert_called_once()

    def test_owner_and_reviewer_can_view_visual_preview_but_other_teacher_cannot(self):
        from apps.accounts.models import ProfileRole
        from apps.exams.tests.test_exam_center_policy import _assign_user_to_org

        parsed = [
            {
                "q_no": 1,
                "text": "Vizual sual?",
                "options": {"A": "a", "B": "b", "C": "c", "D": "d"},
                "correct": ["A"],
                "answer_mode": "single",
                "source_index": 3,
            }
        ]
        submission = submit_question_set(
            teacher=self.teacher,
            organization=self.org,
            title="Preview media",
            subject="Riyaziyyat",
            group_label="V1",
            language="az",
            raw_text=VALID_TEXT,
            parsed=parsed,
            import_token=self.token,
        )
        other_teacher = User.objects.create_user("visual-other", "visual-other@example.com", "pw")
        _assign_user_to_org(other_teacher, self.org, ProfileRole.TEACHER, "teacher")
        # Mərkəz vizualı yalnız KAFEDRA TƏSDİQİNDƏN sonra görür.
        self._to_center(submission)
        url = reverse(
            "exams:question_submission_visual_preview",
            kwargs={"submission_id": submission.pk, "source_index": 3},
        )

        with patch(
            "apps.exams.views.teacher.submission_media.render_stashed_question_preview",
            return_value=b"\x89PNG\r\n\x1a\npreview",
        ) as render_preview:
            owner_response = self._client_for(self.teacher).get(url)
            reviewer_response = self._client_for(self.exam_center).get(url)
            denied_response = self._client_for(other_teacher).get(url)

        self.assertEqual(owner_response.status_code, 200)
        self.assertEqual(reviewer_response.status_code, 200)
        self.assertEqual(denied_response.status_code, 404)
        self.assertEqual(render_preview.call_count, 2)
        self.assertEqual(owner_response["Cache-Control"], "private, no-store")

        review = self._client_for(self.exam_center).get(
            reverse("exams:question_submission_review", kwargs={"submission_id": submission.pk})
        )
        self.assertContains(review, url)
        self.assertContains(review, 'class="qsubp-source-preview"', count=1)
        self.assertContains(review, 'class="qsubp-answer"', count=1)
        self.assertContains(review, 'class="qsubp-card__text sr-only"', count=1)
        self.assertNotContains(review, 'class="qsubp-options"')

    def test_visual_preview_rejects_source_index_not_selected_in_snapshot(self):
        submission = submit_question_set(
            teacher=self.teacher,
            organization=self.org,
            title="Subset preview",
            subject="Riyaziyyat",
            group_label="V1",
            language="az",
            raw_text=VALID_TEXT,
            parsed=[
                {
                    "q_no": 1,
                    "text": "Sual?",
                    "options": {"A": "a", "B": "b", "C": "c", "D": "d"},
                    "correct": ["A"],
                    "source_index": 2,
                }
            ],
            import_token=self.token,
        )
        url = reverse(
            "exams:question_submission_visual_preview",
            kwargs={"submission_id": submission.pk, "source_index": 1},
        )
        self.assertEqual(self._client_for(self.teacher).get(url).status_code, 404)


class QuestionSubmissionVisualServiceTests(_Base):
    token = "b" * 32

    def _submission(self):
        parsed = [
            {
                "q_no": 1,
                "text": "Vizual sual?",
                "options": {"A": "Bir", "B": "İki", "C": "Üç", "D": "Dörd"},
                "correct": ["A"],
                "answer_mode": "single",
                "source_index": 7,
            }
        ]
        return submit_question_set(
            teacher=self.teacher,
            organization=self.org,
            title="Vizual servis",
            subject="Riyaziyyat",
            group_label="V1",
            language="az",
            raw_text=VALID_TEXT,
            parsed=parsed,
            import_token=self.token,
        )

    def test_accept_forwards_teacher_scope_and_cleans_token(self):
        submission = self._to_center(self._submission())
        with (
            patch(
                "apps.exams.views.teacher.question_library._shared._save_bank_questions",
                return_value=1,
            ) as save_questions,
            patch("apps.exams.services.import_media.clear_stash") as clear_stash,
            self.captureOnCommitCallbacks(execute=True),
        ):
            _bank, created_count = accept_submission(
                submission,
                reviewer=self.exam_center,
                new_bank_name="Vizual qəbul",
            )

        submission.refresh_from_db()
        self.assertEqual(created_count, 1)
        self.assertEqual(submission.import_token, "")
        self.assertEqual(save_questions.call_args.kwargs["math_token"], self.token)
        self.assertEqual(save_questions.call_args.kwargs["media_owner_id"], self.teacher.pk)
        clear_stash.assert_called_once_with(self.token)

    def test_changed_resubmission_discards_stale_manifest(self):
        submission = self._submission()
        with (
            patch("apps.exams.services.import_media.clear_stash") as clear_stash,
            self.captureOnCommitCallbacks(execute=True),
        ):
            resubmit_question_set(
                submission,
                raw_text=VALID_TEXT.replace("Bakı", "Bakı şəhəri"),
            )

        submission.refresh_from_db()
        self.assertEqual(submission.import_token, "")
        clear_stash.assert_called_once_with(self.token)

    def test_unchanged_resubmission_preserves_source_binding_for_accept(self):
        submission = self._submission()
        resubmit_question_set(submission, raw_text=submission.raw_text)
        submission.refresh_from_db()
        self.assertEqual(submission.parsed_snapshot[0]["source_index"], 7)
        self._to_center(submission)

        with (
            patch(
                "apps.exams.views.teacher.question_library._shared._save_bank_questions",
                return_value=1,
            ) as save_questions,
            patch("apps.exams.services.import_media.clear_stash"),
            self.captureOnCommitCallbacks(execute=True),
        ):
            accept_submission(
                submission,
                reviewer=self.exam_center,
                new_bank_name="Binding saxlanır",
            )

        parsed = save_questions.call_args.kwargs["parsed"]
        self.assertEqual(parsed[0]["source_index"], 7)
