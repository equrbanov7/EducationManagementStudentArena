"""University video editor access, effective catalogue visibility and private file lifecycle."""

import struct
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from uuid import uuid4

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile, TemporaryUploadedFile
from django.db import DatabaseError, connection, transaction
from django.test import Client, RequestFactory, TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import FaqVideoGuide
from apps.accounts.views.profile.faq import faq_page
from apps.accounts.views.profile.faq_catalog import GUIDES
from apps.accounts.views.profile.faq_editor_catalog import can_manage_videos
from apps.accounts.views.profile.faq_editor_forms import version
from apps.accounts.views.profile.faq_uploads import check_vtt, video_duration
from apps.subject_folder.tests import factories as f


def video(seconds=10):
    def box(name, data):
        return struct.pack(">I4s", len(data) + 8, name) + data

    clock = bytes(12) + struct.pack(">II", 100, 100 * seconds)
    handler = box(b"hdlr", bytes(8) + b"vide")
    body = box(b"ftyp", b"isom\x00\x00\x00\x01iso2")
    body += box(b"moov", box(b"mvhd", clock) + box(b"trak", box(b"mdia", handler)))
    return SimpleUploadedFile("clip.mp4", body + box(b"mdat", b"synthetic"), content_type="video/mp4")


def subtitres(text="Nümunə"):
    body = f"WEBVTT\n\n00:00:00.000 --> 00:00:02.000\n{text}\n"
    return SimpleUploadedFile("caption.vtt", body.encode(), content_type="text/vtt")


def org_client(user, org):
    client = Client()
    client.force_login(user)
    session = client.session
    session["active_organization"] = org.slug
    session.save()
    return client


def editor_url(key):
    return reverse("accounts:faq_video_edit", args=[key])


def profile_faq(request_user, org, params=None, caps=None):
    request = RequestFactory().get("/")
    request.user, request.organization = request_user, org
    return faq_page(params or {}, {"faq", "my-journal"}, caps or {}, request=request)


@override_settings(UNIVERSITY_MODE=True)
class FAQVideoEditorTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org, cls.other = f.make_org(), f.make_org()
        cls.staff = f.make_user("rim")
        cls.head = f.make_user("head")
        cls.rector = f.make_user("rector")
        for user, org, name in [
            (cls.staff, cls.org, "rim_staff"),
            (cls.head, cls.org, "ikt_rehber"),
            (cls.rector, cls.org, "rector"),
            (cls.head, cls.other, "ikt_rehber"),
        ]:
            role = org.roles.get(name=name)
            role.memberships.create(organization=org, user=user, is_active=True)
        cls.student = f.make_student(cls.org)
        cls.teacher = f.make_teacher(cls.org)

    def setUp(self):
        super().setUp()
        media = TemporaryDirectory()
        self.addCleanup(media.cleanup)
        self.media_root = Path(media.name)
        self.enterContext(self.settings(MEDIA_ROOT=media.name))
        self.staff_client = org_client(self.staff, self.org)
        self.create_url = reverse("accounts:faq_video_create")

    def create_data(self, **changes):
        return {
            "action": "save",
            "all_roles": not changes.get("audience"),
            "required_guides": ["@general"],
            "version": "0",
            "create_token": str(uuid4()),
            "title": "Nümunə dərs",
            "topic": "Jurnal",
            "steps": "Bir\nİki",
            "chapters": "00:00 Giriş\n00:04.5 Son",
            "video": video(),
            **changes,
        }

    def test_editor_requires_explicit_active_org_scoped_grant(self):
        url = reverse("accounts:faq_video_editor")
        self.assertEqual(
            (
                set(self.org.roles.filter(permissions__contains=["faq.video.manage"]).values_list("name", flat=True))
                if connection.vendor == "postgresql"
                else {r.name for r in self.org.roles.all() if "faq.video.manage" in r.permissions}
            ),
            {"ikt_rehber", "rim_staff"},
        )
        for user in (self.staff, self.head):
            client = org_client(user, self.org)
            self.assertContains(client.get(url), reverse("accounts:faq_video_create"))
            self.assertTrue(profile_faq(user, self.org)["can_manage_videos"])
        for user in (self.rector, self.student, self.teacher, self.org.owner):
            client = org_client(user, self.org)
            self.assertEqual(client.get(url).status_code, 403)
            self.assertEqual(client.post(self.create_url, {}).status_code, 403)
        request = RequestFactory().get("/")
        request.organization, request.user, request.is_view_as = self.org, self.head, True
        self.assertFalse(can_manage_videos(request))
        if connection.vendor == "postgresql":
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname='accounts_faqvideoguide'"
                )
                self.assertEqual(cursor.fetchone(), (True, True))

    def test_template_only_grant_cannot_be_delegated_or_used_by_other_roles(self):
        custom_user = f.make_user("departmentadmin")
        role = f.activate_member(self.org, custom_user, "custom_admin", permissions=["*"], level=91)
        editor = org_client(self.head, self.org)
        key = "faq.video.manage"
        for params in (
            {"action": "add", "permission": key, "with_delegation": "1"},
            {"action": "grant_delegation", "permission": key},
            {"action": "bulk_add", "permissions": [key]},
        ):
            self.assertEqual(
                editor.post(reverse("accounts:permission_editor"), {"role_id": role.pk, **params}).status_code, 302
            )
            role.refresh_from_db()
            self.assertNotIn(key, role.permissions)
            self.assertNotIn("grant:" + key, role.permissions)
        role.permissions = ["*", key]
        role.save(update_fields=["permissions"])
        self.assertEqual(org_client(custom_user, self.org).get(self.create_url).status_code, 403)
        rector_role = self.org.roles.get(name="rector")
        rector_role.permissions = ["*", key]
        rector_role.save(update_fields=["permissions"])
        self.assertEqual(org_client(self.rector, self.org).get(self.create_url).status_code, 403)

    def test_public_login_guides_remain_original_after_tenant_edit_or_remove(self):
        for key in ("login", "recover"):
            public = reverse("accounts:faq_public_media", args=[key, "mp4"])
            private = reverse("accounts:faq_media", args=[key, "mp4"])
            initial = self.client.head(public)
            self.assertEqual(initial.status_code, 200)
            url = editor_url(key)
            self.assertEqual(
                self.staff_client.post(url, {"action": "remove", "version": "0", "confirm": "yes"}).status_code, 302
            )
            self.assertEqual(self.staff_client.head(private).status_code, 404)
            self.assertEqual(self.client.head(public)["Content-Length"], initial["Content-Length"])
            self.assertEqual(
                org_client(self.head, self.other).head(private)["Content-Length"], initial["Content-Length"]
            )

    def test_shared_upload_requires_the_viewers_actual_operation_access(self):
        url = reverse("accounts:faq_video_create")
        for bad in ([], ["unknown-operation"], ["@general", "section-exam-score-entry"]):
            self.assertEqual(self.staff_client.post(url, self.create_data(required_guides=bad)).status_code, 400)
        self.assertEqual(
            self.staff_client.post(url, self.create_data(required_guides=["section-exam-score-entry"])).status_code, 302
        )
        row = FaqVideoGuide.objects.get(organization=self.org)
        for user in (self.teacher, self.student):
            client = org_client(user, self.org)
            for extension in ("mp4", "vtt"):
                response = client.get(reverse("accounts:faq_media", args=[row.key, extension]), HTTP_RANGE="bytes=0-3")
                self.assertEqual(response.status_code, 404)
            page = client.get(
                reverse("accounts:profile_section_fragment", kwargs={"section": "faq"}),
                {"faq_results": "1", "faq_guide": row.key},
            )
            self.assertNotContains(page, f'data-faq-guide="{row.key}"')

    def test_unclassified_custom_upload_waits_for_editor_to_select_its_audience(self):
        row = FaqVideoGuide.objects.create(organization=self.org, key="custom-old", title="Mövzu")
        self.assertEqual(profile_faq(self.teacher, self.org, {"faq_guide": row.key})["page"].paginator.count, 0)
        self.assertContains(self.staff_client.get(editor_url(row.key)), "Videoda göstərilən əməliyyatlar")

    def test_custom_create_edit_replace_delete_and_stale_submission(self):
        data = self.create_data(subtitles=subtitres(), audience=["teacher"])
        response = self.staff_client.post(self.create_url, data)
        self.assertEqual(response.status_code, 302, response.context and response.context["form"].errors)
        guide = FaqVideoGuide.objects.get(organization=self.org)
        self.assertTrue(guide.key.startswith("custom-"))
        self.assertEqual(guide.duration, 10)
        self.assertEqual(guide.audience_roles, ["teacher"])
        self.assertTrue(guide.video_file.name.startswith(f"faq_guides/{self.org.pk}/"))
        tag = version(guide)
        old_video, old_track = guide.video_file, guide.subtitle_file
        self.assertTrue(old_video.storage.exists(old_video.name))
        self.assertTrue(old_track.storage.exists(old_track.name))
        for user, visible in ((self.teacher, True), (self.student, False)):
            page = profile_faq(user, self.org, {"faq_guide": guide.key, "faq_at": "4.5"})
            self.assertEqual(page["page"].paginator.count, int(visible))
            self.assertEqual(page["chapter_start"], 4.5 if visible else 0)
        self.assertEqual(profile_faq(self.head, self.other, {"faq_guide": guide.key})["page"].paginator.count, 0)
        self.assertEqual(profile_faq(self.rector, self.other, {"faq_guide": guide.key})["page"].paginator.count, 0)
        self.assertEqual(org_client(self.head, self.other).get(editor_url(guide.key)).status_code, 404)
        duplicate = self.create_data(create_token=data["create_token"])
        self.assertEqual(self.staff_client.post(self.create_url, duplicate).status_code, 409)
        self.assertEqual(FaqVideoGuide.objects.count(), 1)
        replacement = self.create_data(version=tag, video=video(12), title="Yenilənmiş dərs")
        with self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(self.staff_client.post(editor_url(guide.key), replacement).status_code, 302)
        guide.refresh_from_db()
        self.assertEqual((guide.title, guide.duration), ("Yenilənmiş dərs", 12))
        self.assertFalse(bool(guide.subtitle_file))
        self.assertFalse(old_video.storage.exists(old_video.name))
        self.assertFalse(old_track.storage.exists(old_track.name))
        stale = {"action": "remove", "version": tag, "confirm": "yes"}
        self.assertEqual(self.staff_client.post(editor_url(guide.key), stale).status_code, 409)
        removal = {**stale, "version": version(guide)}
        self.assertEqual(self.staff_client.post(editor_url(guide.key), {**removal, "confirm": ""}).status_code, 400)
        new_video = guide.video_file
        with self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(self.staff_client.post(editor_url(guide.key), removal).status_code, 302)
        self.assertFalse(FaqVideoGuide.objects.exists())
        self.assertFalse(new_video.storage.exists(new_video.name))

    def test_builtin_overlay_deeplink_and_restore(self):
        key = "journal-entry"
        original = next(g for g in GUIDES if g.key == key)
        data = {
            "version": "0",
            "title": "Təşkilatın jurnal dərsi",
            "topic": "Kabinet",
            "steps": "Yoxlayın",
            "audience": ["teacher"],
            "chapters": "00:00 Giriş\n00:06 Son",
        }
        url = editor_url(key)
        self.assertEqual(self.staff_client.post(url, data).status_code, 302)
        guide = FaqVideoGuide.objects.get(organization=self.org, key=key)
        for user, caps, expected in (
            (self.teacher, {"is_teacher": True, "faq_write_own_journal": True}, 1),
            (self.teacher, {}, 0),
            (self.student, {"is_teacher": True, "faq_write_own_journal": True}, 0),
        ):
            page = profile_faq(user, self.org, {"faq_guide": key, "faq_at": "6"}, caps)
            self.assertEqual(page["page"].paginator.count, expected)
            if expected:
                self.assertEqual(page["chapter_start"], 6)
                self.assertEqual(page["selected"], key)
                self.assertIn("login", page["allowed_guide_keys"])
                self.assertTrue(page["page"][0].has_subtitles)
                self.assertEqual(page["page"][0].video, original.video)
        self.assertEqual(
            profile_faq(
                self.teacher,
                self.org,
                {"faq_guide": key, "faq_at": "6.001"},
                {"is_teacher": True, "faq_write_own_journal": True},
            )["chapter_start"],
            original.start,
        )
        self.assertEqual(
            self.staff_client.post(url, {"action": "remove", "version": version(guide), "confirm": "yes"}).status_code,
            302,
        )
        self.assertNotIn(
            key,
            profile_faq(
                self.teacher, self.org, {"faq_guide": key}, {"is_teacher": True, "faq_write_own_journal": True}
            )["allowed_guide_keys"],
        )
        guide.refresh_from_db()
        self.assertEqual(self.staff_client.post(url, {"action": "restore", "version": version(guide)}).status_code, 302)
        self.assertFalse(FaqVideoGuide.objects.filter(organization=self.org, key=key).exists())
        self.assertEqual(
            profile_faq(
                self.teacher, self.org, {"faq_guide": key}, {"is_teacher": True, "faq_write_own_journal": True}
            )["page"][0],
            original,
        )

    def test_new_video_requires_requested_audience_and_all_roles_keeps_builtin_acl(self):
        for values in ({"all_roles": ""}, {"audience": ["teacher"], "all_roles": "on"}):
            response = self.staff_client.post(self.create_url, self.create_data(**values))
            self.assertEqual(response.status_code, 400)
            self.assertIn("audience", response.context["form"].errors)
        self.assertFalse(FaqVideoGuide.objects.exists())
        response = self.staff_client.post(self.create_url, self.create_data(all_roles="on"))
        self.assertEqual(response.status_code, 302)
        new = FaqVideoGuide.objects.get(organization=self.org)
        self.assertIn(new.key, profile_faq(self.student, self.org)["allowed_guide_keys"])
        source = "journal-entry"
        self.assertEqual(
            self.staff_client.post(
                editor_url(source), {"version": "0", "title": "Jurnal", "topic": "Jurnal", "all_roles": "on"}
            ).status_code,
            302,
        )
        self.assertNotIn(source, profile_faq(self.student, self.org)["allowed_guide_keys"])
        self.assertIn(
            source,
            profile_faq(self.teacher, self.org, caps={"is_teacher": True, "faq_write_own_journal": True})[
                "allowed_guide_keys"
            ],
        )

    def test_scoped_postgresql_policy_hides_other_organizations_and_rejects_cross_org_insert(self):
        if connection.vendor != "postgresql":
            self.skipTest("PostgreSQL row-level security")
        FaqVideoGuide.objects.create(organization=self.org, key="only-a")
        FaqVideoGuide.objects.create(organization=self.other, key="only-b")
        with connection.cursor() as cur:
            cur.execute("SET LOCAL ROLE rls_app_role")
            cur.execute("SELECT set_config('app.bypass_rls','off',true)")
            cur.execute("SELECT set_config('app.current_org_id',%s,true)", [str(self.org.pk)])
        self.assertEqual(list(FaqVideoGuide.objects.values_list("key", flat=True)), ["only-a"])
        with self.assertRaises(DatabaseError), transaction.atomic():
            FaqVideoGuide.objects.create(organization=self.other, key="outside")
        with connection.cursor() as cur:
            cur.execute("SELECT set_config('app.current_org_id','',true)")
        self.assertFalse(FaqVideoGuide.objects.exists())

    def test_storage_cleanup_on_rollback_and_inactive_audience_preserved_in_form(self):
        with patch("apps.accounts.views.profile.faq_editor.log_action", side_effect=RuntimeError("write failed")):
            with self.assertRaises(RuntimeError):
                self.staff_client.post(self.create_url, self.create_data(subtitles=subtitres()))
        self.assertFalse(FaqVideoGuide.objects.exists())
        self.assertFalse(any(path.is_file() for path in self.media_root.rglob("*")))
        row = FaqVideoGuide.objects.create(
            organization=self.org, key="recover", title="Sual", topic="Hesab", audience_roles=["retired_role"]
        )
        form = self.staff_client.get(editor_url(row.key)).context["form"]
        self.assertIn("retired_role", dict(form.fields["audience"].choices))
        self.assertEqual(form["audience"].value(), ["retired_role"])

    def test_upload_endpoint_body_limit_csrf_and_nginx(self):
        url = reverse("accounts:faq_video_upload_create")
        self.assertContains(self.staff_client.get(self.create_url), url)
        self.assertEqual(self.staff_client.get(url).status_code, 405)
        self.assertEqual(self.staff_client.post(url, CONTENT_LENGTH=str(209 * 1024 * 1024)).status_code, 413)
        self.assertEqual(
            org_client(self.teacher, self.org).post(url, CONTENT_LENGTH=str(209 * 1024 * 1024)).status_code, 403
        )
        self.assertEqual(self.staff_client.post(url, self.create_data()).status_code, 302)
        client = Client(enforce_csrf_checks=True)
        client.cookies = self.staff_client.cookies.copy()
        self.assertEqual(client.post(url, self.create_data()).status_code, 403)
        for name in ("nginx.conf", "nginx.ci.conf"):
            conf = (Path(__file__).resolve().parents[3] / "docker" / "nginx" / name).read_text()
            block = conf.split("location ^~ /accounts/faq/video-upload/ {", 1)[1].split("}", 1)[0]
            self.assertIn("client_max_body_size    210m;", block)
            self.assertIn("proxy_request_buffering on;", block)

    def test_validation_and_no_partial_writes(self):
        for changes in (
            {"chapters": "00:08 Bir\n00:03 İki"},
            {"chapters": "00:10 Son"},
            {"audience": ["outside"]},
            {"video": SimpleUploadedFile("clip.mp4", b"not a movie", content_type="video/mp4")},
            {"subtitles": subtitres("<b>Salam</b>")},
            {"video": ""},
            {"create_token": ""},
        ):
            result = self.staff_client.post(self.create_url, self.create_data(**changes))
            self.assertEqual(result.status_code, 400, changes.keys())
            self.assertFalse(FaqVideoGuide.objects.exists())
        # A sparse, valid top-level free box exercises the genuine 200 MiB boundary without loading it into memory.
        limit = 200 * 1024 * 1024
        tiny = video()
        with TemporaryUploadedFile("large.mp4", "video/mp4", limit, None) as large:
            large.write(tiny.read())
            large.write(struct.pack(">I4s", limit - tiny.size, b"free"))
            large.seek(limit - 1)
            large.write(b"\0")
            large.seek(0)
            self.assertEqual(video_duration(large), 10)
        oversized = video()
        oversized.size = 201 * 1024 * 1024
        with self.assertRaises(ValidationError):
            video_duration(oversized)
        with self.assertRaises(ValidationError):
            check_vtt(subtitres(), duration=1)
