"""Engine-neutral checks for the remaining migration-target validators."""

import datetime

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit
from apps.registrar import rubrics, services
from apps.registrar.integrity import validate_same_organization_actor
from apps.registrar.models import Curriculum, CurriculumSubject, Program, Rubric, Subject
from core.constants import AcademicPeriodType, OrganizationType, OrgUnitType
from core.rls import bypass_rls

User = get_user_model()


class RemainingIntegrityServiceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        with bypass_rls():
            cls.owner_a = User.objects.create_user("remaining_owner_a", password="pw")
            cls.owner_b = User.objects.create_user("remaining_owner_b", password="pw")
            cls.org_a = Organization.objects.create(
                name="Remaining Integrity A",
                slug="remaining-integrity-a",
                org_type=OrganizationType.UNIVERSITY,
                owner=cls.owner_a,
                status="active",
                is_active=True,
            )
            cls.org_b = Organization.objects.create(
                name="Remaining Integrity B",
                slug="remaining-integrity-b",
                org_type=OrganizationType.UNIVERSITY,
                owner=cls.owner_b,
                status="active",
                is_active=True,
            )
            cls.group_a = OrgUnit.objects.create(
                organization=cls.org_a,
                name="Remaining Group A",
                slug="remaining-group-a",
                unit_type=OrgUnitType.GROUP,
            )
            cls.period_a = AcademicPeriod.objects.create(
                organization=cls.org_a,
                name="Remaining Period A",
                period_type=AcademicPeriodType.SEMESTER,
                academic_year="2026/2027",
                start_date=datetime.date(2026, 9, 1),
                end_date=datetime.date(2027, 1, 31),
            )
            cls.program_a = Program.objects.create(
                organization=cls.org_a,
                code="RIA",
                name="Remaining A",
            )
            cls.curriculum_a = Curriculum.objects.create(
                organization=cls.org_a,
                program=cls.program_a,
                admission_year=2026,
            )
            cls.elective_a = Subject.objects.create(
                organization=cls.org_a,
                code="RIA-E",
                name="Valid elective",
            )
            cls.non_elective_a = Subject.objects.create(
                organization=cls.org_a,
                code="RIA-N",
                name="Not in elective block",
            )
            CurriculumSubject.objects.create(
                organization=cls.org_a,
                curriculum=cls.curriculum_a,
                subject=cls.elective_a,
                semester_number=1,
                is_elective=True,
                elective_group="BLOCK-A",
            )
            cls.inactive_actor = User.objects.create_user("remaining_inactive_actor", password="pw")
            Membership.objects.create(
                organization=cls.org_a,
                user=cls.inactive_actor,
                role=cls.org_a.roles.get(name="member"),
                is_active=False,
            )
            cls.cross_actor = User.objects.create_user("remaining_cross_actor", password="pw")
            Membership.objects.create(
                organization=cls.org_b,
                user=cls.cross_actor,
                role=cls.org_b.roles.get(name="member"),
                is_active=True,
            )

    def test_historical_actor_accepts_inactive_same_org_membership(self):
        with bypass_rls():
            validate_same_organization_actor(
                organization=self.org_a,
                user=self.inactive_actor,
            )

    def test_live_actor_requires_active_membership(self):
        with bypass_rls(), self.assertRaises(ValidationError) as caught:
            services.choose_group_elective(
                organization=self.org_a,
                group=self.group_a,
                curriculum=self.curriculum_a,
                period=self.period_a,
                elective_group="BLOCK-A",
                subject=self.elective_a,
                decided_by=self.inactive_actor,
                enforce_window=False,
            )
        self.assertIn("decided_by", caught.exception.message_dict)

    def test_live_actor_requires_an_active_organization(self):
        with bypass_rls():
            Organization.objects.filter(pk=self.org_a.pk).update(is_active=False)
            with self.assertRaises(ValidationError) as caught:
                validate_same_organization_actor(
                    organization=self.org_a,
                    user=self.owner_a,
                    require_active=True,
                )
        self.assertIn("actor", caught.exception.message_dict)

    def test_cross_tenant_actor_is_rejected(self):
        with bypass_rls(), self.assertRaises(ValidationError) as caught:
            validate_same_organization_actor(
                organization=self.org_a,
                user=self.cross_actor,
            )
        self.assertIn("actor", caught.exception.message_dict)

    def test_elective_choice_must_be_an_option_in_the_named_block(self):
        with bypass_rls(), self.assertRaises(ValidationError) as caught:
            services.choose_group_elective(
                organization=self.org_a,
                group=self.group_a,
                curriculum=self.curriculum_a,
                period=self.period_a,
                elective_group="BLOCK-A",
                subject=self.non_elective_a,
                decided_by=self.owner_a,
                enforce_window=False,
            )
        self.assertIn("chosen_subject", caught.exception.message_dict)

    def test_existing_rubric_cannot_be_edited_through_another_tenant(self):
        with bypass_rls():
            rubric = Rubric.objects.create(
                organization=self.org_b,
                name="Foreign rubric",
            )
            with self.assertRaises(ValidationError) as caught:
                rubrics.save_rubric(
                    organization=self.org_a,
                    name="Tampered rubric",
                    description="",
                    criteria=[("Criterion", 10)],
                    rubric=rubric,
                )
            rubric.refresh_from_db()
        self.assertIn("rubric", caught.exception.message_dict)
        self.assertEqual(rubric.name, "Foreign rubric")
