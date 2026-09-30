"""«Akademik fəaliyyət» 2026-10-01 (sahib): yeni növlər + rol qapısı, fayl
qoşması (PDF/şəkil), əvəzləmə/silmə, fayl təmizliyi, sahiblik və giriş siyasəti.

Giriş siyasəti (services/academic_attachments.check_attachment_media_access):
qoşma, qeydi açıq profildə görə bilən HƏR DAXİL OLMUŞ istifadəçiyə açıqdır;
anonim → girişə yönləndirilir; heç bir qeydə bağlı olmayan yol → 404.
"""

import io
import shutil
import tempfile

from django.contrib.auth import get_user_model
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from PIL import Image

from apps.accounts.models import AcademicProfileItem
from apps.accounts.services import academic_profile
from apps.accounts.services.academic_attachments import check_attachment_media_access
from core.roles import ProfileRole

User = get_user_model()
Kind = AcademicProfileItem.Kind

PDF_BYTES = b"%PDF-1.4\n1 0 obj << /Type /Catalog >> endobj\ntrailer << /Root 1 0 R >>\n%%EOF\n"


def _make_user(username, role):
    user = User.objects.create_user(username=username, email=f"{username}@example.com", password="testpass123")
    profile = user.profile
    profile.role = role
    profile.save(update_fields=["role", "updated_at"])
    return user


def _pdf(name="sertifikat.pdf", content=PDF_BYTES):
    return SimpleUploadedFile(name, content, content_type="application/pdf")


def _image_bytes(fmt="PNG", size=(60, 40), exif=None):
    buffer = io.BytesIO()
    image = Image.new("RGB", size, (200, 30, 30))
    kwargs = {"exif": exif.tobytes()} if exif is not None else {}
    image.save(buffer, format=fmt, **kwargs)
    return buffer.getvalue()


def _png(name="diplom.png"):
    return SimpleUploadedFile(name, _image_bytes("PNG"), content_type="image/png")


class _MediaSandbox(TestCase):
    """Hər sinif müvəqqəti MEDIA_ROOT-da işləyir (real media/ çirklənmir)."""

    @classmethod
    def setUpClass(cls):
        cls._media_root = tempfile.mkdtemp(prefix="acad_media_")
        cls._media_override = override_settings(MEDIA_ROOT=cls._media_root)
        cls._media_override.enable()
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls._media_override.disable()
        shutil.rmtree(cls._media_root, ignore_errors=True)

    def setUp(self):
        self.teacher = _make_user("acad10_teacher", ProfileRole.TEACHER)
        self.student = _make_user("acad10_student", ProfileRole.STUDENT)
        self.url = reverse("accounts:academic_items_api")

    def _post(self, user, **data):
        self.client.force_login(user)
        with self.captureOnCommitCallbacks(execute=True):
            return self.client.post(self.url, data=data)


class KindsAndGatingTest(_MediaSandbox):
    def test_new_kinds_exist_in_display_order(self):
        self.assertEqual(
            [k.value for k in Kind],
            [
                "subject",
                "education",
                "experience",
                "publication",
                "book",
                "conference",
                "project",
                "patent",
                "certificate",
                "award",
            ],
        )

    def test_teacher_gets_all_kinds_student_loses_teaching_only(self):
        teacher_kinds = {str(k.value) for k in academic_profile.allowed_kinds_for({}, user=self.teacher)}
        student_kinds = {str(k.value) for k in academic_profile.allowed_kinds_for({}, user=self.student)}
        self.assertEqual(teacher_kinds, {str(k.value) for k in Kind})
        self.assertEqual(teacher_kinds - student_kinds, {"subject", "book", "patent"})
        for kind in ("education", "experience", "project", "award", "certificate", "publication", "conference"):
            self.assertIn(kind, student_kinds)

    def test_student_cannot_create_book_or_patent_but_can_create_award(self):
        for kind in ("book", "patent"):
            response = self._post(self.student, action="create", kind=kind, title="X")
            self.assertEqual(response.status_code, 400, kind)
        response = self._post(self.student, action="create", kind="award", title="Olimpiada qalibi")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.student.academic_items.get().kind, Kind.AWARD)

    def test_teacher_creates_book(self):
        response = self._post(self.teacher, action="create", kind="book", title="Alqoritmlər", detail="Elm, 2024")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Alqoritmlər", response.json()["html"])

    def test_manage_html_has_hints_and_compact_empty_groups(self):
        response = self._post(self.teacher, action="create", kind="publication", title="Konsensus")
        html = response.json()["html"]
        # Dolu qrup kart kimi, qalan 9 növ «Boş bölmələr (9)» çip sırasında.
        self.assertEqual(html.count('class="academic-items-group"'), 1)
        self.assertIn("Boş bölmələr (9)", html)
        self.assertEqual(html.count("academic-items-chip js-academic-item-add"), 9)
        self.assertNotIn("Hələ qeyd əlavə edilməyib.</p>", html)
        # Növ üzrə placeholder-lər və fayl icazəsi modal üçün data-atributlarda.
        self.assertIn('data-detail-hint="Jurnal, cild / nömrə, həmmüəlliflər"', html)
        self.assertIn('data-kind="subject"', html)

    def test_edit_profile_page_renders_new_ui(self):
        AcademicProfileItem.objects.create(user=self.teacher, kind=Kind.EDUCATION, title="Magistr")
        self.client.force_login(self.teacher)
        response = self.client.get(reverse("accounts:profile") + "?section=edit-profile")
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn("academic_items_manage.css", html)
        self.assertIn('id="academicItemAttachmentField"', html)
        self.assertIn("modal-fullscreen-sm-down", html)
        self.assertIn("Magistr", html)


class AttachmentUploadTest(_MediaSandbox):
    def test_pdf_upload_happy_path(self):
        from apps.audit.models import AuditLog

        response = self._post(
            self.teacher, action="create", kind="certificate", title="CCNA", attachment=_pdf("CCNA sertifikat.pdf")
        )
        self.assertEqual(response.status_code, 200, response.content)
        item = self.teacher.academic_items.get()
        self.assertTrue(item.attachment.name.startswith(f"academic_attachments/{self.teacher.id}/"))
        self.assertTrue(item.attachment.name.endswith(".pdf"))
        self.assertNotIn("CCNA", item.attachment.name)  # orijinal ad yolda saxlanmır
        self.assertEqual(item.attachment_name, "CCNA sertifikat.pdf")
        self.assertEqual(item.attachment_size, len(PDF_BYTES))
        self.assertFalse(item.attachment_thumb)
        self.assertTrue(default_storage.exists(item.attachment.name))
        self.assertIn(item.attachment_url, response.json()["html"])
        log = AuditLog.objects.get(user=self.teacher, resource_type="AcademicProfileItem", action="create")
        self.assertEqual(log.changes, {"attachment": "uploaded"})

    def test_png_upload_is_reencoded_with_thumbnail(self):
        response = self._post(self.student, action="create", kind="education", title="Bakalavr", attachment=_png())
        self.assertEqual(response.status_code, 200, response.content)
        item = self.student.academic_items.get()
        self.assertTrue(item.attachment.name.endswith(".png"))
        self.assertTrue(item.attachment_thumb.name.endswith(".jpg"))
        self.assertTrue(default_storage.exists(item.attachment_thumb.name))
        with default_storage.open(item.attachment.name) as stored, Image.open(stored) as image:
            self.assertEqual(image.format, "PNG")
            self.assertEqual(image.size, (60, 40))

    def test_jpeg_metadata_is_stripped(self):
        exif = Image.Exif()
        exif[0x010F] = "GizliKamera"  # Make
        upload = SimpleUploadedFile("foto.jpg", _image_bytes("JPEG", exif=exif), content_type="image/jpeg")
        response = self._post(self.teacher, action="create", kind="award", title="Mükafat", attachment=upload)
        self.assertEqual(response.status_code, 200, response.content)
        item = self.teacher.academic_items.get()
        with default_storage.open(item.attachment.name) as stored:
            data = stored.read()
        self.assertNotIn(b"GizliKamera", data)

    def _assert_rejected(self, upload, kind="certificate"):
        response = self._post(self.teacher, action="create", kind=kind, title="Rədd", attachment=upload)
        self.assertEqual(response.status_code, 400, response.content)
        self.assertFalse(self.teacher.academic_items.exists())
        return response.json()["error"]

    def test_svg_rejected(self):
        svg = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
        self._assert_rejected(SimpleUploadedFile("logo.svg", svg, content_type="image/svg+xml"))

    def test_html_renamed_pdf_rejected(self):
        html = b"<html><body><script>alert(1)</script></body></html>"
        self._assert_rejected(SimpleUploadedFile("fake.pdf", html, content_type="application/pdf"))

    def test_comment_prefixed_html_renamed_pdf_rejected(self):
        # `%PDF` ilk 1 KB-da olsa da, fayl onunla BAŞLAMIRSA rədd (sərt yoxlama).
        html = b"<!-- %PDF-1.4 --><script>alert(1)</script>"
        self._assert_rejected(SimpleUploadedFile("fake.pdf", html, content_type="application/pdf"))

    def test_text_renamed_png_rejected(self):
        self._assert_rejected(SimpleUploadedFile("fake.png", b"not an image at all", content_type="image/png"))

    def test_png_content_with_jpg_extension_rejected(self):
        self._assert_rejected(SimpleUploadedFile("fake.jpg", _image_bytes("PNG"), content_type="image/jpeg"))

    def test_executable_and_unknown_extensions_rejected(self):
        self._assert_rejected(SimpleUploadedFile("run.exe", b"MZ\x90\x00", content_type="application/octet-stream"))
        self._assert_rejected(SimpleUploadedFile("doc.docx", b"PK\x03\x04", content_type="application/zip"))

    def test_oversized_rejected(self):
        big = PDF_BYTES + b"0" * (10 * 1024 * 1024)
        error = self._assert_rejected(_pdf("big.pdf", big))
        self.assertIn("10", error)

    def test_attachment_not_allowed_for_subject_and_experience(self):
        self._assert_rejected(_pdf(), kind="subject")
        self._assert_rejected(_pdf(), kind="experience")


class AttachmentReplaceRemoveTest(_MediaSandbox):
    def setUp(self):
        super().setUp()
        self._post(self.teacher, action="create", kind="publication", title="Məqalə", attachment=_png())
        self.item = self.teacher.academic_items.get()
        self.old_names = [self.item.attachment.name, self.item.attachment_thumb.name]

    def _update(self, user=None, **extra):
        data = {"action": "update", "item_id": str(self.item.pk), "kind": "publication", "title": "Məqalə"}
        data.update(extra)
        return self._post(user or self.teacher, **data)

    def test_replace_deletes_old_files(self):
        from apps.audit.models import AuditLog

        response = self._update(attachment=_pdf())
        self.assertEqual(response.status_code, 200, response.content)
        self.item.refresh_from_db()
        self.assertTrue(self.item.attachment.name.endswith(".pdf"))
        self.assertFalse(self.item.attachment_thumb)
        self.assertTrue(default_storage.exists(self.item.attachment.name))
        for name in self.old_names:
            self.assertFalse(default_storage.exists(name), name)
        log = AuditLog.objects.filter(resource_type="AcademicProfileItem", action="update").latest("id")
        self.assertEqual(log.changes, {"attachment": "replaced"})

    def test_update_without_file_keeps_attachment(self):
        response = self._update(detail="Jurnal")
        self.assertEqual(response.status_code, 200)
        self.item.refresh_from_db()
        self.assertEqual(self.item.attachment.name, self.old_names[0])
        self.assertTrue(default_storage.exists(self.old_names[0]))

    def test_remove_attachment_clears_fields_and_files(self):
        response = self._update(remove_attachment="1")
        self.assertEqual(response.status_code, 200)
        self.item.refresh_from_db()
        self.assertFalse(self.item.attachment)
        self.assertEqual(self.item.attachment_name, "")
        self.assertIsNone(self.item.attachment_size)
        for name in self.old_names:
            self.assertFalse(default_storage.exists(name), name)

    def test_delete_item_deletes_files(self):
        response = self._post(self.teacher, action="delete", item_id=str(self.item.pk))
        self.assertEqual(response.status_code, 200)
        for name in self.old_names:
            self.assertFalse(default_storage.exists(name), name)

    def test_user_cascade_delete_deletes_files(self):
        with self.captureOnCommitCallbacks(execute=True):
            self.teacher.delete()
        for name in self.old_names:
            self.assertFalse(default_storage.exists(name), name)

    def test_other_user_cannot_modify_or_attach(self):
        other = _make_user("acad10_other", ProfileRole.TEACHER)
        response = self._update(user=other, attachment=_pdf())
        self.assertEqual(response.status_code, 404)
        response = self._update(user=other, remove_attachment="1")
        self.assertEqual(response.status_code, 404)
        response = self._post(other, action="delete", item_id=str(self.item.pk))
        self.assertEqual(response.status_code, 404)
        self.item.refresh_from_db()
        self.assertEqual(self.item.attachment.name, self.old_names[0])
        for name in self.old_names:
            self.assertTrue(default_storage.exists(name), name)
        self.assertFalse(other.academic_items.exists())


class AttachmentAccessPolicyTest(_MediaSandbox):
    def setUp(self):
        super().setUp()
        self._post(self.teacher, action="create", kind="certificate", title="CCNA", attachment=_pdf())
        self._post(self.teacher, action="create", kind="award", title="Mükafat", attachment=_png())
        self.pdf_item = self.teacher.academic_items.get(kind=Kind.CERTIFICATE)
        self.img_item = self.teacher.academic_items.get(kind=Kind.AWARD)
        self.client.logout()

    def test_owner_and_other_logged_in_user_can_open(self):
        for viewer in (self.teacher, self.student):
            self.client.force_login(viewer)
            response = self.client.get(self.pdf_item.attachment_url)
            self.assertEqual(response.status_code, 200, viewer.username)
            self.assertEqual(response["Content-Type"], "application/pdf")
            self.assertEqual(response["X-Content-Type-Options"], "nosniff")
            self.assertIn("no-store", response["Cache-Control"])
            b"".join(response.streaming_content)
            thumb = self.client.get(self.img_item.attachment_thumb_url)
            self.assertEqual(thumb.status_code, 200)
            b"".join(thumb.streaming_content)

    def test_anonymous_is_redirected_to_login(self):
        response = self.client.get(self.pdf_item.attachment_url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response["Location"])

    def test_unknown_or_stale_path_is_404(self):
        self.client.force_login(self.student)
        path = f"academic_attachments/{self.teacher.id}/{'0' * 32}.pdf"
        response = self.client.get(reverse("protected_media", kwargs={"path": path}))
        self.assertEqual(response.status_code, 404)
        old_url = self.pdf_item.attachment_url
        self._post(
            self.teacher,
            action="update",
            item_id=str(self.pdf_item.pk),
            kind="certificate",
            title="CCNA",
            remove_attachment="1",
        )
        self.client.force_login(self.student)
        self.assertEqual(self.client.get(old_url).status_code, 404)

    def test_checker_rejects_malformed_and_foreign_paths(self):
        name = self.pdf_item.attachment.name
        self.assertTrue(check_attachment_media_access(self.student, name))
        # Başqa istifadəçi id-si altında eyni fayl adı → yox.
        foreign = name.replace(f"/{self.teacher.id}/", f"/{self.student.id}/")
        self.assertFalse(check_attachment_media_access(self.student, foreign))
        self.assertFalse(check_attachment_media_access(self.student, "academic_attachments/x/y.pdf"))
        self.assertFalse(check_attachment_media_access(self.student, "academic_attachments/../avatars/a.png"))

    def test_public_profile_shows_chip_only_to_logged_in_viewers(self):
        url = reverse("accounts:public_profile", args=[self.teacher.username])
        anonymous = self.client.get(url)
        self.assertContains(anonymous, "CCNA")
        self.assertNotContains(anonymous, self.pdf_item.attachment_url)
        self.client.force_login(self.student)
        logged_in = self.client.get(url)
        self.assertContains(logged_in, self.pdf_item.attachment_url)
        self.assertContains(logged_in, self.img_item.attachment_thumb_url)
        # Orijinal fayl adı üçüncü şəxsə göstərilmir.
        self.assertNotContains(logged_in, "sertifikat.pdf")

    def test_profile_info_shows_chip_to_owner(self):
        self.client.force_login(self.teacher)
        response = self.client.get(reverse("accounts:profile") + "?section=profile-info")
        self.assertContains(response, self.pdf_item.attachment_url)
        self.assertContains(response, "academic_attachment.css")
