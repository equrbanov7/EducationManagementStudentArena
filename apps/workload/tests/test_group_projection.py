import uuid

from django.test import SimpleTestCase

from apps.workload.services.group_projection import project_group_settings


class GroupProjectionTests(SimpleTestCase):
    def test_academic_identity_omits_unexported_settings_without_mutating_them(self):
        raw = {"degree_level": "master", "sector": "az", "private_note": {"keep": True}}
        self.assertEqual(
            project_group_settings(raw, canonical_group_ids=[]), {"degree_level": "master", "sector": "az"}
        )
        self.assertEqual(raw["private_note"], {"keep": True})

    def test_cohort_flag_cannot_export_a_freeform_string(self):
        self.assertEqual(project_group_settings({"language_level_cohort": "private"}, canonical_group_ids=[]), {})
        self.assertEqual(
            project_group_settings({"language_level_cohort": True}, canonical_group_ids=[]),
            {"language_level_cohort": True},
        )

    def test_canonical_alias_is_only_exported_for_a_same_tenant_group(self):
        own, foreign = uuid.uuid4(), uuid.uuid4()
        for known in ([own], [str(own)]):
            self.assertEqual(
                project_group_settings({"canonical_group": str(own)}, canonical_group_ids=known),
                {"canonical_group": str(own)},
            )
        self.assertEqual(project_group_settings({"canonical_group": str(foreign)}, canonical_group_ids=[own]), {})
        self.assertEqual(
            project_group_settings({"canonical_group": {"private": "value"}}, canonical_group_ids=[own]), {}
        )
