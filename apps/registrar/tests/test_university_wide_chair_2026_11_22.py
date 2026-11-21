"""Xarici dillər kafedrası — tələbə seçimi bütün universitet üzrə (sahib 2026-11-22, RİM rəhbəri).

Sahib: «Xarici dil kafedrasında tyutorlar və dekanlıq işçiləri qrup yaradanda və ya alt qrupa tələbə əlavə edəndə
bütün universitetdən qrupları götürürlər — onların qrup-tələbə görünüşünü universitet üzrə dəyişin».

* kafedranın səviyyə qrupunun jurnalında «Alt qrupdan tələbə əlavə et» başqa məktəbin qrupunu və tələbəsini göstərir
  və əlavə edir (axtarış → tələbələr → önbaxış → əlavə);
* adi kafedranın tyutoru yenə yalnız öz əhatəsini görür;
* başqa təşkilatın qrupu / tələbəsi heç vaxt görünmür;
* ümumi açar sönülü və ya kafedrada ``university_wide_students: false`` → əvvəlki qayda; başqa kafedra açıq
  ``true`` ilə qoşula bilər;
* səviyyə qrupları (kohort) və «Alt qrupa yerləşdirmə» aləti eyni qaydanı işlədir.
"""

from types import SimpleNamespace

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit
from apps.organizations.university_wide_scope import is_university_wide_chair, unit_is_university_wide
from apps.registrar import language_cohort_query, roster_source_scope, services, subgroup_access
from apps.registrar.models import (
    CourseOffering,
    Curriculum,
    CurriculumSubject,
    Enrollment,
    Program,
    StudentAcademicRecord,
    Subject,
)
from apps.registrar.tests import test_guest_roster as _guest_tests
from apps.registrar.tests import test_language_cohorts as _cohort_tests
from core.constants import AcademicPeriodType, OrganizationType, OrgUnitType
from core.rls import bypass_rls

User = get_user_model()


def _doc():
    return SimpleUploadedFile(
        "teqdimat.pdf", b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n", content_type="application/pdf"
    )


def _org(slug, owner):
    return Organization.objects.create(
        name=slug, slug=slug, org_type=OrganizationType.UNIVERSITY, owner=owner, status="active", is_active=True
    )


class _Base(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("uw_owner", "uw_owner@qku.edu.az", "pw")
        with bypass_rls():
            cls.org = _org("uw-univ", cls.owner)
            unit = OrgUnit.objects.create
            cls.philology = unit(organization=cls.org, name="Filologiya", slug="uw-f", unit_type=OrgUnitType.FACULTY)
            cls.lang_chair = unit(
                organization=cls.org,
                name="Xarici dillər kafedrası",
                slug="uw-lang",
                unit_type=OrgUnitType.CHAIR,
                parent=cls.philology,
            )
            cls.plain_chair = unit(
                organization=cls.org,
                name="Tarix kafedrası",
                slug="uw-tar",
                unit_type=OrgUnitType.CHAIR,
                parent=cls.philology,
            )
            cls.lang_group = unit(
                organization=cls.org, name="İng B1", slug="uw-b1", unit_type=OrgUnitType.GROUP, parent=cls.lang_chair
            )
            cls.plain_group = unit(
                organization=cls.org, name="TAR-1", slug="uw-t1", unit_type=OrgUnitType.GROUP, parent=cls.plain_chair
            )
            cls.far_faculty = unit(organization=cls.org, name="Rəqəmsal", slug="uw-ff", unit_type=OrgUnitType.FACULTY)
            cls.far_group = unit(
                organization=cls.org, name="İT-24", slug="uw-it", unit_type=OrgUnitType.GROUP, parent=cls.far_faculty
            )
            cls.period = AcademicPeriod.objects.create(
                organization=cls.org,
                name="2026/2027 Payız",
                period_type=AcademicPeriodType.SEMESTER,
                academic_year="2026/2027",
                start_date="2026-09-01",
                end_date="2027-01-31",
                is_current=True,
            )
            cls.teacher = User.objects.create_user("uw_teacher", "uw_teacher@qku.edu.az", "pw")
            cls.lang_tutor = User.objects.create_user("uw_lang_tutor", "uw_lang_tutor@qku.edu.az", "pw")
            cls.plain_tutor = User.objects.create_user("uw_plain_tutor", "uw_plain_tutor@qku.edu.az", "pw")
            cls.lang_dean = User.objects.create_user("uw_lang_dean", "uw_lang_dean@qku.edu.az", "pw")
            cls.plain_dean = User.objects.create_user("uw_plain_dean", "uw_plain_dean@qku.edu.az", "pw")
            for user, role, scope_unit in (
                (cls.teacher, "teacher", None),
                (cls.lang_tutor, "tutor", cls.lang_chair),
                (cls.plain_tutor, "tutor", cls.plain_chair),
                (cls.lang_dean, "dean", cls.lang_chair),
                (cls.plain_dean, "dean", cls.plain_chair),
            ):
                Membership.objects.create(
                    user=user,
                    organization=cls.org,
                    role=cls.org.roles.get(name=role),
                    scope_unit=scope_unit,
                    is_primary=True,
                    is_active=True,
                )
            cls.program = Program.objects.create(organization=cls.org, code="IT", name="İT")
            cls.curriculum = Curriculum.objects.create(organization=cls.org, program=cls.program, admission_year=2026)
            history = Subject.objects.create(organization=cls.org, code="TAR101", name="Tarix")
            CurriculumSubject.objects.create(
                organization=cls.org, curriculum=cls.curriculum, subject=history, semester_number=1
            )
            cls.far_student = cls._student("uw_far", cls.far_group)
            cls.english = Subject.objects.create(organization=cls.org, code="ENG-B1", name="İngilis dili B1")
            cls.lang_offering = CourseOffering.objects.create(
                organization=cls.org,
                group=cls.lang_group,
                subject=cls.english,
                period=cls.period,
                instructor=cls.teacher,
            )
            cls.plain_offering = CourseOffering.objects.create(
                organization=cls.org,
                group=cls.plain_group,
                subject=cls.english,
                period=cls.period,
                instructor=cls.teacher,
            )
            # Başqa təşkilat — eyni adlı kafedra, qrup və tələbə heç vaxt görünməməlidir.
            cls.foreign_owner = User.objects.create_user("uw_f_owner", "uw_f_owner@qku.edu.az", "pw")
            cls.foreign = _org("uw-foreign", cls.foreign_owner)
            cls.foreign_group = OrgUnit.objects.create(
                organization=cls.foreign, name="Yad qrup", slug="uw-yad", unit_type=OrgUnitType.GROUP
            )

    @classmethod
    def _student(cls, username, group):
        student = User.objects.create_user(username, f"{username}@qku.edu.az", "pw")
        student.first_name, student.last_name = "Uzaq", "Tələbə"
        student.save(update_fields=["first_name", "last_name"])
        Membership.objects.create(
            user=student, organization=cls.org, role=cls.org.roles.get(name="student"), is_primary=True, is_active=True
        )
        record = StudentAcademicRecord.objects.create(
            organization=cls.org,
            student=student,
            program=cls.program,
            curriculum=cls.curriculum,
            group=group,
            admission_year=2026,
        )
        services.enroll_mandatory_subjects(record=record, period=cls.period, semester_number=1)
        return student

    def _client(self, user):
        client = Client()
        client.force_login(user)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        return client

    def _group_ids(self, user, offering):
        response = self._client(user).get(reverse("registrar:journal_guest_group_search", args=[offering.pk]))
        self.assertEqual(response.status_code, 200, response.content)
        return {row["id"] for row in response.json()["results"]}

    def _set_flag(self, unit, value):
        with bypass_rls():
            settings = dict(unit.settings or {})
            settings["university_wide_students"] = value
            OrgUnit.objects.filter(pk=unit.pk).update(settings=settings)


class ChairDetectionTest(_Base):
    def test_default_is_the_foreign_language_chair_only(self):
        self.assertTrue(is_university_wide_chair(self.lang_chair))
        self.assertFalse(is_university_wide_chair(self.plain_chair))
        self.assertTrue(unit_is_university_wide(self.org, self.lang_group))
        self.assertTrue(unit_is_university_wide(self.org, self.lang_group.pk))
        self.assertFalse(unit_is_university_wide(self.org, self.plain_group))
        self.assertFalse(unit_is_university_wide(self.org, self.far_group))

    def test_structure_key_marks_a_renamed_chair(self):
        unit = OrgUnit(
            unit_type=OrgUnitType.CHAIR,
            name="Dillər mərkəzi",
            settings={"structure_key": "qku-structure-2026-09-27:ch_foreign_lang"},
        )
        self.assertTrue(is_university_wide_chair(unit))
        self.assertFalse(is_university_wide_chair(OrgUnit(unit_type=OrgUnitType.GROUP, name="Xarici dil qrupu")))


class GuestRosterUniversityWideTest(_Base):
    def test_language_chair_tutor_sees_and_adds_student_from_another_school(self):
        self.assertIn(str(self.far_group.pk), self._group_ids(self.lang_tutor, self.lang_offering))
        client = self._client(self.lang_tutor)
        students = client.get(
            reverse("registrar:journal_guest_student_search", args=[self.lang_offering.pk]),
            {"group": str(self.far_group.pk)},
        ).json()["results"]
        self.assertEqual([row["id"] for row in students], [str(self.far_student.pk)])
        preview = client.get(
            reverse("registrar:journal_guest_add_preview", args=[self.lang_offering.pk]),
            {"group": str(self.far_group.pk), "student": str(self.far_student.pk)},
        )
        self.assertEqual(preview.status_code, 200, preview.content)
        response = client.post(
            reverse("registrar:journal_guest_add", args=[self.lang_offering.pk]),
            {"group": str(self.far_group.pk), "student": str(self.far_student.pk), "reason": "B1", "document": _doc()},
        )
        self.assertEqual(response.status_code, 200, response.content)
        with bypass_rls():
            enrollment = Enrollment.objects.get(offering=self.lang_offering, student=self.far_student)
            record = StudentAcademicRecord.objects.get(student=self.far_student)
        self.assertEqual(enrollment.source_group_id, self.far_group.pk)
        self.assertEqual(record.group_id, self.far_group.pk)  # ev qrupu toxunulmur

    def test_plain_chair_tutor_still_sees_only_own_scope(self):
        ids = self._group_ids(self.plain_tutor, self.plain_offering)
        self.assertNotIn(str(self.far_group.pk), ids)
        response = self._client(self.plain_tutor).post(
            reverse("registrar:journal_guest_add", args=[self.plain_offering.pk]),
            {"group": str(self.far_group.pk), "student": str(self.far_student.pk), "reason": "x", "document": _doc()},
        )
        self.assertEqual(response.status_code, 403, response.content)

    def test_who_may_manage_the_roster_is_unchanged(self):
        """Dil kafedrasının tyutoru başqa kafedranın jurnalını açmır (404) — yalnız namizədlər genişlənir."""
        response = self._client(self.lang_tutor).get(
            reverse("registrar:journal_guest_group_search", args=[self.plain_offering.pk])
        )
        self.assertEqual(response.status_code, 404)

    def test_other_organization_never_appears(self):
        ids = self._group_ids(self.lang_tutor, self.lang_offering)
        self.assertNotIn(str(self.foreign_group.pk), ids)
        self.assertNotIn(str(self.lang_group.pk), ids)  # jurnalın öz qrupu
        payload = (
            self._client(self.lang_tutor)
            .get(
                reverse("registrar:journal_guest_student_search", args=[self.lang_offering.pk]),
                {"group": str(self.foreign_group.pk)},
            )
            .json()
        )
        self.assertEqual(payload["results"], [])

    @override_settings(ACADEMIC_UNIVERSITY_WIDE_CHAIRS=False)
    def test_switch_off_restores_old_behaviour(self):
        self.assertNotIn(str(self.far_group.pk), self._group_ids(self.lang_tutor, self.lang_offering))

    def test_explicit_flag_opts_out_and_opts_in(self):
        self._set_flag(self.lang_chair, False)
        self.assertNotIn(str(self.far_group.pk), self._group_ids(self.lang_tutor, self.lang_offering))
        self._set_flag(self.plain_chair, True)
        self.assertIn(str(self.far_group.pk), self._group_ids(self.plain_tutor, self.plain_offering))


class CohortAndPlacementToolTest(_Base):
    def _cohort(self, chair):
        return SimpleNamespace(organization=self.org, department=chair)

    def test_language_cohort_candidates_cover_the_university(self):
        cohort = self._cohort(self.lang_chair)
        groups = set(roster_source_scope.cohort_source_groups(self.lang_tutor, cohort).values_list("pk", flat=True))
        self.assertIn(self.far_group.pk, groups)
        self.assertNotIn(self.foreign_group.pk, groups)
        self.assertTrue(roster_source_scope.cohort_allows_group(self.lang_tutor, cohort, self.far_group.pk))
        self.assertFalse(roster_source_scope.cohort_allows_group(self.lang_tutor, cohort, self.foreign_group.pk))

    def test_plain_chair_cohort_keeps_scope(self):
        cohort = self._cohort(self.plain_chair)
        groups = set(roster_source_scope.cohort_source_groups(self.plain_tutor, cohort).values_list("pk", flat=True))
        self.assertNotIn(self.far_group.pk, groups)
        self.assertFalse(roster_source_scope.cohort_allows_group(self.plain_tutor, cohort, self.far_group.pk))

    def test_teacher_without_roster_key_gets_nothing_new(self):
        cohort = self._cohort(self.lang_chair)
        self.assertFalse(roster_source_scope.cohort_is_wide(self.teacher, cohort))
        self.assertFalse(roster_source_scope.cohort_source_groups(self.teacher, cohort).exists())

    def test_placement_tool_dean_of_language_chair_sees_the_university(self):
        lang = set(subgroup_access.scoped_groups(self.lang_dean, self.org).values_list("pk", flat=True))
        plain = set(subgroup_access.scoped_groups(self.plain_dean, self.org).values_list("pk", flat=True))
        self.assertIn(self.far_group.pk, lang)
        self.assertNotIn(self.foreign_group.pk, lang)
        self.assertTrue(subgroup_access.group_in_scope(self.lang_dean, self.org, self.far_group.pk))
        self.assertNotIn(self.far_group.pk, plain)
        self.assertFalse(subgroup_access.group_in_scope(self.plain_dean, self.org, self.far_group.pk))

    @override_settings(ACADEMIC_UNIVERSITY_WIDE_CHAIRS=False)
    def test_switch_off_keeps_cohort_and_tool_scope(self):
        self.assertNotIn(
            self.far_group.pk,
            set(
                roster_source_scope.cohort_source_groups(self.lang_tutor, self._cohort(self.lang_chair)).values_list(
                    "pk", flat=True
                )
            ),
        )
        self.assertFalse(subgroup_access.group_in_scope(self.lang_dean, self.org, self.far_group.pk))


class LanguageCohortPlacementTest(_guest_tests._GuestRosterBase):
    """Real səviyyə qrupu: dil kafedrasının koordinatoru başqa məktəbin tələbəsini öz səviyyə jurnalından keçirir."""

    create = _cohort_tests.LanguageCohortTests.create
    record = _cohort_tests.LanguageCohortTests.record
    move = _cohort_tests.LanguageCohortTests.move

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        with bypass_rls():
            from apps.workload.tests.factories import activate_member

            activate_member(
                cls.org,
                cls.coordinator,
                "uw_source_reader",
                permissions=["journal.view"],
                scope_unit=cls.chair,
                scope_type="unit",
            )
            OrgUnit.objects.filter(pk=cls.chair.pk).update(name="Xarici dillər kafedrası")
            cls.chair.refresh_from_db()
            cls.history.name = "Xarici dil-1 (Elementary)"
            cls.history.save(update_fields=["name"])
            cls.intermediate = Subject.objects.create(
                organization=cls.org, code="UW-LANG-INT", name="Xarici dil-1 (Intermediate)"
            )
            for user in (cls.host, cls.guest, cls.far_student, cls.teacher):
                user.profile.organization = cls.org
                user.profile.save(update_fields=["organization"])

    def _candidate_ids(self, cohort):
        records = language_cohort_query.candidate_records(cohort=cohort, actor=self.coordinator)
        return {record.student_id for record in records}

    def test_student_from_another_school_is_candidate_and_moves_from_own_level_journal(self):
        with bypass_rls():
            cohort = self.create()
            self.assertIn(self.far_student.pk, self._candidate_ids(cohort))
            source = Enrollment.objects.get(student=self.far_student, offering__subject=self.history)
            target = self.move(cohort, student=self.far_student)
            source.refresh_from_db()
        self.assertEqual(source.status, Enrollment.Status.DROPPED)
        self.assertEqual(target.source_group_id, self.far_group.pk)
        self.assertEqual(self.record(self.far_student).group_id, self.far_group.pk)

    @override_settings(ACADEMIC_UNIVERSITY_WIDE_CHAIRS=False)
    def test_switch_off_keeps_the_old_scope(self):
        with bypass_rls():
            cohort = self.create()
            self.assertNotIn(self.far_student.pk, self._candidate_ids(cohort))
            with self.assertRaises(PermissionDenied):
                self.move(cohort, student=self.far_student)
