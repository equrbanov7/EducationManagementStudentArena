"""The continuous cabinet program and its offsets follow the same effective audience as media."""

from dataclasses import asdict, replace
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.core.files.base import ContentFile
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import FaqVideoGuide
from apps.accounts.views._helpers import _load_user_profile, _role_capabilities
from apps.accounts.views.profile.faq import faq_capabilities, faq_page
from apps.accounts.views.profile.faq_catalog import BUILTIN_BY_KEY
from apps.accounts.views.profile.faq_editor_catalog import TenantGuide
from apps.accounts.views.profile.faq_featured import featured_player
from apps.accounts.views.profile.faq_tours import tour_catalog, tour_key
from apps.accounts.views.profile.faq_visibility import required_capabilities
from apps.subject_folder.tests import factories

from .test_faq_video_editor import org_client


def for_role(role, missing_section=None, missing_flag=None, params=None):
    tour = tour_catalog()[role]
    chapters = set(tour["sections"])
    sections = {"system-settings" if s.startswith("system-settings-") else s for s in chapters}
    if "external-journal" in chapters:
        sections.add("my-journal")
    sections.discard(missing_section)
    flags = dict.fromkeys(required_capabilities(BUILTIN_BY_KEY[tour_key(role)]), True)
    flags.pop(missing_flag, None)
    return faq_page(params or {}, sections, flags)


class ProgramChapterTests(SimpleTestCase):
    def test_all_recorded_roles_start_with_their_own_entire_tour_only_when_authorized(self):
        for role in tour_catalog():
            with self.subTest(role=role):
                eligible = for_role(role)
                current = tour_key(role)
                player = eligible["featured"]
                self.assertEqual(player["playlist"][0], current)
                self.assertEqual(set(player["targets"]), eligible["allowed_guide_keys"])
                self.assertEqual([s["key"] for s in player["sources"]], player["playlist"])
                self.assertEqual(set(k for k in player["playlist"] if k.startswith("tour-")), {current})
                self.assertEqual(len(player["playlist"]), len(set(player["playlist"])))
                restricted = for_role(role, missing_section="dashboard")["featured"]
                self.assertEqual(restricted["mode"], "playlist")
                self.assertFalse(any(k.startswith("tour-") for k in restricted["playlist"]))
                self.assertNotIn(current, restricted["targets"])

    def test_authored_button_in_complete_tour_and_precise_focused_operation(self):
        page = for_role("telebe")
        player = page["featured"]
        tour = BUILTIN_BY_KEY["tour-telebe"]
        exact = next(c["start"] for c in tour.chapters if c["title"] == "Müraciətlərim · Yeni müraciət")
        application = player["targets"]["open-application"]
        self.assertEqual((application["key"], application["start"]), (tour.key, exact))
        limit = player["targets"]["journal-limit"]
        self.assertEqual(limit["start"], 48)
        self.assertEqual(limit["key"], limit["source"])
        self.assertIn(limit["key"], player["playlist"])
        self.assertEqual(limit["source"], player["targets"]["grades"]["source"])
        self.assertNotIn("locked-mark", player["targets"])
        self.assertEqual(player["targets"]["exam-pin"]["start"], 14)
        self.assertEqual(player["targets"]["quiz-start"]["start"], 15)

    def test_revoked_operation_without_a_sidebar_change_rejects_the_whole_video(self):
        full = for_role("muellim")["featured"]
        self.assertIn("tour-muellim", full["playlist"])
        self.assertEqual(full["targets"]["locked-mark"]["start"], 50.701)
        limited = for_role("muellim", missing_flag="faq_write_own_journal")["featured"]
        self.assertNotIn("tour-muellim", limited["targets"])
        self.assertNotIn("locked-mark", limited["targets"])
        self.assertNotIn("journal-entry", limited["targets"])
        self.assertIn("teacher-schedule", limited["targets"])

    def test_primary_then_other_permitted_tours_and_shared_stock_edit(self):
        first, second = (BUILTIN_BY_KEY[tour_key(role)] for role in ("lead_student", "telebe"))
        grades, alias = (BUILTIN_BY_KEY[key] for key in ("grades", "journal-limit"))
        tenant = TenantGuide(**asdict(alias), chapter_rows=tuple(alias.chapters), original_start=alias.start)
        program = featured_player([second, first, grades, tenant], ["lead_student", "telebe"], "")
        self.assertEqual(program["playlist"][:2], [first.key, second.key])
        self.assertEqual(len(program["playlist"]), 3)
        shared = program["targets"][grades.key]["source"]
        self.assertEqual(program["playlist"][-1], shared)
        self.assertEqual(program["targets"][alias.key], {"key": shared, "start": 48, "source": shared})
        # A replacement chapter track is independent even when it still uses the original MP4.
        custom = replace(tenant, chapter_rows=({"title": "Öz fəsli", "start": 3},))
        new = featured_player([grades, custom], (), "")
        self.assertEqual(new["playlist"], [grades.key, alias.key])
        self.assertEqual(new["sources"][-1]["chapters"][0], {"start": 3, "title": "Öz fəsli"})

    def test_search_chapter_and_explicit_chapter_on_the_same_scoped_file(self):
        params = {"faq_guide": "syllabus", "faq_q": "sillabusu redaktə", "faq_at": "8.491"}
        page = for_role("muellim", params=params)
        row = page["page"][0]
        target = page["featured"]["targets"][row.key]
        source = next(s for s in page["featured"]["sources"] if s["key"] == target["source"])
        self.assertEqual(row.match_chapter["start"], 31.483)
        self.assertTrue(page["requested_chapter"])
        self.assertEqual(page["chapter_start"], 8.491)
        offsets = {c["start"] for c in source["chapters"]}
        self.assertTrue({31.483, 8.491} <= offsets)
        self.assertFalse(for_role("telebe", params=params)["page"].object_list)

    def test_partial_or_unrecorded_role_uses_visible_files_only(self):
        general = BUILTIN_BY_KEY["login"]
        faq = BUILTIN_BY_KEY["section-faq"]
        schedule = BUILTIN_BY_KEY["section-my-schedule"]
        result = featured_player([faq, general, schedule], ["local-role"], "Yerli rol")
        self.assertEqual(result["role_label"], "Yerli rol")
        self.assertEqual(result["playlist"], [schedule.key, faq.key, general.key])
        self.assertEqual(result["mode"], "playlist")
        self.assertIsNone(featured_player([], (), ""))

    def test_results_only_does_not_construct_the_program_and_time_is_exact(self):
        params = {"faq_guide": "section-science-room", "faq_at": "73.44"}
        with patch("apps.accounts.views.profile.faq.featured_player") as builder:
            p = faq_page(params, {"faq", "science-room"}, {}, include_featured=False)
        self.assertIsNone(p["featured"])
        builder.assert_not_called()
        self.assertTrue(p["requested_chapter"])
        self.assertEqual(p["chapter_start"], 73.44)
        p = faq_page({**params, "faq_at": "73"}, {"faq", "science-room"}, {}, include_featured=False)
        self.assertFalse(p["requested_chapter"])


@override_settings(UNIVERSITY_MODE=True)
class EffectiveProgramTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org = factories.make_org()
        cls.other = factories.make_org()
        cls.student = factories.make_student(cls.org)
        cls.teacher = factories.make_teacher(cls.org)
        factories.activate_member(cls.other, cls.student, "teacher", permissions=["grade.input"], level=60)

    def program(self, client, *, view_as=None):
        response = client.get(reverse("accounts:profile"), {"section": "faq"})
        self.assertEqual(response.status_code, 200)
        req = response.wsgi_request
        if view_as:
            req.is_view_as = True
            req.real_user = view_as
        profile, _ = _load_user_profile(req.user)
        caps = faq_capabilities(req, _role_capabilities(req.user, profile))
        return faq_page({}, caps["allowed_sections"], caps, request=req)["featured"]

    def test_effective_user_tenant_overrides_and_both_private_tracks(self):
        with TemporaryDirectory() as tmp, self.settings(MEDIA_ROOT=tmp):
            guide = FaqVideoGuide.objects.create(
                organization=self.org,
                key="custom-room-lesson",
                title="Yerli sual",
                topic="Mövzu",
                duration=10,
                chapters=[{"start": 2.5, "time": "0:02", "title": "Yerli fəsil"}],
                audience_roles=["student"],
                required_guides=["@general"],
            )
            guide.video_file.save("a.mp4", ContentFile(b"private clip"))
            guide.subtitle_file.save("a.vtt", ContentFile(b"WEBVTT\n"))
            student, teacher, other = (
                org_client(self.student, self.org),
                org_client(self.teacher, self.org),
                org_client(self.student, self.other),
            )
            current = self.program(student, view_as=self.teacher)
            source = next(s for s in current["sources"] if s["key"] == guide.key)
            self.assertEqual(source["chapters"][0]["start"], 2.5)
            self.assertIn(guide.key, current["playlist"])
            self.assertNotIn("tour-muellim", current["targets"])
            for who in (teacher, other):
                self.assertNotIn(guide.key, self.program(who)["targets"])
            for fmt, url in (("mp4", source["src"]), ("vtt", source["track"])):
                self.assertEqual(url, reverse("accounts:faq_media", args=[guide.key, fmt]))
                self.assertEqual(student.get(url, HTTP_RANGE="bytes=0-0").status_code, 206)
                self.assertEqual(teacher.head(url).status_code, 404)
                self.assertEqual(other.head(url).status_code, 404)
            guide.hidden = True
            guide.save(update_fields=["hidden"])
            self.assertNotIn(guide.key, self.program(student)["targets"])
            self.assertEqual(student.head(source["src"]).status_code, 404)
            self.assertEqual(student.head(source["track"]).status_code, 404)
