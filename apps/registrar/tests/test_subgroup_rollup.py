"""Alt qrupları birləşik qrupun jurnalına yığmaq (sahib qərarı 2026-09-20).

«234 K az» açılışlarında tələbə yoxdur, uşaqlar «234 K-1»/«234 K-2»-dədir →
hər ikisinin tələbələri birləşik jurnala «alt qrupdan əlavə» kimi düşür
(provenans ``source_group``, qrup DƏYİŞMİR). Yoxlanılır: namizəd qaydası
(öz tələbəsi olan qrup namizəd DEYİL; ad şablonuna uymayan qonşu qrup
götürülmür), idempotentlik, DRY rejimi, hesabat sayları.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit
from apps.registrar import services, subgroup_rollup
from apps.registrar.models import Curriculum, Enrollment, Program, StudentAcademicRecord, Subject
from core.constants import AcademicPeriodType, OrganizationType, OrgUnitType
from core.rls import bypass_rls

User = get_user_model()


class SubgroupRollupTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("sr_owner", "sr_owner@qku.edu.az", "pw")
        with bypass_rls():
            cls.org = Organization.objects.create(
                name="SR Univ",
                slug="sr-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=cls.owner,
                status="active",
                is_active=True,
            )
            cls.specialty = OrgUnit.objects.create(
                organization=cls.org, name="Kompüter Mühəndisliyi", slug="sr-ce", unit_type=OrgUnitType.SPECIALTY
            )

            def unit(name, slug):
                return OrgUnit.objects.create(
                    organization=cls.org, name=name, slug=slug, unit_type=OrgUnitType.GROUP, parent=cls.specialty
                )

            cls.merged = unit("234 K az", "sr-234k")  # tələbəsiz birləşik qrup
            cls.sub1 = unit("234 K-1", "sr-234k1")
            cls.sub2 = unit("234 K-2", "sr-234k2")
            cls.other = unit("234 KE az", "sr-234ke")  # öz tələbəsi var → namizəd deyil
            cls.other_sub = unit("234 KE-1", "sr-234ke1")  # 234 K-in şablonuna uymur
            cls.period = AcademicPeriod.objects.create(
                organization=cls.org,
                name="2026/2027 Payız",
                period_type=AcademicPeriodType.SEMESTER,
                academic_year="2026/2027",
                start_date="2026-09-15",
                end_date="2027-01-31",
                is_current=True,
            )
            cls.admin = User.objects.create_user("sr_admin", "sr_admin@qku.edu.az", "pw", is_superuser=True)
            cls.program = Program.objects.create(organization=cls.org, code="KM", name="Kompüter mühəndisliyi")
            cls.curriculum = Curriculum.objects.create(organization=cls.org, program=cls.program, admission_year=2024)
            cls.mobile = Subject.objects.create(organization=cls.org, code="QKU-1855", name="Mobil proqramlaşdırma")
            cls.web = Subject.objects.create(organization=cls.org, code="QKU-993", name="Veb proqramlaşdırma")
            cls.s1 = cls._student("sr_s1", cls.sub1)
            cls.s2 = cls._student("sr_s2", cls.sub1)
            cls.s3 = cls._student("sr_s3", cls.sub2)
            cls.s_other = cls._student("sr_so", cls.other)
            cls._student("sr_sosub", cls.other_sub)
            cls.off_mobile = services.get_or_create_offering(
                organization=cls.org, subject=cls.mobile, period=cls.period, group=cls.merged
            )
            cls.off_web = services.get_or_create_offering(
                organization=cls.org, subject=cls.web, period=cls.period, group=cls.merged
            )
            cls.off_other = services.get_or_create_offering(
                organization=cls.org, subject=cls.mobile, period=cls.period, group=cls.other
            )

    @classmethod
    def _student(cls, username, group):
        student = User.objects.create_user(username, f"{username}@qku.edu.az", "pw")
        Membership.objects.create(
            user=student,
            organization=cls.org,
            role=cls.org.roles.get(name="student"),
            is_primary=True,
            is_active=True,
        )
        StudentAcademicRecord.objects.create(
            organization=cls.org,
            student=student,
            program=cls.program,
            curriculum=cls.curriculum,
            group=group,
            admission_year=2024,
        )
        return student

    def test_base_name_and_pattern(self):
        self.assertEqual(subgroup_rollup.base_group_name("234 K az"), "234 K")
        self.assertEqual(subgroup_rollup.base_group_name("234 K-1"), "234 K-1")
        pattern = subgroup_rollup.subgroup_pattern("234 K")
        self.assertTrue(pattern.match("234 k-1"))
        self.assertTrue(pattern.match("234 k az-2"))
        self.assertFalse(pattern.match("234 ke-1"))
        self.assertFalse(pattern.match("234 k az"))

    def test_candidates_only_for_student_less_groups_with_matching_subgroups(self):
        with bypass_rls():
            cands = subgroup_rollup.find_candidates(self.org, self.period)
        self.assertEqual({c.offering.pk for c in cands}, {self.off_mobile.pk, self.off_web.pk})
        for cand in cands:
            self.assertEqual([g.name for g in cand.subgroups], ["234 K-1", "234 K-2"])
            self.assertEqual(len(cand.records), 3)

    def test_dry_run_writes_nothing(self):
        with bypass_rls():
            report = subgroup_rollup.rollup(self.org, self.period, by_user=self.admin, reason="test", dry=True)
            self.assertEqual((report["offerings"], report["added"]), (2, 6))
            self.assertFalse(Enrollment.objects.filter(offering__in=[self.off_mobile, self.off_web]).exists())

    def test_rollup_enrolls_with_provenance_and_is_idempotent(self):
        with bypass_rls():
            report = subgroup_rollup.rollup(self.org, self.period, by_user=self.admin, reason="birləşmə")
            self.assertEqual(report["errors"], [])
            self.assertEqual(report["added"], 6)
            rows = Enrollment.objects.filter(offering=self.off_mobile, status=Enrollment.Status.ENROLLED)
            self.assertEqual(rows.count(), 3)
            self.assertEqual(
                {(r.student.username, r.source_group.name) for r in rows.select_related("student", "source_group")},
                {("sr_s1", "234 K-1"), ("sr_s2", "234 K-1"), ("sr_s3", "234 K-2")},
            )
            # Tələbələrin öz qrupu DƏYİŞMİR.
            self.assertEqual(StudentAcademicRecord.objects.get(student=self.s1).group_id, self.sub1.pk)
            # Kənar qrupun jurnalına toxunulmur.
            self.assertEqual(Enrollment.objects.filter(offering=self.off_other).count(), 0)
            # Təkrar qaçış: heç nə əlavə olunmur, hamısı «artıq jurnaldadır».
            again = subgroup_rollup.rollup(self.org, self.period, by_user=self.admin, reason="birləşmə")
            self.assertEqual((again["added"], again["skipped_present"], again["errors"]), (0, 6, []))
