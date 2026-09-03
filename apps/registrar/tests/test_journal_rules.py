"""Jurnal sərt qaydaları: 2 saat pəncərələri, bu-gün qaydası, tavanlar,
kollokvium/sərbəst iş/kurs işi servisləri (yenidən-dizayn dalğası)."""

import datetime
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit
from apps.registrar import gradebook, journal_extras, services
from apps.registrar.models import (
    AttendanceStatus,
    ComponentKind,
    ComponentScore,
    CourseWork,
    Curriculum,
    CurriculumSubject,
    Lesson,
    LessonKind,
    LessonMark,
    Program,
    SelfWorkMark,
    SelfWorkTopic,
    StudentAcademicRecord,
    Subject,
)
from core.constants import AcademicPeriodType, OrganizationType, OrgUnitType
from core.rls import bypass_rls

User = get_user_model()

TODAY = timezone.localdate


def _setup_offering(cls, prefix):
    """Minimal universitet konteksti: 1 fənn, 1 qrup tələbəsi, 1 müəllim."""
    cls.owner = User.objects.create_user(f"{prefix}_owner", f"{prefix}_owner@qku.edu.az", "pw")
    cls.org = Organization.objects.create(
        name=f"{prefix} Univ",
        slug=f"{prefix}-univ",
        org_type=OrganizationType.UNIVERSITY,
        owner=cls.owner,
        status="active",
        is_active=True,
    )
    specialty = OrgUnit.objects.create(
        organization=cls.org, name="CS", slug=f"{prefix}-cs", unit_type=OrgUnitType.SPECIALTY
    )
    cls.group = OrgUnit.objects.create(
        organization=cls.org, name="JR-101", slug=f"{prefix}-jr101", unit_type=OrgUnitType.GROUP, parent=specialty
    )
    cls.period = AcademicPeriod.objects.create(
        organization=cls.org,
        name="Payız",
        period_type=AcademicPeriodType.SEMESTER,
        academic_year="2026/2027",
        start_date=datetime.date(2026, 6, 1),
        end_date=datetime.date(2026, 12, 31),
        is_current=True,
    )
    cls.program = Program.objects.create(organization=cls.org, code="JR", name="JR Proqram")
    cls.curriculum = Curriculum.objects.create(organization=cls.org, program=cls.program, admission_year=2026)
    cls.subject = Subject.objects.create(organization=cls.org, code="JR101", name="Jurnal qaydaları")
    CurriculumSubject.objects.create(
        organization=cls.org, curriculum=cls.curriculum, subject=cls.subject, semester_number=1
    )
    cls.teacher = User.objects.create_user(f"{prefix}_teacher", f"{prefix}_teacher@qku.edu.az", "pw")
    cls.student = User.objects.create_user(f"{prefix}_student", f"{prefix}_student@qku.edu.az", "pw")
    Membership.objects.create(
        user=cls.teacher,
        organization=cls.org,
        role=cls.org.roles.get(name="teacher"),
        is_primary=True,
        is_active=True,
    )
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
        admission_year=2026,
    )
    services.enroll_mandatory_subjects(record=cls.record, period=cls.period, semester_number=1)
    cls.enrollment = cls.student.enrollments.get()
    cls.offering = cls.enrollment.offering
    cls.offering.instructor = cls.teacher
    cls.offering.lesson_hours = 60
    cls.offering.save(update_fields=["instructor", "lesson_hours"])


class LessonWindowRulesTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        with bypass_rls():
            _setup_offering(cls, "jrl")

    def test_create_lesson_past_date_rejected(self):
        with bypass_rls():
            with self.assertRaises(gradebook.LessonRuleError):
                gradebook.create_lesson(
                    offering=self.offering, date=TODAY() - datetime.timedelta(days=1), created_by=self.teacher
                )

    def test_create_lesson_today_and_future_ok(self):
        with bypass_rls():
            gradebook.create_lesson(offering=self.offering, date=TODAY(), created_by=self.teacher)
            gradebook.create_lesson(
                offering=self.offering, date=TODAY() + datetime.timedelta(days=7), created_by=self.teacher
            )
            self.assertEqual(Lesson.objects.filter(offering=self.offering).count(), 2)

    def test_delete_lesson_only_within_window(self):
        with bypass_rls():
            lesson = gradebook.create_lesson(offering=self.offering, date=TODAY(), created_by=self.teacher)
            gradebook.save_marks(
                offering=self.offering,
                entries=[{"lesson_id": lesson.id, "enrollment_id": self.enrollment.id, "status": "absent"}],
                by_user=self.teacher,
            )
            # Pəncərə içində silinir — markları ilə birgə, qayıb saatı yenilənir.
            self.assertTrue(gradebook.delete_lesson(lesson=lesson, by_user=self.teacher))
            self.assertFalse(LessonMark.objects.filter(enrollment=self.enrollment).exists())
            self.enrollment.refresh_from_db()
            self.assertEqual(self.enrollment.absence_hours, 0)

            frozen = gradebook.create_lesson(offering=self.offering, date=TODAY(), created_by=self.teacher)
            Lesson.objects.filter(pk=frozen.pk).update(created_at=timezone.now() - datetime.timedelta(hours=3))
            frozen.refresh_from_db()
            self.assertFalse(gradebook.delete_lesson(lesson=frozen, by_user=self.teacher))
            self.assertTrue(Lesson.objects.filter(pk=frozen.pk).exists())


class MarkRulesTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        with bypass_rls():
            _setup_offering(cls, "jrm")

    def _mark(self, lesson, **extra):
        entry = {"lesson_id": lesson.id, "enrollment_id": self.enrollment.id, "status": "present"}
        entry.update(extra)
        return gradebook.save_marks(offering=self.offering, entries=[entry], by_user=self.teacher)

    def test_new_mark_only_on_lesson_day(self):
        with bypass_rls():
            future = gradebook.create_lesson(
                offering=self.offering, date=TODAY() + datetime.timedelta(days=3), created_by=self.teacher
            )
            self.assertEqual(self._mark(future), 0)  # sabahkı dərsə bu gün yazmaq olmaz
            today_lesson = gradebook.create_lesson(offering=self.offering, date=TODAY(), created_by=self.teacher)
            self.assertEqual(self._mark(today_lesson), 1)

    def test_mark_frozen_after_two_hours(self):
        with bypass_rls():
            lesson = gradebook.create_lesson(offering=self.offering, date=TODAY(), created_by=self.teacher)
            self._mark(lesson, status="absent")
            mark = LessonMark.objects.get(lesson=lesson, enrollment=self.enrollment)
            LessonMark.objects.filter(pk=mark.pk).update(created_at=timezone.now() - datetime.timedelta(hours=3))
            written = self._mark(lesson, status="present")
            self.assertEqual(written, 0)
            mark.refresh_from_db()
            self.assertEqual(mark.status, AttendanceStatus.ABSENT)  # dondu

    def test_seminar_score_clamped_to_ten(self):
        with bypass_rls():
            lesson = gradebook.create_lesson(
                offering=self.offering, date=TODAY(), kind=LessonKind.SEMINAR, created_by=self.teacher
            )
            self._mark(lesson, score="37")
            mark = LessonMark.objects.get(lesson=lesson, enrollment=self.enrollment)
            self.assertEqual(mark.score, Decimal("10"))


class KollokviumTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        with bypass_rls():
            _setup_offering(cls, "jrk")

    def test_ensure_three_kollokviums_idempotent(self):
        with bypass_rls():
            first = journal_extras.ensure_kollokviums(self.offering)
            second = journal_extras.ensure_kollokviums(self.offering)
            self.assertEqual([c.name for c in first], ["Kollokvium 1", "Kollokvium 2", "Kollokvium 3"])
            self.assertEqual([c.id for c in first], [c.id for c in second])
            self.assertTrue(all(c.kind == ComponentKind.KOLLOKVIUM for c in first))

    def test_kollokvium_score_and_date_flow(self):
        with bypass_rls():
            k1 = journal_extras.ensure_kollokviums(self.offering)[0]
            self.assertTrue(journal_extras.set_kollokvium_date(component=k1, held_on=TODAY()))
            # Kollokvium yalnız İmtahan Mərkəzi pəncərəsi vasitəsilə yazılır
            # (bypass_edit_window=True); generic save_component_scores onu skip edir.
            gradebook.save_component_scores(
                offering=self.offering,
                entries=[{"component_id": k1.id, "enrollment_id": self.enrollment.id, "score": "25"}],
                by_user=self.teacher,
                bypass_edit_window=True,
            )
            cs = ComponentScore.objects.get(component=k1, enrollment=self.enrollment)
            self.assertEqual(cs.score, Decimal("10"))  # max_score=10 clamp
            # Kollokvium 2 saat kilidinə TABE DEYİL — pəncərə açıq olduqca (bypass)
            # bal dəyişdirilə bilər (window-gating 2h kilidini əvəz edir).
            ComponentScore.objects.filter(pk=cs.pk).update(created_at=timezone.now() - datetime.timedelta(hours=3))
            gradebook.save_component_scores(
                offering=self.offering,
                entries=[{"component_id": k1.id, "enrollment_id": self.enrollment.id, "score": "1"}],
                by_user=self.teacher,
                bypass_edit_window=True,
            )
            cs.refresh_from_db()
            self.assertEqual(cs.score, Decimal("1"))


class SelfWorkTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        with bypass_rls():
            _setup_offering(cls, "jrs")

    def test_topic_cap_and_entry_score(self):
        with bypass_rls():
            for i in range(journal_extras.SELF_WORK_MAX_TOPICS):
                self.assertIsNotNone(journal_extras.add_selfwork_topic(offering=self.offering, title=f"Mövzu {i+1}"))
            self.assertIsNone(journal_extras.add_selfwork_topic(offering=self.offering, title="11-ci"))
            topics = list(SelfWorkTopic.objects.filter(offering=self.offering))
            for t in topics[:4]:
                journal_extras.set_selfwork_mark(
                    offering=self.offering, topic_id=t.id, enrollment_id=self.enrollment.id, done=True
                )
            self.assertEqual(gradebook.entry_score_for(self.enrollment, 50), Decimal("4"))

    def test_revoke_blocked_after_window(self):
        with bypass_rls():
            topic = journal_extras.add_selfwork_topic(offering=self.offering, title="T1")
            journal_extras.set_selfwork_mark(
                offering=self.offering, topic_id=topic.id, enrollment_id=self.enrollment.id, done=True
            )
            mark = SelfWorkMark.objects.get(topic=topic, enrollment=self.enrollment)
            SelfWorkMark.objects.filter(pk=mark.pk).update(updated_at=timezone.now() - datetime.timedelta(hours=3))
            ok = journal_extras.set_selfwork_mark(
                offering=self.offering, topic_id=topic.id, enrollment_id=self.enrollment.id, done=False
            )
            self.assertFalse(ok)
            mark.refresh_from_db()
            self.assertTrue(mark.done)

    def test_revoke_allowed_with_override_after_window(self):
        # İKT/superuser (allow_locked=True) 2 saat pəncərəsindən sonra da geri ala bilər.
        with bypass_rls():
            topic = journal_extras.add_selfwork_topic(offering=self.offering, title="T1")
            journal_extras.set_selfwork_mark(
                offering=self.offering, topic_id=topic.id, enrollment_id=self.enrollment.id, done=True
            )
            mark = SelfWorkMark.objects.get(topic=topic, enrollment=self.enrollment)
            SelfWorkMark.objects.filter(pk=mark.pk).update(updated_at=timezone.now() - datetime.timedelta(hours=3))
            ok = journal_extras.set_selfwork_mark(
                offering=self.offering,
                topic_id=topic.id,
                enrollment_id=self.enrollment.id,
                done=False,
                allow_locked=True,
            )
            self.assertTrue(ok)
            mark.refresh_from_db()
            self.assertFalse(mark.done)

    def test_topic_delete_cascades_marks(self):
        # Yeni davranış (istifadəçi tələbi): mövzu işarələnmiş olsa belə silinir və
        # bu mövzu üzrə SelfWorkMark-lar da (bal) FK cascade ilə birlikdə silinir.
        # UI silmədən əvvəl xəbərdarlıq modalı göstərir.
        with bypass_rls():
            topic = journal_extras.add_selfwork_topic(offering=self.offering, title="T1")
            journal_extras.set_selfwork_mark(
                offering=self.offering, topic_id=topic.id, enrollment_id=self.enrollment.id, done=True
            )
            self.assertTrue(SelfWorkMark.objects.filter(topic=topic).exists())
            self.assertTrue(journal_extras.delete_selfwork_topic(topic=topic))
            self.assertFalse(SelfWorkTopic.objects.filter(pk=topic.pk).exists())
            self.assertFalse(SelfWorkMark.objects.filter(topic_id=topic.pk).exists())


class CourseWorkTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        with bypass_rls():
            _setup_offering(cls, "jrc")

    def test_save_clamp_and_freeze(self):
        with bypass_rls():
            ok = journal_extras.save_course_work(
                enrollment=self.enrollment,
                topic="Verilənlər bazasının optimallaşdırılması",
                score="140",
                submitted_on=TODAY(),
                by_user=self.teacher,
            )
            self.assertTrue(ok)
            work = CourseWork.objects.get(enrollment=self.enrollment)
            self.assertEqual(work.score, Decimal("100"))  # 0-100 clamp
            CourseWork.objects.filter(pk=work.pk).update(created_at=timezone.now() - datetime.timedelta(hours=3))
            self.assertFalse(
                journal_extras.save_course_work(
                    enrollment=self.enrollment, topic="Dəyişdirilmiş", score="10", by_user=self.teacher
                )
            )
            work.refresh_from_db()
            self.assertEqual(work.score, Decimal("100"))  # dondu

    def test_save_allowed_with_override_after_freeze(self):
        # İKT/superuser (allow_locked=True) donmuş kurs işini də dəyişə bilər.
        with bypass_rls():
            journal_extras.save_course_work(
                enrollment=self.enrollment, topic="İlk", score="50", submitted_on=TODAY(), by_user=self.teacher
            )
            work = CourseWork.objects.get(enrollment=self.enrollment)
            CourseWork.objects.filter(pk=work.pk).update(created_at=timezone.now() - datetime.timedelta(hours=3))
            ok = journal_extras.save_course_work(
                enrollment=self.enrollment, topic="Düzəliş", score="90", by_user=self.teacher, allow_locked=True
            )
            self.assertTrue(ok)
            work.refresh_from_db()
            self.assertEqual(work.score, Decimal("90"))


class JournalNotificationTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        with bypass_rls():
            _setup_offering(cls, "jrn")

    def test_absent_and_score_notified_once_per_student(self):
        from apps.notifications.models import InAppNotification

        with bypass_rls():
            lesson = gradebook.create_lesson(
                offering=self.offering, date=TODAY(), kind=LessonKind.SEMINAR, created_by=self.teacher
            )
            with self.captureOnCommitCallbacks(execute=True):
                gradebook.save_marks(
                    offering=self.offering,
                    entries=[
                        {
                            "lesson_id": lesson.id,
                            "enrollment_id": self.enrollment.id,
                            "status": "absent",
                            "score": "7",
                        }
                    ],
                    by_user=self.teacher,
                )
            notes = list(InAppNotification.objects.filter(recipient=self.student))
            self.assertEqual(len(notes), 1)  # eyni save → tək toplu bildiriş
            self.assertIn("Elektron jurnal", notes[0].title)

    def test_kollokvium_score_notifies(self):
        from apps.notifications.models import InAppNotification

        with bypass_rls():
            k1 = journal_extras.ensure_kollokviums(self.offering)[0]
            with self.captureOnCommitCallbacks(execute=True):
                gradebook.save_component_scores(
                    offering=self.offering,
                    entries=[{"component_id": k1.id, "enrollment_id": self.enrollment.id, "score": "8"}],
                    by_user=self.teacher,
                    bypass_edit_window=True,  # kollokvium İmtahan Mərkəzi pəncərəsi ilə yazılır
                )
            self.assertTrue(InAppNotification.objects.filter(recipient=self.student).exists())


class StudentJournalViewTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        with bypass_rls():
            _setup_offering(cls, "jrv")

    def _context(self, params=None):
        from django.test import RequestFactory

        from apps.registrar import public

        request = RequestFactory().get("/accounts/profile/", params or {})
        request.user = self.student
        return public.build_student_journal_context(request, organization=self.org)

    def test_today_marks_hidden_from_student(self):
        with bypass_rls():
            # Dünənki dərs (seed) + bu günkü dərs — tələbə yalnız dünəni görür.
            past = gradebook.create_lesson(
                offering=self.offering,
                date=TODAY() - datetime.timedelta(days=1),
                kind=LessonKind.SEMINAR,
                created_by=self.teacher,
                allow_past=True,
            )
            gradebook.save_marks(
                offering=self.offering,
                entries=[{"lesson_id": past.id, "enrollment_id": self.enrollment.id, "status": "present", "score": 8}],
                by_user=self.teacher,
                enforce_day=False,
            )
            today_lesson = gradebook.create_lesson(offering=self.offering, date=TODAY(), created_by=self.teacher)
            gradebook.save_marks(
                offering=self.offering,
                entries=[{"lesson_id": today_lesson.id, "enrollment_id": self.enrollment.id, "status": "absent"}],
                by_user=self.teacher,
            )
            context = self._context({"subject": str(self.enrollment.id)})
            detail = context["journal_student_section"]["detail"]
            self.assertIsNotNone(detail)
            dates = [m.lesson.date for m in detail["marks"]]
            self.assertIn(past.date, dates)
            self.assertNotIn(TODAY(), dates)  # bu günün qeydi gizlidir
            self.assertTrue(detail["hidden_today"])

    def test_foreign_enrollment_rejected(self):
        with bypass_rls():
            context = self._context({"subject": "00000000-0000-0000-0000-000000000000"})
            self.assertIsNone(context["journal_student_section"]["detail"])

    def test_non_student_gets_none(self):
        from django.test import RequestFactory

        from apps.registrar import public

        request = RequestFactory().get("/accounts/profile/")
        request.user = self.teacher
        with bypass_rls():
            self.assertIsNone(public.build_student_journal_context(request, organization=self.org))


class KollokviumAdoptTest(TestCase):
    """Köhnə "Kollokvium N" adlı generic komponentlər mənimsənilir (unique toqquşması yox)."""

    @classmethod
    def setUpTestData(cls):
        with bypass_rls():
            _setup_offering(cls, "jra")

    def test_existing_generic_kollokvium_adopted(self):
        from apps.registrar.models import AssessmentComponent

        with bypass_rls():
            legacy = AssessmentComponent.objects.create(
                organization=self.org,
                offering=self.offering,
                name="Kollokvium 1",
                kind=ComponentKind.GENERIC,
                max_score=15,
                order=0,
            )
            comps = journal_extras.ensure_kollokviums(self.offering)
            self.assertEqual(len(comps), 3)
            legacy.refresh_from_db()
            self.assertEqual(legacy.kind, ComponentKind.KOLLOKVIUM)  # mənimsənildi
            self.assertEqual(legacy.max_score, 15)  # tavan toxunulmaz
            names = sorted(c.name for c in comps)
            self.assertEqual(names, ["Kollokvium 1", "Kollokvium 2", "Kollokvium 3"])


class MarkTriggerDbTest(TestCase):
    """DB-səviyyəli zəmanət: 2 saatdan köhnə LessonMark UPDATE-i trigger rədd edir.

    Yalnız Postgres-də işləyir (sqlite-da servis qatı yoxlanır)."""

    @classmethod
    def setUpTestData(cls):
        with bypass_rls():
            _setup_offering(cls, "jrt")

    def test_db_trigger_blocks_stale_update(self):
        from django.db import connection

        if connection.vendor != "postgresql":
            self.skipTest("Postgres-only DB trigger testi")
        from django.db.utils import InternalError

        with bypass_rls():
            lesson = gradebook.create_lesson(offering=self.offering, date=TODAY(), created_by=self.teacher)
            gradebook.save_marks(
                offering=self.offering,
                entries=[{"lesson_id": lesson.id, "enrollment_id": self.enrollment.id, "status": "absent"}],
                by_user=self.teacher,
            )
            mark = LessonMark.objects.get(lesson=lesson, enrollment=self.enrollment)
            # Təzə sətri geriyə tarixləmək olar (OLD.created_at hələ təzədir).
            LessonMark.objects.filter(pk=mark.pk).update(created_at=timezone.now() - datetime.timedelta(hours=3))
            # İndi köhnə sətrə İSTƏNİLƏN update — ORM-dən yan keçsə belə — rədd edilir.
            with self.assertRaises(InternalError):
                with transaction_atomic():
                    LessonMark.objects.filter(pk=mark.pk).update(status=AttendanceStatus.PRESENT)
            mark.refresh_from_db()
            self.assertEqual(mark.status, AttendanceStatus.ABSENT)


def transaction_atomic():
    from django.db import transaction as _t

    return _t.atomic()
