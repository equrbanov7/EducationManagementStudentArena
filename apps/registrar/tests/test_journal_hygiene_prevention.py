"""«Jurnal təmizliyi» — ÖNLƏMƏ (sahib 2026-10-10): yeni «ayrılmış» və «boş» sətir yaranmasın.

Kilidlənən qaydalar (hər biri açar söndürüləndə köhnə davranışa qayıdır — ``JOURNAL_HYGIENE_PREVENTION``):

* oxumayan tələbəyə (arxiv hesab, xaric / məzuniyyət / məzun, passiv qeyd) YENİ qeydiyyat yaranmır —
  ``enroll_student_in_subject``, ``enroll_mandatory_subjects``, ``enroll_group_students``,
  ``choose_group_elective``; mövcud sətir olduğu kimi qaytarılır (yenidən aktivləşdirilmir);
* qrup seçmə fənni dəyişəndə köhnə seçimin BOŞ sətirləri ``dropped`` olur (məlumatlı sətir qalır), qrup
  həmin fənnə qayıdanda bu qərarlar geri qaytarılır;
* açılış ləğv olunanda onun BOŞ sətirləri ``dropped`` olur, məlumatlı sətir toxunulmur;
* xaric / akademik məzuniyyət sinxronu gələcək (açıq jurnallı) semestri də dondurur, bərpa onu qaytarır.
"""

from __future__ import annotations

from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory, override_settings

from apps.registrar import enrollment_suspension
from apps.registrar import journal_hygiene as hygiene
from apps.registrar import semester_actions, services
from apps.registrar.models import (
    AcademicStatus,
    CourseOffering,
    CurriculumSubject,
    Enrollment,
    EnrollmentKind,
    JournalHygieneDecision,
    StudentAcademicRecord,
    Subject,
)
from core.rls import bypass_rls

from .journal_hygiene_fixture import REASON, HygieneBase


class EnrollGuardTest(HygieneBase):
    def _record(self, user):
        return StudentAcademicRecord.objects.select_related("organization", "group").get(student=user)

    def _enroll(self, user, **extra):
        with bypass_rls():
            return services.enroll_student_in_subject(
                record=self._record(user),
                subject=self.subject_b,
                period=self.current,
                kind=EnrollmentKind.MANDATORY,
                **extra,
            )

    def test_students_who_left_get_no_new_rows(self):
        with bypass_rls():
            users = [
                self.make_student("jh_g_exp", status=AcademicStatus.EXPELLED),
                self.make_student("jh_g_leave", status=AcademicStatus.ACADEMIC_LEAVE),
                self.make_student("jh_g_inactive", is_active=False),
                self.make_student("jh_g_archived", archived=True),
            ]
        for user in users:
            with self.subTest(user=user.username):
                self.assertEqual(self._enroll(user), (None, False))
                self.assertFalse(Enrollment.objects.filter(student=user).exists())
        with bypass_rls():
            active = self.make_student("jh_g_active")
        enrollment, created = self._enroll(active)
        self.assertTrue(created)
        self.assertEqual(enrollment.status, Enrollment.Status.ENROLLED)

    def test_existing_row_is_returned_and_not_reactivated(self):
        with bypass_rls():
            user = self.make_student("jh_g_hist", status=AcademicStatus.EXPELLED)
            row = self.enroll(user, self._offering(self.subject_b, self.current), status=Enrollment.Status.DROPPED)
        enrollment, created = self._enroll(user)
        self.assertEqual((enrollment.pk, created, enrollment.status), (row.pk, False, Enrollment.Status.DROPPED))

    def test_transfer_path_may_still_carry_rows(self):
        with bypass_rls():
            user = self.make_student("jh_g_carry", status=AcademicStatus.EXPELLED)
        enrollment, created = self._enroll(user, allow_inactive=True)
        self.assertTrue(created)

    def test_mandatory_subjects_and_group_enrollment_skip_archived(self):
        with bypass_rls():
            archived = self.make_student("jh_g_arch2", archived=True)
            active = self.make_student("jh_g_act2")
            self.assertEqual(
                services.enroll_mandatory_subjects(
                    record=self._record(archived), period=self.future, semester_number=1
                ),
                0,
            )
            self.assertEqual(
                services.enroll_mandatory_subjects(record=self._record(active), period=self.future, semester_number=1),
                2,
            )
            offering = self._offering(self.subject_c, self.current)
            report = services.enroll_group_students(offerings=[offering])
            enrolled = set(offering.enrollments.values_list("student__username", flat=True))
        self.assertEqual(enrolled, {"jh_g_act2"})
        self.assertEqual((report["created"], report["not_member"]), (1, 1))

    @override_settings(JOURNAL_HYGIENE_PREVENTION=False)
    def test_switch_off_restores_old_behaviour(self):
        with bypass_rls():
            user = self.make_student("jh_g_old", status=AcademicStatus.EXPELLED)
            archived = self.make_student("jh_g_old_arch", archived=True)
        self.assertTrue(self._enroll(user)[1])
        with bypass_rls():
            self.assertEqual(
                services.enroll_mandatory_subjects(
                    record=self._record(archived), period=self.future, semester_number=1
                ),
                2,
            )


class ElectiveRechoiceTest(HygieneBase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        with bypass_rls():
            cls.el_a = Subject.objects.create(organization=cls.org, code="JH-EA", name="Seçmə A")
            cls.el_b = Subject.objects.create(organization=cls.org, code="JH-EB", name="Seçmə B")
            for subject in (cls.el_a, cls.el_b):
                CurriculumSubject.objects.create(
                    organization=cls.org,
                    curriculum=cls.curriculum,
                    subject=subject,
                    semester_number=2,
                    is_elective=True,
                    elective_group="SB1",
                )
            cls.alice = cls.make_student("jh_el_alice")
            cls.bob = cls.make_student("jh_el_bob")

    def _choose(self, subject):
        with bypass_rls():
            return services.choose_group_elective(
                organization=self.org,
                group=self.group,
                curriculum=self.curriculum,
                period=self.current,
                elective_group="SB1",
                subject=subject,
                decided_by=self.owner,
            )

    def _row(self, user, subject):
        with bypass_rls():
            return Enrollment.objects.get(student=user, offering__subject=subject, offering__period=self.current)

    def test_rechoice_drops_previous_empty_rows_and_keeps_rows_with_data(self):
        self._choose(self.el_a)
        with bypass_rls():
            self.mark(self._row(self.alice, self.el_a))
        _, enrolled = self._choose(self.el_b)
        self.assertEqual(enrolled, 2)
        self.assertEqual(self._row(self.alice, self.el_a).status, Enrollment.Status.ENROLLED)  # balı var
        bob_old = self._row(self.bob, self.el_a)
        self.assertEqual(bob_old.status, Enrollment.Status.DROPPED)
        with bypass_rls():
            decision = JournalHygieneDecision.objects.get(enrollment=bob_old)
        self.assertEqual((decision.category, decision.reason_code), (hygiene.EMPTY, hygiene.SOURCE_REPLACED))
        self.assertEqual(decision.decided_by, self.owner)

    def test_switching_back_restores_the_dropped_rows(self):
        self._choose(self.el_a)
        self._choose(self.el_b)
        _, enrolled = self._choose(self.el_a)
        self.assertEqual(enrolled, 2)  # bərpa olunan sətirlər yenidən yazılmış sayılır
        for user in (self.alice, self.bob):
            self.assertEqual(self._row(user, self.el_a).status, Enrollment.Status.ENROLLED)
            self.assertEqual(self._row(user, self.el_b).status, Enrollment.Status.DROPPED)
        with bypass_rls():
            first = JournalHygieneDecision.objects.filter(enrollment__offering__subject=self.el_a)
            self.assertEqual(first.count(), 2)
            self.assertFalse(first.filter(reverted_at__isnull=True).exists())
            self.assertEqual(
                JournalHygieneDecision.objects.filter(
                    enrollment__offering__subject=self.el_b, reverted_at__isnull=True
                ).count(),
                2,
            )

    def test_archived_member_is_not_enrolled_by_the_group_choice(self):
        with bypass_rls():
            self.make_student("jh_el_archived", archived=True)
        _, enrolled = self._choose(self.el_a)
        self.assertEqual(enrolled, 2)
        with bypass_rls():
            self.assertFalse(Enrollment.objects.filter(student__username="jh_el_archived").exists())

    @override_settings(JOURNAL_HYGIENE_PREVENTION=False)
    def test_switch_off_keeps_previous_choice_rows(self):
        self._choose(self.el_a)
        self._choose(self.el_b)
        self.assertEqual(self._row(self.bob, self.el_a).status, Enrollment.Status.ENROLLED)
        self.assertFalse(JournalHygieneDecision.objects.exists())


class CancelOfferingTest(HygieneBase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        with bypass_rls():
            cls.cancel_target = cls._offering(cls.subject_b, cls.current)
            cls.with_data = cls.enroll(cls.make_student("jh_c_data"), cls.cancel_target)
            cls.without_data = cls.enroll(cls.make_student("jh_c_empty"), cls.cancel_target)
            cls.mark(cls.with_data)

    def _cancel(self, reason=REASON):
        request = RequestFactory().post(
            "/semestr/emel/", {"action": "cancel_offering", "id": str(self.cancel_target.pk), "reason": reason}
        )
        request.user = self.owner
        request.organization = self.org
        request.org_permissions = ["semester.view", "semester.open"]
        with bypass_rls():
            return semester_actions.semester_action(request)

    def test_cancel_drops_only_empty_rows_with_a_decision(self):
        response = self._cancel()
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'"dropped_empty": 1', response.content)
        self.assertFalse(CourseOffering.objects.get(pk=self.cancel_target.pk).is_active)
        self.assertEqual(self.status_of(self.with_data), Enrollment.Status.ENROLLED)
        self.assertEqual(self.status_of(self.without_data), Enrollment.Status.DROPPED)
        with bypass_rls():
            decision = JournalHygieneDecision.objects.get()
        self.assertEqual(decision.enrollment_id, self.without_data.pk)
        self.assertEqual(decision.reason_code, hygiene.SOURCE_CANCELLED)
        self.assertIn(REASON, decision.reason)

    def test_short_reason_cancels_nothing(self):
        response = self._cancel(reason="qısa")
        self.assertEqual(response.status_code, 400)
        self.assertTrue(CourseOffering.objects.get(pk=self.cancel_target.pk).is_active)
        self.assertEqual(self.status_of(self.without_data), Enrollment.Status.ENROLLED)

    def test_anonymous_request_is_refused(self):
        request = RequestFactory().post("/semestr/emel/", {"action": "cancel_offering"})
        request.user = AnonymousUser()
        self.assertEqual(semester_actions.semester_action(request).status_code, 302)

    @override_settings(JOURNAL_HYGIENE_PREVENTION=False)
    def test_switch_off_only_deactivates(self):
        response = self._cancel()
        self.assertIn(b'"dropped_empty": 0', response.content)
        self.assertEqual(self.status_of(self.without_data), Enrollment.Status.ENROLLED)


class SuspensionScopeTest(HygieneBase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        with bypass_rls():
            cls.student = cls.make_student("jh_s_student")
            cls.record = StudentAcademicRecord.objects.get(student=cls.student)
            cls.now_row = cls.enroll(cls.student)
            cls.next_row = cls.enroll(cls.student, cls._offering(cls.subject_b, cls.future))
            closed_offering = cls._offering(cls.subject_c, cls.future)
            cls.closed_row = cls.enroll(cls.student, closed_offering)
            cls.close_journal(closed_offering)
            cls.past_row = cls.enroll(
                cls.student, cls._offering(cls.subject, cls.past), status=Enrollment.Status.COMPLETED
            )

    def _sync(self, previous, to_status):
        with bypass_rls():
            return enrollment_suspension.sync_enrollments_for_status(
                record=self.record, previous=previous, to_status=to_status, actor=self.owner
            )

    def test_expulsion_suspends_current_and_future_open_journals_and_reinstatement_restores(self):
        result = self._sync(AcademicStatus.ENROLLED, AcademicStatus.EXPELLED)
        self.assertEqual(result["suspended"], 2)
        self.assertEqual(self.status_of(self.now_row), Enrollment.Status.SUSPENDED)
        self.assertEqual(self.status_of(self.next_row), Enrollment.Status.SUSPENDED)
        self.assertEqual(self.status_of(self.closed_row), Enrollment.Status.ENROLLED)  # bağlı jurnal toxunulmur
        self.assertEqual(self.status_of(self.past_row), Enrollment.Status.COMPLETED)
        restored = self._sync(AcademicStatus.EXPELLED, AcademicStatus.ENROLLED)
        self.assertEqual(restored["restored"], 2)
        self.assertEqual(self.status_of(self.next_row), Enrollment.Status.ENROLLED)

    @override_settings(JOURNAL_HYGIENE_PREVENTION=False)
    def test_switch_off_keeps_current_period_only(self):
        result = self._sync(AcademicStatus.ENROLLED, AcademicStatus.ACADEMIC_LEAVE)
        self.assertEqual(result["suspended"], 1)
        self.assertEqual(self.status_of(self.next_row), Enrollment.Status.ENROLLED)
