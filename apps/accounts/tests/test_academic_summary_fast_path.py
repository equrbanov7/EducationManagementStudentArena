"""Xülasə box-larının SÜRƏTLİ yolu (``academic_summary``) köhnə qiymətləndirici
ilə eyni rəqəmləri verir — reqressiya kilidi.

2026-09 QA P2-19 optimallaşdırması ``build_records_summary``-ni
``analytics._evaluate`` + ``_accumulate`` cütündən ayırıb ayrıca, obyektsiz
aqreqasiya yoluna keçirdi (7.2 s → 1.8 s, org-səviyyəli aktor).  Riyaziyyat
KÖÇÜRÜLÜB, dəyişməyib — bu test onu kilidləyir: eyni fikstura üzərində hər iki
yol işlədilir və akkumulyatorlar bayt-bayt müqayisə olunur.

Fikstura qəsdən «çirklidir» — düsturun bütün qolları təmsil olunsun deyə:

* giriş balı komponentlərdən (generic, öz tavanı ilə kəsilmiş) VƏ dərs
  ballarından (komponentsiz açılış) gəlir;
* kollokvium + sərbəst iş (≤10) üstəgəl olunur, giriş tavanı (custom sxem) kəsir;
* təkrar imtahan (``resit``) imtahan balını əvəz edir və buraxılış qadağasını
  qaldırır; bonus ümumi bala əlavə olunur;
* davamiyyətdən kəsr (``qb``), idmançı istisnası, məxrəci olmayan açılış
  (``allowed = 0`` → qərar verilmir);
* «qiymətləndirilməyib» — həm ``FinalGrade`` yoxdur, həm ``exam_score=None``;
* auditoriya saatı həm kanonik sahədən, həm dərs cəmi fallback-indən;
* iki fərqli kredit (ECTS) və həm custom, həm defolt sxem hədləri.
"""

from __future__ import annotations

from decimal import Decimal
from unittest import mock

from apps.accounts import academic_records, academic_summary
from apps.accounts.tests.test_academic_records import _RecordsBase
from apps.organizations.scoping import ORG_WIDE_SCOPE
from apps.registrar import exam_eligibility
from apps.registrar.models import (
    AssessmentComponent,
    AssessmentScheme,
    ComponentKind,
    ComponentScore,
    CourseOffering,
    Enrollment,
    FinalGrade,
    ResitReason,
    ResitRecord,
    ResitStatus,
    SelfWorkMark,
    SelfWorkTopic,
    StudentAcademicRecord,
    Subject,
)
from core.rls import bypass_rls


def _legacy_box(organization, enrollment_qs) -> dict:
    """2026-09 optimallaşdırmasından ƏVVƏLKİ yol — ``build_records_summary``-nin
    köhnə gövdəsi (``analytics._evaluate`` → ``_accumulate``)."""
    box = academic_records._empty_summary()
    for _enrollment, result in academic_records._evaluate_all(organization, enrollment_qs):
        academic_records._accumulate(box, result)
    return box


class FastPathParityTest(_RecordsBase):
    """Sürətli yol ≡ köhnə qiymətləndirici (eyni fikstura, eyni rəqəmlər)."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        with bypass_rls():
            cls._enrich()

    @classmethod
    def _enrich(cls):
        a0, a1, a2 = cls.students_a
        b0, b1 = cls.students_b
        offering_a = a0.enrollments.get().offering
        offering_b = b0.enrollments.get().offering

        # ── Açılış A: komponentli giriş balı + custom sxem hədləri ────────────
        # ``lesson_hours`` 0 qalır → məxrəc dərs cəmindən (4 dərs × 2 saat = 8)
        # bərpa olunur: ``exam_eligibility.lesson_hours_for`` fallback-i.
        AssessmentScheme.objects.update_or_create(
            offering=offering_a,
            defaults={
                "organization": cls.org,
                "entry_score_max": 40,
                "pass_threshold": 60,
                "min_final_exam_score": 20,
            },
        )
        generic = AssessmentComponent.objects.create(
            organization=cls.org, offering=offering_a, name="Aralıq", kind=ComponentKind.GENERIC, max_score=30
        )
        kollokvium = AssessmentComponent.objects.create(
            organization=cls.org, offering=offering_a, name="K1", kind=ComponentKind.KOLLOKVIUM, max_score=10
        )
        enr_a0 = a0.enrollments.get()
        enr_a1 = a1.enrollments.get()
        # Tavanı AŞAN ballar — hər ikisi öz komponent tavanına kəsilməlidir.
        ComponentScore.objects.create(
            organization=cls.org, component=generic, enrollment=enr_a0, score=Decimal("35.00")
        )
        ComponentScore.objects.create(
            organization=cls.org, component=kollokvium, enrollment=enr_a0, score=Decimal("12.00")
        )
        ComponentScore.objects.create(
            organization=cls.org, component=generic, enrollment=enr_a1, score=Decimal("20.00")
        )

        # Sərbəst iş: 12 təhvil → 10 balla kəsilir; a1-də 3 təhvil.
        topics = [
            SelfWorkTopic.objects.create(organization=cls.org, offering=offering_a, title=f"SDF {i}", order=i)
            for i in range(12)
        ]
        for index, topic in enumerate(topics):
            SelfWorkMark.objects.create(organization=cls.org, topic=topic, enrollment=enr_a0, done=True)
            SelfWorkMark.objects.create(organization=cls.org, topic=topic, enrollment=enr_a1, done=index < 3)

        # a0: təkrar imtahan imtahan balını əvəz edir VƏ qayıb qadağasını qaldırır.
        # ⚠️ ``finals.set_exam_score`` kəsilən tələbəyə onsuz da balsız resit
        # açır (b0-da o, ``resit_score=None`` ilə qalır — sayılmır).
        ResitRecord.objects.update_or_create(
            enrollment=enr_a0,
            defaults={
                "organization": cls.org,
                "reason": ResitReason.EXAM,
                "status": ResitStatus.COMPLETED,
                "resit_score": Decimal("70.00"),
            },
        )
        Enrollment.objects.filter(pk=enr_a0.pk).update(absence_hours=5)  # həddi aşır, resit qaldırır
        # a1: idmançı istisnası — saatlar aşır, amma buraxılış qadağası qalxmır.
        Enrollment.objects.filter(pk=enr_a1.pk).update(absence_hours=5)
        StudentAcademicRecord.objects.filter(organization=cls.org, student=a1).update(national_athlete_exemption=True)

        # ── Açılış B: komponentsiz (dərs balı cəmi) + kanonik saat + bonus/qb ──
        CourseOffering.objects.filter(pk=offering_b.pk).update(lesson_hours=20)  # icazəli qayıb = 5
        FinalGrade.objects.filter(enrollment__student=b0).update(bonus=Decimal("5.00"))
        Enrollment.objects.filter(student=b1).update(absence_hours=9)  # 9 > 5 → q/b kəsri

        # ── Açılış C: məxrəci olmayan (saat 0, dərs yoxdur) + fərqli kredit ───
        subject_c = Subject.objects.create(organization=cls.org, code="REC202", name="Fənn C", ects=3)
        offering_c = CourseOffering.objects.create(
            organization=cls.org,
            subject=subject_c,
            period=cls.period,
            group=cls.group_a,
            lesson_hours=0,
        )
        enr_c = {
            student: Enrollment.objects.create(organization=cls.org, student=student, offering=offering_c)
            for student in (a0, a1, a2)
        }
        Enrollment.objects.filter(pk=enr_c[a2].pk).update(absence_hours=99)  # məxrəc yoxdur → qərar yoxdur
        FinalGrade.objects.create(organization=cls.org, enrollment=enr_c[a0], exam_score=Decimal("30.00"))
        # ⚠️ Bal YAZILMAYIB (``exam_score=None``) — nə keçib, nə kəsilib.
        FinalGrade.objects.create(organization=cls.org, enrollment=enr_c[a2], exam_score=None, bonus=Decimal("3.00"))
        cls.offering_ids = [offering_a.id, offering_b.id, offering_c.id]

    # ── Köməkçilər ───────────────────────────────────────────────────────────

    def _enrollment_qs(self):
        records = academic_records._scoped_records(self.org, ORG_WIDE_SCOPE, {})
        return academic_records._enrollment_qs(self.org, records.order_by().values("student_id"), None)

    def _both_boxes(self):
        with bypass_rls():
            legacy = _legacy_box(self.org, self._enrollment_qs())
            fast = academic_records._empty_summary()
            academic_summary.accumulate_summary(self.org, self._enrollment_qs(), fast)
        return legacy, fast

    # ── Testlər ──────────────────────────────────────────────────────────────

    def test_fixture_exercises_every_branch(self):
        """Kilidin dişi olsun: fikstura bütün qutuları DOLU qaytarmalıdır."""
        _legacy, fast = self._both_boxes()
        self.assertGreater(fast["credits_earned"], 0, "keçən yazılış yoxdur")
        self.assertGreater(fast["qb"], 0, "davamiyyətdən kəsr (q/b) yoxdur")
        self.assertGreater(fast["exam25"], 0, "imtahandan kəsr (25%) yoxdur")
        self.assertGreater(fast["ungraded"], 0, "qiymətləndirilməyib sətri yoxdur")
        self.assertGreater(fast["gpa_credits"], 0, "ÜOMG məxrəci boşdur")
        self.assertEqual(fast["fails"], fast["qb"] + fast["exam25"])

    def test_fast_path_matches_legacy_evaluator(self):
        legacy, fast = self._both_boxes()
        self.assertEqual(fast, legacy)

    def test_fast_path_matches_legacy_evaluator_when_frozen(self):
        """DONMUŞ (köçürülmüş + bağlı jurnal) açılışlarda da eyni rəqəmlər.

        Donma qərarı hər iki yolda EYNİ köməkçidən (``frozen_offering_ids``)
        gəlir, ona görə onu birbaşa əvəzləmək kifayətdir — ``legacy_import``
        fiksturası qurmadan qolu yoxlayır.  Donmuş dilimdə ``barred`` heç vaxt
        qalxmır, yəni q/b kəsri exam25-ə keçir."""
        frozen = frozenset(self.offering_ids)
        with mock.patch.object(exam_eligibility, "frozen_offering_ids", return_value=frozen):
            legacy, fast = self._both_boxes()
        self.assertEqual(fast, legacy)
        self.assertEqual(fast["qb"], 0, "donmuş dilimdə q/b damğası vurulmamalıdır")

    def test_summary_payload_matches_legacy_path(self):
        """Public payload (``_public_summary`` + ÜOMG) da eyni qalır."""
        with bypass_rls():
            legacy = _legacy_box(self.org, self._enrollment_qs())
            legacy["students"] = academic_records._distinct_student_count(
                academic_records._scoped_records(self.org, ORG_WIDE_SCOPE, {})
            )
            expected = academic_records._public_summary(legacy)
            payload = academic_records.build_records_summary(organization=self.org, scope=ORG_WIDE_SCOPE, filters={})
        self.assertEqual(payload["summary"], expected)
        self.assertTrue(payload["summary"]["avg_gpa_available"])
