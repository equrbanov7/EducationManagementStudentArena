from types import SimpleNamespace
from unittest.mock import patch

from django.test import RequestFactory, SimpleTestCase, TestCase

from apps.accounts.views.profile import faq_operational_access as access
from apps.accounts.views.profile.faq_catalog import GUIDES, media_metadata
from apps.subject_folder.tests import factories


class GuideActionMediaTests(SimpleTestCase):
    def test_clips_end_before_the_next_role_starts(self):
        expected = {
            "practice-assign": ("workload-practice-distribute", 3),
            "load-lab-edit": ("workload-lab-row-edit", 8),
            "teacher-load-hours": ("teacher-load-read", 2),
            "lab-group-create": ("lab-group-placement", 6),
            "load-exam": ("workload-activities-staff", 9),
        }
        by_key = {guide.key: guide for guide in GUIDES}
        for key, (video, chapters) in expected.items():
            with self.subTest(key=key):
                self.assertEqual(by_key[key].video, video)
                self.assertEqual(len(media_metadata()[video]["chapters"]), chapters)
        self.assertIn("faq_object_workload", access.REQUIRED_FLAGS["practice-personal"])
        self.assertNotIn("faq_object_workload", access.REQUIRED_FLAGS["teacher-load-hours"])

    def test_chapter_starts_match_the_permission_trimmed_recordings(self):
        by_key = {guide.key: guide for guide in GUIDES}
        expected = {
            "load-lab-hours": "İki tam laboratoriya qrupu",
            "load-consult": "Məsləhət saatını müəllimə ver",
            "load-exam": "İmtahan saatını müəllimə ver",
            "load-thesis": "Buraxılış işinə rəhbərliyi yaz",
            "load-postgrad": "Dissertant rəhbərliyini yaz",
            "practice-assign": "Saatları müəllimə bölüşdür",
        }
        for key, title in expected.items():
            with self.subTest(key=key):
                guide = by_key[key]
                chapter = next(c for c in guide.chapters if c["title"] == title)
                self.assertEqual(guide.start, chapter["start"])

    def test_range_request_only_runs_its_named_gate(self):
        request = SimpleNamespace(user=SimpleNamespace(is_authenticated=True, is_active=True), organization=object())
        sections = {"hr-contracts", "schedule-manage", "workload-center", "syllabus-review"}
        with (
            patch.object(access, "contract_management_allowed", return_value=False) as contracts,
            patch.object(access.workload, "resolve_actor") as workload,
            patch.object(access.syllabus, "resolve_actor") as syllabus,
            patch.object(access.schedule_manage, "can_view") as schedules,
        ):
            result = access.operational_capabilities(
                request, {"allowed_sections": sections}, {"faq_manage_hr_contracts"}
            )
        self.assertEqual(result, {"faq_manage_hr_contracts": False})
        contracts.assert_called_once_with(request)
        workload.assert_not_called()
        syllabus.assert_not_called()
        schedules.assert_not_called()


class TenantGuideActionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org = factories.make_org()
        cls.other = factories.make_org()
        cls.actor = factories.make_user("guide-operator")
        cls.permissions = ["schedule.view", "workload.distribute", "workload.view", "hr.contracts_view"]
        factories.activate_member(cls.org, cls.actor, "guide-viewer", permissions=cls.permissions)
        factories.activate_member(
            cls.other,
            cls.actor,
            "guide-manager",
            permissions=["schedule.manage", "workload.manage", "hr.contracts_manage"],
        )

    def rights(self, org, permissions, **options):
        request = RequestFactory().get("/accounts/profile/")
        request.organization = org
        request.user = self.actor
        request.org_permissions = permissions
        request.is_view_as = options.get("view_as", False)
        return access.operational_capabilities(
            request, {"allowed_sections": {"schedule-manage", "hr-contracts", "workload-distribution"}}
        )

    def test_scoped_read_access_does_not_open_writes(self):
        flags = self.rights(self.org, self.permissions)
        self.assertTrue(flags["faq_export_schedule"])
        self.assertTrue(flags["faq_distribute_workload"])
        for name in [
            "faq_manage_schedule",
            "faq_manage_workload_row",
            "faq_edit_and_distribute_workload",
            "faq_manage_hr_contracts",
        ]:
            self.assertFalse(flags[name], name)

    def test_other_tenant_management_does_not_grant_distribution(self):
        flags = self.rights(self.other, ["schedule.manage", "workload.manage", "hr.contracts_manage"])
        self.assertTrue(flags["faq_manage_schedule"])
        self.assertTrue(flags["faq_manage_workload_row"])
        self.assertTrue(flags["faq_manage_hr_contracts"])
        self.assertFalse(flags["faq_edit_and_distribute_workload"])

    def test_view_as_does_not_authorize_writes_or_schedule_exports(self):
        flags = self.rights(self.org, self.permissions, view_as=True)
        self.assertFalse(flags["faq_export_schedule"])
        self.assertFalse(flags["faq_distribute_workload"])
