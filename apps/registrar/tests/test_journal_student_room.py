"""Tələbə jurnalının dərs-tarixçəsi otaq/bina göstərir (əvvəllər YOX idi).

``apps.registrar.public.build_student_journal_context`` — hər tarixçə sətri
üçün ``room_label`` (ad + bina, ``exams.ExamRoom.notes`` DAXİL EDİLMİR).
Otaq təyin edilməyibsə ``None`` (şablon "—" göstərir). Bax SCOUT §3: "Room/
building NOT shown to student" — bu boşluğu qapadır.
"""

from __future__ import annotations

import datetime

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.exams.models import ExamRoom
from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit
from apps.registrar import services
from apps.registrar.models import (
    AttendanceStatus,
    Curriculum,
    CurriculumSubject,
    Lesson,
    LessonKind,
    LessonMark,
    Program,
    StudentAcademicRecord,
    Subject,
)
from apps.registrar.public import build_student_journal_context
from core.constants import AcademicPeriodType, OrganizationType, OrgUnitType
from core.rls import bypass_rls

User = get_user_model()


class StudentJournalRoomLabelTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("jsr_owner", "jsr_owner@qku.edu.az", "pw")
        with bypass_rls():
            cls.org = Organization.objects.create(
                name="JSR Univ",
                slug="jsr-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=cls.owner,
                status="active",
                is_active=True,
            )
            cls.group = OrgUnit.objects.create(
                organization=cls.org, name="JSR-G1", slug="jsr-g1", unit_type=OrgUnitType.GROUP
            )
            cls.period = AcademicPeriod.objects.create(
                organization=cls.org,
                name="2024/2025 Payız",
                period_type=AcademicPeriodType.SEMESTER,
                academic_year="2024/2025",
                start_date="2024-09-01",
                end_date="2025-01-31",
                is_current=True,
            )
            cls.subject = Subject.objects.create(organization=cls.org, code="JSR101", name="Fənn")
            cls.program = Program.objects.create(organization=cls.org, code="JSR", name="Proqram")
            cls.curriculum = Curriculum.objects.create(organization=cls.org, program=cls.program, admission_year=2024)
            CurriculumSubject.objects.create(
                organization=cls.org, curriculum=cls.curriculum, subject=cls.subject, semester_number=1
            )
            cls.teacher = User.objects.create_user("jsr_teacher", "jsr_teacher@qku.edu.az", "pw")
            Membership.objects.create(
                user=cls.teacher,
                organization=cls.org,
                role=cls.org.roles.get(name="teacher"),
                is_primary=True,
                is_active=True,
            )
            cls.student = User.objects.create_user("jsr_student", "jsr_student@qku.edu.az", "pw")
            Membership.objects.create(
                user=cls.student,
                organization=cls.org,
                role=cls.org.roles.get(name="student"),
                is_primary=True,
                is_active=True,
            )
            cls.record = StudentAcademicRecord.objects.create(
                organization=cls.org,
                student=cls.student,
                program=cls.program,
                curriculum=cls.curriculum,
                group=cls.group,
                admission_year=2024,
            )
            services.enroll_mandatory_subjects(record=cls.record, period=cls.period, semester_number=1)
            cls.enrollment = cls.student.enrollments.get()
            cls.offering = cls.enrollment.offering
            cls.offering.instructor = cls.teacher
            cls.offering.save(update_fields=["instructor"])

            cls.room = ExamRoom.objects.create(
                organization=cls.org, name="204", code="A204", building="I korpus", capacity=30
            )

            yesterday = datetime.date(2024, 10, 2)
            day_before = datetime.date(2024, 10, 1)
            cls.lesson_with_room = Lesson.objects.create(
                organization=cls.org,
                offering=cls.offering,
                date=day_before,
                kind=LessonKind.SEMINAR,
                hours=2,
                room=cls.room,
            )
            cls.lesson_without_room = Lesson.objects.create(
                organization=cls.org,
                offering=cls.offering,
                date=yesterday,
                kind=LessonKind.SEMINAR,
                hours=2,
            )
            LessonMark.objects.create(
                organization=cls.org,
                lesson=cls.lesson_with_room,
                enrollment=cls.enrollment,
                status=AttendanceStatus.PRESENT,
                score=8,
            )
            LessonMark.objects.create(
                organization=cls.org,
                lesson=cls.lesson_without_room,
                enrollment=cls.enrollment,
                status=AttendanceStatus.PRESENT,
                score=9,
            )

    def _client(self, user):
        client = Client()
        client.force_login(user)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        return client

    def _history(self):
        url = f"{reverse('accounts:profile')}?section=my-journal&subject={self.enrollment.id}"
        request = self._client(self.student).get(url).wsgi_request
        section = build_student_journal_context(request, organization=self.org)["journal_student_section"]
        return {row["mark"].lesson_id: row for row in section["detail"]["history"]}

    def test_lesson_with_room_exposes_name_and_building(self):
        history = self._history()
        row = history[self.lesson_with_room.id]
        self.assertEqual(row["room_label"], "204 (I korpus)")

    def test_lesson_without_room_is_none_in_context(self):
        history = self._history()
        row = history[self.lesson_without_room.id]
        self.assertIsNone(row["room_label"])

    def test_room_notes_are_never_exposed(self):
        """Müəllimin daxili qeydləri (`ExamRoom.notes`) tələbəyə SIZMIR."""
        with bypass_rls():
            self.room.notes = "Konfidensial: proyektor xarabdır"
            self.room.save(update_fields=["notes"])
        history = self._history()
        row = history[self.lesson_with_room.id]
        self.assertNotIn("Konfidensial", row["room_label"])

    def test_page_renders_room_column_and_dash_fallback(self):
        """Partial-ın özünü render edir (SPA qabıq/bölmə seçimi plumbing-indən
        asılı olmadan) — dəqiq bu deliverable-ı yoxlayır: otaq varsa ad+bina,
        yoxdursa cədvəldə "—"."""
        from django.template.loader import render_to_string

        url = f"{reverse('accounts:profile')}?section=my-journal&subject={self.enrollment.id}"
        request = self._client(self.student).get(url).wsgi_request
        section = build_student_journal_context(request, organization=self.org)["journal_student_section"]
        html = render_to_string(
            "registrar/partials/_journal_student_content.html",
            {"journal_student_section": section},
            request=request,
        )
        self.assertIn("204 (I korpus)", html)
        self.assertIn('data-room="—"', html)
