"""Struktur planı (sahib 2026-09-27): yeni forma + köhnə ad/yer tarixçəsi, idempotent."""

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase

from apps.accounts.services import staff_roster as roster
from apps.organizations.models import Membership, Organization, OrgUnit
from apps.organizations.structure_plan import apply_structure_plan, norm, unit_history
from core.constants import OrganizationType, OrgUnitType
from core.rls import bypass_rls

User = get_user_model()

PLAN = {
    "source": "t-plan",
    "date": "2026-09-27",
    "units": [
        {"key": "office", "name": "Arxiv şöbəsi", "type": "department", "aliases": ["Arxiv şöbəsi"]},
        {
            "key": "old_school",
            "name": "Köhnə məktəb",
            "type": "faculty",
            "aliases": ["Köhnə Məktəbi"],
            "from": [{"type": "faculty", "name": "Köhnə fakültə"}],
        },
        {"key": "new_school", "name": "Yeni məktəb", "type": "faculty", "specialties": ["Kompüter elmləri"]},
        {
            "key": "chair",
            "name": "İT kafedrası",
            "type": "chair",
            "parent": "new_school",
            "from": [{"type": "chair", "name": "İnformasiya texnologiyaları"}],
            "merge": [{"type": "chair", "name": "Proqramlaşdırma"}],
        },
    ],
    "campuses": {"Korpus B": ["Yeni məktəb"]},
}


class StructurePlanTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("sp_owner", "sp_owner@qku.edu.az", "pw")
        with bypass_rls():
            cls.org = Organization.objects.create(
                name="SP Univ",
                slug="sp-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=cls.owner,
                status="active",
                is_active=True,
                settings={"campuses": [{"building": "Korpus B", "units": ["Kompüter elmləri"]}]},
            )
            mk = lambda **kw: OrgUnit.objects.create(organization=cls.org, **kw)  # noqa: E731
            cls.faculty = mk(name="Köhnə fakültə", slug="kf", unit_type=OrgUnitType.FACULTY)
            cls.chair = mk(
                name="İnformasiya texnologiyaları", slug="it", unit_type=OrgUnitType.CHAIR, parent=cls.faculty
            )
            cls.victim = mk(name="Proqramlaşdırma", slug="pr", unit_type=OrgUnitType.CHAIR, parent=cls.faculty)
            cls.specialty = mk(name="Kompüter Elmləri", slug="ke", unit_type=OrgUnitType.SPECIALTY, parent=cls.faculty)
            cls.group = mk(name="231 KE", slug="g231", unit_type=OrgUnitType.GROUP, parent=cls.specialty)
            cls.other_specialty = mk(name="Biologiya", slug="bio", unit_type=OrgUnitType.SPECIALTY, parent=cls.faculty)
            teacher = User.objects.create_user("sp_teacher", "sp_teacher@qku.edu.az", "pw")
            cls.membership = Membership.objects.create(
                user=teacher,
                organization=cls.org,
                role=cls.org.roles.get(name="teacher"),
                scope_unit=cls.victim,
                is_active=True,
            )

    def _run(self, apply):
        with bypass_rls():
            return apply_structure_plan(self.org, PLAN, apply=apply)

    def test_dry_run_writes_nothing(self):
        report = self._run(False)
        self.assertEqual(report.counts["YARADILIR"], 2)
        self.assertEqual(report.counts["DƏYİŞİR"], 2)
        self.assertEqual(report.counts["İXTİSAS"], 1)
        self.assertFalse(OrgUnit.objects.filter(name="Yeni məktəb").exists())
        self.chair.refresh_from_db()
        self.assertEqual(self.chair.name, "İnformasiya texnologiyaları")

    def test_apply_renames_moves_and_keeps_history(self):
        report = self._run(True)
        self.assertFalse(report.problems)
        new_school = OrgUnit.objects.get(organization=self.org, name="Yeni məktəb")
        self.faculty.refresh_from_db()
        self.chair.refresh_from_db()
        self.specialty.refresh_from_db()
        self.group.refresh_from_db()
        self.other_specialty.refresh_from_db()
        self.assertEqual(self.faculty.name, "Köhnə məktəb")
        self.assertEqual(unit_history(self.faculty)[0]["name"], "Köhnə fakültə")
        # Kafedra: ad + yer dəyişir, tarixçədə KÖHNƏ valideynin KÖHNƏ adı qalır.
        self.assertEqual((self.chair.name, self.chair.parent_id), ("İT kafedrası", new_school.id))
        self.assertEqual(unit_history(self.chair)[0]["parent"], "Köhnə fakültə")
        # İxtisas qrupu ilə birlikdə köçür (path kaskadı); siyahıda olmayan ixtisas yerində qalır.
        self.assertEqual(self.specialty.parent_id, new_school.id)
        self.assertTrue(self.group.path.startswith(f"{new_school.path}/"))
        self.assertEqual(self.other_specialty.parent_id, self.faculty.id)
        # Qovuşma: üzvlük hədəfə keçir, qovuşan vahid arxivlənir.
        self.membership.refresh_from_db()
        self.victim.refresh_from_db()
        self.assertEqual(self.membership.scope_unit_id, self.chair.id)
        self.assertFalse(self.victim.is_active)
        self.assertEqual(unit_history(self.victim)[0]["merged_into_name"], "İT kafedrası")
        # Yeni vahid ləqəbi və korpus xəritəsi.
        office = OrgUnit.objects.get(organization=self.org, name="Arxiv şöbəsi")
        self.assertEqual(office.settings["aliases"], ["Arxiv şöbəsi"])
        self.org.refresh_from_db()
        self.assertIn("Yeni məktəb", self.org.settings["campuses"][0]["units"])

    def test_second_run_is_noop(self):
        self._run(True)
        report = self._run(True)
        self.assertEqual(set(report.counts), {"EYNİDİR", "QOVUŞMA-YOX"})
        self.faculty.refresh_from_db()
        self.assertEqual(len(unit_history(self.faculty)), 1)

    def test_roster_matches_section_by_alias(self):
        self._run(True)
        units = list(OrgUnit.objects.filter(organization=self.org, is_active=True))
        self.assertEqual(roster.match_unit("Köhnə Məktəbi", units).id, self.faculty.id)


class HelpersTest(SimpleTestCase):
    def test_norm_folds_azerbaijani_letters(self):
        self.assertEqual(norm("İnformasiya  Texnologiyaları"), norm("informasiya texnologiyalari"))

    def test_head_titles(self):
        self.assertTrue(roster.is_head_title("Müdir "))
        self.assertTrue(roster.is_head_title("Dekan"))
        self.assertFalse(roster.is_head_title("Müdir müavini"))
        self.assertFalse(roster.is_head_title("Müdir əvəzi"))
        self.assertFalse(roster.is_head_title("Dekan müvini"))
        self.assertFalse(roster.is_head_title("Laborant"))
