"""``Organization.settings`` lost update (2026-10-07).

Ssenari: yazıçı təşkilatı ƏVVƏLCƏDƏN yükləyib (köhnə nüsxə), arada başqa yol elan / sorğu
qapısı xülasəsini atomik yazır, sonra köhnə nüsxə ilə yazıçı çağırılır. Əvvəl bütöv dict
``save(update_fields=["settings"])`` ilə yazılırdı və xülasə SƏSSİZCƏ itirdi. İndi hər
yazıçı yalnız ÖZ açarını atomik birləşdirir, ``Organization.save()`` isə idarə olunan
(xülasə) açarları kilidli sətirdən götürür.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.announcements.constants import SNAPSHOT_KEY
from apps.announcements.services.snapshot import sync_snapshot
from apps.organizations.cabinet_modules import MODULE_VISIBILITY_SETTINGS_KEY, is_module_enabled
from apps.organizations.models import Organization
from apps.organizations.public import (
    REMOVE_SETTINGS_KEY,
    UNCHANGED_SETTINGS_KEY,
    save_review_identity_reveal,
    set_module_enabled,
    set_settings_keys,
    update_settings_key,
)
from apps.organizations.review_visibility import REVIEW_VISIBILITY_SETTINGS_KEY
from apps.organizations.settings_store import managed_settings_keys
from apps.organizations.structure_plan import apply_structure_plan
from apps.registrar import grading_scale
from apps.surveys.constants import GATE_SNAPSHOT_KEY
from apps.surveys.services.gate_snapshot import sync_gate_snapshot
from core.constants import OrganizationType
from core.rls import bypass_rls

User = get_user_model()

CAMPUSES = [{"building": "Korpus B", "units": ["Kompüter elmləri"]}]
BANDS = [[85, "S", "4.00"], [51, "P", "2.00"], [0, "F", "0.00"]]


def _fresh(org) -> Organization:
    with bypass_rls():
        return Organization.objects.get(pk=org.pk)


class _StaleWorld(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("ss_owner", "ss_owner@qku.edu.az", "pw")
        with bypass_rls():
            cls.org = Organization.objects.create(
                name="Settings Store Univ",
                slug="settings-store",
                org_type=OrganizationType.UNIVERSITY,
                owner=cls.owner,
                status="active",
                is_active=True,
                settings={"campuses": CAMPUSES, "custom": {"a": 1}},
            )

    def _stale_then_snapshots(self):
        """Köhnə nüsxə götürülür, SONRA başqa nüsxə ilə hər iki xülasə yazılır."""
        stale = _fresh(self.org)
        other = _fresh(self.org)
        with bypass_rls():
            announcements = sync_snapshot(other)
            gate = sync_gate_snapshot(other)
        self.assertNotIn(SNAPSHOT_KEY, stale.settings)
        return stale, announcements["v"], gate["v"]

    def _assert_snapshots(self, ann_version, gate_version):
        stored = _fresh(self.org).settings
        self.assertEqual(stored[SNAPSHOT_KEY]["v"], ann_version)
        self.assertEqual(stored[GATE_SNAPSHOT_KEY]["v"], gate_version)
        return stored


class SnapshotSurvivesStaleWritersTest(_StaleWorld):
    def test_snapshot_keys_are_registered_as_managed(self):
        self.assertLessEqual({SNAPSHOT_KEY, GATE_SNAPSHOT_KEY}, managed_settings_keys())

    def test_cabinet_module_toggle(self):
        stale, ann, gate = self._stale_then_snapshots()
        with bypass_rls():
            set_module_enabled(stale, "posts", True)
        stored = self._assert_snapshots(ann, gate)
        self.assertEqual(stored[MODULE_VISIBILITY_SETTINGS_KEY], {"posts": True})
        self.assertEqual(stored["custom"], {"a": 1})
        self.assertEqual(stale.settings, stored)  # nüsxə DB-dən təzələnir
        self.assertTrue(is_module_enabled(stale, "posts"))

    def test_concurrent_module_toggles_both_survive(self):
        first, second = _fresh(self.org), _fresh(self.org)
        with bypass_rls():
            set_module_enabled(first, "posts", True)
            set_module_enabled(second, "statistics", False)  # köhnə nüsxə — «posts»-u görmür
        self.assertEqual(
            _fresh(self.org).settings[MODULE_VISIBILITY_SETTINGS_KEY], {"posts": True, "statistics": False}
        )

    def test_grading_scale_set_and_reset(self):
        stale, ann, gate = self._stale_then_snapshots()
        with bypass_rls():
            grading_scale.set_bands(stale, BANDS)
        stored = self._assert_snapshots(ann, gate)
        self.assertEqual(stored[grading_scale.LETTER_BANDS_SETTINGS_KEY], BANDS)
        self.assertTrue(grading_scale.is_custom(stale))

        stale_again = _fresh(self.org)
        stale_again.settings.pop(grading_scale.LETTER_BANDS_SETTINGS_KEY)  # nüsxə açarı görmür
        with bypass_rls():
            grading_scale.reset_bands(stale_again)
        stored = self._assert_snapshots(ann, gate)
        self.assertNotIn(grading_scale.LETTER_BANDS_SETTINGS_KEY, stored)  # yenə də silinir
        self.assertFalse(grading_scale.is_custom(stale_again))

    def test_review_identity_reveal(self):
        stale, ann, gate = self._stale_then_snapshots()
        other = _fresh(self.org)
        with bypass_rls():
            save_review_identity_reveal(other, "assignment", True)
            save_review_identity_reveal(stale, "written_exam", True)  # köhnə nüsxə — «assignment»-i görmür
        stored = self._assert_snapshots(ann, gate)
        self.assertEqual(
            stored[REVIEW_VISIBILITY_SETTINGS_KEY],
            {"assignment_identity_reveal_enabled": True, "written_exam_identity_reveal_enabled": True},
        )
        self.assertTrue(stale.written_exam_identity_reveal_enabled)
        with self.assertRaises(ValueError):
            save_review_identity_reveal(stale, "unknown", True)

    def test_structure_plan_campuses(self):
        stale, ann, gate = self._stale_then_snapshots()
        with bypass_rls():
            report = apply_structure_plan(stale, {"campuses": {"Korpus B": ["Yeni məktəb"]}}, apply=True)
        stored = self._assert_snapshots(ann, gate)
        self.assertEqual(stored["campuses"][0]["units"], ["Kompüter elmləri", "Yeni məktəb"])
        self.assertEqual(report.counts.get("KORPUS"), 1)
        # Təkrar qaçış idempotentdir: əlavə yoxdur, yazı da yoxdur.
        before = _fresh(self.org).updated_at
        with bypass_rls():
            report = apply_structure_plan(_fresh(self.org), {"campuses": {"Korpus B": ["Yeni məktəb"]}}, apply=True)
        self.assertNotIn("KORPUS", report.counts)
        self.assertEqual(_fresh(self.org).updated_at, before)

    def test_structure_plan_dry_run_writes_nothing(self):
        stale, ann, gate = self._stale_then_snapshots()
        with bypass_rls():
            report = apply_structure_plan(stale, {"campuses": {"Korpus B": ["Yeni məktəb"]}}, apply=False)
        self.assertEqual(report.counts.get("KORPUS"), 1)
        stored = self._assert_snapshots(ann, gate)
        self.assertEqual(stored["campuses"], CAMPUSES)

    def test_model_full_save_keeps_snapshots(self):
        """Admin / forma yolu: bütöv ``save()`` köhnə nüsxədən xülasəni əzmir, öz dəyişikliyini yazır."""
        stale, ann, gate = self._stale_then_snapshots()
        stale.description = "Yeni təsvir"
        stale.settings = {**stale.settings, "custom": {"a": 2}}
        with bypass_rls():
            stale.save()
        stored = self._assert_snapshots(ann, gate)
        self.assertEqual(stored["custom"], {"a": 2})
        self.assertEqual(_fresh(self.org).description, "Yeni təsvir")
        self.assertEqual(stale.settings[SNAPSHOT_KEY]["v"], ann)  # nüsxə də düzəlir

    def test_model_update_fields_save_keeps_snapshots(self):
        stale, ann, gate = self._stale_then_snapshots()
        stale.settings[SNAPSHOT_KEY] = {"v": "stale", "items": []}  # köhnə/saxta xülasə yazılmır
        stale.settings["custom"] = {"b": 1}
        with bypass_rls():
            stale.save(update_fields=["settings", "updated_at"])
        stored = self._assert_snapshots(ann, gate)
        self.assertEqual(stored["custom"], {"b": 1})

    def test_model_save_does_not_resurrect_cleared_snapshot(self):
        with bypass_rls():
            sync_snapshot(self.org)
        stale = _fresh(self.org)
        with bypass_rls():
            Organization.objects.filter(pk=self.org.pk).update(settings={"custom": {"a": 1}})
            stale.save(update_fields=["settings"])
        self.assertNotIn(SNAPSHOT_KEY, _fresh(self.org).settings)

    def test_save_without_settings_skips_lock_query(self):
        stale = _fresh(self.org)
        stale.name = "Yeni ad"
        with bypass_rls(), CaptureQueriesContext(connection) as queries:
            stale.save(update_fields=["name", "updated_at"])
        self.assertFalse([q for q in queries.captured_queries if "FOR UPDATE" in q["sql"]])

    def test_org_settings_page_post_does_not_write_settings_json(self):
        stale, ann, gate = self._stale_then_snapshots()
        self.client.force_login(self.owner)
        with CaptureQueriesContext(connection) as queries:
            response = self.client.post(
                reverse("organizations:settings", kwargs={"slug": self.org.slug}),
                {"description": "Təsvir", "email": "info@qku.edu.az", "phone": "", "address": "", "website": ""},
            )
        self.assertEqual(response.status_code, 302)
        updates = [q["sql"] for q in queries.captured_queries if q["sql"].startswith('UPDATE "organizations_org')]
        self.assertTrue(updates)
        self.assertFalse([sql for sql in updates if '"settings"' in sql], updates)
        self._assert_snapshots(ann, gate)
        self.assertEqual(_fresh(self.org).email, "info@qku.edu.az")


class SettingsStoreHelperTest(_StaleWorld):
    def test_set_settings_keys_merges_and_removes_atomically(self):
        stale = _fresh(self.org)
        with bypass_rls():
            set_settings_keys(_fresh(self.org), {"other": 1})
            before = _fresh(self.org).updated_at
            result = set_settings_keys(stale, {"custom": {"z": 9}}, remove=["campuses"])
        stored = _fresh(self.org)
        self.assertEqual(stored.settings, {"other": 1, "custom": {"z": 9}})
        self.assertEqual(result, stored.settings)
        self.assertEqual(stale.settings, stored.settings)
        self.assertGreater(stored.updated_at, before)
        self.assertEqual(stale.updated_at, stored.updated_at)

    def test_touch_false_keeps_updated_at(self):
        before = _fresh(self.org).updated_at
        with bypass_rls():
            set_settings_keys(_fresh(self.org), {"derived": [1]}, touch=False)
        self.assertEqual(_fresh(self.org).updated_at, before)

    def test_non_object_settings_is_replaced_by_object(self):
        with bypass_rls():
            Organization.objects.filter(pk=self.org.pk).update(settings=[1, 2])
            set_settings_keys(_fresh(self.org), {"k": "v"})
        self.assertEqual(_fresh(self.org).settings, {"k": "v"})

    def test_noop_calls_write_nothing(self):
        with CaptureQueriesContext(connection) as queries:
            self.assertEqual(set_settings_keys(self.org, {}), self.org.settings)
        self.assertEqual(len(queries.captured_queries), 0)
        before = _fresh(self.org).updated_at
        with bypass_rls():
            update_settings_key(_fresh(self.org), "custom", lambda current: current)
            update_settings_key(_fresh(self.org), "missing", lambda current: REMOVE_SETTINGS_KEY)
            update_settings_key(_fresh(self.org), "missing", lambda current: UNCHANGED_SETTINGS_KEY)
        self.assertEqual(_fresh(self.org).updated_at, before)
        self.assertNotIn("missing", _fresh(self.org).settings)

    def test_update_settings_key_reads_fresh_value_and_can_remove(self):
        stale = _fresh(self.org)
        with bypass_rls():
            set_settings_keys(_fresh(self.org), {"custom": {"a": 1, "b": 2}})
            update_settings_key(stale, "custom", lambda current: {**current, "c": 3})
        self.assertEqual(_fresh(self.org).settings["custom"], {"a": 1, "b": 2, "c": 3})
        with bypass_rls():
            update_settings_key(stale, "custom", lambda current: REMOVE_SETTINGS_KEY)
        self.assertNotIn("custom", _fresh(self.org).settings)
        self.assertNotIn("custom", stale.settings)

    def test_unsaved_instance_merges_in_memory_only(self):
        org = Organization(name="Yaddaş", slug="yaddas", org_type=OrganizationType.UNIVERSITY, owner=self.owner)
        set_settings_keys(org, {"k": 1})
        self.assertEqual(org.settings, {"k": 1})
        with bypass_rls():
            org.save()
        self.assertEqual(_fresh(org).settings, {"k": 1})
