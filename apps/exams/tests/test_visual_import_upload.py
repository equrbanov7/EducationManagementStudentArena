"""Workbench visual upload helper-inin scope və cleanup invariantları."""

from unittest.mock import patch

from django.core.exceptions import PermissionDenied
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase

from apps.exams.services.visual_import_upload import prepare_question_upload


class VisualImportUploadScopeTests(SimpleTestCase):
    def test_foreign_previous_token_cannot_be_deleted(self):
        previous = "a" * 32
        created = "b" * 32
        upload = SimpleUploadedFile("new.pdf", b"%PDF-1.4")

        def get_text(token, **scope):
            if token == previous:
                raise PermissionDenied("foreign token")
            self.assertEqual(scope, {"owner_id": 11, "organization_id": 22})
            return "1. Sual\nA) a\nB) b\nC) c\nD) d"

        with (
            patch(
                "apps.exams.services.visual_import_upload.stash_math_images",
                return_value=created,
            ),
            patch(
                "apps.exams.services.visual_import_upload.get_stashed_import_text",
                side_effect=get_text,
            ),
            patch("apps.exams.services.visual_import_upload.clear_stash") as clear,
            self.assertRaises(PermissionDenied),
        ):
            prepare_question_upload(
                upload,
                previous_token=previous,
                owner_id=11,
                organization_id=22,
            )

        clear.assert_called_once_with(created)

    def test_nonvisual_replacement_checks_previous_scope_before_delete(self):
        previous = "c" * 32
        upload = SimpleUploadedFile("questions.txt", b"plain text")
        with (
            patch(
                "apps.exams.services.visual_import_upload.extract_text_from_upload",
                return_value="plain text",
            ),
            patch(
                "apps.exams.services.visual_import_upload.get_stashed_import_text",
                side_effect=PermissionDenied("foreign token"),
            ),
            patch("apps.exams.services.visual_import_upload.clear_stash") as clear,
            self.assertRaises(PermissionDenied),
        ):
            prepare_question_upload(
                upload,
                previous_token=previous,
                owner_id=11,
                organization_id=22,
            )

        clear.assert_not_called()
