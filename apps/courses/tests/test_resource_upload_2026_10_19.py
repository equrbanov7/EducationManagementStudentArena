"""«Yeni Resurs» — tip üzrə format/ölçü, video yükləmə və oynatma (2026-10-19).

Sahib: «Video seçdim, IMG_0189.MOV → «Xəta baş verdi»». Kök səbəb: nginx-in qlobal 64M limiti iPhone
videosunu HTML 413 ilə kəsirdi, modal JS-i JSON gözlədiyindən ümumi toast çıxırdı; ipucu hər tip üçün
eyni idi. İndi: tip üzrə siyasət (apps/courses/resource_upload.py), ayrıca nginx location, aydın JSON xətaları.
"""

import re
import shutil
import tempfile
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import ProfileRole
from apps.courses.models import Course, CourseResource
from apps.courses.resource_upload import MB, POLICIES, UPLOAD_BODY_MAX_BYTES, format_mb, validate_resource_file
from core.upload_video import register_video_mimetypes, video_signature_ok

from .test_tenant_isolation import _assign_user_to_org, _create_org, _create_role, _login_with_org

User = get_user_model()
ROOT = Path(settings.BASE_DIR)

MP4 = b"\x00\x00\x00\x20ftypisom\x00\x00\x02\x00isomiso2avc1mp41" + b"\x00" * 64
MOV = b"\x00\x00\x00\x14ftypqt  \x00\x00\x00\x00qt  " + b"\x00\x00\x00\x08wide" + b"\x00" * 64
WEBM = b"\x1a\x45\xdf\xa3\x9f\x42\x86\x81\x01webm" + b"\x00" * 64
PDF = b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n1 0 obj\n" + b"\x00" * 64
ZIP = b"PK\x03\x04\x14\x00\x00\x00" + b"\x00" * 64
PNG = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR" + b"\x00" * 64


def _file(name, content, content_type="application/octet-stream", size=None):
    upload = SimpleUploadedFile(name, content, content_type=content_type)
    if size is not None:
        upload.size = size
    return upload


def _messages(kind, upload):
    try:
        validate_resource_file(upload, kind)
    except ValidationError as error:
        return " ".join(error.messages)
    return ""


class PolicyAndSignatureTest(SimpleTestCase):
    def test_per_type_formats_and_limits(self):
        self.assertEqual(POLICIES["video"].display_formats, "MP4, MOV, WEBM, M4V")
        self.assertEqual(POLICIES["video"].max_mb, 200)
        self.assertEqual(POLICIES["document"].display_formats, "PDF, DOC, DOCX, PPT, PPTX, XLS, XLSX, ODT, TXT")
        self.assertEqual(POLICIES["document"].max_mb, 50)
        file_formats = POLICIES["file"].display_formats
        for fmt in ("PDF", "DOCX", "ZIP", "RAR", "7Z", "PNG", "JPG", "GIF", "WEBP"):
            self.assertIn(fmt, file_formats)
        self.assertNotIn("MP4", file_formats)
        self.assertEqual(POLICIES["file"].max_mb, 100)

    def test_video_signatures(self):
        self.assertTrue(video_signature_ok(".mp4", MP4))
        self.assertTrue(video_signature_ok(".m4v", MP4))
        self.assertTrue(video_signature_ok(".mov", MOV))
        self.assertTrue(video_signature_ok(".webm", WEBM))
        self.assertFalse(video_signature_ok(".mp4", PDF))
        self.assertFalse(video_signature_ok(".mov", b"MZ\x90\x00" + b"\x00" * 60))
        self.assertFalse(video_signature_ok(".webm", MP4))
        self.assertFalse(video_signature_ok(".mp4", b"\x00\x00\x00\x04ftyp"))  # ölçü başlıqdan kiçik

    def test_size_formatting(self):
        self.assertEqual(format_mb(312 * MB), "312")
        self.assertEqual(format_mb(int(200.4 * MB)), "200,4")

    def test_m4v_gets_a_video_content_type(self):
        register_video_mimetypes()
        import mimetypes

        self.assertEqual(mimetypes.guess_type("a.m4v")[0], "video/x-m4v")
        self.assertEqual(mimetypes.guess_type("IMG_0189.MOV")[0], "video/quicktime")


class PerTypeValidationTest(SimpleTestCase):
    def test_video_accepts_iphone_mov_mp4_webm_m4v(self):
        self.assertEqual(_messages("video", _file("IMG_0189.MOV", MOV, "video/quicktime")), "")
        self.assertEqual(_messages("video", _file("lecture.mp4", MP4, "video/mp4")), "")
        self.assertEqual(_messages("video", _file("clip.webm", WEBM, "video/webm")), "")
        self.assertEqual(_messages("video", _file("clip.m4v", MP4, "video/x-m4v")), "")
        # Brauzer tipi tanımayanda octet-stream göndərir — imza həlledicidir.
        self.assertEqual(_messages("video", _file("clip.mov", MOV)), "")

    def test_video_rejects_wrong_extension_with_clear_message(self):
        message = _messages("video", _file("setup.exe", b"MZ\x90\x00" * 8))
        self.assertIn("Bu format «Video» üçün qəbul edilmir: .exe. İcazə verilənlər: MP4, MOV, WEBM, M4V", message)
        message = _messages("video", _file("slides.pdf", PDF, "application/pdf"))
        self.assertIn("«Sənəd» tipini seçin", message)

    def test_video_rejects_fake_content(self):
        message = _messages("video", _file("fake.mp4", PDF, "video/mp4"))
        self.assertIn("Faylın məzmunu .mp4 formatına uyğun deyil", message)
        self.assertIn(
            "uyğun deyil", _messages("video", _file("page.mov", b"<html><script>x</script>", "video/quicktime"))
        )

    def test_video_rejects_html_mime_and_double_extension(self):
        self.assertNotEqual(_messages("video", _file("clip.mp4", MP4, "text/html")), "")
        self.assertIn("bloklanıb", _messages("video", _file("shell.php.mp4", MP4, "video/mp4")))

    def test_size_limit_per_type(self):
        message = _messages("video", _file("big.mov", MOV, "video/quicktime", size=312 * MB))
        self.assertEqual(message, "Fayl çox böyükdür: 312 MB (maks. 200 MB)")
        self.assertEqual(_messages("video", _file("ok.mov", MOV, "video/quicktime", size=199 * MB)), "")
        message = _messages("document", _file("big.pdf", PDF, "application/pdf", size=51 * MB))
        self.assertEqual(message, "Fayl çox böyükdür: 51 MB (maks. 50 MB)")
        message = _messages("file", _file("big.zip", ZIP, "application/zip", size=101 * MB))
        self.assertEqual(message, "Fayl çox böyükdür: 101 MB (maks. 100 MB)")

    def test_empty_file(self):
        self.assertEqual(_messages("video", _file("empty.mp4", b"", "video/mp4")), "Fayl boşdur.")

    def test_document_allow_and_deny(self):
        self.assertEqual(_messages("document", _file("a.pdf", PDF, "application/pdf")), "")
        self.assertEqual(_messages("document", _file("a.docx", ZIP)), "")
        self.assertEqual(_messages("document", _file("a.odt", ZIP, "application/vnd.oasis.opendocument.text")), "")
        self.assertEqual(_messages("document", _file("notes.txt", "Salam, dünya\n".encode(), "text/plain")), "")
        self.assertNotEqual(_messages("document", _file("a.pdf", b"GIF89a" + b"\x00" * 40, "application/pdf")), "")
        self.assertNotEqual(_messages("document", _file("x.txt", b"<html><script>1</script>", "text/plain")), "")
        self.assertNotEqual(_messages("document", _file("x.txt", b"MZ\x00\x00binary\x00", "text/plain")), "")
        self.assertNotEqual(_messages("document", _file("a.odt", PDF)), "")
        message = _messages("document", _file("lecture.mp4", MP4, "video/mp4"))
        self.assertIn("Bu format «Sənəd» üçün qəbul edilmir: .mp4", message)
        self.assertIn("«Video» tipini seçin", message)
        self.assertIn("qəbul edilmir: .zip", _messages("document", _file("a.zip", ZIP, "application/zip")))

    def test_file_allows_archives_and_images_but_not_video(self):
        self.assertEqual(_messages("file", _file("a.zip", ZIP, "application/zip")), "")
        self.assertEqual(_messages("file", _file("a.rar", b"Rar!\x1a\x07\x01\x00" + b"\x00" * 40)), "")
        self.assertEqual(_messages("file", _file("a.7z", b"7z\xbc\xaf\x27\x1c" + b"\x00" * 40)), "")
        self.assertEqual(_messages("file", _file("a.png", PNG, "image/png")), "")
        self.assertEqual(_messages("file", _file("a.pdf", PDF, "application/pdf")), "")
        self.assertNotEqual(_messages("file", _file("a.png", b"<svg onload=1>", "image/png")), "")
        self.assertNotEqual(_messages("file", _file("a.zip", PDF, "application/zip")), "")
        self.assertIn("«Video» tipini seçin", _messages("file", _file("clip.mov", MOV, "video/quicktime")))
        self.assertIn("qəbul edilmir: .svg", _messages("file", _file("x.svg", b"<svg/>", "image/svg+xml")))


_TMP_MEDIA = tempfile.mkdtemp(prefix="ems-res-upload-")


@override_settings(MEDIA_ROOT=_TMP_MEDIA)
class AddResourceEndpointTest(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(_TMP_MEDIA, ignore_errors=True)

    def setUp(self):
        self.owner = User.objects.create_user("res_up_owner", "res_up_owner@orga.com", "StrongPass123!")
        self.other = User.objects.create_user("res_up_other", "res_up_other@orga.com", "StrongPass123!")
        self.org = _create_org("ResUp Org", "res-up-org", self.owner)
        role = _create_role(self.org, "teacher", level=60, permissions=["course.*"])
        _assign_user_to_org(self.owner, self.org, ProfileRole.TEACHER, role)
        _assign_user_to_org(self.other, self.org, ProfileRole.TEACHER, role)
        self.course = Course.objects.create(
            owner=self.owner, title="Video kurs", status="published", organization=self.org
        )
        self.url = reverse("courses:add_resource", kwargs={"course_id": self.course.id})
        self.client = Client()
        _login_with_org(self.client, self.owner, self.org)

    def _post(self, data, client=None, **extra):
        return (client or self.client).post(self.url, data, HTTP_X_REQUESTED_WITH="XMLHttpRequest", **extra)

    def _video(self, kind="video", upload=None):
        return {
            "title": "Mühazirə 1",
            "resource_type": kind,
            "file": upload or _file("IMG_0189.MOV", MOV, "video/quicktime"),
        }

    def test_url_has_the_fixed_nginx_prefix(self):
        self.assertEqual(self.url, f"/courses/resource-upload/{self.course.id}/")

    def test_iphone_mov_video_upload_succeeds(self):
        response = self._post(self._video())
        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(response.json()["success"])
        resource = CourseResource.objects.get(course=self.course)
        self.assertEqual(resource.resource_type, "video")
        self.assertRegex(resource.file.name, r"^course_resources/\d{4}/\d{2}/[0-9a-f]{32}\.mov$")
        self.assertNotIn("IMG_0189", resource.file.name)
        self.assertTrue(resource.is_video_file and resource.is_quicktime_video)
        self.assertTrue(Path(_TMP_MEDIA, resource.file.name).is_file())

    def test_video_bigger_than_global_5mb_body_cap_is_accepted(self):
        content = MP4 + b"\x00" * (6 * MB)
        response = self._post(self._video(upload=_file("lecture.mp4", content, "video/mp4")))
        self.assertEqual(response.status_code, 200, response.content[:300])
        self.assertEqual(CourseResource.objects.get(course=self.course).file.size, len(content))

    def test_wrong_format_returns_field_error_json(self):
        response = self._post(self._video(upload=_file("setup.exe", b"MZ" * 40)))
        self.assertEqual(response.status_code, 400)
        errors = response.json()["errors"]
        self.assertEqual(
            errors["file"], ["Bu format «Video» üçün qəbul edilmir: .exe. İcazə verilənlər: MP4, MOV, WEBM, M4V"]
        )
        self.assertFalse(CourseResource.objects.exists())

    def test_fake_video_content_is_rejected(self):
        response = self._post(self._video(upload=_file("fake.mp4", PDF, "video/mp4")))
        self.assertEqual(response.status_code, 400)
        self.assertIn("Faylın məzmunu .mp4 formatına uyğun deyil", response.json()["errors"]["file"][0])

    def test_file_type_requires_a_file(self):
        response = self._post({"title": "Boş", "resource_type": "video"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["errors"]["file"], ["«Video» üçün fayl seçin."])

    def test_body_over_cap_is_rejected_before_parsing(self):
        response = self._post(self._video(), CONTENT_LENGTH=str(UPLOAD_BODY_MAX_BYTES + 1))
        self.assertEqual(response.status_code, 413)
        self.assertEqual(response.json()["errors"]["__all__"], ["Fayl çox böyükdür: 208 MB (maks. 200 MB)"])
        self.assertFalse(CourseResource.objects.exists())

    def test_link_validation(self):
        ok = self._post({"title": "Docs", "resource_type": "link", "url": "https://docs.python.org/3/"})
        self.assertEqual(ok.status_code, 200)
        for bad in ("ftp://example.com/a", "javascript:alert(1)"):
            response = self._post({"title": "Bad", "resource_type": "link", "url": bad})
            self.assertEqual(response.status_code, 400, bad)
            self.assertIn("url", response.json()["errors"])
        missing = self._post({"title": "Yox", "resource_type": "link"})
        self.assertEqual(missing.json()["errors"]["url"], ["Link üçün URL daxil edin (http:// və ya https://)."])
        with_file = self._post(
            {"title": "Q", "resource_type": "link", "url": "https://a.az/", "file": _file("a.pdf", PDF)}
        )
        self.assertEqual(with_file.status_code, 400)
        self.assertIn("file", with_file.json()["errors"])
        url_on_video = self._post(dict(self._video(), url="https://a.az/"))
        self.assertIn("url", url_on_video.json()["errors"])
        self.assertEqual(CourseResource.objects.count(), 1)

    def test_anonymous_gets_401_json(self):
        response = self._post(self._video(), client=Client())
        self.assertEqual(response.status_code, 401)
        self.assertIn("Sessiyanız bitib", response.json()["errors"]["__all__"][0])

    def test_non_owner_teacher_gets_404(self):
        client = Client()
        _login_with_org(client, self.other, self.org)
        response = self._post(self._video(), client=client)
        self.assertEqual(response.status_code, 404)
        self.assertFalse(CourseResource.objects.exists())

    def test_get_is_not_allowed(self):
        self.assertEqual(self.client.get(self.url).status_code, 405)

    def test_csrf_is_still_enforced(self):
        client = Client(enforce_csrf_checks=True)
        _login_with_org(client, self.owner, self.org)
        self.assertEqual(self._post(self._video(), client=client).status_code, 403)
        page = client.get(reverse("courses:course_dashboard", kwargs={"course_id": self.course.id}))
        token = re.search(rb'name="csrfmiddlewaretoken" value="([^"]+)"', page.content).group(1).decode()
        response = self._post(dict(self._video(), csrfmiddlewaretoken=token), client=client)
        self.assertEqual(response.status_code, 200, response.content[:300])

    def test_dashboard_renders_per_type_hints_and_video_player(self):
        self._post(self._video())
        page = self.client.get(reverse("courses:course_dashboard", kwargs={"course_id": self.course.id}))
        html = page.content.decode()
        self.assertIn(f'action="{self.url}"', html)
        self.assertIn('data-accept=".mp4,.mov,.webm,.m4v"', html)
        self.assertIn("Dəstəklənən formatlar: MP4, MOV, WEBM, M4V · maks. 200 MB", html)
        self.assertIn("iPhone videosu: mümkünsə MP4 seçin", html)
        self.assertIn(f'data-max-bytes="{200 * MB}"', html)
        self.assertIn("data-resource-dropzone", html)
        self.assertRegex(html, r'<video class="cd-res-video__player" controls playsinline preload="metadata"')
        self.assertIn("iPhone (.MOV) videosu bəzi brauzerlərdə", html)
        self.assertIn("courses/css/course_resource_media.css", html)

    @override_settings(MEDIA_ACCEL_REDIRECT_URL="/internal_media")
    def test_video_is_served_inline_with_video_content_type(self):
        self._post(self._video())
        resource = CourseResource.objects.get(course=self.course)
        response = self.client.get(resource.file.url, HTTP_RANGE="bytes=0-99")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["X-Accel-Redirect"], f"/internal_media/{resource.file.name}")
        self.assertEqual(response["Content-Type"], "video/quicktime")
        self.assertNotIn("Content-Disposition", response)


class NginxUploadLocationTest(SimpleTestCase):
    def test_upload_location_allows_the_largest_type_and_keeps_proxy_headers(self):
        conf = (ROOT / "docker/nginx/nginx.conf").read_text(encoding="utf-8")
        match = re.search(r"location \^~ /courses/resource-upload/ \{(.*?)\n    \}", conf, re.S)
        self.assertIsNotNone(match)
        body = match.group(1)
        limit_mb = int(re.search(r"client_max_body_size\s+(\d+)m;", body).group(1))
        self.assertGreater(limit_mb * MB, UPLOAD_BODY_MAX_BYTES)
        self.assertIn("proxy_request_buffering on;", body)
        self.assertIn("limit_req zone=emsarena_general burst=1000 nodelay;", body)
        for header in ("Host              $host", "X-Forwarded-For   $remote_addr", "X-EMS-Zone        $ems_zone"):
            self.assertIn(f"proxy_set_header {header};", body)
        # Qlobal limit dəyişmir — böyük gövdə yalnız bu prefiksə verilir.
        self.assertIn("    client_max_body_size 64M;", conf)
