"""Role-specific FAQ, search across pages, anonymous sign-in guides and lazy media."""

from django.contrib.staticfiles import finders
from django.test import RequestFactory, SimpleTestCase
from django.urls import reverse

from apps.accounts.views.profile.faq import PAGE_SIZE, faq_page, login_help
from apps.accounts.views.profile.faq_catalog import GUIDES, media_metadata
from apps.accounts.views.profile.faq_extra import EXTRA
from apps.accounts.views.profile.faq_media import BUILTIN_DIR
from apps.accounts.views.profile.section_assets import asset_sections_for
from apps.accounts.views.profile.sections_api import SECTION_PARTIALS


class CabinetFAQTests(SimpleTestCase):
    def test_sections_are_covered_with_media_and_chapters(self):
        self.assertEqual(set(EXTRA), set(SECTION_PARTIALS))
        self.assertEqual(len(GUIDES), len({g.key for g in GUIDES}))
        for guide in GUIDES:
            with self.subTest(guide=guide.key):
                self.assertGreaterEqual(len(guide.steps), 2)
                for extension in ("mp4", "vtt"):
                    self.assertTrue((BUILTIN_DIR / f"{guide.video}.{extension}").is_file())
                    self.assertIsNone(finders.find(f"accounts/faq/{guide.video}.{extension}"))
                self.assertGreaterEqual(len(guide.chapters), 2)
                starts = [c["start"] for c in guide.chapters]
                self.assertEqual(starts, sorted(set(starts)))
                self.assertLess(starts[-1], media_metadata()[guide.video]["duration"])

    def test_search_runs_on_the_full_role_catalog_before_pagination(self):
        sections = set(SECTION_PARTIALS)
        caps = {"is_student": True, "can_view_student_assignments": True}
        first = faq_page({}, sections, caps)["page"]
        self.assertEqual(len(first), PAGE_SIZE)
        self.assertNotEqual(first.object_list, faq_page({"faq_page": "2"}, sections, caps)["page"].object_list)
        found = faq_page({"faq_q": "PİNKOD"}, sections, caps)["page"]
        self.assertIn("exam-pin", {g.key for g in found})
        self.assertEqual(faq_page({"faq_q": "123XYZ?"}, sections, caps)["page"].paginator.count, 0)

    def test_search_only_returns_permitted_sections_and_actions(self):
        basic = {"faq", "my-schedule", "schedule-manage"}
        result = faq_page({"faq_q": "cedvel"}, basic, {})["page"].paginator.object_list
        self.assertNotIn("schedule-admin", {g.key for g in result})
        self.assertNotIn("teacher-schedule", {g.key for g in result})
        self.assertFalse(any(g.section == "account-password-reset" for g in result))
        read_only = faq_page({"faq_q": "cedvel"}, basic, {"can_view_schedule": True, "faq_export_schedule": True})[
            "page"
        ].paginator.object_list
        self.assertIn("schedule-excel-admin", {g.key for g in read_only})
        self.assertNotIn("schedule-admin", {g.key for g in read_only})
        allowed = faq_page({"faq_q": "cedvel"}, basic, {"can_manage_schedule": True, "faq_manage_schedule": True})[
            "page"
        ].paginator.object_list
        self.assertIn("schedule-admin", {g.key for g in allowed})

    def test_login_help_is_public_and_contains_no_eager_video_sources(self):
        url = reverse("accounts:login_help")
        response = login_help(RequestFactory().get(url))
        self.assertContains(response, "data-faq-watch", count=2)
        self.assertNotContains(response, "<video")
        self.assertNotContains(response, "<source")
        self.assertNotContains(response, "Parolu sıfırla")
        self.assertNotIn("faq", asset_sections_for("dashboard", {"dashboard", "faq"}))

    def test_read_only_guides_use_recordings_without_staff_editing_screens(self):
        personal = {"faq", "applications", "my-workload"}
        caps = {"can_create_support": True, "can_view_language_cohorts": True, "faq_view_own_workload": True}
        rows = {g.key: g.video for g in faq_page({}, personal, caps)["page"].paginator.object_list}
        self.assertNotIn("practice-personal", rows)
        self.assertEqual(rows["teacher-load-hours"], "teacher-load-read")
        writable = {**caps, "faq_object_workload": True}
        own = {g.key: g.video for g in faq_page({}, personal, writable)["page"].paginator.object_list}
        self.assertEqual(own["practice-personal"], "practice-personal")
        self.assertEqual(rows["language-cohort"], "language-cohort-read")
        self.assertEqual(rows["document"], "document-verify")
        self.assertEqual(rows["open-application"], "section-applications")
        self.assertNotIn("teacher-journal-support", rows)
        self.assertFalse(
            {"workload-practice", "workload-explained", "language-cohort", "document", "support"} & set(rows.values())
        )
