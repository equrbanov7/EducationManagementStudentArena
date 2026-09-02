"""Tarixi (köçürülmüş + bağlı) semestrdə imtahana buraxılış statusu DONUR.

Sahibin qərarı (2026-08-31): köçürülmüş bağlı semestrlərdə buraxılış statusu
**hesablanmasın**, köhnə sistemin faktiki nəticəsi göstərilsin.  Yeni qayda
yalnız bundan sonrakı semestrlərə işləsin.  Heç bir saxlanmış dəyər dəyişmir —
status **oxu vaxtı** həll olunur (bax :mod:`apps.registrar.exam_eligibility`).

Bu fayl dörd şeyi kilidləyir:

1. **706 kritik hal** — köhnə sistem imtahana BURAXIB (imtahan balı var), yeni
   sistem isə «Kəsilir · q/b» göstərirdi.  Artıq göstərməməlidir
   (:class:`FrozenSemesterShowsLegacyResult`).
2. **Canlı semestrdə qayda İŞLƏYİR** — donma yalnız hər İKİ şərt ödənəndə baş
   verir (:class:`LiveSemesterStillComputes`).
3. **Altı çağırış nöqtəsi eyni cavabı verir** — dağınıqlıq problemin kökü idi
   (:class:`CallSitesAgree`).
4. **Sərhəd halları** — sübut sətri yox / imtahan balı 0 / məxrəcsiz
   (:class:`FrozenEdgeCases`, :class:`ResolverPureUnits`).
"""

from __future__ import annotations

import datetime
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import RequestFactory, TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit
from apps.registrar import (
    analytics,
    exam_bridge,
    exam_eligibility,
    finals,
    gradebook,
    guest_merge,
    guest_roster,
    journal_extras,
    page_contexts,
    public,
    services,
    transcript,
)
from apps.registrar.models import (
    ApprovalStatus,
    CourseOffering,
    Curriculum,
    CurriculumSubject,
    Enrollment,
    LessonKind,
    LessonMark,
    Program,
    StudentAcademicRecord,
    Subject,
)
from core.constants import AcademicPeriodType, OrganizationType, OrgUnitType
from core.rls import bypass_rls

User = get_user_model()

# Fənn 40 saatlıq, hədd 25% → 10 saat icazəli. 6 dərs × 2 saat = 12 saat qayıb,
# yəni 12 > 10 → CANLI qaydada tələbə imtahana buraxılmır.
LESSON_HOURS = 40
ABSENT_LESSONS = 6
ABSENCE_HOURS = ABSENT_LESSONS * 2

#: ``get_offering_journal``-ın MÖVCUD sətir-başına sorğu xərci
#: (``entry_score_for``: komponentlər + işarələr).  Bu işə aid deyil —
#: ayrıca düzəliş tələb edir; burada yalnız DONMA yoxlamasının ora
#: qarışmadığını kilidləyirik.
# 2026-09-02: ``finals_batch`` sətir-başına N+1-i sildi (PHASE24) — indi sətir xərci 0-dır.
_PRE_EXISTING_PER_ROW_QUERIES = 0

# Qayıb / bal dərslərinin başlanğıc tarixləri (flake8 B008: çağırış default-da olmasın).
_ABSENCE_BASE_DAY = datetime.date(2023, 10, 2)
_SCORE_BASE_DAY = datetime.date(2023, 11, 6)


def _seed_org(slug):
    """Bir tenant + proqram + kurikulum + qrup; ``(ctx)`` sözlüyü qaytarır."""
    owner = User.objects.create_user(f"{slug}_owner", f"{slug}_owner@qku.edu.az", "pw")
    with bypass_rls():
        org = Organization.objects.create(
            name=f"{slug} Univ",
            slug=slug,
            org_type=OrganizationType.UNIVERSITY,
            owner=owner,
            status="active",
            is_active=True,
        )
        faculty = OrgUnit.objects.create(
            organization=org, name="Fakültə", slug=f"{slug}-fac", unit_type=OrgUnitType.FACULTY
        )
        group = OrgUnit.objects.create(
            organization=org, name="QR-101", slug=f"{slug}-grp", unit_type=OrgUnitType.GROUP, parent=faculty
        )
        program = Program.objects.create(organization=org, code=f"{slug}-P", official_code="060501", name="Proqram")
        curriculum = Curriculum.objects.create(organization=org, program=program, admission_year=2022)
        subject = Subject.objects.create(organization=org, code=f"{slug}-S1", name="Fənn", ects=6)
        CurriculumSubject.objects.create(organization=org, curriculum=curriculum, subject=subject, semester_number=1)
        teacher = User.objects.create_user(f"{slug}_t", f"{slug}_t@qku.edu.az", "pw")
        Membership.objects.create(
            user=teacher, organization=org, role=org.roles.get(name="teacher"), is_primary=True, is_active=True
        )
    return {
        "org": org,
        "faculty": faculty,
        "group": group,
        "program": program,
        "curriculum": curriculum,
        "subject": subject,
        "teacher": teacher,
    }


def _seed_period(ctx, *, name, year, start, end, current=False):
    """Dövr yarat; ``current=True`` — siyahı əməliyyatlarına AÇIQ semestr.

    ⚠️ ``AcademicPeriod.is_current`` SAXLANMIŞ bayraqdır (tarixdən çıxarılmır) və
    defolt ``False``-dur.  ``guest_roster.period_allows_roster`` məhz onu oxuyur,
    yəni bayraq qoyulmasa alt qrup birləşməsi fikstürü «Bu semestr bağlıdır»
    ilə çökür (:class:`MergedGuestSurfacesAgree` ilk yazılışda buna düşmüşdü).
    Donma testləri isə bayraqsız qalır — onların semestri qəsdən keçmişdir.
    """
    with bypass_rls():
        return AcademicPeriod.objects.create(
            organization=ctx["org"],
            name=name,
            period_type=AcademicPeriodType.SEMESTER,
            academic_year=year,
            start_date=start,
            end_date=end,
            is_current=current,
        )


def _seed_student(ctx, username, period, *, group=None):
    """Tələbə + qeyd + yazılış; fənnə avtomatik yazılır.

    ``group`` verilə bilər: mandat yazılış HƏR qrup üçün ayrıca açılış yaradır,
    yəni ikinci qrupdakı tələbə eyni fənnin ÖZ jurnalını alır — alt qrup
    birləşməsi ssenarisinin ilkin şərti məhz budur.
    """
    with bypass_rls():
        student = User.objects.create_user(username, f"{username}@qku.edu.az", "pw")
        Membership.objects.create(
            user=student,
            organization=ctx["org"],
            role=ctx["org"].roles.get(name="student"),
            is_primary=True,
            is_active=True,
        )
        record = StudentAcademicRecord.objects.create(
            organization=ctx["org"],
            student=student,
            program=ctx["program"],
            curriculum=ctx["curriculum"],
            group=group or ctx["group"],
            admission_year=2022,
        )
        services.enroll_mandatory_subjects(record=record, period=period, semester_number=1)
    enrollment = Enrollment.objects.get(student=student, offering__period=period)
    return student, record, enrollment


def _make_absences(ctx, offering, enrollment, *, count=ABSENT_LESSONS, base_day=_ABSENCE_BASE_DAY):
    """Qayıb saatlarını REAL jurnal işarələri ilə yığır (denormalizə də dolur)."""
    with bypass_rls():
        for i in range(count):
            lesson = gradebook.create_lesson(
                allow_past=True,
                offering=offering,
                date=base_day + datetime.timedelta(days=i),
                kind=LessonKind.SEMINAR,
                hours=2,
            )
            gradebook.save_marks(
                enforce_day=False,
                offering=offering,
                entries=[{"lesson_id": lesson.id, "enrollment_id": enrollment.id, "status": "absent"}],
                by_user=ctx["teacher"],
            )


def _score_lessons(ctx, offering, enrollment, *, count=4, base_day=_SCORE_BASE_DAY):
    """Giriş balı yığır: iştirak edilmiş, qiymətlənmiş seminarlar (hər biri 10 bal).

    Qayıb ƏLAVƏ ETMİR — yalnız bu yazılışa işarə yazılır, buna görə digər
    tələbələrin qayıb saatı toxunulmaz qalır.
    """
    with bypass_rls():
        for i in range(count):
            lesson = gradebook.create_lesson(
                allow_past=True,
                offering=offering,
                date=base_day + datetime.timedelta(days=i),
                kind=LessonKind.SEMINAR,
                hours=2,
            )
            gradebook.save_marks(
                enforce_day=False,
                offering=offering,
                entries=[{"lesson_id": lesson.id, "enrollment_id": enrollment.id, "status": "present", "score": 10}],
                by_user=ctx["teacher"],
            )


def _stamp_migrated(ctx, offering):
    """Açılışa ``legacy_import`` köçürmə möhürü vurur (donma meyarının yarısı)."""
    from django.apps import apps as django_apps

    run_model = django_apps.get_model("legacy_import", "LegacyMigrationRun")
    map_model = django_apps.get_model("legacy_import", "LegacyEntityMap")
    with bypass_rls():
        # Scope başına YALNIZ BİR aktiv run ola bilər (``legacy_run_active_scope_uniq``);
        # eyni tenant-da ikinci möhür üçün mövcud RUNNING run yenidən işlədilir.
        run = run_model.objects.filter(
            organization=ctx["org"], source_system="myedu", status=run_model.Status.RUNNING
        ).first()
        if run is not None:
            map_model.objects.create(
                organization=ctx["org"],
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
            return run
        run = run_model.objects.create(
            organization=ctx["org"],
            source_system="myedu",
            snapshot_sha256="a" * 64,
            snapshot_size_bytes=1,
            schema_version="v1",
            transform_version="v1",
            mode=run_model.Mode.CUTOVER,
            # PG lifecycle guard-ları (legacy_import.0004) real köçürmə axınını
            # məcbur edir: run PRISTINE PENDING yaradılır, sonra RUNNING-ə keçir,
            # və canonical entity map yalnız RUNNING run altında yazıla bilər.
            # Testin özü də köçürmənin həqiqi izini qoyur, saxta sətir yox.
        )
        run.status = run_model.Status.RUNNING
        run.started_at = timezone.now()
        run.save(update_fields=["status", "started_at"])
        map_model.objects.create(
            organization=ctx["org"],
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
        return run


def _student_journal_detail(student, organization, enrollment):
    """``public.build_student_journal_context``-in DETAL bölməsi (tələbə ekranı).

    2-ci blokerin ikinci tərəfi məhz buradadır: eyni sətir üçün müəllim
    ekranından FƏRQLİ davamiyyət balı göstərilirdi.
    """
    request = RequestFactory().get(f"/?subject={enrollment.id}")
    request.user = student
    ctx = public.build_student_journal_context(request, organization=organization)
    return ctx["journal_student_section"]["detail"]


def _lock_journal(offering):
    """RİM-in jurnalı bağlaması (donma meyarının ikinci yarısı).

    ``journal_close.close_journals``-un yazdığı EYNİ iki sahə qoyulur:
    ``registrar_scheme_publish_state_valid`` CheckConstraint-i ``is_published``
    və ``approval_status``-un birlikdə dəyişməsini tələb edir (registrar.0040/0048).
    Servisin özü ``can_close_journals`` icazəsi istəyir; bu test buraxılış
    məntiqini yoxlayır, RBAC-ı yox — ona görə vəziyyət birbaşa qurulur.
    """
    with bypass_rls():
        scheme = gradebook.ensure_assessment_scheme(offering=offering)
        scheme.is_published = True
        scheme.approval_status = ApprovalStatus.APPROVED
        scheme.save(update_fields=["is_published", "approval_status"])
        return scheme


def _reopen_journal(offering):
    """RİM səhv bağlamanı geri alır (``journal_close.reopen_journals`` güzgüsü)."""
    with bypass_rls():
        scheme = gradebook.ensure_assessment_scheme(offering=offering)
        scheme.is_published = False
        scheme.approval_status = ApprovalStatus.DRAFT
        scheme.save(update_fields=["is_published", "approval_status"])
        return scheme


# ── 1) 706 KRİTİK HAL ────────────────────────────────────────────────────────


class FrozenSemesterShowsLegacyResult(TestCase):
    """Köhnə sistem imtahana BURAXIB → yeni sistem «kəsilir» GÖSTƏRMƏMƏLİDİR.

    Sübut bazasındakı 706 yazılışın modeli: qayıb 25% həddindən yuxarıdır
    (yeni qayda «buraxılmır» deyir), amma köhnə sistem imtahan balı yazıb —
    yəni tələbə həmin imtahana REAL girib.  Ölçülmüş bölgü: 452-si keçir
    (A qutusu), 266-sı kəsilir amma SƏBƏBİ dəyişir (B qutusu).
    """

    @classmethod
    def setUpTestData(cls):
        cls.ctx = _seed_org("frz")
        cls.period = _seed_period(
            cls.ctx, name="2023/2024 Payız", year="2023/2024", start="2023-09-15", end="2024-01-31"
        )
        # A qutusu: giriş 40 + imtahan 45 = 85 → keçir.
        cls.pass_student, cls.pass_record, cls.pass_enr = _seed_student(cls.ctx, "frz_pass", cls.period)
        # B qutusu: giriş 40 + imtahan 5 = 45 → kəsilir, amma q/b-dən yox.
        cls.fail_student, cls.fail_record, cls.fail_enr = _seed_student(cls.ctx, "frz_fail", cls.period)
        # C qutusu: heç bir imtahan balı yoxdur (6,188 hal).
        cls.void_student, cls.void_record, cls.void_enr = _seed_student(cls.ctx, "frz_void", cls.period)

        cls.offering = cls.pass_enr.offering
        with bypass_rls():
            cls.offering.lesson_hours = LESSON_HOURS
            cls.offering.instructor = cls.ctx["teacher"]
            cls.offering.save(update_fields=["lesson_hours", "instructor"])

        for enr in (cls.pass_enr, cls.fail_enr, cls.void_enr):
            _make_absences(cls.ctx, cls.offering, enr)

        # A qutusu tələbəsi giriş balı da toplayıb (4 × 10 = 40): köhnə sistemdə
        # imtahana girib və 45 alıb → 85 → KEÇİB. Yeni sistem bunu «Kəsilir · q/b»
        # göstərirdi; qərardan sonra göstərməməlidir.
        _score_lessons(cls.ctx, cls.offering, cls.pass_enr)
        with bypass_rls():
            finals.set_exam_score(enrollment=cls.pass_enr, score=45, by_user=cls.ctx["teacher"])
            finals.set_exam_score(enrollment=cls.fail_enr, score=5, by_user=cls.ctx["teacher"])

        # Köçürmə + bağlanma möhürləri MƏHZ BUNDAN SONRA vurulur: bal yazılışı
        # canlı semestrdə baş verib, sonra semestr bağlanıb.
        _stamp_migrated(cls.ctx, cls.offering)
        _lock_journal(cls.offering)

    def _fresh(self, enrollment):
        return Enrollment.objects.select_related("offering", "offering__subject").get(pk=enrollment.pk)

    def test_absence_really_exceeds_the_limit(self):
        """Sınağın özü mənalı olsun: qayıb HƏQİQƏTƏN həddi keçir."""
        enr = self._fresh(self.pass_enr)
        self.assertEqual(enr.absence_hours, ABSENCE_HOURS)
        self.assertGreater(ABSENCE_HOURS, LESSON_HOURS * 25 / 100)

    def test_offering_is_frozen(self):
        self.assertTrue(exam_eligibility.is_frozen(self._fresh(self.pass_enr).offering))

    def test_barred_is_never_raised_in_a_frozen_semester(self):
        elig = services.get_exam_eligibility(enrollment=self._fresh(self.pass_enr), limit_percent=25)
        self.assertFalse(elig["barred"])
        self.assertFalse(elig["over_limit"])
        self.assertTrue(elig["frozen"])
        self.assertEqual(elig["source"], exam_eligibility.SOURCE_LEGACY)

    def test_box_a_student_who_sat_the_exam_now_passes(self):
        """A qutusu (452 yazılış): «Kəsilir · q/b» → «Keçib»."""
        result = finals.compute_final_result(enrollment=self._fresh(self.pass_enr))
        self.assertFalse(result["barred"])
        self.assertTrue(result["graded"])
        self.assertTrue(result["passed"], f"gözlənilirdi keçsin, total={result['total']}")
        self.assertFalse(result["failed"])

    def test_box_b_student_still_fails_but_the_reason_changes(self):
        """B qutusu (266 yazılış): kəsr qalır, səbəb ``qb`` → ``exam25``.

        Fərq real hüquqdur: ``qb`` = fənni YENİDƏN keç; ``exam25`` = 25% ödənişlə
        bir dəfə təkrar imtahan.
        """
        result = finals.compute_final_result(enrollment=self._fresh(self.fail_enr))
        self.assertFalse(result["barred"])
        self.assertTrue(result["failed"])
        self.assertEqual(transcript._fail_reason_code(result), "exam25")

    def test_box_c_is_labelled_not_silently_blank(self):
        """C qutusu (6,188 yazılış): «nə keçib, nə kəsilib» GÖRÜNƏN etiket alır."""
        result = finals.compute_final_result(enrollment=self._fresh(self.void_enr))
        self.assertFalse(result["barred"])
        self.assertFalse(result["passed"])
        self.assertFalse(result["failed"])
        self.assertEqual(result["status_code"], exam_eligibility.STATUS_LEGACY_NO_RESULT)
        self.assertTrue(str(result["status_label"]))
        self.assertTrue(str(result["status_notice"]))

    def test_stored_values_are_untouched(self):
        """Qırmızı xətt: köhnə data DƏYİŞMİR — status yalnız oxu vaxtı həll olunur."""
        enr = self._fresh(self.pass_enr)
        self.assertEqual(enr.absence_hours, ABSENCE_HOURS)
        self.assertEqual(enr.offering.lesson_hours, LESSON_HOURS)
        grade = finals.FinalGrade.objects.get(enrollment=enr)
        self.assertEqual(grade.exam_score, Decimal("45"))
        # `barred` adlı saxlanmış sahə ÜMUMİYYƏTLƏ yaranmamalıdır.
        self.assertFalse(any(f.name == "barred" for f in Enrollment._meta.get_fields()))

    def test_reopening_the_journal_restores_live_computation(self):
        """RİM səhv bağlamanı geri alsa, canlı hesablama QAYIDIR (şüurlu qərar)."""
        _reopen_journal(self.offering)
        try:
            enr = self._fresh(self.pass_enr)
            self.assertFalse(exam_eligibility.is_frozen(enr.offering))
            self.assertTrue(services.get_exam_eligibility(enrollment=enr, limit_percent=25)["barred"])
        finally:
            _lock_journal(self.offering)


# ── 2) CANLI SEMESTRDƏ QAYDA İŞLƏYİR ─────────────────────────────────────────


class LiveSemesterStillComputes(TestCase):
    """Donma yalnız hər İKİ şərt ödənəndə baş verir.

    Üç canlı ssenari — hər biri sübut bazasında real olaraq mövcuddur:

    * möhür VAR, kilid YOX → canlı 2025/2026 Yay dilimi (10 açılış, 0 barred);
    * kilid VAR, möhür YOX → RİM gələcək semestri bağlayanda;
    * heç biri yoxdur → adi cari semestr.
    """

    @classmethod
    def setUpTestData(cls):
        cls.ctx = _seed_org("liv")
        cls.period = _seed_period(
            cls.ctx, name="2026/2027 Payız", year="2026/2027", start="2026-09-15", end="2027-01-31"
        )
        cls.student, cls.record, cls.enr = _seed_student(cls.ctx, "liv_s1", cls.period)
        cls.offering = cls.enr.offering
        with bypass_rls():
            cls.offering.lesson_hours = LESSON_HOURS
            cls.offering.instructor = cls.ctx["teacher"]
            cls.offering.save(update_fields=["lesson_hours", "instructor"])
        _make_absences(cls.ctx, cls.offering, cls.enr, base_day=datetime.date(2026, 10, 1))

    def _fresh(self):
        return Enrollment.objects.select_related("offering").get(pk=self.enr.pk)

    def _barred(self):
        return services.get_exam_eligibility(enrollment=self._fresh(), limit_percent=25)["barred"]

    def test_plain_live_semester_bars(self):
        self.assertTrue(self._barred())

    def test_migrated_but_journal_still_open_stays_live(self):
        """Canlı 2025/2026 Yay modeli: köçürülüb, amma jurnal hələ DRAFT."""
        _stamp_migrated(self.ctx, self.offering)
        self.assertFalse(exam_eligibility.is_frozen(self._fresh().offering))
        self.assertTrue(self._barred())

    def test_locked_but_not_migrated_stays_live(self):
        """RİM gələcək semestri bağlayır — yeni qayda ORAYA yayılmamalıdır."""
        _lock_journal(self.offering)
        self.assertFalse(exam_eligibility.is_frozen(self._fresh().offering))
        self.assertTrue(self._barred())

    def test_only_both_together_freeze(self):
        _stamp_migrated(self.ctx, self.offering)
        _lock_journal(self.offering)
        self.assertTrue(exam_eligibility.is_frozen(self._fresh().offering))
        self.assertFalse(self._barred())


# ── 3) ALTI ÇAĞIRIŞ NÖQTƏSİ EYNİ CAVABI VERİR ────────────────────────────────


def collect_surfaces(*, org, record, student, period, enrollment_id, semester_number=1):
    """DOKUZ səthin GÖRÜNƏN sahələri — ``{ad: {sahə: dəyər}}``.

    Modul səviyyəsindədir ki, eyni prob İKİ fikstür üzərində işlədilsin:
    adi (birləşməsiz) sətir və ALT QRUP BİRLƏŞMƏSİ ilə gələn qonaq sətir
    (bax :class:`MergedGuestSurfacesAgree`).  Birləşmə halı 9-cu səthin
    (tələbə kabinet jurnalı) qayıb saatını ÖZ işarələrindən yığmasını
    ifşa edən yeganə ssenaridir — mövcud fikstürdə birləşmə olmadığı üçün
    köhnə test onu tuta bilmirdi.
    ⚠️ Müqayisə YALNIZ ``barred``-ı yığmır — ekranda görünən BÜTÜN sahələri
    əhatə edir: davamiyyət balı, giriş balı, buraxılış, istisna, keçdi/kəsildi
    və kəsr səbəbi.  Köhnə (yalnız-``barred``) versiya məhz buna görə müəllim
    ``dav=None`` / tələbə ``dav=7.00`` fərqini TUTMAMIŞDI.
    """
    enr = Enrollment.objects.select_related("offering", "offering__subject").get(pk=enrollment_id)
    offering = enr.offering
    out = {}

    # 1) services.get_exam_eligibility (kanonik açar)
    elig = services.get_exam_eligibility(enrollment=enr, limit_percent=25, exempt=record.national_athlete_exemption)
    out["services"] = {"barred": elig["barred"], "dav": elig["attendance_score"], "exempt": elig["exempt"]}

    # 2) analytics._evaluate (riyaziyyat mühərriki)
    maps = analytics.build_evaluation_maps(org, [enr])
    res = analytics.evaluate_enrollment(enr, maps)
    out["analytics"] = {
        "barred": res["barred"],
        "dav": res["attendance_score"],
        "exempt": res["exempt"],
        "passed": res["passed"],
        "failed": res["failed"],
        "status_code": res["status_code"],
    }

    # 3) journal_extras.get_final_breakdown (müəllim «yekun bölgü» tabı)
    breakdown = journal_extras.get_final_breakdown(offering)
    row = next(r for r in breakdown["rows"] if r["enrollment"].id == enr.id)
    out["journal_extras"] = {
        "barred": row["barred"],
        "dav": row["dav"],
        "exempt": row["eligibility"]["exempt"],
        "entry": row["entry"],
    }

    # 4) page_contexts._student_offering_stats (cədvəl modalı)
    stats = page_contexts._student_offering_stats(student, org, record, period)
    st = stats[offering.id]
    out["page_contexts"] = {
        "barred": st["barred"],
        "dav": st["attendance_score"],
        "exempt": st["eligibility"]["exempt"],
        "entry": st["entry_score"],
    }

    # 5) gradebook.get_offering_journal (müəllim jurnal qridi)
    grid = gradebook.get_offering_journal(offering=offering)
    grow = next(r for r in grid["rows"] if r["enrollment"].id == enr.id)
    out["journal_grid"] = {
        "barred": grow["barred"],
        "dav": grow["eligibility"]["attendance_score"],
        "exempt": grow["eligibility"]["exempt"],
        "entry": grow["entry_score"],
    }

    # 6) gradebook.get_student_journal_summary (tələbə kabinet jurnalı)
    summary = gradebook.get_student_journal_summary(record=record, period=period, semester_number=semester_number)
    srow = next(s for s in summary["subjects"] if s["enrollment"].id == enr.id)["journal"]
    out["cabinet_summary"] = {
        "barred": srow["barred"],
        "dav": srow["eligibility"]["attendance_score"],
        "exempt": srow["eligibility"]["exempt"],
        "entry": srow["entry_score"],
    }

    # 7) finals.compute_final_result (yekun qiymət mühərriki)
    fin = finals.compute_final_result(enrollment=enr)
    out["finals"] = {
        "barred": fin["barred"],
        "dav": fin["attendance_score"],
        "exempt": fin["exempt"],
        "entry": fin["entry_score"],
        "passed": fin["passed"],
        "failed": fin["failed"],
        "status_code": fin["status_code"],
    }

    # 8) public.build_student_journal_context (tələbənin öz jurnal ekranı) —
    #    2-ci blokerin ikinci tərəfi.
    ctx = _student_journal_detail(student, org, enr)
    out["student_journal"] = {
        "barred": ctx["dav_barred"],
        "dav": ctx["dav_score"],
        "entry": ctx["entry_score"],
    }

    # 9) exam_bridge.exam_eligibility — İMTAHAN GİRİŞ QAPISI.
    #    Bu, digər səkkizi kimi sadəcə etiket göstərmir: ``barred`` olduqda
    #    imtahana start BLOKLANIR (exams.journal_sync.registrar_block_reason).
    #    Qapı ``exempt``-i ötürmədiyi müddətdə idmançı-tələbə kabinetdə
    #    «buraxılır» görüb imtahan düyməsində dayandırılırdı.
    gate = exam_bridge.exam_eligibility(student=student, subject_id=offering.subject_id, organization=org)
    out["exam_gate"] = {"barred": gate["barred"]}
    return out


class CallSitesAgree(TestCase):
    """Altı səth eyni yazılış üçün EYNİ ``barred`` cavabını verməlidir.

    2026-08-31 auditinin əsas tapıntısı: eyni müqayisə altı yerdə təkrarlanırdı
    və məxrəc üç fərqli yerdən götürüldüyü üçün nəticələr bir-birini təkzib
    edirdi.  Bu test həmin dağınıqlığın geri qayıtmasını dayandırır.
    """

    @classmethod
    def setUpTestData(cls):
        cls.ctx = _seed_org("agr")
        cls.period = _seed_period(cls.ctx, name="2023/2024 Yaz", year="2023/2024", start="2024-02-01", end="2024-06-30")
        cls.student, cls.record, cls.enr = _seed_student(cls.ctx, "agr_s1", cls.period)
        cls.offering = cls.enr.offering
        with bypass_rls():
            cls.offering.lesson_hours = LESSON_HOURS
            cls.offering.instructor = cls.ctx["teacher"]
            cls.offering.save(update_fields=["lesson_hours", "instructor"])
        _make_absences(cls.ctx, cls.offering, cls.enr, base_day=datetime.date(2024, 3, 4))

    def _surfaces(self):
        """Bu fikstürün səth probu (ortaq :func:`collect_surfaces`)."""
        return collect_surfaces(
            org=self.ctx["org"],
            record=self.record,
            student=self.student,
            period=self.period,
            enrollment_id=self.enr.pk,
        )

    def _assert_agree(self, surfaces, field, expected):
        """Sahəni bildirən BÜTÜN səthlər eyni dəyəri verməlidir."""
        got = {name: data[field] for name, data in surfaces.items() if field in data}
        self.assertGreaterEqual(len(got), 2, f"«{field}» yalnız bir səthdə var — müqayisə mənasızdır")
        self.assertEqual(set(got.values()), {expected}, f"«{field}» səthlər arasında fərqləndi: {got}")

    def test_all_surfaces_agree_while_live(self):
        surfaces = self._surfaces()
        self._assert_agree(surfaces, "barred", True)
        # Buraxılmayan tələbədə davamiyyət balı GÖSTƏRİLMİR — hər səthdə eyni.
        self._assert_agree(surfaces, "dav", None)
        self._assert_agree(surfaces, "exempt", False)
        self._assert_agree(surfaces, "entry", surfaces["journal_extras"]["entry"])

    def test_all_surfaces_agree_once_frozen(self):
        _stamp_migrated(self.ctx, self.offering)
        _lock_journal(self.offering)
        surfaces = self._surfaces()
        self._assert_agree(surfaces, "barred", False)
        self._assert_agree(surfaces, "exempt", False)
        self._assert_agree(surfaces, "entry", surfaces["journal_extras"]["entry"])

    def test_frozen_attendance_score_is_identical_on_every_screen(self):
        """2-ci BLOKER: müəllim ``dav=None``, tələbə ``dav=7.00`` görürdü.

        Səbəb: tələbə tərəfi donmuş halda ``attendance_score(..., exempt=True)``
        ilə balı YENİDƏN oxuyurdu, müəllim tərəfi isə köhnə çağırışı saxlamışdı
        və 25% keçildiyi üçün ``None`` alırdı.  İndi bal resolver-dən gəlir.
        """
        _stamp_migrated(self.ctx, self.offering)
        _lock_journal(self.offering)
        surfaces = self._surfaces()
        # 40 saat, 12 saat qayıb → 10 × (1 − 12/40) = 7.00 (aşağı yuvarlanmış).
        self._assert_agree(surfaces, "dav", Decimal("7.00"))
        self.assertEqual(surfaces["journal_extras"]["dav"], surfaces["student_journal"]["dav"])

    def test_the_denominator_is_the_offering_not_the_students_own_marks(self):
        """2-ci BLOKERİN ikinci yarısı: MƏXRƏC də tək mənbədən gəlməlidir.

        Tələbə tərəfi məxrəci öz işarələrindən yığırdı
        (``sum(m.lesson.hours for m in marks)``) — işarəsi olmayan dərs məxrəcə
        düşmürdü, yəni eyni sətir müəllim ekranında başqa bal verirdi.  Burada
        açılışın ``lesson_hours``-u sıfırlanır ki, fallback yolu işə düşsün, və
        tələbənin İŞARƏSİ OLMAYAN bir dərs əlavə olunur.
        """
        with bypass_rls():
            self.offering.lesson_hours = 0
            self.offering.save(update_fields=["lesson_hours"])
            # Bu tələbənin işarəsi OLMAYAN əlavə dərs (2 saat).
            gradebook.create_lesson(
                allow_past=True,
                offering=self.offering,
                date=datetime.date(2024, 5, 20),
                kind=LessonKind.SEMINAR,
                hours=2,
            )
        _stamp_migrated(self.ctx, self.offering)
        _lock_journal(self.offering)
        surfaces = self._surfaces()
        # Açılışın bütün dərsləri: 6 × 2 (qayıb) + 2 (işarəsiz) = 14 saat.
        # 10 × (1 − 12/14) = 1.4285… → 1.42 (ROUND_DOWN).  Köhnə tələbə yolu
        # məxrəci 12 sayıb 0.00 verirdi.
        self._assert_agree(surfaces, "dav", Decimal("1.42"))

    def test_athlete_exemption_reaches_every_surface(self):
        """3-cü BLOKER: istisna kabinetdə «buraxılır», analitikada «kəsilib» idi.

        ``analytics._evaluate`` ``exempt``-i QƏSDƏN ötürmürdü; ``services``
        ötürürdü.  İndi istisna resolver-dən keçir və hər səth eyni cavabı alır.
        CANLI semestrdə yoxlanılır — donma onu onsuz da örtərdi.
        """
        with bypass_rls():
            self.record.national_athlete_exemption = True
            self.record.save(update_fields=["national_athlete_exemption"])
        try:
            surfaces = self._surfaces()
            self._assert_agree(surfaces, "barred", False)
            self._assert_agree(surfaces, "exempt", True)
            # İstisna qayıb SAATINI silmir — bal real qayıba görə hesablanır.
            self._assert_agree(surfaces, "dav", Decimal("7.00"))
            # Kəsr səbəbi də dəyişir: «q/b» deyil (imtahan yoxdur → qeyri-müəyyən).
            self.assertNotEqual(surfaces["finals"]["status_code"], "")
            self.assertFalse(surfaces["analytics"]["failed"])
            self.assertFalse(surfaces["finals"]["failed"])
            # ⚠️ Ən bahalı səth: qapı istisnanı görməsə tələbə imtahana
            # BURAXILMIR (ekran etiketi deyil, real blok).
            gate = exam_bridge.exam_eligibility(
                student=self.student, subject_id=self.offering.subject_id, organization=self.ctx["org"]
            )
            self.assertTrue(gate["linked"])
            self.assertFalse(gate["barred"], "imtahan giriş qapısı idmançı istisnasını hələ də görmür")
            self.assertEqual(gate["reason"], "")
        finally:
            with bypass_rls():
                self.record.national_athlete_exemption = False
                self.record.save(update_fields=["national_athlete_exemption"])

    def test_the_cabinet_and_the_analytics_engine_no_longer_split(self):
        """3-cü blokerin ilkin probu: ``cabinet_barred`` vs ``analytics_barred``."""
        with bypass_rls():
            self.record.national_athlete_exemption = True
            self.record.save(update_fields=["national_athlete_exemption"])
        try:
            cabinet = services.get_student_cabinet_data(record=self.record, period=self.period, semester_number=1)
            cabinet_barred = next(
                s["eligibility"]["barred"] for s in cabinet["subjects"] if s["enrollment"].id == self.enr.id
            )
            enr = Enrollment.objects.select_related("offering", "offering__subject").get(pk=self.enr.pk)
            maps = analytics.build_evaluation_maps(self.ctx["org"], [enr])
            res = analytics.evaluate_enrollment(enr, maps)
            self.assertFalse(cabinet_barred)
            self.assertFalse(res["barred"], "analitika hələ də istisnanı görmür")
            self.assertFalse(res["failed"], "istisna qoyulmuş tələbə analitikada «kəsilir» qalıb")
        finally:
            with bypass_rls():
                self.record.national_athlete_exemption = False
                self.record.save(update_fields=["national_athlete_exemption"])

    def test_frozen_semester_hides_the_warning_band_too(self):
        """«Həddə yaxınlaşır» xəbərdarlığı da susur — qərar verilə bilməyən yerdə
        xəbərdarlıq mənasızdır."""
        _stamp_migrated(self.ctx, self.offering)
        _lock_journal(self.offering)
        grid = gradebook.get_offering_journal(offering=self.offering)
        row = next(r for r in grid["rows"] if r["enrollment"].id == self.enr.id)
        self.assertFalse(row["barred"])
        self.assertFalse(row["warning"])


# ── 3b) ALT QRUP BİRLƏŞMƏSİ: EYNİ RAZILIQ QONAQ SƏTİRDƏ DƏ ──────────────────

#: Birləşmə səbəbi (audit izi boş qala bilməz).
MERGE_REASON = "Dekanlıq sərəncamı №101 — alt qrup birləşməsi"

#: Mənbə jurnalda qazanılmış giriş balı: 2 qiymətli seminar × 10 bal.
SOURCE_SCORED_LESSONS = 2
SOURCE_ENTRY_SCORE = 20


class MergedGuestSurfacesAgree(TestCase):
    """Birləşdirilmiş QONAQ sətrində də doqquz səth eyni cavabı verməlidir.

    ⚠️ NİYƏ AYRICA FİKSTÜR.  :class:`CallSitesAgree` adi (birləşməsiz) sətri
    yoxlayır və məhz buna görə 9-cu səthin qüsurunu TUTA BİLMİRDİ:
    ``gradebook.get_student_journal_summary`` qayıb saatını tələbənin ÖZ
    işarələrindən yığırdı, birləşmə olmayan fikstürdə isə «öz işarələr» ilə
    ``Enrollment.absence_hours`` onsuz da eyni rəqəmdir — iki fərqli tərif üst-
    üstə düşür və fərq görünmür.

    Alt qrup birləşməsi onları AYIRIR: hədəf jurnalda tələbənin hələ heç bir
    işarəsi yoxdur, amma ``Enrollment.absence_hours`` mənbə jurnaldan köçürülmüş
    saatı daşıyır.  Ölçülmüş köhnə vəziyyət: səkkiz səth «6 saat · barred»,
    tələbə kabineti isə «0 saat · buraxılır · dav 10.00» — yəni tələbə
    «buraxılıram» görürdü, ``exam_bridge`` isə onu imtahandan BLOKLAYIRDI.
    """

    @classmethod
    def setUpTestData(cls):
        cls.ctx = _seed_org("mgd")
        # Birləşmə CANLI semestrdə baş verir — `add_guest_student` bağlı dövrdə
        # siyahını dəyişməyə icazə vermir (`guest_roster.assert_roster_open`).
        cls.period = _seed_period(
            cls.ctx, name="2025/2026 Payız", year="2025/2026", start="2025-09-01", end="2026-01-31", current=True
        )
        with bypass_rls():
            cls.group2 = OrgUnit.objects.create(
                organization=cls.ctx["org"],
                name="QR-102",
                slug="mgd-grp2",
                unit_type=OrgUnitType.GROUP,
                parent=cls.ctx["faculty"],
            )
            cls.coordinator = User.objects.create_user("mgd_coord", "mgd_coord@qku.edu.az", "pw")
            Membership.objects.create(
                user=cls.coordinator,
                organization=cls.ctx["org"],
                role=cls.ctx["org"].roles.get(name="program_coordinator"),
                scope_unit=cls.ctx["faculty"],
                is_primary=True,
                is_active=True,
            )
        # Hədəf jurnal QR-101-indir (ev sahibi tələbə onu yaradır).
        cls.host, _, host_enrollment = _seed_student(cls.ctx, "mgd_host", cls.period)
        cls.offering = host_enrollment.offering
        # Qonaq QR-102-dədir və ÖZ jurnalında iz qoyur: qayıb DA, bal DA.
        cls.student, cls.record, cls.source_enr = _seed_student(cls.ctx, "mgd_guest", cls.period, group=cls.group2)
        cls.source_offering = cls.source_enr.offering
        with bypass_rls():
            for offering in (cls.offering, cls.source_offering):
                offering.lesson_hours = LESSON_HOURS
                offering.instructor = cls.ctx["teacher"]
                offering.save(update_fields=["lesson_hours", "instructor"])
        _make_absences(cls.ctx, cls.source_offering, cls.source_enr, base_day=datetime.date(2025, 10, 6))
        _score_lessons(
            cls.ctx,
            cls.source_offering,
            cls.source_enr,
            count=SOURCE_SCORED_LESSONS,
            base_day=datetime.date(2025, 11, 10),
        )
        with bypass_rls():
            cls.target_enr = guest_roster.add_guest_student(
                offering=cls.offering,
                student=cls.student,
                by_user=cls.coordinator,
                source_group=cls.group2,
                reason=MERGE_REASON,
                release_source=True,
            )

    def _surfaces(self):
        return collect_surfaces(
            org=self.ctx["org"],
            record=self.record,
            student=self.student,
            period=self.period,
            enrollment_id=self.target_enr.pk,
        )

    def test_the_merge_moved_the_hours_but_left_no_marks_behind(self):
        """Fikstürün öz ilkin şərti: sayğac 12, hədəf jurnalda işarə 0.

        Bu iddia sınmasa, aşağıdakı razılıq testləri qüsuru heç vaxt görməzdi —
        «öz işarələr» ilə denormallaşmış sayğac yenidən üst-üstə düşərdi.
        """
        target = Enrollment.objects.get(pk=self.target_enr.pk)
        self.source_enr.refresh_from_db()
        self.assertEqual(target.absence_hours, ABSENCE_HOURS)
        self.assertEqual(LessonMark.objects.filter(enrollment=target).count(), 0)
        self.assertEqual(self.source_enr.status, Enrollment.Status.DROPPED)
        self.assertEqual(self.source_enr.superseded_by_id, target.pk)

    def test_every_surface_agrees_on_the_carried_hours(self):
        """9-CU SƏTH: tələbə kabineti də köçürülmüş saatı görməlidir.

        Ölçülmüş köhnə fərq: ``cabinet_summary`` ``barred=False``/``dav=10.00``,
        qalan səkkiz səth ``barred=True``/``dav=None``.
        """
        surfaces = self._surfaces()
        self._assert_agree(surfaces, "barred", True)
        self._assert_agree(surfaces, "dav", None)
        self._assert_agree(surfaces, "entry", Decimal("0"))

    def test_the_cabinet_summary_reports_the_denormalised_counter(self):
        """Səbəbin özü: kabinet xülasəsi ``Enrollment.absence_hours``-u oxuyur."""
        summary = gradebook.get_student_journal_summary(record=self.record, period=self.period, semester_number=1)
        row = next(s for s in summary["subjects"] if s["enrollment"].id == self.target_enr.pk)["journal"]
        self.assertEqual(row["absence_hours"], ABSENCE_HOURS)
        self.assertTrue(row["barred"])

    def test_the_student_page_no_longer_contradicts_itself(self):
        """``public`` EYNİ səhifədə iki rəqəm göstərirdi: kart 0 saat, detal 12.

        ⚠️ Müqayisə ``detail["journal"]`` ilə APARILMIR: o, kartın öz sözlüyünün
        EYNİ obyektidir (``section["subjects"]`` da, ``detail["journal"]`` da
        bir ``get_student_journal_summary`` çağırışından gəlir), yəni belə bir
        iddia həmişə doğrudur və heç nə qorumur.  Detal panelinin MÜSTƏQİL
        hesablanan tərəfi ``dav_score``/``dav_barred``-dır: onlar birbaşa
        ``enrollment.absence_hours``-dan çıxır (``public`` ~382-ci sətir).
        Ziddiyyət məhz orada görünürdü — kart öz işarələrindən 0 saat yığıb
        «buraxılır», panel isə sayğacdan 12 saat oxuyub «buraxılmır» deyirdi.
        """
        request = RequestFactory().get(f"/?subject={self.target_enr.pk}")
        request.user = self.student
        section = public.build_student_journal_context(request, organization=self.ctx["org"])["journal_student_section"]
        card = next(s for s in section["subjects"] if s["enrollment"].id == self.target_enr.pk)["journal"]
        detail = section["detail"]
        # Kartın saatı denormallaşmış sayğacdan gəlir (öz işarələri hələ 0-dır).
        self.assertEqual(card["absence_hours"], ABSENCE_HOURS)
        self.assertEqual(Enrollment.objects.get(pk=self.target_enr.pk).absence_hours, card["absence_hours"])
        # Panelin müstəqil qərarı kartla eynidir — səhifə özünü təkzib etmir.
        self.assertEqual(card["barred"], detail["dav_barred"])
        self.assertEqual(card["eligibility"]["attendance_score"], detail["dav_score"])

    def test_the_exam_gate_and_the_cabinet_now_tell_the_same_story(self):
        """Ən bahalı ziddiyyət: ekran «buraxılır», qapı isə imtahanı BLOKLAYIR."""
        summary = gradebook.get_student_journal_summary(record=self.record, period=self.period, semester_number=1)
        cabinet_barred = next(s for s in summary["subjects"] if s["enrollment"].id == self.target_enr.pk)["journal"][
            "barred"
        ]
        gate = exam_bridge.exam_eligibility(
            student=self.student, subject_id=self.offering.subject_id, organization=self.ctx["org"]
        )
        self.assertTrue(gate["linked"])
        self.assertEqual(cabinet_barred, gate["barred"])

    def test_the_carried_entry_score_is_shown_not_silently_dropped(self):
        """BAL ASİMMETRİYASI: ziyan köçürülür, xeyir isə görünməli idi.

        Bal KÖÇÜRÜLMÜR (uydurma xana yaranardı) — amma mənbə jurnalda
        qazanılmış rəqəm hədəf sətrin xülasəsində GÖRÜNMƏLİDİR, əks halda
        müəllim əvvəlki jurnalda nə qazanıldığını heç yerdən öyrənə bilmir.
        """
        summary = guest_merge.carry_over_map([self.target_enr.pk])[self.target_enr.pk]
        self.assertEqual(summary["absence_hours"], ABSENCE_HOURS)
        self.assertEqual(summary["entry_score"], SOURCE_ENTRY_SCORE)
        self.assertEqual(summary["entry_score_max"], 50)
        # Hədəf sətrin ÖZ giriş balı toxunulmazdır — bal köçürülmür, göstərilir.
        self.assertEqual(gradebook.entry_score_for(self.target_enr, 50), Decimal("0"))

    def test_the_grid_row_carries_the_previous_entry_score(self):
        """Müəllim qridi: sətir həm q/b, həm də əvvəlki balı daşıyır."""
        grid = gradebook.get_offering_journal(offering=self.offering)
        row = next(r for r in grid["rows"] if r["enrollment"].id == self.target_enr.pk)
        self.assertEqual(row["own_absence_hours"], 0)
        self.assertEqual(row["absence_hours"], ABSENCE_HOURS)
        self.assertEqual(row["carry_over"]["entry_score"], SOURCE_ENTRY_SCORE)
        self.assertEqual(row["carry_over"]["groups"], ["QR-102"])

    def test_the_hot_recompute_path_does_not_pay_for_the_score(self):
        """``carried_absence_hours`` HƏR işarə yazılışında çağırılır — bal oxumur."""
        target = Enrollment.objects.get(pk=self.target_enr.pk)
        with CaptureQueriesContext(connection) as ctx:
            hours = guest_merge.carried_absence_hours(target)
        self.assertEqual(hours, ABSENCE_HOURS)
        # Yalnız iki sorğu: əvəzlənmiş qeydiyyatlar + onların işarələri.
        self.assertEqual(len(ctx.captured_queries), 2, [q["sql"] for q in ctx.captured_queries])

    _assert_agree = CallSitesAgree._assert_agree


# ── 4) SƏRHƏD HALLARI ────────────────────────────────────────────────────────


class FrozenEdgeCases(TestCase):
    """Sərhəd halları — hər biri ölçmə mərhələsinin qərarına uyğun."""

    @classmethod
    def setUpTestData(cls):
        cls.ctx = _seed_org("edg")
        cls.period = _seed_period(cls.ctx, name="2022/2023 Yaz", year="2022/2023", start="2023-02-01", end="2023-06-30")
        # İmtahan balı SIFIR — «buraxılıb, gəlməyib» (33 hal).
        cls.zero_student, cls.zero_record, cls.zero_enr = _seed_student(cls.ctx, "edg_zero", cls.period)
        # Heç bir sübut sətri yoxdur (6,156 hal).
        cls.void_student, cls.void_record, cls.void_enr = _seed_student(cls.ctx, "edg_void", cls.period)
        cls.offering = cls.zero_enr.offering
        with bypass_rls():
            cls.offering.lesson_hours = LESSON_HOURS
            cls.offering.instructor = cls.ctx["teacher"]
            cls.offering.save(update_fields=["lesson_hours", "instructor"])
        for enr in (cls.zero_enr, cls.void_enr):
            _make_absences(cls.ctx, cls.offering, enr, base_day=datetime.date(2023, 3, 6))
        with bypass_rls():
            finals.set_exam_score(enrollment=cls.zero_enr, score=0, by_user=cls.ctx["teacher"])
        _stamp_migrated(cls.ctx, cls.offering)
        _lock_journal(cls.offering)

    def _fresh(self, enrollment):
        return Enrollment.objects.select_related("offering", "offering__subject").get(pk=enrollment.pk)

    def test_exam_score_zero_counts_as_sat_the_exam(self):
        """Bal ``0`` = «buraxılıb, amma gəlməyib/sıfır alıb» — «buraxılmayıb» DEYİL.

        Köhnə sistemdə ``yekun`` sətrinin ÖZÜ yaranıb; buraxılmamanın izi sətrin
        ümumiyyətlə olmamasıdır, içindəki sıfır deyil.  Ona görə ``graded=True``
        qalır və sətir normal kəsr yolundan (``exam25``) keçir.
        """
        result = finals.compute_final_result(enrollment=self._fresh(self.zero_enr))
        self.assertTrue(result["graded"])
        self.assertFalse(result["barred"])
        self.assertTrue(result["failed"])
        self.assertEqual(result["status_code"], exam_eligibility.STATUS_LEGACY)
        self.assertEqual(transcript._fail_reason_code(result), "exam25")

    def test_no_evidence_row_is_neither_pass_nor_fail(self):
        """Sübutun YOXLUĞU «buraxılmayıb» sübutu deyil — üç səbəbi ayırd etmək
        mümkün deyil (buraxılmayıb / nəticə yazılmayıb / fənni tərk edib)."""
        result = finals.compute_final_result(enrollment=self._fresh(self.void_enr))
        self.assertFalse(result["graded"])
        self.assertFalse(result["passed"])
        self.assertFalse(result["failed"])
        self.assertEqual(result["status_code"], exam_eligibility.STATUS_LEGACY_NO_RESULT)

    def test_zero_denominator_never_bars_in_a_frozen_semester(self):
        """``lesson_hours=0`` (25,314 hal): donmuş dilimdə qərar VERİLMİR.

        Dərs sətirləri qalıbsa saat cəmi məxrəci bərpa edir — amma bu, YALNIZ
        davamiyyət balının miqyasıdır.  Buraxılış qərarı donmuş dilimdə heç
        vaxt verilmir, ona görə «2,176 qərar fərqlənir» riski oyanmır (bax
        :func:`exam_eligibility.lesson_hours_for`, 2-ci qayda).
        """
        with bypass_rls():
            self.offering.lesson_hours = 0
            self.offering.save(update_fields=["lesson_hours"])
        try:
            elig = services.get_exam_eligibility(enrollment=self._fresh(self.zero_enr), limit_percent=25)
            self.assertFalse(elig["barred"])
            self.assertFalse(elig["over_limit"])
            # Miqyas bərpa olunub → bal göstərilir; qərar isə YOXDUR.
            self.assertTrue(elig["hours_known"])
            self.assertIsNotNone(elig["attendance_score"])
        finally:
            with bypass_rls():
                self.offering.lesson_hours = LESSON_HOURS
                self.offering.save(update_fields=["lesson_hours"])

    def test_no_hours_and_no_lessons_announces_the_gap(self):
        """Nə ``lesson_hours``, nə dərs sətri — məxrəc HEÇ CÜR bərpa olunmur.

        Bu halda nə qərar verilir, nə də süni «10.00 tam davamiyyət» balı
        göstərilir: boşluq ``hours_known=False`` ilə AÇIQ bildirilir.
        """
        elig = exam_eligibility.resolve(absence_hours=12, lesson_hours=0, limit_percent=25)
        self.assertFalse(elig["barred"])
        self.assertFalse(elig["hours_known"])
        self.assertIsNone(elig["attendance_score"])
        self.assertEqual(elig["notice"], exam_eligibility.UNKNOWN_HOURS_NOTICE)


class ResolverPureUnits(TestCase):
    """Resolver-in özü — DB-siz, sırf düstur davranışı."""

    def test_live_rule_is_strict_greater_than(self):
        """Tam 25% hələ buraxılır; bir saat çox artıq buraxılmır."""
        exactly = exam_eligibility.resolve(absence_hours=10, lesson_hours=40, limit_percent=25)
        over = exam_eligibility.resolve(absence_hours=11, lesson_hours=40, limit_percent=25)
        self.assertFalse(exactly["barred"])
        self.assertTrue(over["barred"])

    def test_frozen_suppresses_both_barred_and_over_limit(self):
        frozen = exam_eligibility.resolve(absence_hours=39, lesson_hours=40, limit_percent=25, frozen=True)
        self.assertFalse(frozen["barred"])
        self.assertFalse(frozen["over_limit"])
        self.assertEqual(frozen["source"], exam_eligibility.SOURCE_LEGACY)
        self.assertIsNotNone(frozen["notice"])
        self.assertIsNotNone(frozen["frozen_badge"])

    def test_frozen_keeps_the_display_scale(self):
        """``allowed_hours`` qərar deyil, davamiyyət zolağının miqyasıdır —
        donmuş rejimdə də hesablanır ki, UI zolağı çökməsin."""
        frozen = exam_eligibility.resolve(absence_hours=39, lesson_hours=40, limit_percent=25, frozen=True)
        self.assertEqual(frozen["allowed_hours"], Decimal(10))

    def test_zero_denominator_never_bars(self):
        for frozen in (False, True):
            res = exam_eligibility.resolve(absence_hours=148, lesson_hours=0, limit_percent=25, frozen=frozen)
            self.assertFalse(res["barred"], f"frozen={frozen}")
            self.assertFalse(res["hours_known"], f"frozen={frozen}")

    def test_unknown_hours_are_announced_not_silently_cleared(self):
        """Canlı semestrdə məxrəcsizlik konfiqurasiya xətasıdır — susmamalıdır."""
        res = exam_eligibility.resolve(absence_hours=148, lesson_hours=0, limit_percent=25)
        self.assertIsNotNone(res["notice"])

    def test_athlete_exemption_lifts_the_bar_but_keeps_the_hours(self):
        res = exam_eligibility.resolve(absence_hours=30, lesson_hours=40, limit_percent=25, exempt=True)
        self.assertFalse(res["barred"])
        self.assertTrue(res["over_limit"])
        self.assertEqual(res["absence_hours"], 30)

    def test_completed_resit_lifts_the_bar(self):
        res = exam_eligibility.resolve(absence_hours=30, lesson_hours=40, limit_percent=25, resit_done=True)
        self.assertFalse(res["barred"])
        self.assertTrue(res["over_limit"])

    def test_precomputed_allowed_hours_wins(self):
        """Çağıranın məxrəci olduğu kimi qəbul edilir (canlı davranış dəyişmir)."""
        res = exam_eligibility.resolve(absence_hours=12, allowed_hours=Decimal("20"), limit_percent=25)
        self.assertFalse(res["barred"])
        self.assertEqual(res["allowed_hours"], Decimal("20"))

    def test_status_code_distinguishes_the_three_worlds(self):
        live = exam_eligibility.resolve(absence_hours=1, lesson_hours=40)
        frozen = exam_eligibility.resolve(absence_hours=1, lesson_hours=40, frozen=True)
        self.assertEqual(exam_eligibility.status_code(live, graded=True), exam_eligibility.STATUS_LIVE)
        self.assertEqual(exam_eligibility.status_code(frozen, graded=True), exam_eligibility.STATUS_LEGACY)
        self.assertEqual(exam_eligibility.status_code(frozen, graded=False), exam_eligibility.STATUS_LEGACY_NO_RESULT)

    def test_unsaved_offering_is_never_frozen_and_never_queries(self):
        from types import SimpleNamespace

        with self.assertNumQueries(0):
            self.assertFalse(exam_eligibility.is_frozen(SimpleNamespace(lesson_hours=40)))
            self.assertFalse(exam_eligibility.is_frozen(None))


# ── 5) SORĞU BÜDCƏSİ ─────────────────────────────────────────────────────────


class FrozenLookupIsBatched(TestCase):
    """Donma yoxlaması İSTİ YOLLARDA sabit sorğu sayı ilə işləməlidir.

    Meyar per-enrollment ``LegacyEntityMap`` sorğusu ilə qurulsaydı, jurnal
    qridi hər SƏTİR üçün bir sorğu edərdi (fəlakət).  Ona görə primitiv
    açılış-səviyyəli və TOPLUdur; bu test onun belə qalmasını kilidləyir.
    """

    @classmethod
    def setUpTestData(cls):
        cls.ctx = _seed_org("btc")
        cls.period = _seed_period(
            cls.ctx, name="2022/2023 Payız", year="2022/2023", start="2022-09-15", end="2023-01-31"
        )
        cls.enrollments = []
        for i in range(5):
            _student, _record, enr = _seed_student(cls.ctx, f"btc_s{i}", cls.period)
            cls.enrollments.append(enr)
        cls.offering = cls.enrollments[0].offering
        with bypass_rls():
            cls.offering.lesson_hours = LESSON_HOURS
            cls.offering.instructor = cls.ctx["teacher"]
            cls.offering.save(update_fields=["lesson_hours", "instructor"])
        # Müqayisə üçün TƏK yazılışlı ikinci açılış (eyni dövr, ayrı fənn).
        with bypass_rls():
            solo_subject = Subject.objects.create(organization=cls.ctx["org"], code="btc-S2", name="Tək fənn", ects=6)
            CurriculumSubject.objects.create(
                organization=cls.ctx["org"],
                curriculum=cls.ctx["curriculum"],
                subject=solo_subject,
                semester_number=2,
            )
        _solo_student, solo_record, cls.solo_enr = _seed_student(cls.ctx, "btc_solo", cls.period)
        with bypass_rls():
            services.enroll_mandatory_subjects(record=solo_record, period=cls.period, semester_number=2)
        cls.solo_offering = Enrollment.objects.get(student=solo_record.student, offering__subject=solo_subject).offering
        with bypass_rls():
            cls.solo_offering.lesson_hours = LESSON_HOURS
            cls.solo_offering.save(update_fields=["lesson_hours"])

        for offering in (cls.offering, cls.solo_offering):
            _stamp_migrated(cls.ctx, offering)
            _lock_journal(offering)

    def test_batch_lookup_is_two_queries_regardless_of_size(self):
        """Bir açılış da, beş açılış da EYNİ iki sorğu (kilid + köçürmə möhürü)."""
        ids = [self.offering.id]
        with self.assertNumQueries(2):
            exam_eligibility.frozen_offering_ids(ids)
        many = ids * 5
        with self.assertNumQueries(2):
            exam_eligibility.frozen_offering_ids(many)

    def test_accepts_a_values_queryset_without_materialising_it(self):
        """``analytics.build_evaluation_maps_for`` id-ləri QUERYSET kimi ötürür.

        Universitet miqyaslı icmalda giriş ``qs.values("id")``-dir ki, Django
        ``IN (SELECT …)`` alt-sorğusu yazsın.  Bu qat onu siyahıya çevirməyə
        çalışsa, ``dict`` elementləri üzərində ``TypeError: unhashable type``
        alınır — regressiya məhz belə baş vermişdi.
        """
        qs = CourseOffering.objects.filter(pk=self.offering.pk).values("id")
        self.assertEqual(exam_eligibility.frozen_offering_ids(qs), frozenset({self.offering.id}))

        empty_qs = CourseOffering.objects.none().values("id")
        self.assertEqual(exam_eligibility.frozen_offering_ids(empty_qs), frozenset())

    def test_migrated_lookup_is_bounded_by_the_locked_set(self):
        """Kilidli açılış yoxdursa köçürmə möhürü ÜMUMİYYƏTLƏ sorğulanmır."""
        with bypass_rls():
            open_offering = CourseOffering.objects.create(
                organization=self.ctx["org"],
                subject=self.ctx["subject"],
                period=_seed_period(self.ctx, name="Açıq", year="2027/2028", start="2027-09-15", end="2028-01-31"),
                group=self.ctx["group"],
            )
        with self.assertNumQueries(1):
            self.assertEqual(exam_eligibility.frozen_offering_ids([open_offering.id]), frozenset())

    def test_empty_input_hits_no_database(self):
        with self.assertNumQueries(0):
            self.assertEqual(exam_eligibility.frozen_offering_ids([]), frozenset())
            self.assertEqual(exam_eligibility.frozen_offering_ids([None]), frozenset())

    def test_is_frozen_memoises_per_instance(self):
        """Eyni obyekt üzərində təkrar yoxlama ƏLAVƏ sorğu etmir."""
        offering = self.enrollments[0].offering
        with self.assertNumQueries(2):
            self.assertTrue(exam_eligibility.is_frozen(offering))
        with self.assertNumQueries(0):
            self.assertTrue(exam_eligibility.is_frozen(offering))

    def test_journal_grid_frozen_lookup_does_not_scale_with_rows(self):
        """Donma yoxlaması sətir sayından ASILI DEYİL.

        Testin ölçdüyü şey DELTA-dır: 1 sətirli və 5 sətirli açılış arasındakı
        sorğu fərqi sətir başına ``_PRE_EXISTING_PER_ROW_QUERIES`` (2026-09-02-dən
        0 — ``finals_batch`` yazılış-başına N+1-i sildi) olmalıdır.  Donma
        sətir başına yoxlansaydı delta hər sətir üçün BİR SORĞU daha böyük olardı.
        """
        with bypass_rls():
            gradebook.get_offering_journal(offering=self.offering)
            gradebook.get_offering_journal(offering=self.solo_offering)

            with CaptureQueriesContext(connection) as many:
                grid_many = gradebook.get_offering_journal(offering=self.offering)
            with CaptureQueriesContext(connection) as one:
                grid_one = gradebook.get_offering_journal(offering=self.solo_offering)

        extra_rows = len(grid_many["rows"]) - len(grid_one["rows"])
        self.assertEqual(len(grid_one["rows"]), 1)
        self.assertGreaterEqual(extra_rows, 4, "müqayisə üçün çox sətirli açılış lazımdır")
        self.assertTrue(all(r["eligibility"]["frozen"] for r in grid_many["rows"]))

        per_row = (len(many) - len(one)) / extra_rows
        self.assertEqual(
            per_row,
            _PRE_EXISTING_PER_ROW_QUERIES,
            f"sətir başına sorğu {per_row} oldu (gözlənilən {_PRE_EXISTING_PER_ROW_QUERIES}) — "
            "donma yoxlaması sətir başına düşüb?",
        )


# ── 5) ÜOMG DÜRÜSTLÜYÜ (2026-08-31 düşmən baxışı, 1-ci bloker) ──────────────


class UomgIsNeverAFakeZero(TestCase):
    """«C qutusu» tələbəsində ÜOMG **0.00 GÖSTƏRİLMİR**.

    Köhnə sistemin nəticə YAZMADIĞI sətirlər (6,188) nə keçmiş, nə kəsilmiş
    sayılır → ÜOMG məxrəcinə düşmür.  231 tələbənin ÜOMG-daşıyan BÜTÜN sətirləri
    belədir; onlarda ``gpa_credits == 0`` olur və köhnə kod ``Decimal("0.00")``
    qaytarırdı.  Rəsmi transkriptdə bu «tələbə sıfır bal aldı» kimi oxunur —
    tələbənin ziyanına yanlış fakt.  İndi hər aqreqat səthi «hesablana bilmir»
    deyir.
    """

    @classmethod
    def setUpTestData(cls):
        cls.ctx = _seed_org("uom")
        cls.period = _seed_period(cls.ctx, name="2021/2022 Yaz", year="2021/2022", start="2022-02-01", end="2022-06-30")
        # C qutusu: köhnə sistemdə HEÇ BİR nəticə yoxdur.
        cls.void_student, cls.void_record, cls.void_enr = _seed_student(cls.ctx, "uom_void", cls.period)
        # Nəzarət: eyni semestrdə imtahana girmiş tələbə (qəti nəticə var).
        cls.ok_student, cls.ok_record, cls.ok_enr = _seed_student(cls.ctx, "uom_ok", cls.period)
        cls.offering = cls.void_enr.offering
        with bypass_rls():
            cls.offering.lesson_hours = LESSON_HOURS
            cls.offering.instructor = cls.ctx["teacher"]
            cls.offering.save(update_fields=["lesson_hours", "instructor"])
        for enr in (cls.void_enr, cls.ok_enr):
            _make_absences(cls.ctx, cls.offering, enr, base_day=datetime.date(2022, 3, 7))
        with bypass_rls():
            finals.set_exam_score(enrollment=cls.ok_enr, score=40, by_user=cls.ctx["teacher"])
        _stamp_migrated(cls.ctx, cls.offering)
        _lock_journal(cls.offering)

    def test_transcript_reports_unavailable_not_zero(self):
        data = transcript.build_student_transcript(student=self.void_student, organization=self.ctx["org"])
        self.assertTrue(data["has_record"])
        self.assertIsNone(data["cumulative_gpa"], "ÜOMG hesablana bilmirsə dəyər OLMAMALIDIR")
        self.assertFalse(data["cumulative_gpa_available"])
        self.assertEqual(data["total_credits_gpa"], 0)
        # Semestr və il səviyyəsində də eyni dürüstlük.
        self.assertFalse(data["semesters"][0]["uomg_available"])
        self.assertIsNone(data["semesters"][0]["gpa"])
        self.assertFalse(data["years"][0]["uomg_available"])

    def test_a_student_with_a_definite_result_still_gets_a_number(self):
        """Düzəliş ÜOMG-ni hamıya söndürmür — yalnız məxrəci olmayanlara."""
        data = transcript.build_student_transcript(student=self.ok_student, organization=self.ctx["org"])
        self.assertTrue(data["cumulative_gpa_available"])
        self.assertIsNotNone(data["cumulative_gpa"])
        self.assertGreater(data["cumulative_gpa"], Decimal("0"))

    def test_zero_is_still_zero_when_it_is_a_real_zero(self):
        """Həqiqi sıfır BASTIRILMIR: qəti nəticəsi olub 0 bal alan tələbədə
        ÜOMG ``0.00``-dır və ``available`` qalır — «məlumat yoxdur» ilə
        qarışdırılmır."""
        value, available = exam_eligibility.uomg_from(Decimal("0"), 6)
        self.assertTrue(available)
        self.assertEqual(value, Decimal("0.00"))

    def test_overall_academic_section_reports_unavailable(self):
        data = transcript.build_student_overall_record(student=self.void_student, organization=self.ctx["org"])
        self.assertTrue(data["has_record"])
        self.assertIsNone(data["overall_uomg"])
        self.assertFalse(data["overall_uomg_available"])
        self.assertEqual(str(data["overall_uomg_label"]), str(exam_eligibility.UOMG_UNAVAILABLE_LABEL))

    def test_analytics_dashboard_reports_unavailable(self):
        data = analytics.build_period_analytics(organization=self.ctx["org"], period=self.period)
        # Nəzarət tələbəsi qəti nəticəlidir → ümumi qutu hesablana bilir.
        self.assertTrue(data["totals"]["avg_gpa_available"])
        # Yalnız C-qutusu tələbəsi olan bir kəsimdə isə hesablana bilmir.
        bucket = analytics._Bucket("k", "")
        result = {
            "barred": False,
            "graded": False,
            "passed": False,
            "failed": False,
            "total": Decimal("0"),
            "credit": 6,
            "absence_hours": 12,
            "lesson_hours": 40,
        }
        bucket.add(self.void_student.id, result)
        summary = bucket.summary()
        self.assertIsNone(summary["avg_gpa"])
        self.assertFalse(summary["avg_gpa_available"])

    def test_staff_records_table_leaves_the_cell_empty(self):
        """Əməkdaş cədvəlində ÜOMG xanası BOŞ gedir (JS "—" göstərir)."""
        from apps.accounts import academic_records as records

        empty = records._public_summary(records._empty_summary())
        self.assertEqual(empty["avg_gpa"], "")
        self.assertFalse(empty["avg_gpa_available"])

    def test_transcript_pdf_prints_the_label_not_a_zero(self):
        """Rəsmi PDF-də ``0.00`` ÇAP OLUNMUR."""
        from apps.registrar import transcript_pdf

        self.assertEqual(transcript_pdf._uomg_text(None), str(exam_eligibility.UOMG_UNAVAILABLE_LABEL))
        self.assertEqual(transcript_pdf._uomg_text(Decimal("72.50")), "72.50")

    def test_credits_earned_are_unaffected(self):
        """Dürüstlük düzəlişi KREDİTLƏRƏ toxunmur — yalnız göstəricinin adına."""
        data = transcript.build_student_transcript(student=self.void_student, organization=self.ctx["org"])
        self.assertEqual(data["total_credits_earned"], 0)
        ok = transcript.build_student_transcript(student=self.ok_student, organization=self.ctx["org"])
        self.assertEqual(ok["total_credits_earned"], 0 if not ok["semesters"][0]["rows"][0]["result"]["passed"] else 6)
