"""«Qruplar» reyestri — Xarici dillər kafedrasının qrupuna tələbə bütün universitetdən (sahib 2026-11-22).

Kafedranın tyutoru öz kafedrasının qrupuna «Tələbə əlavə et» açanda başqa məktəbin qrupsuz tələbəsini və (axtarışda)
başqa qrupdakı tələbəni görür və əlavə edir; adi kafedrada əvvəlki əhatə qalır; başqa təşkilat görünmür; ümumi açar
sönülüdürsə əvvəlki qayda.
"""

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit
from apps.registrar.models import Curriculum, Program, StudentAcademicRecord
from core.constants import AcademicPeriodType, OrganizationType, OrgUnitType
from core.rls import bypass_rls

User = get_user_model()


def _org(slug, owner):
    return Organization.objects.create(
        name=slug, slug=slug, org_type=OrganizationType.UNIVERSITY, owner=owner, status="active", is_active=True
    )


class UniversityWideRegistryTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("uwr_owner", "uwr_owner@qku.edu.az", "pw")
        with bypass_rls():
            cls.org = _org("uwr-univ", cls.owner)
            unit = OrgUnit.objects.create
            philology = unit(organization=cls.org, name="Filologiya", slug="uwr-f", unit_type=OrgUnitType.FACULTY)
            cls.lang_chair = unit(
                organization=cls.org,
                name="Xarici dillər kafedrası",
                slug="uwr-lang",
                unit_type=OrgUnitType.CHAIR,
                parent=philology,
            )
            plain_chair = unit(
                organization=cls.org,
                name="Tarix kafedrası",
                slug="uwr-tar",
                unit_type=OrgUnitType.CHAIR,
                parent=philology,
            )
            cls.lang_group = unit(
                organization=cls.org, name="İng B1", slug="uwr-b1", unit_type=OrgUnitType.GROUP, parent=cls.lang_chair
            )
            cls.plain_group = unit(
                organization=cls.org, name="TAR-1", slug="uwr-t1", unit_type=OrgUnitType.GROUP, parent=plain_chair
            )
            far = unit(organization=cls.org, name="Rəqəmsal", slug="uwr-ff", unit_type=OrgUnitType.FACULTY)
            specialty = unit(
                organization=cls.org, name="İT ixtisası", slug="uwr-sp", unit_type=OrgUnitType.SPECIALTY, parent=far
            )
            cls.far_group = unit(
                organization=cls.org, name="İT-24", slug="uwr-it", unit_type=OrgUnitType.GROUP, parent=specialty
            )
            AcademicPeriod.objects.create(
                organization=cls.org,
                name="2026/2027 Payız",
                period_type=AcademicPeriodType.SEMESTER,
                academic_year="2026/2027",
                start_date="2026-09-01",
                end_date="2027-01-31",
                is_current=True,
            )
            cls.lang_tutor = cls._staff("uwr_lang_tutor", cls.lang_chair)
            cls.plain_tutor = cls._staff("uwr_plain_tutor", plain_chair)
            program = Program.objects.create(organization=cls.org, code="UWR-IT", name="İT", specialty_unit=specialty)
            plan = Curriculum.objects.create(organization=cls.org, program=program, admission_year=2026)
            cls.free_far = cls._record(cls.org, "uwr_free", program, plan, None)
            cls.member_far = cls._record(cls.org, "uwr_member", program, plan, cls.far_group)

            foreign_owner = User.objects.create_user("uwr_f_owner", "uwr_f_owner@qku.edu.az", "pw")
            foreign = _org("uwr-foreign", foreign_owner)
            foreign_program = Program.objects.create(organization=foreign, code="UWR-X", name="X")
            foreign_plan = Curriculum.objects.create(organization=foreign, program=foreign_program, admission_year=2026)
            cls.foreign_free = cls._record(foreign, "uwr_foreign", foreign_program, foreign_plan, None)

    @classmethod
    def _staff(cls, username, scope_unit):
        user = User.objects.create_user(username, f"{username}@qku.edu.az", "pw")
        Membership.objects.create(
            user=user,
            organization=cls.org,
            role=cls.org.roles.get(name="tutor"),
            scope_unit=scope_unit,
            is_primary=True,
            is_active=True,
        )
        return user

    @classmethod
    def _record(cls, organization, username, program, plan, group):
        user = User.objects.create_user(username, f"{username}@qku.edu.az", "pw")
        user.first_name, user.last_name = "Uzaq", "Tələbə"
        user.save(update_fields=["first_name", "last_name"])
        Membership.objects.create(
            user=user,
            organization=organization,
            role=organization.roles.get(name="student"),
            is_primary=True,
            is_active=True,
        )
        return StudentAcademicRecord.objects.create(
            organization=organization, student=user, program=program, curriculum=plan, group=group, admission_year=2026
        )

    def _client(self, user):
        client = Client()
        client.force_login(user)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        return client

    def _candidates(self, user, group, **params):
        url = reverse("organizations:group_student_candidates", kwargs={"slug": self.org.slug, "unit_id": group.pk})
        response = self._client(user).get(url, {"limit": 50, **params})
        self.assertEqual(response.status_code, 200, response.content)
        return {row["id"].removeprefix("x:") for row in response.json()["results"]}

    def test_language_chair_tutor_sees_students_of_the_whole_university(self):
        self.assertIn(str(self.free_far.pk), self._candidates(self.lang_tutor, self.lang_group))
        found = self._candidates(self.lang_tutor, self.lang_group, q="Uzaq")
        self.assertIn(str(self.member_far.pk), found)
        self.assertNotIn(str(self.foreign_free.pk), found)

    def test_language_chair_tutor_adds_student_from_another_school(self):
        response = self._client(self.lang_tutor).post(
            reverse("organizations:group_action", kwargs={"slug": self.org.slug}),
            {"action": "add_students", "id": str(self.lang_group.pk), "record_ids": [str(self.free_far.pk)]},
        )
        self.assertEqual(response.status_code, 200, response.content)
        with bypass_rls():
            self.free_far.refresh_from_db()
        self.assertEqual(self.free_far.group_id, self.lang_group.pk)

    def test_plain_chair_tutor_keeps_own_scope(self):
        self.assertNotIn(str(self.free_far.pk), self._candidates(self.plain_tutor, self.plain_group))
        self.assertNotIn(str(self.member_far.pk), self._candidates(self.plain_tutor, self.plain_group, q="Uzaq"))
        response = self._client(self.plain_tutor).post(
            reverse("organizations:group_action", kwargs={"slug": self.org.slug}),
            {"action": "add_students", "id": str(self.plain_group.pk), "record_ids": [str(self.free_far.pk)]},
        )
        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(response.json()["error"], "no_candidates")

    @override_settings(ACADEMIC_UNIVERSITY_WIDE_CHAIRS=False)
    def test_switch_off_restores_old_scope(self):
        self.assertNotIn(str(self.free_far.pk), self._candidates(self.lang_tutor, self.lang_group))
