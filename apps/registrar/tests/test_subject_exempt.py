"""«Fəndən azad et» — tələbə qrupda qalır, yalnız BİR fənnin jurnalından çıxır (sahib 2026-10-15).

Yoxlanılır:

* azadlıq yalnız HƏMİN açılışın jurnalından / statistikasından çıxarır; qrup, akademik qeyd və digər fənn
  toxunulmur; qərar jurnalı («Jurnal təmizliyi», ``subject_exempt``) + audit yazılır;
* «Bərpa et» tələbəni qaytarır (bir dəfə);
* icazə: açarsız aktor → 403, əhatədən kənar → 404, RİM (org-wide ``journal.correct``) → hər jurnal;
* bağlı jurnalda əməl 409;
* tələbə kabineti fənni kartlardan çıxarır və «Azad edilib» kimi göstərir.
"""

import json

from django.contrib.auth import get_user_model
from django.test import Client, RequestFactory, TestCase, override_settings
from django.urls import reverse

from apps.audit.models import AuditLog
from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit
from apps.registrar import gradebook, services, subject_exempt
from apps.registrar.models import (
    AssessmentScheme,
    Curriculum,
    CurriculumSubject,
    Enrollment,
    HygieneCategory,
    JournalHygieneDecision,
    Program,
    StudentAcademicRecord,
    Subject,
)
from core.constants import AcademicPeriodType, OrganizationType, OrgUnitType
from core.rls import bypass_rls

User = get_user_model()


class _ExemptBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("se_owner", "se_owner@qku.edu.az", "pw")
        with bypass_rls():
            cls.org = Organization.objects.create(
                name="SE Univ",
                slug="se-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=cls.owner,
                status="active",
                is_active=True,
            )
            cls.faculty = OrgUnit.objects.create(
                organization=cls.org, name="Fakültə", slug="se-f", unit_type=OrgUnitType.FACULTY
            )
            cls.group = OrgUnit.objects.create(
                organization=cls.org, name="SE-1", slug="se-g1", unit_type=OrgUnitType.GROUP, parent=cls.faculty
            )
            cls.far_faculty = OrgUnit.objects.create(
                organization=cls.org, name="Uzaq", slug="se-ff", unit_type=OrgUnitType.FACULTY
            )
            cls.period = AcademicPeriod.objects.create(
                organization=cls.org,
                name="2025/2026 Payız",
                period_type=AcademicPeriodType.SEMESTER,
                academic_year="2025/2026",
                start_date="2025-09-01",
                end_date="2026-01-31",
                is_current=True,
            )
            cls.teacher = cls._member("se_teacher", "teacher")
            cls.coordinator = cls._member("se_coord", "program_coordinator", cls.faculty)
            cls.outsider = cls._member("se_out", "program_coordinator", cls.far_faculty)
            cls.rim = cls._member("se_rim", "ikt_rehber")
            cls.program = Program.objects.create(organization=cls.org, code="SEP", name="Fizika")
            cls.curriculum = Curriculum.objects.create(organization=cls.org, program=cls.program, admission_year=2025)
            cls.physics = Subject.objects.create(organization=cls.org, code="FIZ101", name="Fizika")
            cls.math = Subject.objects.create(organization=cls.org, code="RIY101", name="Riyaziyyat")
            for subject in (cls.physics, cls.math):
                CurriculumSubject.objects.create(
                    organization=cls.org, curriculum=cls.curriculum, subject=subject, semester_number=1
                )
            cls.student = cls._student("se_stu")
            cls.classmate = cls._student("se_mate")
            cls.enrollment = cls.student.enrollments.get(offering__subject=cls.physics)
            cls.offering = cls.enrollment.offering
            cls.offering.instructor = cls.teacher
            cls.offering.save(update_fields=["instructor"])
            cls.math_enrollment = cls.student.enrollments.get(offering__subject=cls.math)

    @classmethod
    def _member(cls, username, role, unit=None):
        user = User.objects.create_user(username, f"{username}@qku.edu.az", "pw")
        Membership.objects.create(
            user=user,
            organization=cls.org,
            role=cls.org.roles.get(name=role),
            scope_unit=unit,
            is_primary=True,
            is_active=True,
        )
        return user

    @classmethod
    def _student(cls, username):
        student = cls._member(username, "student")
        record = StudentAcademicRecord.objects.create(
            organization=cls.org,
            student=student,
            program=cls.program,
            curriculum=cls.curriculum,
            group=cls.group,
            admission_year=2025,
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

    def _post(self, user, name, payload):
        return self._client(user).post(
            reverse(name, args=[self.offering.id]), data=json.dumps(payload), content_type="application/json"
        )

    def _exempt(self, user=None, **extra):
        return self._post(
            user or self.coordinator,
            "registrar:journal_subject_exempt",
            {"enrollment": str(self.enrollment.pk), **extra},
        )

    @staticmethod
    def _status(enrollment):
        with bypass_rls():
            return Enrollment.objects.get(pk=enrollment.pk).status


class SubjectExemptFlowTest(_ExemptBase):
    def test_exempt_removes_only_this_journal(self):
        response = self._exempt(reason="", doc_number="12/a", doc_date="2025-10-01")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(response.json()["ok"])
        with bypass_rls():
            journal = gradebook.get_offering_journal(offering=self.offering)
            math_journal = gradebook.get_offering_journal(offering=self.math_enrollment.offering)
            record = StudentAcademicRecord.objects.get(organization=self.org, student=self.student)
            decision = JournalHygieneDecision.objects.get(enrollment=self.enrollment)
        ids = [row["student"].id for row in journal["rows"]]
        self.assertNotIn(self.student.id, ids)  # jurnal + onun hesablamaları
        self.assertIn(self.classmate.id, ids)
        self.assertIn(self.student.id, [row["student"].id for row in math_journal["rows"]])
        self.assertEqual(self._status(self.enrollment), Enrollment.Status.DROPPED)
        self.assertEqual(self._status(self.math_enrollment), Enrollment.Status.ENROLLED)
        self.assertEqual(record.group_id, self.group.id)  # qrupda qalır
        self.assertTrue(record.is_active)
        self.assertEqual(decision.category, HygieneCategory.SUBJECT_EXEMPT)
        self.assertEqual(decision.from_status, Enrollment.Status.ENROLLED)
        self.assertEqual(decision.evidence["document"], {"number": "12/a", "date": "2025-10-01"})
        self.assertIn("12/a 01.10.2025", decision.reason)
        self.assertEqual(decision.decided_by_id, self.coordinator.id)
        with bypass_rls():
            self.assertTrue(
                AuditLog.objects.filter(
                    resource_type="registrar.journal_hygiene", resource_id=str(decision.batch)
                ).exists()
            )

    def test_journal_page_lists_exempted_and_hides_row(self):
        self._exempt()
        page = self._client(self.coordinator).get(reverse("registrar:journal_detail", args=[self.offering.id]))
        self.assertEqual(page.status_code, 200)
        self.assertTrue(page.context["can_exempt"])
        listed = [item["student"].id for item in page.context["exempt_rows"]]
        self.assertEqual(listed, [self.student.id])
        self.assertContains(page, "data-jse-restore=")
        self.assertContains(page, "journal_subject_exempt.js")
        self.assertNotContains(page, f'data-jse-open="{self.enrollment.pk}"')
        self.assertContains(page, "data-jse-open=")  # sinif yoldaşının sətrində düymə var

    def test_restore_brings_student_back_once(self):
        self._exempt()
        with bypass_rls():
            decision = JournalHygieneDecision.objects.get(enrollment=self.enrollment)
        response = self._post(
            self.coordinator, "registrar:journal_subject_exempt_restore", {"decision": str(decision.pk)}
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(self._status(self.enrollment), Enrollment.Status.ENROLLED)
        with bypass_rls():
            decision.refresh_from_db()
            journal = gradebook.get_offering_journal(offering=self.offering)
        self.assertIsNotNone(decision.reverted_at)
        self.assertTrue(decision.revert_reason)
        self.assertIn(self.student.id, [row["student"].id for row in journal["rows"]])
        again = self._post(self.coordinator, "registrar:journal_subject_exempt_restore", {"decision": str(decision.pk)})
        self.assertEqual(again.status_code, 404)

    def test_exempt_twice_is_rejected(self):
        self._exempt()
        self.assertEqual(self._exempt().status_code, 409)

    def test_invalid_document_date(self):
        response = self._exempt(doc_date="31.31.2025")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self._status(self.enrollment), Enrollment.Status.ENROLLED)

    def test_closed_journal_is_frozen(self):
        with bypass_rls():
            scheme = gradebook.ensure_assessment_scheme(offering=self.offering)
            AssessmentScheme.objects.filter(pk=scheme.pk).update(is_published=True, approval_status="approved")
        self.assertEqual(self._exempt().status_code, 409)
        self.assertEqual(self._status(self.enrollment), Enrollment.Status.ENROLLED)


class SubjectExemptPermissionTest(_ExemptBase):
    def test_teacher_without_key_gets_403(self):
        response = self._exempt(self.teacher)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self._status(self.enrollment), Enrollment.Status.ENROLLED)
        page = self._client(self.teacher).get(reverse("registrar:journal_detail", args=[self.offering.id]))
        self.assertFalse(page.context["can_exempt"])
        self.assertNotContains(page, "data-jse-open=")

    def test_out_of_scope_roster_holder_gets_404(self):
        self.assertEqual(self._exempt(self.outsider).status_code, 404)
        self.assertEqual(self._status(self.enrollment), Enrollment.Status.ENROLLED)

    def test_rim_org_wide_correct_may_exempt_and_restore(self):
        self.assertEqual(self._exempt(self.rim).status_code, 200)
        with bypass_rls():
            decision = JournalHygieneDecision.objects.get(enrollment=self.enrollment)
        outsider = self._post(self.outsider, "registrar:journal_subject_exempt_restore", {"decision": str(decision.pk)})
        self.assertEqual(outsider.status_code, 404)
        restored = self._post(self.rim, "registrar:journal_subject_exempt_restore", {"decision": str(decision.pk)})
        self.assertEqual(restored.status_code, 200)

    def test_service_level_scope(self):
        with bypass_rls():
            self.assertTrue(subject_exempt.can_exempt(self.coordinator, self.offering))
            self.assertTrue(subject_exempt.can_exempt(self.rim, self.offering))
            self.assertFalse(subject_exempt.can_exempt(self.outsider, self.offering))
            self.assertFalse(subject_exempt.can_exempt(self.teacher, self.offering))
            self.assertFalse(subject_exempt.has_any_power(self.teacher, self.org))

    def test_get_is_not_allowed(self):
        client = self._client(self.coordinator)
        self.assertEqual(
            client.get(reverse("registrar:journal_subject_exempt", args=[self.offering.id])).status_code, 405
        )


class SubjectExemptCabinetTest(_ExemptBase):
    def _section(self):
        from apps.registrar.public import build_student_subjects_context

        request = RequestFactory().get("/")
        request.user = self.student
        with bypass_rls():
            return build_student_subjects_context(request, organization=self.org, semester_number=1)[
                "student_subjects_section"
            ]

    def test_cabinet_hides_card_and_shows_exempt_note(self):
        before = self._section()
        self.assertIn(self.physics.id, [row["subject"].id for row in before["subjects"]])
        self.assertEqual(before["exempt_subjects"], [])
        self._exempt()
        after = self._section()
        self.assertNotIn(self.physics.id, [row["subject"].id for row in after["subjects"]])
        self.assertIn(self.math.id, [row["subject"].id for row in after["subjects"]])
        self.assertEqual(after["exempt_subjects"], [{"code": "FIZ101", "name": "Fizika"}])
        with override_settings(UNIVERSITY_MODE=True):
            with bypass_rls():
                profile = self.student.profile
                profile.password_change_required = False
                profile.email_verified = True
                profile.save(update_fields=["password_change_required", "email_verified"])
            fragment = self._client(self.student).get(
                reverse("accounts:profile_section_fragment", kwargs={"section": "my-subjects"})
            )
        self.assertEqual(fragment.status_code, 200, fragment.content[:300])
        html = fragment.json()["html"]
        self.assertIn("data-msx-exempt", html)
        self.assertIn("Fizika", html)


class SubjectExemptScheduleTest(_ExemptBase):
    """Azad edilən fənn tələbənin ÖZ cədvəlindən və «növbəti dərs»indən düşür; qrup cədvəli toxunulmazdır (QA-1 F6)."""

    def _slots(self):
        import datetime

        from apps.registrar.models import ScheduleSlot

        with bypass_rls():
            for offering in (self.offering, self.math_enrollment.offering):
                ScheduleSlot.objects.create(
                    organization=self.org,
                    offering=offering,
                    weekday=1,
                    start_time=datetime.time(8, 30),
                    end_time=datetime.time(10, 0),
                )

    def _subjects(self, slots):
        return {slot.offering.subject_id for slot in slots}

    def test_student_schedule_and_group_schedule_drop_only_the_exempt_subject(self):
        from apps.registrar import schedule

        self._slots()
        with bypass_rls():
            before = schedule.get_student_schedule(self.org, self.student, self.group, self.period)
            dash_before = schedule.get_group_schedule(
                organization=self.org, group=self.group, period=self.period, exclude_exempt_for=self.student.id
            )
        self.assertEqual(self._subjects(before), {self.physics.id, self.math.id})
        self.assertEqual(self._subjects(dash_before), {self.physics.id, self.math.id})

        self._exempt()
        with bypass_rls():
            mine = schedule.get_student_schedule(self.org, self.student, self.group, self.period)
            dashboard = schedule.get_group_schedule(
                organization=self.org, group=self.group, period=self.period, exclude_exempt_for=self.student.id
            )
            classmate = schedule.get_student_schedule(self.org, self.classmate, self.group, self.period)
            group_view = schedule.get_group_schedule(organization=self.org, group=self.group, period=self.period)
        self.assertEqual(self._subjects(mine), {self.math.id})
        self.assertEqual(self._subjects(dashboard), {self.math.id})
        # Sinif yoldaşı və qrupun (müəllim/redaktor) cədvəli toxunulmazdır.
        self.assertEqual(self._subjects(classmate), {self.physics.id, self.math.id})
        self.assertEqual(self._subjects(group_view), {self.physics.id, self.math.id})

    def test_restore_brings_the_subject_back_into_the_schedule(self):
        from apps.registrar import schedule

        self._slots()
        self._exempt()
        with bypass_rls():
            decision = JournalHygieneDecision.objects.get(category=HygieneCategory.SUBJECT_EXEMPT.value)
        response = self._post(
            self.coordinator, "registrar:journal_subject_exempt_restore", {"decision": str(decision.pk)}
        )
        self.assertEqual(response.status_code, 200, response.content[:300])
        with bypass_rls():
            slots = schedule.get_student_schedule(self.org, self.student, self.group, self.period)
        self.assertEqual(self._subjects(slots), {self.physics.id, self.math.id})

    def test_empty_states_say_exempt_not_unregistered(self):
        """Yalnız bir fənni olan tələbə azad edilib: boş-hal «qeydiyyat yoxdur» deməməlidir."""
        from apps.registrar.public import build_student_subjects_context

        self._exempt()
        with bypass_rls():
            Enrollment.objects.filter(pk=self.math_enrollment.pk).update(status=Enrollment.Status.DROPPED)
        request = RequestFactory().get("/")
        request.user = self.student
        with bypass_rls():
            section = build_student_subjects_context(request, organization=self.org, semester_number=1)[
                "student_subjects_section"
            ]
        self.assertEqual(section["subjects"], [])
        self.assertEqual([item["code"] for item in section["exempt_subjects"]], ["FIZ101"])
