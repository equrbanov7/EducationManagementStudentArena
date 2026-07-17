"""«İmtahan şansı ver» (ikinci şans) + midterm/final yaratma məhdudiyyəti testləri.

* Yaratma: müəllim final/midterm yarada bilməz (forma + seçimlər); mərkəz bilər.
* grant_second_chance: grant + yeni PIN + final biletinin sıfırlanması + audit.
* exam-chance view: icazə, qrupa şans, mesajlar.
* Tələbə siyahısı: limit bitəndən sonra grant imtahanı geri qaytarır.
"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import ProfileRole
from apps.exams.domain.final_center import TICKET_STATUS_ASSIGNED, TICKET_STATUS_COMPLETED, FinalExamTicket
from apps.exams.forms.exam import ExamForm
from apps.exams.models import Exam, ExamStudentPin, StudentExamAttemptGrant, StudentGroup
from apps.exams.services.second_chance import SecondChanceError, grant_second_chance
from apps.exams.services.student_pins import provision_exam_student_pins, revoke_student_pin, student_visible_pin
from apps.exams.tests.test_exam_center_policy import PASSWORD, _assign_user_to_org
from apps.organizations.models import Organization
from core.constants import OrganizationType

User = get_user_model()


class _Base(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("sc_owner", "sc_owner@test.az", PASSWORD)
        cls.org = Organization.objects.create(
            name="SC University",
            org_type=OrganizationType.UNIVERSITY,
            owner=cls.owner,
            status="active",
            is_active=True,
        )
        cls.teacher = User.objects.create_user("sc_teacher", "sc_teacher@test.az", PASSWORD)
        _assign_user_to_org(cls.teacher, cls.org, ProfileRole.TEACHER, "teacher")
        cls.center = User.objects.create_user("sc_center", "sc_center@test.az", PASSWORD)
        _assign_user_to_org(cls.center, cls.org, ProfileRole.MEMBER, "exam_center")
        cls.student = User.objects.create_user("sc_student", "sc_student@test.az", PASSWORD)
        _assign_user_to_org(cls.student, cls.org, ProfileRole.STUDENT, "student")

    def _make_exam(self, category="final", **overrides):
        now = timezone.now()
        defaults = {
            "title": f"SC {category} imtahanı",
            "author": self.center,
            "organization": self.org,
            "exam_type": "test",
            "exam_type_extended": category,
            "is_active": True,
            "is_public": False,
            "max_attempts_per_user": 1,
            "total_duration_minutes": 60,
            "start_datetime": now - timedelta(hours=1),
            "end_datetime": now + timedelta(hours=3),
        }
        defaults.update(overrides)
        exam = Exam.objects.create(**defaults)
        exam.allowed_users.add(self.student)
        return exam

    def _client_for(self, user):
        client = Client()
        client.force_login(user)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        return client


class SecureCategoryCreationTests(_Base):
    def setUp(self):
        # Rol propertiləri yalnız aktiv org konteksti altında resolve olunur.
        self.teacher.set_active_organization_context(self.org)
        self.center.set_active_organization_context(self.org)

    def _form(self, user, category):
        return ExamForm(
            data={"title": "Kateqoriya testi", "exam_type": "test", "exam_type_extended": category},
            user=user,
            organization=self.org,
        )

    def test_teacher_cannot_pick_midterm_or_final(self):
        form = ExamForm(user=self.teacher, organization=self.org)
        offered = {value for value, _ in form.fields["exam_type_extended"].choices}
        self.assertNotIn("final", offered)
        self.assertNotIn("midterm", offered)
        self.assertIn("quiz", offered)

    def test_center_sees_midterm_and_final(self):
        form = ExamForm(user=self.center, organization=self.org)
        offered = {value for value, _ in form.fields["exam_type_extended"].choices}
        self.assertIn("final", offered)
        self.assertIn("midterm", offered)

    def test_teacher_midterm_rejected_in_clean(self):
        form = self._form(self.teacher, "midterm")
        form.is_valid()
        self.assertIn("exam_type_extended", form.errors)

    def test_center_midterm_accepted_in_clean(self):
        form = self._form(self.center, "midterm")
        form.is_valid()
        self.assertNotIn("exam_type_extended", form.errors)


class GrantSecondChanceServiceTests(_Base):
    def test_grant_increases_attempts_and_reissues_pin(self):
        exam = self._make_exam("midterm")
        provision_exam_student_pins(exam)
        old_pin = student_visible_pin(exam, self.student)
        # İmtahan başlayanda PIN birdəfəlik ləğv olunur.
        revoke_student_pin(exam, self.student)
        self.assertIsNone(student_visible_pin(exam, self.student))

        summary = grant_second_chance(exam=exam, students=[self.student], extra=1, granted_by=self.center)

        self.assertEqual(summary["students"], 1)
        self.assertEqual(summary["pins_reissued"], 1)
        self.assertEqual(exam.attempts_left_for(self.student), 2)  # 1 limit + 1 grant, 0 istifadə
        new_pin = student_visible_pin(exam, self.student)
        self.assertIsNotNone(new_pin)
        self.assertNotEqual(new_pin, old_pin)
        pin_row = ExamStudentPin.objects.get(exam=exam, student=self.student)
        self.assertIsNone(pin_row.revoked_at)

    def test_grant_resets_completed_final_ticket(self):
        exam = self._make_exam("final")
        ticket = FinalExamTicket.objects.create(
            organization=self.org,
            exam=exam,
            student=self.student,
            status=TICKET_STATUS_COMPLETED,
            completed_at=timezone.now(),
            reconnect_count=3,
        )
        summary = grant_second_chance(exam=exam, students=[self.student], granted_by=self.center)
        self.assertEqual(summary["tickets_reset"], 1)
        ticket.refresh_from_db()
        self.assertEqual(ticket.status, TICKET_STATUS_ASSIGNED)
        self.assertIsNone(ticket.completed_at)
        self.assertIsNone(ticket.session)
        self.assertEqual(ticket.reconnect_count, 0)

    def test_grant_writes_audit_log(self):
        from apps.audit.models import AuditLog

        exam = self._make_exam("final")
        grant_second_chance(exam=exam, students=[self.student], extra=2, granted_by=self.center)
        entry = AuditLog.objects.filter(reason="exam_second_chance_granted").order_by("-id").first()
        self.assertIsNotNone(entry)
        self.assertEqual(entry.new_values.get("student_count"), 1)
        self.assertEqual(entry.new_values.get("extra_attempts"), 2)

    def test_grant_requires_students(self):
        exam = self._make_exam("final")
        with self.assertRaises(SecondChanceError):
            grant_second_chance(exam=exam, students=[], granted_by=self.center)

    def test_repeat_grant_accumulates(self):
        exam = self._make_exam("midterm")
        grant_second_chance(exam=exam, students=[self.student], extra=1, granted_by=self.center)
        grant_second_chance(exam=exam, students=[self.student], extra=1, granted_by=self.center)
        grant = StudentExamAttemptGrant.objects.get(exam=exam, student=self.student)
        self.assertEqual(grant.extra_attempts, 2)


class ExamChanceViewTests(_Base):
    def test_requires_exam_center(self):
        exam = self._make_exam("final")
        response = self._client_for(self.teacher).post(
            reverse("accounts:exam_chance"),
            {"exam_id": str(exam.pk), "usernames": self.student.username},
        )
        self.assertEqual(response.status_code, 403)

    def test_grants_to_group_and_usernames(self):
        exam = self._make_exam("final")
        group = StudentGroup.objects.create(teacher=self.teacher, organization=self.org, name="SC-901")
        group.students.add(self.student)
        other = User.objects.create_user("sc_student2", "sc_student2@test.az", PASSWORD)
        _assign_user_to_org(other, self.org, ProfileRole.STUDENT, "student")

        response = self._client_for(self.center).post(
            reverse("accounts:exam_chance"),
            {
                "exam_id": str(exam.pk),
                "group_id": str(group.pk),
                "usernames": f"{other.username}\nmovcud-deyil",
                "extra_attempts": "1",
            },
        )
        self.assertEqual(response.status_code, 302)
        granted = set(StudentExamAttemptGrant.objects.filter(exam=exam).values_list("student__username", flat=True))
        self.assertEqual(granted, {self.student.username, other.username})

    def test_section_renders_for_center(self):
        self._make_exam("final", title="Görünən final")
        response = self._client_for(self.center).get(f"{reverse('accounts:profile')}?section=exam-chance")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Görünən final")
        self.assertContains(response, 'name="exam_id"')

    def test_rejects_non_secure_exam(self):
        exam = self._make_exam("quiz")
        response = self._client_for(self.center).post(
            reverse("accounts:exam_chance"),
            {"exam_id": str(exam.pk), "usernames": self.student.username},
        )
        self.assertEqual(response.status_code, 404)


class StudentListGrantAwareTests(_Base):
    def test_exhausted_exam_reappears_after_grant(self):
        from apps.exams.constants import ATTEMPT_FINISHED_STATUSES
        from apps.exams.models import ExamAttempt

        exam = self._make_exam("midterm", title="Limitli imtahan")
        ExamAttempt.objects.create(
            user=self.student, exam=exam, status=ATTEMPT_FINISHED_STATUSES[0], finished_at=timezone.now()
        )

        client = self._client_for(self.student)
        # Tələbə imtahan siyahısı — limit bitib → SQL filtri imtahanı gizlədir.
        response = client.get(reverse("exams:assigned_exam_list"))
        self.assertNotContains(response, "Limitli imtahan", status_code=200)

        grant_second_chance(exam=exam, students=[self.student], granted_by=self.center)
        # Grant limiti artırır → imtahan həm siyahıda, həm tapşırıqlarda geri gəlir.
        response = client.get(reverse("exams:assigned_exam_list"))
        self.assertContains(response, "Limitli imtahan")


class ExamDetailControlsVisibilityTests(_Base):
    """Final/midterm detalında canlı-sessiya və aktiv/deaktiv düymələri gizlidir."""

    def _detail(self, exam):
        return self._client_for(self.center).get(reverse("exams:teacher_exam_detail", kwargs={"slug": exam.slug}))

    def test_final_hides_live_start_but_keeps_active_toggle(self):
        exam = self._make_exam("final")
        response = self._detail(exam)
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "live-start-section")
        # Aktivləşdir/Deaktiv et BÜTÜN kateqoriyalarda qalır (istifadəçi tələbi).
        self.assertContains(response, f"/{exam.slug}/toggle-active/")

    def test_midterm_hides_live_start_but_keeps_active_toggle(self):
        exam = self._make_exam("midterm")
        response = self._detail(exam)
        self.assertNotContains(response, "live-start-section", status_code=200)
        self.assertContains(response, f"/{exam.slug}/toggle-active/")

    def test_quiz_keeps_live_start_and_active_toggle(self):
        exam = self._make_exam("quiz")
        response = self._detail(exam)
        self.assertContains(response, f"/{exam.slug}/toggle-active/", status_code=200)
        self.assertContains(response, "live-start-section")


class ExamChanceFilterTests(_Base):
    """exam-chance filtr paneli: il/semestr, fakültə→kafedra, imtahan/tələbə axtarışı."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        from apps.organizations.models import AcademicPeriod, OrgUnit
        from core.constants import AcademicPeriodType, OrgUnitType

        cls.faculty = OrgUnit.objects.create(
            organization=cls.org, unit_type=OrgUnitType.FACULTY, name="Mühəndislik fakültəsi"
        )
        cls.kafedra = OrgUnit.objects.create(
            organization=cls.org, unit_type=OrgUnitType.CHAIR, name="İnformatika kafedrası", parent=cls.faculty
        )
        cls.other_faculty = OrgUnit.objects.create(
            organization=cls.org, unit_type=OrgUnitType.FACULTY, name="İqtisadiyyat fakültəsi"
        )
        cls.other_kafedra = OrgUnit.objects.create(
            organization=cls.org, unit_type=OrgUnitType.CHAIR, name="Maliyyə kafedrası", parent=cls.other_faculty
        )
        cls.group = StudentGroup.objects.create(
            teacher=cls.teacher, organization=cls.org, name="INF-840i", org_unit=cls.kafedra
        )
        cls.group.students.add(cls.student)
        cls.period = AcademicPeriod.objects.create(
            organization=cls.org,
            name="Payız semestri",
            period_type=AcademicPeriodType.SEMESTER,
            academic_year="2026-2027",
            start_date=timezone.now().date() - timedelta(days=10),
            end_date=timezone.now().date() + timedelta(days=100),
            is_active=True,
        )

    def _section(self, query=""):
        return self._client_for(self.center).get(f"{reverse('accounts:profile')}?section=exam-chance{query}")

    def test_faculty_filter_narrows_exams_and_kafedra_options(self):
        inside = self._make_exam("final", title="Fakültə daxili final")
        inside.allowed_groups.add(self.group)
        self._make_exam("final", title="Fakültəsiz final")

        response = self._section(f"&chance_faculty={self.faculty.pk}")
        self.assertContains(response, "Fakültə daxili final")
        self.assertNotContains(response, "Fakültəsiz final")
        # Kafedra seçimləri yalnız seçilmiş fakültənin uşaqlarıdır.
        self.assertContains(response, "İnformatika kafedrası")
        self.assertNotContains(response, "Maliyyə kafedrası")

    def test_year_filter_narrows_exams(self):
        self._make_exam("final", title="Bu semestr finalı")
        self._make_exam(
            "final",
            title="Köhnə final",
            start_datetime=timezone.now() - timedelta(days=400),
            end_datetime=timezone.now() - timedelta(days=399),
        )
        response = self._section("&chance_year=2026-2027")
        self.assertContains(response, "Bu semestr finalı")
        self.assertNotContains(response, "Köhnə final")

    def test_exam_title_search(self):
        self._make_exam("final", title="Riyaziyyat finalı")
        self._make_exam("final", title="Fizika finalı")
        response = self._section("&chance_exam_q=Riyaziyyat")
        self.assertContains(response, "Riyaziyyat finalı")
        self.assertNotContains(response, "Fizika finalı")

    def test_student_search_by_group_username_and_name(self):
        self._make_exam("final")
        self.student.first_name = "Aygün"
        self.student.last_name = "Məmmədova"
        self.student.save(update_fields=["first_name", "last_name"])

        # Qrup adı ilə
        response = self._section("&chance_student_q=INF-840")
        self.assertContains(response, 'name="student_ids"')
        self.assertContains(response, self.student.username)
        # Ad-soyad ilə
        response = self._section("&chance_student_q=Məmmədova")
        self.assertContains(response, self.student.username)
        # İstifadəçi adı ilə
        response = self._section(f"&chance_student_q={self.student.username[:8]}")
        self.assertContains(response, self.student.username)

    def test_grant_via_student_ids(self):
        exam = self._make_exam("final", title="Checkbox finalı")
        response = self._client_for(self.center).post(
            reverse("accounts:exam_chance"),
            {"exam_id": str(exam.pk), "student_ids": [str(self.student.pk)], "extra_attempts": "1"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(StudentExamAttemptGrant.objects.filter(exam=exam, student=self.student).exists())
