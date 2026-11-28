"""FAQ media is read through the same guide/tenant audience, for both tracks and videos."""

from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock

from django.core.files.base import ContentFile
from django.core.management import call_command
from django.http import HttpResponse
from django.test import AsyncRequestFactory, Client, RequestFactory, SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from apps.accounts.faq_storage import PrivateGuideObjects
from apps.accounts.models import FaqVideoGuide
from apps.accounts.views._helpers import _load_user_profile, _role_capabilities
from apps.accounts.views.profile.faq import faq_capabilities, faq_page
from apps.accounts.views.profile.faq_catalog import GUIDES
from apps.accounts.views.profile.faq_media import BUILTIN_DIR, _stream
from apps.subject_folder.tests import factories as f
from core.static_middleware import StaticFilesMiddleware


def _url(key, extension="mp4", public=False):
    route = "faq_public_media" if public else "faq_media"
    return reverse("accounts:" + route, kwargs={"key": key, "extension": extension})


def _client(user, org):
    client = Client()
    client.force_login(user)
    session = client.session
    session["active_organization"] = org.slug
    session.save()
    return client


@override_settings(UNIVERSITY_MODE=True)
class FAQMediaAccessTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org = f.make_org()
        cls.other = f.make_org()
        cls.student = f.make_student(cls.org)
        cls.teacher = f.make_teacher(cls.org)
        f.activate_member(cls.other, cls.student, "teacher", permissions=["grade.input"], level=60)

    def test_student_entire_catalog_matches_visible_active_tenant_guides(self):
        client = _client(self.student, self.org)
        entry = client.get(reverse("accounts:profile"), {"section": "faq"})
        self.assertEqual(entry.status_code, 200)
        request = entry.wsgi_request
        profile, _ = _load_user_profile(request.user)
        caps = faq_capabilities(request, _role_capabilities(request.user, profile))
        visible = {
            g.key for g in faq_page({}, caps["allowed_sections"], caps, request=request)["page"].paginator.object_list
        }
        self.assertTrue({"grades", "journal-limit", "grade-reconciliation"} <= visible)
        self.assertFalse({"teacher-journal-support", "room-monitor", "journal-entry", "schedule-admin"} & visible)
        self.assertNotIn(
            "tour-telebe", visible
        )  # This member lacks the appeal and support operations in the full tour.
        self.assertNotIn("tour-muellim", visible)
        media = {g.video for g in GUIDES if g.key in visible}
        self.assertIn("document-verify", media)
        if "open-application" in visible:
            self.assertIn("section-applications", media)
        self.assertFalse({"document", "support", "workload-explained", "workload-practice", "language-cohort"} & media)
        for guide in GUIDES:
            expected = 200 if guide.key in visible else 404
            for ext in ("mp4", "vtt"):
                response = client.head(_url(guide.key, ext))
                self.assertEqual(response.status_code, expected, (guide.key, ext))
                self.assertIn("no-store", response["Cache-Control"])
        staff = _client(self.student, self.other)
        for ext in ("mp4", "vtt"):
            self.assertEqual(staff.head(_url("journal-entry", ext)).status_code, 200)
            self.assertEqual(staff.head(_url("journal-limit", ext)).status_code, 404)
            self.assertEqual(staff.head(_url("tour-muellim", ext)).status_code, 404)
            self.assertEqual(staff.head(_url("tour-telebe", ext)).status_code, 404)

    def test_public_login_and_byte_ranges(self):
        for key in ("login", "recover"):
            for ext in ("mp4", "vtt"):
                url = _url(key, ext, public=True)
                path = BUILTIN_DIR / f"{key}.{ext}"
                full = path.read_bytes()
                head = self.client.head(url)
                self.assertEqual(head.status_code, 200)
                self.assertEqual(int(head["Content-Length"]), len(full))
                self.assertEqual(head.content, b"")
                for value, selected, start in (
                    ("bytes=0-4", full[:5], 0),
                    ("bytes=-8", full[-8:], len(full) - 8),
                    (f"bytes={len(full)-3}-", full[-3:], len(full) - 3),
                ):
                    result = self.client.get(url, HTTP_RANGE=value)
                    self.assertEqual(result.status_code, 206)
                    self.assertEqual(b"".join(result.streaming_content), selected)
                    self.assertEqual(result["Content-Range"], f"bytes {start}-{start+len(selected)-1}/{len(full)}")
                    self.assertEqual(int(result["Content-Length"]), len(selected))
                self.assertEqual(self.client.get(url, HTTP_RANGE=f"bytes={len(full)}-").status_code, 416)
                self.assertEqual(self.client.head(_url(key, ext)).status_code, 404)
        for key in ("grades", "journal-entry", "room-monitor", "custom-123"):
            self.assertEqual(self.client.head(_url(key, public=True)).status_code, 404)
            self.assertEqual(self.client.head(_url(key)).status_code, 404)
        html = self.client.get(reverse("accounts:login_help")).content.decode()
        self.assertIn(_url("login", public=True), html)
        self.assertNotIn(_url("login"), html)

    def test_overrides_revoke_media_and_keep_public_and_other_tenant_isolated(self):
        with TemporaryDirectory() as tmp, self.settings(MEDIA_ROOT=tmp):
            guide = FaqVideoGuide.objects.create(organization=self.org, key="login", audience_roles=["student"])
            guide.video_file.save("clip.mp4", ContentFile(b"tenant-student-video"))
            client = _client(self.student, self.org)
            self.assertEqual(b"".join(client.get(_url("login")).streaming_content), b"tenant-student-video")
            self.assertEqual(client.head(_url("login", "vtt")).status_code, 404)
            self.assertEqual(
                int(client.head(_url("login", public=True))["Content-Length"]),
                (BUILTIN_DIR / "login.mp4").stat().st_size,
            )
            self.assertEqual(_client(self.teacher, self.org).head(_url("login")).status_code, 404)
            other = _client(self.student, self.other)
            self.assertEqual(
                int(other.head(_url("login"))["Content-Length"]), (BUILTIN_DIR / "login.mp4").stat().st_size
            )
            guide.subtitle_file.save("sub.vtt", ContentFile(b"WEBVTT\n"))
            self.assertEqual(b"".join(client.get(_url("login", "vtt")).streaming_content), b"WEBVTT\n")
            with self.assertRaises(ValueError):
                _ = guide.video_file.url
            self.assertEqual(client.get("/media/" + guide.video_file.name).status_code, 404)
            guide.hidden = True
            guide.save(update_fields=["hidden"])
            self.assertEqual(client.head(_url("login")).status_code, 404)
            self.assertEqual(client.head(_url("login", "vtt")).status_code, 404)
            self.assertEqual(self.client.head(_url("login", "vtt", public=True)).status_code, 200)
            # Even a row with a mismatched stored key cannot serve another organization's object.
            injected = FaqVideoGuide.objects.create(
                organization=self.other, key="custom-test", video_file=guide.video_file.name
            )
            self.assertEqual(other.head(_url(injected.key)).status_code, 404)
            self.assertEqual(client.head(_url(injected.key)).status_code, 404)


class FAQStreamTests(SimpleTestCase):
    async def test_asgi_stream_delivers_bounded_slice_and_closes(self):
        payload = b"x" * 700000
        raw = BytesIO(payload)

        def opened(start, end, partial):
            raw.seek(start)
            return raw

        request = AsyncRequestFactory().get("/", headers={"range": "bytes=9-610007"})
        response = _stream(request, size=len(payload), open_stream=opened, content_type="video/mp4")
        self.assertTrue(response.is_async)
        chunks = [part async for part in response.streaming_content]
        self.assertGreater(len(chunks), 1)
        self.assertEqual(b"".join(chunks), payload[9:610008])
        response.close()
        self.assertTrue(raw.closed)

    def test_private_s3_reads_only_requested_range_and_exposes_no_url(self):
        storage = PrivateGuideObjects(
            bucket_name="private-demo", access_key="test", secret_key="test", location="backups"
        )
        fake = Mock()
        fake.Object.return_value.get.return_value = {"Body": BytesIO(b"xyz")}
        storage._bucket = fake
        body = storage.open_range("faq_guides/a/video.mp4", "bytes=20-22")
        self.assertEqual(body.read(), b"xyz")
        fake.Object.assert_called_once_with("backups/faq_guides/a/video.mp4")
        fake.Object.return_value.get.assert_called_once_with(Range="bytes=20-22")
        with self.assertRaises(ValueError):
            storage.url("faq_guides/a/video.mp4")

    def test_retired_public_assets_stay_closed_and_collectstatic_purges_only_them(self):
        with TemporaryDirectory() as root, self.settings(STATIC_ROOT=root, STATICFILES_DIRS=[], STATICFILES_FINDERS=[]):
            path = Path(root) / "accounts" / "faq" / "old.34567890abcd.mp4"
            path.parent.mkdir(parents=True)
            path.write_bytes(b"old")
            keep = path.parent.parent / "other.js"
            keep.write_text("ok")
            middleware = StaticFilesMiddleware(lambda request: HttpResponse("fallthrough"))
            self.assertEqual(middleware(RequestFactory().get("/static/accounts/faq/" + path.name)).status_code, 404)
            call_command("collectstatic", interactive=False, verbosity=0, dry_run=True)
            self.assertTrue(path.exists())
            call_command("collectstatic", interactive=False, verbosity=0)
            self.assertFalse(path.parent.exists())
            self.assertTrue(keep.exists())
