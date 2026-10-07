"""Elan sənədləri — storage faylı DB tranzaksiyası ilə uyğun (2026-10-07).

* Yaradılış: DB hissəsi uğursuz olsa (növbəti sənəd rədd edilir, INSERT yıxılır) artıq yazılmış
  fayllar silinir — yetim fayl qalmır.
* Silmə (birdəfəlik silinən qaralama, tək sənəd): fayl YALNIZ commit-dən sonra silinir; rollback
  olsa sətir də, fayl da yerində qalır.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from unittest import mock

from django.core.exceptions import ValidationError
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import DatabaseError, transaction
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.announcements.models import Announcement, AnnouncementAttachment
from apps.announcements.services import manage
from apps.announcements.services.access import manage_scope
from core.rls import bypass_rls

from .world import _Req, build_world, client_for, make_announcement

PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"


class _Boom(Exception):
    """Sınaq: əməliyyatdan sonra tranzaksiyanı geri almaq üçün."""


def _pdf(name="cedvel.pdf"):
    return SimpleUploadedFile(name, PDF, content_type="application/pdf")


class AttachmentStorageTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = build_world("annfs")

    def setUp(self):
        self.media = tempfile.mkdtemp(prefix="ann-media-")
        override = override_settings(MEDIA_ROOT=self.media)
        override.enable()
        self.addCleanup(override.disable)
        self.addCleanup(shutil.rmtree, self.media, ignore_errors=True)
        self.request = _Req(self.w["owner"], self.w["org"])

    def _scope(self):
        with bypass_rls():
            return manage_scope(self.w["owner"], self.w["org"])

    def _files(self):
        found = []
        for root, _dirs, names in os.walk(self.media):
            found.extend(os.path.join(root, name) for name in names)
        return found

    def _draft_with_attachment(self):
        draft = make_announcement(self.w, title="Qaralama sənədli", publish=False)
        with bypass_rls():
            (attachment,) = manage.add_attachments(self.request, self.w["org"], draft, [_pdf()])
        self.assertTrue(default_storage.exists(attachment.file.name))
        return draft, attachment

    # ── yaradılış ───────────────────────────────────────────────────────────
    def test_rejected_second_file_removes_already_written_first_file(self):
        item = make_announcement(self.w, title="İki sənəd", publish=False)
        with bypass_rls(), self.assertRaises(ValidationError):
            manage.add_attachments(
                self.request,
                self.w["org"],
                item,
                [_pdf("ok.pdf"), SimpleUploadedFile("virus.exe", b"MZ\x90\x00", "application/octet-stream")],
            )
        with bypass_rls():
            self.assertFalse(AnnouncementAttachment.objects.filter(announcement=item).exists())
        self.assertEqual(self._files(), [])

    def test_insert_failure_after_file_write_removes_the_file(self):
        item = make_announcement(self.w, title="DB xətası", publish=False)
        with (
            bypass_rls(),
            mock.patch.object(AnnouncementAttachment, "_do_insert", side_effect=DatabaseError("boom")),
            self.assertRaises(DatabaseError),
        ):
            manage.add_attachments(self.request, self.w["org"], item, [_pdf()])
        self.assertEqual(self._files(), [])

    def test_form_with_rejected_file_leaves_no_orphan(self):
        owner = client_for(self.w["org"], self.w["owner"])
        response = owner.post(
            reverse("announcements:manage_create"),
            {
                "title": "Yeni elan",
                "category": "general",
                "priority": "0",
                "audience_families": ["students"],
                "apply_mode": "none",
                "files": [_pdf("ok.pdf"), SimpleUploadedFile("page.html", b"<html></html>", "text/html")],
            },
        )
        self.assertEqual(response.status_code, 200)  # forma xətası
        with bypass_rls():
            self.assertFalse(Announcement.objects.filter(organization=self.w["org"], title="Yeni elan").exists())
        self.assertEqual(self._files(), [])

    def test_successful_upload_keeps_files(self):
        item = make_announcement(self.w, title="Uğurlu", publish=False)
        with bypass_rls():
            created = manage.add_attachments(self.request, self.w["org"], item, [_pdf("a.pdf"), _pdf("b.pdf")])
        self.assertEqual(len(created), 2)
        self.assertEqual(len(self._files()), 2)

    # ── silmə ───────────────────────────────────────────────────────────────
    def test_hard_delete_rollback_keeps_row_and_file(self):
        draft, attachment = self._draft_with_attachment()
        draft_pk = draft.pk  # `Model.delete()` nüsxənin pk-sını None edir
        with bypass_rls(), self.captureOnCommitCallbacks(execute=True) as callbacks:
            with self.assertRaises(_Boom), transaction.atomic():
                manage.transition(self.request, self.w["org"], self._scope(), draft, "delete")
                raise _Boom
        self.assertEqual(callbacks, [])  # rollback → silmə callback-i atıldı
        with bypass_rls():
            self.assertTrue(Announcement.objects.filter(pk=draft_pk).exists())
            self.assertTrue(AnnouncementAttachment.objects.filter(pk=attachment.pk).exists())
        self.assertTrue(default_storage.exists(attachment.file.name))

    def test_hard_delete_removes_file_only_after_commit(self):
        draft, attachment = self._draft_with_attachment()
        draft_pk = draft.pk
        with bypass_rls(), self.captureOnCommitCallbacks(execute=False) as callbacks:
            manage.transition(self.request, self.w["org"], self._scope(), draft, "delete")
            self.assertTrue(default_storage.exists(attachment.file.name))  # hələ commit yoxdur
        with bypass_rls():
            self.assertFalse(Announcement.objects.filter(pk=draft_pk).exists())
        for callback in callbacks:
            callback()
        self.assertFalse(default_storage.exists(attachment.file.name))

    def test_remove_attachment_rollback_keeps_file_commit_removes_it(self):
        draft, attachment = self._draft_with_attachment()
        with bypass_rls(), self.captureOnCommitCallbacks(execute=True) as callbacks:
            with self.assertRaises(_Boom), transaction.atomic():
                self.assertTrue(manage.remove_attachment(self.w["org"], draft, attachment.pk))
                raise _Boom
        self.assertEqual(callbacks, [])
        with bypass_rls():
            self.assertTrue(AnnouncementAttachment.objects.filter(pk=attachment.pk).exists())
        self.assertTrue(default_storage.exists(attachment.file.name))

        with bypass_rls(), self.captureOnCommitCallbacks(execute=True) as callbacks:
            self.assertTrue(manage.remove_attachment(self.w["org"], draft, attachment.pk))
        self.assertEqual(len(callbacks), 1)
        with bypass_rls():
            self.assertFalse(AnnouncementAttachment.objects.filter(pk=attachment.pk).exists())
        self.assertFalse(default_storage.exists(attachment.file.name))

    def test_storage_error_on_delete_is_logged_not_raised(self):
        draft, attachment = self._draft_with_attachment()
        with (
            bypass_rls(),
            mock.patch("django.core.files.storage.FileSystemStorage.delete", side_effect=OSError("disk")),
            self.assertLogs("apps.announcements.services.manage", level="WARNING"),
            self.captureOnCommitCallbacks(execute=True),
        ):
            self.assertTrue(manage.remove_attachment(self.w["org"], draft, attachment.pk))
        with bypass_rls():
            self.assertFalse(AnnouncementAttachment.objects.filter(pk=attachment.pk).exists())
