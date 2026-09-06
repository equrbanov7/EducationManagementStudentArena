"""Analitikanın SÜRƏTLİ yolu (``analytics_fast``) köhnə qiymətləndirici ilə eyni
rəqəmləri verir — reqressiya kilidi.

2026-09 QA P2-2 optimallaşdırması :func:`analytics.build_period_analytics`-i
``_evaluate`` + ``select_related`` gövdəsindən ayırıb obyektsiz aqreqasiya
yoluna keçirdi (rektor əhatəsi: 3.0–3.9 s → 0.5–0.6 s).  Riyaziyyat KÖÇÜRÜLÜB,
dəyişməyib — bu test onu kilidləyir: eyni fikstura üzərində hər iki yol
işlədilir və payload (``totals`` / ``programs`` / ``groups`` / ``at_risk``)
sahə-sahə müqayisə olunur.

Fikstura qəsdən «çirklidir» — düsturun bütün qolları təmsil olunsun deyə:

* giriş balı həm komponentlərdən (generic, öz tavanı ilə kəsilmiş + kollokvium),
  həm də dərs ballarından (komponentsiz açılış) gəlir;
* sərbəst iş ≤10 balla kəsilir, giriş tavanı (custom sxem) ümumi cəmi kəsir;
* təkrar imtahan (``resit``) imtahan balını əvəz edir və buraxılış qadağasını
  qaldırır; bonus ümumi bala əlavə olunur; imtahan minimumu (``min_exam``)
  keçilməyəndə kəsr olur;
* davamiyyətdən kəsr (``qb``), idmançı istisnası (fərqli proqram həddi ilə),
  məxrəci olmayan açılış (``allowed = 0`` → qərar verilmir);
* DONMUŞ (köçürülmüş + jurnalı bağlı) açılış — canlı qayda kəsərdi, donmuş
  rejimdə kəsmir;
* qrupu OLMAYAN açılış (``groups`` bucket-inə düşmür) və akademik qeydi
  OLMAYAN tələbə (``programs`` bucket-inə düşmür);
* ATILMIŞ (``dropped``) yazılış — heç bir rəqəmə girmir;
* iki proqram (biri yalnız KÖHNƏ rəsmi şifrlə → ``display_code`` geri çəkilməsi),
  iki fərqli qayıb həddi, dörd fərqli kredit (ECTS), həm custom, həm defolt sxem.
"""

from __future__ import annotations

import datetime
from decimal import Decimal

from django.apps import apps as django_apps
from django.db.models import Q
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.organizations.models import AcademicPeriod, Membership, OrgUnit
from apps.registrar import analytics, gradebook
from apps.registrar.models import (
    ApprovalStatus,
    AssessmentComponent,
    AssessmentScheme,
    ComponentKind,
    ComponentScore,
    CourseOffering,
    Curriculum,
    Enrollment,
    FinalGrade,
    Lesson,
    LessonKind,
    Program,
    ResitReason,
    ResitRecord,
    ResitStatus,
    SelfWorkMark,
    SelfWorkTopic,
    StudentAcademicRecord,
    Subject,
)
from apps.registrar.tests.test_analytics import User, _AnalyticsBase
from core.constants import AcademicPeriodType, OrgUnitType
from core.rls import bypass_rls


def _legacy_period_analytics(organization, period, scope_q=None) -> dict:
    """2026-09 P2-2 optimallaşdırmasından ƏVVƏLKİ gövdə.

    ``analytics.build_evaluation_maps`` + ``evaluate_enrollment`` (hər ikisi
    transkript və akademik-qeyd səthlərində HƏLƏ DƏ işlənir) üzərində qurulub —
    yəni test köhnə kodun surətini deyil, canlı qiymətləndiricini işlədir."""
    enrollment_qs = Enrollment.objects.filter(organization=organization, offering__period=period)
    if scope_q is not None:
        enrollment_qs = enrollment_qs.filter(scope_q)
    enrollments = list(
        enrollment_qs.exclude(status=Enrollment.Status.DROPPED).select_related(
            "offering", "offering__subject", "offering__group"
        )
    )
    if not enrollments:
        return {"has_data": False, "period": period, "totals": None, "programs": [], "groups": [], "at_risk": []}

    maps = analytics.build_evaluation_maps(organization, enrollments)
    overall = analytics._Bucket("overall", "")
    programs: dict = {}
    groups: dict = {}
    subjects: dict = {}

    for enrollment in enrollments:
        result = analytics.evaluate_enrollment(enrollment, maps)
        overall.add(enrollment.student_id, result)

        record = maps["records"].get(enrollment.student_id)
        if record is not None and record.program_id:
            bucket = programs.get(record.program_id)
            if bucket is None:
                bucket = programs[record.program_id] = analytics._Bucket(
                    record.program_id, record.program.name, record.program.display_code
                )
            bucket.add(enrollment.student_id, result)

        group = enrollment.offering.group
        if group is not None:
            bucket = groups.get(group.id)
            if bucket is None:
                bucket = groups[group.id] = analytics._Bucket(group.id, group.name)
            bucket.add(enrollment.student_id, result)

        subject = enrollment.offering.subject
        bucket = subjects.get(enrollment.offering_id)
        if bucket is None:
            bucket = subjects[enrollment.offering_id] = analytics._Bucket(
                enrollment.offering_id, subject.name, subject.code
            )
        bucket.add(enrollment.student_id, result)

    return analytics.assemble_payload(period, overall, programs, groups, subjects)


def _freeze(org, offering) -> None:
    """Açılışı DONDURUR: jurnal bağlanır + köçürmə möhürü vurulur.

    İki şərt birdən lazımdır — bax :mod:`apps.registrar.exam_eligibility`
    docstring-i («Donma meyarı»)."""
    scheme, _ = AssessmentScheme.objects.get_or_create(organization=org, offering=offering)
    scheme.is_published = True
    scheme.approval_status = ApprovalStatus.APPROVED
    scheme.save(update_fields=["is_published", "approval_status"])

    run_model = django_apps.get_model("legacy_import", "LegacyMigrationRun")
    map_model = django_apps.get_model("legacy_import", "LegacyEntityMap")
    run = run_model.objects.filter(organization=org, source_system="myedu", status=run_model.Status.RUNNING).first()
    if run is None:
        run = run_model.objects.create(
            organization=org,
            source_system="myedu",
            snapshot_sha256="a" * 64,
            snapshot_size_bytes=1,
            schema_version="v1",
            transform_version="v1",
            mode=run_model.Mode.CUTOVER,
        )
        run.status = run_model.Status.RUNNING
        run.started_at = timezone.now()
        run.save(update_fields=["status", "started_at"])
    map_model.objects.create(
        organization=org,
        source_system="myedu",
        entity_type="course_offering",
        legacy_pk=str(offering.id),
        source_row_hash="b" * 64,
        transform_version="v1",
        target_model_label="registrar.courseoffering",
        target_pk=str(offering.id),
        created_run=run,
        state=map_model.State.MIGRATED,
    )


class FastPathParityTest(_AnalyticsBase):
    """Sürətli yol ≡ köhnə qiymətləndirici (eyni fikstura, eyni payload)."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        with bypass_rls():
            cls._enrich()

    # ── Fikstura ─────────────────────────────────────────────────────────────

    @classmethod
    def _enrich(cls):
        a0, a1, a2 = cls.students

        # Baza açılışı (komponentsiz, dərs balı yolu): student1-i davamiyyətdən
        # kəs — məxrəc dərs cəmindən gəlir (4 dərs × 2 saat = 8, hədd 25% → 2).
        base = cls.enrollments["an_student1"]
        base.absence_hours = 5
        base.save(update_fields=["absence_hours"])

        # ── İkinci proqram: YALNIZ köhnə rəsmi şifr + fərqli qayıb həddi ──────
        cls.program_b = Program.objects.create(
            organization=cls.org,
            code="MYEDU-EC",
            official_code="",
            legacy_official_code="050624",
            name="Aqrar iqtisadiyyat",
            absence_limit_percent=10,
        )
        cls.curriculum_b = Curriculum.objects.create(organization=cls.org, program=cls.program_b, admission_year=2024)
        cls.group_b = OrgUnit.objects.create(
            organization=cls.org, name="AI-201", slug="an-g2", unit_type=OrgUnitType.GROUP, parent=cls.faculty
        )

        # ── Dörd yeni fənn: komponentli / məxrəcsiz / donmuş / hədd-sınağı ────
        subject_b = Subject.objects.create(organization=cls.org, code="CS201", name="Alqoritmlər", ects=4)
        subject_c = Subject.objects.create(organization=cls.org, code="CS301", name="Statistika", ects=3)
        subject_d = Subject.objects.create(organization=cls.org, code="CS401", name="Tarix", ects=5)
        subject_e = Subject.objects.create(organization=cls.org, code="CS501", name="Fəlsəfə", ects=2)

        # Komponentli açılış: kanonik saat 30, custom sxem hədləri.
        cls.off_b = CourseOffering.objects.create(
            organization=cls.org, subject=subject_b, period=cls.period, group=cls.group_b, lesson_hours=30
        )
        AssessmentScheme.objects.update_or_create(
            offering=cls.off_b,
            defaults={
                "organization": cls.org,
                "entry_score_max": 40,
                "pass_threshold": 60,
                "min_final_exam_score": 20,
            },
        )
        generic = AssessmentComponent.objects.create(
            organization=cls.org, offering=cls.off_b, name="Aralıq", kind=ComponentKind.GENERIC, max_score=30
        )
        kollokvium = AssessmentComponent.objects.create(
            organization=cls.org, offering=cls.off_b, name="K1", kind=ComponentKind.KOLLOKVIUM, max_score=10
        )

        # QRUPSUZ açılış, məxrəc YOXDUR (saat 0, dərs yoxdur) → qərar verilmir.
        cls.off_c = CourseOffering.objects.create(
            organization=cls.org, subject=subject_c, period=cls.period, group=None, lesson_hours=0
        )

        # DONMUŞ açılış: canlı qayda kəsərdi (10 saat, 25% → 2.5), donmuş yox.
        cls.off_d = CourseOffering.objects.create(
            organization=cls.org, subject=subject_d, period=cls.period, group=cls.group_b, lesson_hours=10
        )
        _freeze(cls.org, cls.off_d)

        # HƏDD sınaq açılışı (DEFOLT sxem: giriş 50, keçid 51, min imtahan 17) —
        # yuxarı/aşağı 100-bal kəsimi və «imtahan minimumu» qolu burada işə düşür.
        cls.off_e = CourseOffering.objects.create(
            organization=cls.org, subject=subject_e, period=cls.period, group=cls.group, lesson_hours=20
        )
        generic_e = AssessmentComponent.objects.create(
            organization=cls.org, offering=cls.off_e, name="Layihə", kind=ComponentKind.GENERIC, max_score=60
        )

        # ── İki yeni tələbə: biri idmançı istisnalı, biri AKADEMİK QEYDSİZ ────
        student_role = cls.org.roles.get(name="student")
        cls.athlete = User.objects.create_user("an_athlete", "an_athlete@qku.edu.az", "pw")
        cls.orphan = User.objects.create_user("an_orphan", "an_orphan@qku.edu.az", "pw")
        cls.strict = User.objects.create_user("an_strict", "an_strict@qku.edu.az", "pw")
        for user in (cls.athlete, cls.orphan, cls.strict):
            Membership.objects.create(
                user=user, organization=cls.org, role=student_role, is_primary=True, is_active=True
            )
        for user, exempt in ((cls.athlete, True), (cls.strict, False)):
            StudentAcademicRecord.objects.create(
                organization=cls.org,
                student=user,
                program=cls.program_b,
                curriculum=cls.curriculum_b,
                group=cls.group_b,
                admission_year=2024,
                national_athlete_exemption=exempt,
            )
        # ``orphan`` üçün QEYD YARADILMIR — ``records`` map-də yoxdur.

        # ── Komponentli açılışın yazılışları ──────────────────────────────────
        enr_b0 = Enrollment.objects.create(organization=cls.org, student=a0, offering=cls.off_b, absence_hours=0)
        enr_b1 = Enrollment.objects.create(organization=cls.org, student=a1, offering=cls.off_b, absence_hours=20)
        enr_b2 = Enrollment.objects.create(organization=cls.org, student=a2, offering=cls.off_b, absence_hours=20)
        enr_b3 = Enrollment.objects.create(
            organization=cls.org, student=cls.athlete, offering=cls.off_b, absence_hours=5
        )

        # Tavanı AŞAN ballar — hər biri öz komponent tavanına kəsilməlidir.
        ComponentScore.objects.create(organization=cls.org, component=generic, enrollment=enr_b0, score=Decimal("35"))
        ComponentScore.objects.create(
            organization=cls.org, component=kollokvium, enrollment=enr_b0, score=Decimal("12")
        )
        ComponentScore.objects.create(organization=cls.org, component=generic, enrollment=enr_b1, score=Decimal("20"))
        # a1-də kollokvium giriş tavanının ALTINDA qalır (20 + 8 + 3 = 31 < 40),
        # yəni onu unutmaq rəqəmi dəyişir — «üstəgəl» qolunun kilidi.
        ComponentScore.objects.create(organization=cls.org, component=kollokvium, enrollment=enr_b1, score=Decimal("8"))
        ComponentScore.objects.create(organization=cls.org, component=generic, enrollment=enr_b3, score=Decimal("25"))

        # Sərbəst iş: 12 təhvil → 10 balla kəsilir; a1-də 3 təhvil.
        topics = [
            SelfWorkTopic.objects.create(organization=cls.org, offering=cls.off_b, title=f"SDF {i}", order=i)
            for i in range(12)
        ]
        for index, topic in enumerate(topics):
            SelfWorkMark.objects.create(organization=cls.org, topic=topic, enrollment=enr_b0, done=True)
            SelfWorkMark.objects.create(organization=cls.org, topic=topic, enrollment=enr_b1, done=index < 3)

        # a0 keçir (giriş tavanı 40 kəsir, bonus əlavə olunur), a1 imtahan
        # minimumundan aşağı qalır (15 < 20) VƏ davamiyyətdən kəsilir.
        FinalGrade.objects.create(organization=cls.org, enrollment=enr_b0, exam_score=Decimal("25"), bonus=Decimal("3"))
        FinalGrade.objects.create(organization=cls.org, enrollment=enr_b1, exam_score=Decimal("15"))
        # a2: kəsilmə həddindədir, amma TƏKRAR İMTAHAN qadağanı qaldırır.
        ResitRecord.objects.create(
            organization=cls.org,
            enrollment=enr_b2,
            reason=ResitReason.ABSENCE,
            status=ResitStatus.COMPLETED,
            resit_score=Decimal("45"),
        )
        # enr_b3 (idmançı): imtahan YOXDUR → «davam edir» qolu.

        # ── Məxrəcsiz açılış: qeydsiz tələbə + ATILMIŞ yazılış ────────────────
        Enrollment.objects.create(organization=cls.org, student=cls.orphan, offering=cls.off_c, absence_hours=40)
        dropped = Enrollment.objects.create(
            organization=cls.org,
            student=a0,
            offering=cls.off_c,
            absence_hours=99,
            status=Enrollment.Status.DROPPED,
        )
        FinalGrade.objects.create(organization=cls.org, enrollment=dropped, exam_score=Decimal("50"))

        # ── Donmuş açılış: köhnə sistemin nəticəsi var / yoxdur ───────────────
        enr_d1 = Enrollment.objects.create(organization=cls.org, student=a1, offering=cls.off_d, absence_hours=9)
        Enrollment.objects.create(organization=cls.org, student=a2, offering=cls.off_d, absence_hours=9)
        FinalGrade.objects.create(organization=cls.org, enrollment=enr_d1, exam_score=Decimal("30"))

        # ── Hədd sınaqları (defolt sxem: giriş 50, keçid 51, min imtahan 17) ──
        enr_e0 = Enrollment.objects.create(organization=cls.org, student=a0, offering=cls.off_e, absence_hours=0)
        # a1: qayıb həddi AŞILIB (10 > 20×25% = 5), amma bal onsuz da keçid
        # həddindən yuxarıdır → «kəsilib» qərarı YALNIZ ``barred``-dan gəlir.
        enr_e1 = Enrollment.objects.create(organization=cls.org, student=a1, offering=cls.off_e, absence_hours=10)
        # a2: qayıb DƏQİQ həddədir (5 = 5) → strict ``>`` qaydası ilə kəsilmir.
        enr_e2 = Enrollment.objects.create(organization=cls.org, student=a2, offering=cls.off_e, absence_hours=5)
        enr_e3 = Enrollment.objects.create(
            organization=cls.org, student=cls.athlete, offering=cls.off_e, absence_hours=0
        )
        # ``strict``: proqram həddi 10% (20 saatın 2-si) — 4 saat qayıb KƏSİR.
        # Defolt 25% həddi ilə (5 saat) kəsməzdi → hədd mənbəyinin kilidi.
        Enrollment.objects.create(organization=cls.org, student=cls.strict, offering=cls.off_e, absence_hours=4)
        # ``orphan``: qeydsiz (defolt hədd 25% → 5 saat), 10 saat qayıb → kəsilir
        # və imtahanı YOXDUR → «kəsilib» qərarı yalnız ``barred``-dan gəlir.
        Enrollment.objects.create(organization=cls.org, student=cls.orphan, offering=cls.off_e, absence_hours=10)
        # Kəsr balı (44.50) — giriş və yekun TAM ƏDƏDƏ yuvarlaqlaşdırılır.
        ComponentScore.objects.create(
            organization=cls.org, component=generic_e, enrollment=enr_e0, score=Decimal("44.50")
        )
        ComponentScore.objects.create(organization=cls.org, component=generic_e, enrollment=enr_e1, score=Decimal("45"))
        ComponentScore.objects.create(organization=cls.org, component=generic_e, enrollment=enr_e2, score=Decimal("60"))
        FinalGrade.objects.create(organization=cls.org, enrollment=enr_e1, exam_score=Decimal("30"))
        # a0: giriş 44.50 → 45 (yarım-yuxarı), 45 + 16.40 = 61.40 → 61 ≥ 51,
        # AMMA imtahan minimumu (17) keçilmir → KƏSR.
        FinalGrade.objects.create(organization=cls.org, enrollment=enr_e0, exam_score=Decimal("16.40"))
        # a2: giriş tavanı 50 kəsir, 50 + 45 + 20 = 115 → 100-ə kəsilir.
        FinalGrade.objects.create(
            organization=cls.org, enrollment=enr_e2, exam_score=Decimal("45"), bonus=Decimal("20")
        )
        # idmançı: 0 + 0 − 10 = −10 → aşağıdan 0-a kəsilir (qiymətləndirilib).
        FinalGrade.objects.create(
            organization=cls.org, enrollment=enr_e3, exam_score=Decimal("0"), bonus=Decimal("-10")
        )

        # Dərs saatı fallback-i: donmuş açılışın dərsləri (kanonik saat 10 olsa
        # da) — ``lesson_hours_for`` kanoniki üstün tutmalıdır, fallback yox.
        Lesson.objects.create(
            organization=cls.org,
            offering=cls.off_d,
            date=datetime.date(2024, 11, 1),
            kind=LessonKind.LECTURE,
            hours=99,
        )

    # ── Köməkçilər ───────────────────────────────────────────────────────────

    @staticmethod
    def _comparable(payload) -> dict:
        """``at_risk`` bərabər kəsr faizli fənlərdə DB skan sırasından asılıdır
        (hər iki yolda eyni cür) — müqayisə üçün açara görə nizamlanır."""
        data = dict(payload)
        data["at_risk"] = sorted(payload["at_risk"], key=lambda s: str(s["key"]))
        return data

    def _assert_same(self, scope_q, label):
        with bypass_rls():
            legacy = _legacy_period_analytics(self.org, self.period, scope_q)
            fast = analytics.build_period_analytics(organization=self.org, period=self.period, scope_q=scope_q)
        self.assertEqual(self._comparable(legacy), self._comparable(fast), label)
        # Sıra da eynidir (fiksturada bərabər kəsr faizi yoxdur).
        self.assertEqual(
            [(s["key"], s["fail_rate"]) for s in legacy["at_risk"]],
            [(s["key"], s["fail_rate"]) for s in fast["at_risk"]],
            f"{label}: at_risk sırası",
        )
        return fast

    # ── Testlər ──────────────────────────────────────────────────────────────

    def test_org_wide_payload_is_identical(self):
        data = self._assert_same(None, "org-səviyyəli")
        # Fikstura həqiqətən «çirklidir» — boş nəticəni səhvən müqayisə etmirik.
        self.assertTrue(data["has_data"])
        self.assertEqual(data["totals"]["enrollments"], 16)
        self.assertEqual(data["totals"]["students"], 6)
        self.assertEqual(len(data["programs"]), 2)
        self.assertEqual(len(data["groups"]), 2)  # qrupsuz açılış bucket YARATMIR

    def test_scoped_payload_is_identical(self):
        """Dekan/kafedra əhatəsi (alt-ağac filtri) — eyni rəqəmlər."""
        data = self._assert_same(Q(offering__group__id__in=[self.group_b.id]), "qrup əhatəsi")
        self.assertTrue(data["has_data"])
        self.assertEqual(len(data["groups"]), 1)

    def test_empty_scope_payload_is_identical(self):
        """Əhatəsi boş aktor — hər iki yol eyni «data yoxdur» payload-u verir."""
        data = self._assert_same(Q(pk__in=[]), "boş əhatə")
        self.assertFalse(data["has_data"])
        self.assertIsNone(data["totals"])

    def test_empty_period_payload_is_identical(self):
        with bypass_rls():
            empty = AcademicPeriod.objects.create(
                organization=self.org,
                name="Boş dövr",
                period_type=AcademicPeriodType.SEMESTER,
                academic_year="2025/2026",
                start_date="2025-09-01",
                end_date="2026-01-31",
            )
            legacy = _legacy_period_analytics(self.org, empty)
            fast = analytics.build_period_analytics(organization=self.org, period=empty)
        self.assertEqual(legacy, fast)
        self.assertFalse(fast["has_data"])

    def test_dropped_enrollment_is_excluded(self):
        """Atılmış yazılışın imtahan balı heç bir bucket-ə girmir."""
        with bypass_rls():
            data = analytics.build_period_analytics(organization=self.org, period=self.period)
        subject_c_rows = [row for row in data["at_risk"] if row["sublabel"] == "CS301"]
        # CS301-də yalnız qeydsiz tələbənin (qiymətsiz) yazılışı qalır → risk yox.
        self.assertEqual(subject_c_rows, [])
        self.assertEqual(data["totals"]["enrollments"], 16)

    def test_frozen_offering_is_not_barred(self):
        """Donmuş açılışda 9 saat qayıb (canlı hədd 2.5) kəsr YARATMIR."""
        with bypass_rls():
            data = analytics.build_period_analytics(organization=self.org, period=self.period)
        frozen_group = next(row for row in data["groups"] if row["key"] == self.group_b.id)
        # Qrupdakı yeganə kəsr davamiyyəti — komponentli açılışdakı a1-dir.
        self.assertEqual(frozen_group["barred"], 1)

    def test_program_display_code_falls_back_to_legacy(self):
        """Cari rəsmi şifri olmayan proqram KÖHNƏ şifrlə göstərilir."""
        with bypass_rls():
            data = analytics.build_period_analytics(organization=self.org, period=self.period)
        codes = {row["label"]: row["sublabel"] for row in data["programs"]}
        self.assertEqual(codes["Aqrar iqtisadiyyat"], "050624")
        self.assertEqual(codes["Kompüter elmləri"], "060501")

    def test_query_count_is_bounded(self):
        """Sorğu sayı yazılış sayından ASILI DEYİL (sabit büdcə)."""
        from django.db import connection

        with bypass_rls():
            with CaptureQueriesContext(connection) as ctx:
                analytics.build_period_analytics(organization=self.org, period=self.period)
        self.assertLessEqual(len(ctx.captured_queries), 13, [q["sql"][:120] for q in ctx.captured_queries])


class FastPathHelpersTest(_AnalyticsBase):
    """Sürətli yolun mətn açarları və birləşdirilmiş skanı."""

    def test_component_sums_match_legacy_maps(self):
        """Birləşdirilmiş ``FILTER`` skanı iki ayrı skanla eyni cəmi verir."""
        from apps.registrar import analytics_fast

        with bypass_rls():
            gradebook.save_components(
                offering=self.offering,
                definitions=[{"name": "Seminar", "max_score": 20}],
                by_user=self.teacher,
            )
            comp = gradebook.get_components(self.offering)[0]
            enrollment = self.enrollments["an_student2"]
            ComponentScore.objects.create(
                organization=self.org, component=comp, enrollment=enrollment, score=Decimal("25")
            )
            legacy = analytics._component_sum_map([enrollment.id])
            generic, _kollokvium = analytics_fast._component_sum_maps([enrollment.id])
        # Tavan hər iki yolda işləyir (25 → 20); açar tipi fərqlidir (UUID vs mətn).
        self.assertEqual(legacy[enrollment.id], Decimal("20"))
        self.assertEqual(list(generic.values()), [Decimal("20")])
