"""``finals_batch`` — toplu yol tək-sətir yolu ilə BAYT-BAYT eyni olmalıdır.

Performans düzəlişi (2026-09-02) ``compute_final_result``-a ``batch=`` əlavə etdi:
komponentlər, komponent balları, sərbəst iş sayğacı, ``FinalGrade``/``ResitRecord``,
donma dəsti, qayıb həddi və idmançı istisnası artıq sətir-sətir yox, BİR dəfə
oxunur.  Bu qapı hər sətri HƏR İKİ yolla hesablayıb nəticələri müqayisə edir —
yəni «sürətləndirdik, amma bal dəyişdi» halı testdə düşür.
"""

import datetime
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit
from apps.registrar import finals, finals_batch, gradebook, services, transcript
from apps.registrar.models import (
    AssessmentComponent,
    ComponentKind,
    ComponentScore,
    Curriculum,
    CurriculumSubject,
    LessonKind,
    Program,
    SelfWorkMark,
    SelfWorkTopic,
    StudentAcademicRecord,
    Subject,
)
from core.constants import AcademicPeriodType, OrganizationType, OrgUnitType
from core.rls import bypass_rls

User = get_user_model()

#: Müqayisədən kənar açarlar: model NÜMUNƏSİ qaytaran sahələr (eyni sətir, fərqli
#: Python obyekti) — dəyər bərabərliyi ayrıca yoxlanılır.
_INSTANCE_KEYS = ("resit",)


def _comparable(result) -> dict:
    plain = {k: v for k, v in result.items() if k not in _INSTANCE_KEYS}
    resit = result.get("resit")
    plain["_resit_id"] = getattr(resit, "id", None)
    plain["_resit_score"] = getattr(resit, "resit_score", None)
    plain["_resit_status"] = getattr(resit, "status", None)
    # Tərcümə proxy-ləri (`status_label`, `status_notice`) mətnə çevrilir ki,
    # müqayisə obyekt kimliyindən yox, GÖRÜNƏN dəyərdən getsin.
    for key in ("status_label", "status_notice"):
        plain[key] = str(plain.get(key, ""))
    plain["eligibility"] = {k: str(v) for k, v in (plain.get("eligibility") or {}).items()}
    return plain


class FinalsBatchEquivalenceTest(TestCase):
    """Toplu yol ↔ tək-sətir yolu eyniliyi (komponentli və komponentsiz açılış)."""

    def setUp(self):
        self.owner = User.objects.create_user("fb_owner", "fb_owner@qku.edu.az", "pw")
        with bypass_rls():
            self.org = Organization.objects.create(
                name="FB Univ",
                slug="fb-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=self.owner,
                status="active",
                is_active=True,
            )
            self.group = OrgUnit.objects.create(
                organization=self.org, name="FB-G1", slug="fb-g1", unit_type=OrgUnitType.GROUP
            )
            self.period = AcademicPeriod.objects.create(
                organization=self.org,
                name="P",
                period_type=AcademicPeriodType.SEMESTER,
                academic_year="2024/2025",
                start_date="2024-09-01",
                end_date="2025-01-31",
                is_current=True,
            )
            self.program = Program.objects.create(
                organization=self.org, code="FB", name="Fizika", absence_limit_percent=25
            )
            self.curriculum = Curriculum.objects.create(
                organization=self.org, program=self.program, admission_year=2024
            )
            self.subject = Subject.objects.create(organization=self.org, code="FB101", name="Mexanika")
            CurriculumSubject.objects.create(
                organization=self.org, curriculum=self.curriculum, subject=self.subject, semester_number=1
            )
            self.teacher = User.objects.create_user("fb_teacher", "fb_teacher@qku.edu.az", "pw")
            Membership.objects.create(
                user=self.teacher,
                organization=self.org,
                role=self.org.roles.get(name="teacher"),
                is_primary=True,
                is_active=True,
            )
            self.students = []
            self.records = []
            for index in range(3):
                student = User.objects.create_user(f"fb_student{index}", f"fb_s{index}@qku.edu.az", "pw")
                Membership.objects.create(
                    user=student,
                    organization=self.org,
                    role=self.org.roles.get(name="student"),
                    is_primary=True,
                    is_active=True,
                )
                record = StudentAcademicRecord.objects.create(
                    organization=self.org,
                    student=student,
                    program=self.program,
                    curriculum=self.curriculum,
                    group=self.group,
                    admission_year=2024,
                    # 3-cü tələbə rəsmi idmançıdır → istisna toplu dəstdən gəlməlidir.
                    national_athlete_exemption=(index == 2),
                )
                services.enroll_mandatory_subjects(record=record, period=self.period, semester_number=1)
                self.students.append(student)
                self.records.append(record)
            self.offering = self.students[0].enrollments.get().offering
            self.offering.lesson_hours = 60
            self.offering.instructor = self.teacher
            self.offering.save(update_fields=["lesson_hours", "instructor"])
            self.enrollments = list(self.offering.enrollments.order_by("student__username"))

    # ── köməkçilər ───────────────────────────────────────────────────────────

    def _seminar_marks(self):
        """Dərs balları (komponentsiz yol — giriş balı dərs cəmindən gəlir)."""
        lesson = gradebook.create_lesson(
            allow_past=True, offering=self.offering, date=datetime.date(2024, 10, 1), kind=LessonKind.SEMINAR
        )
        gradebook.save_marks(
            enforce_day=False,
            offering=self.offering,
            entries=[
                {"lesson_id": lesson.id, "enrollment_id": e.id, "status": "present", "score": 5 + i}
                for i, e in enumerate(self.enrollments)
            ],
            by_user=self.teacher,
        )

    def _components(self):
        """GENERIC + KOLLOKVIUM + SELF_WORK komponentləri və ballar."""
        generic = AssessmentComponent.objects.create(
            organization=self.org, offering=self.offering, name="Seminar cəmi", kind=ComponentKind.GENERIC, max_score=20
        )
        kollokvium = AssessmentComponent.objects.create(
            organization=self.org,
            offering=self.offering,
            name="Kollokvium 1",
            kind=ComponentKind.KOLLOKVIUM,
            max_score=10,
        )
        AssessmentComponent.objects.create(
            organization=self.org,
            offering=self.offering,
            name="Sərbəst iş",
            kind=ComponentKind.SELF_WORK,
            max_score=10,
        )
        topics = [
            SelfWorkTopic.objects.create(organization=self.org, offering=self.offering, title=f"Mövzu {n}")
            for n in range(3)
        ]
        for index, enrollment in enumerate(self.enrollments):
            ComponentScore.objects.create(
                organization=self.org, component=generic, enrollment=enrollment, score=Decimal(10 + index)
            )
            ComponentScore.objects.create(
                organization=self.org, component=kollokvium, enrollment=enrollment, score=Decimal(3 + index)
            )
            for topic in topics[: index + 1]:
                SelfWorkMark.objects.create(organization=self.org, topic=topic, enrollment=enrollment, done=True)

    def _scores(self):
        """Yekun imtahan balı + təkrar imtahan (kəsilən sətir üçün)."""
        finals.set_exam_score(enrollment=self.enrollments[0], score=40, by_user=self.teacher)
        finals.set_exam_score(enrollment=self.enrollments[1], score=10, by_user=self.teacher)
        # 3-cü tələbədə bal ümumiyyətlə yoxdur ("hələ qiymətləndirilməyib" yolu).

    def _assert_equivalent(self):
        with bypass_rls():
            enrollments = list(self.offering.enrollments.order_by("student__username"))
            batch = finals_batch.build(enrollments)
            for enrollment in enrollments:
                single = finals.compute_final_result(enrollment=enrollment)
                batched = finals.compute_final_result(enrollment=enrollment, batch=batch)
                self.assertEqual(
                    _comparable(batched),
                    _comparable(single),
                    msg=f"toplu ↔ tək-sətir fərqi: {enrollment.student.username}",
                )

    # ── testlər ──────────────────────────────────────────────────────────────

    def test_equivalent_without_components(self):
        with bypass_rls():
            self._seminar_marks()
            self._scores()
        self._assert_equivalent()

    def test_equivalent_with_components(self):
        with bypass_rls():
            self._seminar_marks()
            self._components()
            self._scores()
        self._assert_equivalent()

    def test_entry_score_batch_matches_single_row(self):
        with bypass_rls():
            self._seminar_marks()
            self._components()
            scheme = gradebook.ensure_assessment_scheme(offering=self.offering)
            enrollments = list(self.offering.enrollments.order_by("student__username"))
            batch = finals_batch.entry_batch(enrollments)
            for enrollment in enrollments:
                self.assertEqual(
                    gradebook.entry_score_for(enrollment, scheme.entry_score_max, **batch.entry_kwargs(enrollment)),
                    gradebook.entry_score_for(enrollment, scheme.entry_score_max),
                )

    def test_offering_results_query_count_is_constant(self):
        """Sətir sayı artanda sorğu sayı ARTMAMALIDIR (N+1 qapısı)."""
        with bypass_rls():
            self._seminar_marks()
            self._components()
            self._scores()
            with CaptureQueriesContext(connection) as captured:
                rows = finals.get_offering_results(offering=self.offering)["rows"]
            self.assertEqual(len(rows), 3)
            # Toplu dəst + sxem oxuması: sabit büdcə, sətir sayından ASILI DEYİL
            # (əvvəl sətir başına ~18 sorğu idi).
            self.assertLessEqual(len(captured), 20, [q["sql"] for q in captured])

    def test_absence_limit_percent_map_matches_single_lookup(self):
        with bypass_rls():
            mapping = finals_batch.absence_limit_percent_map([self.offering])
            self.assertEqual(
                mapping[(self.offering.organization_id, self.offering.group_id)],
                gradebook.absence_limit_percent_for(self.offering),
            )

    def test_transcript_rows_unchanged_by_batching(self):
        """Transkript sətirləri toplu yol ilə eyni yekun balı verməlidir."""
        with bypass_rls():
            self._seminar_marks()
            self._components()
            self._scores()
            for student in self.students:
                data = transcript.build_student_transcript(student=student, organization=self.org)
                for semester in data["semesters"]:
                    for row in semester["rows"]:
                        single = finals.compute_final_result(enrollment=row["enrollment"])
                        self.assertEqual(_comparable(row["result"]), _comparable(single))
