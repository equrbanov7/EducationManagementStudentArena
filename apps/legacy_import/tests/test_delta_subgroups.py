"""Köhnə sistemin ALT QRUP tələbələri — ``subgroups`` fazası (sahib 2026-10-25).

Yoxlanılır: legacy-də alt qrupda olan, yeni sistemdə ana qrupda olan tələbənin alt qrup jurnalındakı «alt
qrupdan əlavə» qeydiyyatına rəsmi «Alt qrupa yerləşdirildi» sətri yazılır (səbəb, mənbə/hədəf qrup, audit);
izi olmayan alt qrup ana qrupa bağlanır («Bi» ↔ «Bİ» fərqi nəzərə alınmır); dry-run heç nə yazmır; ikinci
qaçış 0 yazı verir; qrupu fərqli, amma alt qrup olmayan legacy qrup yalnız sayılır.
"""

from django.test import SimpleTestCase, TestCase

from apps.audit.models import AuditLog
from apps.legacy_import.services.delta.subgroups import REASON, is_family, looks_like_subgroup
from apps.organizations.models import OrgUnit
from apps.registrar.models import CourseOffering, Enrollment, SubgroupPlacementEvent
from core.rls import bypass_rls

from . import test_delta_apply as base
from .test_delta_apply import _bundle

GROUP_901 = {
    "id": 901,
    "name": "101 A1",
    "speciality_id": 5,
    "department_id": 3,
    "start_year": 2026,
    "eyani_qiyabi": "Əyani",
    "bak_or_mag": "bak",
    "sector": "az",
    "kollec_or_uni": "University",
    "is_new": True,
}


def _subgroup_bundle():
    """Mövcud tələbə (legacy id 1) legacy-də «101 A1» alt qrupundadır; jurnal yalnız alt qrupundur."""
    bundle = _bundle()
    bundle["students"] = [dict(bundle["students"][0], group_id=901)]
    bundle["journals"] = [dict(bundle["journals"][0], groups_id='["901"]', students_id='["1"]')]
    bundle["points"] = [p for p in bundle["points"] if p["student_id"] == 1 and p["journal_uniqid"] == "abcDEF1234"]
    bundle["syllabi"] = []
    return bundle


class DeltaSubgroupsTests(TestCase):
    """``DeltaApplyTests``-in fikstürü (təşkilat, «101 A» ana qrupu, mövcud tələbə) üzərində."""

    setUpTestData = classmethod(base.DeltaApplyTests.setUpTestData.__func__)
    _run = base.DeltaApplyTests._run

    def test_subgroup_student_gets_official_placement_and_rerun_is_noop(self):
        bundle = _subgroup_bundle()
        dry = self._run(apply=False, bundle=bundle)
        self.assertEqual(dry.counters["subgroups.placement_recorded"], 1)
        with bypass_rls():
            self.assertFalse(SubgroupPlacementEvent.objects.exists())

        run = self._run(apply=True, bundle=bundle)
        self.assertEqual(run.counters["subgroups.placement_recorded"], 1)
        self.assertEqual(run.counters["subgroups.student_marked"], 1)
        with bypass_rls():
            subgroup = OrgUnit.objects.get(organization=self.org, slug="myedu-grp-901")
            self.assertEqual(subgroup.settings["parent_group"], str(self.group.pk))
            offering = CourseOffering.objects.get(organization=self.org, group=subgroup)
            enrollment = Enrollment.objects.get(offering=offering, student=self.existing)
            self.assertEqual(enrollment.source_group_id, self.group.pk)
            event = SubgroupPlacementEvent.objects.get(enrollment=enrollment)
            self.assertEqual((event.kind, event.reason), ("place", REASON))
            self.assertEqual((event.source_group_id, event.target_group_id), (self.group.pk, subgroup.pk))
            self.assertEqual(event.details["via"], "import")
            self.assertEqual(event.actor_id, self.actor.pk)
            self.assertTrue(
                AuditLog.objects.filter(
                    resource_type="registrar.subgroup_placement", resource_id=str(event.pk)
                ).exists()
            )

        again = self._run(apply=True, bundle=bundle)
        self.assertEqual(again.counters["subgroups.placement_already_recorded"], 1)
        self.assertNotIn("written.subgroup_placements", again.counters)
        with bypass_rls():
            self.assertEqual(SubgroupPlacementEvent.objects.count(), 1)

    def test_existing_subgroup_without_trail_is_linked_dotted_i_tolerant(self):
        with bypass_rls():
            parent = OrgUnit.objects.create(
                organization=self.org, name="101 Bİ", slug="d-g-bi", unit_type="group", parent=self.specialty
            )
            subgroup = OrgUnit.objects.create(
                organization=self.org, name="101 Bi 1", slug="d-g-bi1", unit_type="group", parent=self.specialty
            )
        bundle = _subgroup_bundle()
        bundle["groups"].append(dict(GROUP_901, id=902, name="101 Bi 1"))
        bundle["students"][0]["group_id"] = 902
        run = self._run(apply=True, bundle=dict(bundle, journals=[], points=[]))
        self.assertEqual(run.counters["subgroups.unit_linked"], 1)
        self.assertEqual(run.counters["subgroups.student_without_subgroup_journal"], 1)
        with bypass_rls():
            subgroup.refresh_from_db()
            self.assertEqual(subgroup.settings["parent_group"], str(parent.pk))
            self.assertTrue(AuditLog.objects.filter(object_id=str(subgroup.pk)).exists())
        self.assertEqual(
            self._run(apply=True, bundle=dict(bundle, journals=[], points=[])).counters["touched.groups"], 0
        )

    def test_other_non_subgroup_legacy_group_is_report_only(self):
        bundle = _subgroup_bundle()
        bundle["groups"].append(dict(GROUP_901, id=903, name="102 B"))
        with bypass_rls():
            OrgUnit.objects.create(
                organization=self.org, name="102 B", slug="d-g-102", unit_type="group", parent=self.specialty
            )
        bundle["students"][0]["group_id"] = 903
        run = self._run(apply=True, bundle=dict(bundle, journals=[], points=[]))
        self.assertEqual(run.counters["subgroups.group_differs_report_only"], 1)
        self.assertNotIn("subgroups.placement_recorded", run.counters)


class SubgroupNameRulesTests(SimpleTestCase):
    def test_family_and_tail_rules(self):
        self.assertTrue(is_family("536 Bİ", "536 Bi 1"))
        self.assertTrue(is_family("135 Sİ", "135Si-2"))
        self.assertTrue(is_family("536 MU", "536 MU1"))
        self.assertFalse(is_family("135 Sİ ing", "135 Si-1"))
        self.assertFalse(is_family("036", "0361"))
        self.assertTrue(looks_like_subgroup("336F2"))
        self.assertTrue(looks_like_subgroup("534 TB 1"))
        self.assertFalse(looks_like_subgroup("01-əcnəbilər2026"))
        self.assertFalse(looks_like_subgroup("2026"))
