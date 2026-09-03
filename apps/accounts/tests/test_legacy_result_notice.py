"""Köçürülmüş nəticənin OXUNAN qeydi — tələbənin iki səthində.

Sual bir dənədir: «köhnə sistemdən köçürülmüş bala baxan tələbə onun dəqiq
olmaya biləcəyini və İmtahan Mərkəzinə müraciət etməli olduğunu MƏTNDƏ görürmü?»

Tooltip yoxlanmır — tooltip-i mobil istifadəçi ümumiyyətlə görmür.  Testlər
render olunmuş HTML-də cümlənin ÖZÜNÜ axtarır, ona görə şablondan ``{% include %}``
silinsə dərhal çökür (mutasiya ilə yoxlanılıb).

Hallar kilidlənir:
  (a) köçürülmüş + qəti nəticə var          → «bu nəticə … dəqiq olmaya bilər»
  (b) köçürülmüş + nəticə yox, MƏNBƏDƏ bal var → «köhnə sistemdə bal var, keçməyib»
      (KOR NÖQTƏ: əvvəl burada qeyd susurdu və rəqəm yalnız tooltip-də idi)
      Mənbə balının ÜÇ formasının HƏR BİRİ ayrıca fikstürdədir — yekun (b1),
      YALNIZ imtahan (b2), YALNIZ təkrar imtahan (b3).  Səbəb ölçüldü: mapping-i
      olan 144,582 faktın cəmi 10.5 %-i yekun bal daşıyır, 85.8 %-i YALNIZ
      imtahan balıdır.  Tək «hamısı dolu» fikstür ``_has_source_result``-un
      ``or`` budaqlarını yoxlamırdı və tək ``raw_final``-a endirən mutasiya
      42 testin hamısından sağ çıxırdı (real datanın ~90 %-i səssizcə susardı).
  (c) köçürülmüş + nə nəticə, nə mənbə balı → qeyd YOX (dəqiqləşdiriləsi heç nə)
  (c2) köçürülmüş + YALNIZ giriş balı       → qeyd YOX (giriş «nəticə» deyil)
  (d) yeni sistemdə yazılmış nəticə         → nə qeyd, nə qlif

MİQYAS da kilidlənir: cədvəl səthində cümlə SEMESTR blokunda bir dəfə çıxır,
sətir-sətir yox (əks halda real tələbədə 45 eyni paraqraf olur), kartda isə
kart başına bir dəfə.

Qırmızı «İmtahan Mərkəzi ilə dəqiqləşdirilsin» qeydi sahibin tələbinə
görə bütün legacy ballarda daimi qalır. Review statusu ayrıdır: VERIFIED
uzun gözləmə qeydini söndürür, amma balın legacy qeydini söndürmür.
"""

import datetime
import pathlib
import re

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit
from apps.registrar import finals, gradebook, services
from apps.registrar.legacy_grade_read import (
    LEGACY_BADGE_LABEL,
    LEGACY_EXAM_CENTER_WARNING,
    LEGACY_RESULT_CHECK_NOTICE,
    LEGACY_SEMESTER_CHECK_NOTICE,
    LEGACY_SEMESTER_MISSING_NOTICE,
    LEGACY_SOURCE_ONLY_NOTICE,
    LEGACY_SOURCE_ONLY_STATUS,
)
from apps.registrar.models import (
    Curriculum,
    CurriculumSubject,
    LegacyGradeFact,
    LegacyGradeReview,
    LessonKind,
    Program,
    StudentAcademicRecord,
    Subject,
)
from core.constants import AcademicPeriodType, OrganizationType, OrgUnitType
from core.rls import bypass_rls

User = get_user_model()

NOTICE = str(LEGACY_RESULT_CHECK_NOTICE)
SOURCE_ONLY = str(LEGACY_SOURCE_ONLY_NOTICE)
SEMESTER_CHECK = str(LEGACY_SEMESTER_CHECK_NOTICE)
SEMESTER_MISSING = str(LEGACY_SEMESTER_MISSING_NOTICE)
SOURCE_ONLY_STATUS = str(LEGACY_SOURCE_ONLY_STATUS)


@override_settings(UNIVERSITY_MODE=True)
class LegacyResultNoticeTest(TestCase):
    """Bir tələbə, üç fənn — üç halın hamısı EYNİ ekranda yan-yana."""

    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("lrn_owner", "lrn_owner@qku.edu.az", "pw")
        with bypass_rls():
            cls.org = Organization.objects.create(
                name="LRN Univ",
                slug="lrn-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=cls.owner,
                status="active",
                is_active=True,
            )
            cls.period = AcademicPeriod.objects.create(
                organization=cls.org,
                name="2023/2024 Payız",
                period_type=AcademicPeriodType.SEMESTER,
                academic_year="2023/2024",
                start_date="2023-09-01",
                end_date="2024-01-31",
                is_current=True,
            )
            cls.chair = OrgUnit.objects.create(
                organization=cls.org, name="Kafedra", slug="lrn-chair", unit_type=OrgUnitType.CHAIR
            )
            cls.group = OrgUnit.objects.create(
                organization=cls.org, name="LRN-1", slug="lrn-g1", unit_type=OrgUnitType.GROUP, parent=cls.chair
            )
            cls.teacher = User.objects.create_user("lrn_teacher", "lrn_teacher@qku.edu.az", "pw")
            cls.student = User.objects.create_user("lrn_student", "lrn_student@qku.edu.az", "pw")
            for user, role in ((cls.teacher, "teacher"), (cls.student, "student")):
                Membership.objects.create(
                    user=user,
                    organization=cls.org,
                    role=cls.org.roles.get(name=role),
                    is_primary=True,
                    is_active=True,
                )

            # (a) nəticəli · (b) nəticəsiz, mənbədə bal VAR · (c) nəticəsiz, mənbə də boş · (d) yeni sistem
            cls.migrated_done = Subject.objects.create(organization=cls.org, code="LRN101", name="Riyaziyyat", ects=6)
            cls.migrated_open = Subject.objects.create(organization=cls.org, code="LRN102", name="Fizika", ects=5)
            cls.native_done = Subject.objects.create(organization=cls.org, code="LRN103", name="Kimya", ects=4)
            cls.migrated_blank = Subject.objects.create(organization=cls.org, code="LRN104", name="Tarix", ects=3)
            # (b2)/(b3) Mənbə balının qalan İKİ forması — real datanın böyük
            # hissəsi məhz buradadır (yalnız imtahan 85.8 %, yalnız təkrar
            # imtahan 3.7 %), ona görə hər budaq AYRI sətirdə yoxlanır.
            cls.migrated_exam_only = Subject.objects.create(
                organization=cls.org, code="LRN105", name="Biologiya", ects=4
            )
            cls.migrated_resit_only = Subject.objects.create(
                organization=cls.org, code="LRN106", name="Coğrafiya", ects=4
            )
            # (c2) YALNIZ giriş balı: giriş davamiyyət/kollokvium toplusudur,
            # «nəticə» deyil — qeyd susmalıdır.  Bu sətir ``_has_source_result``-u
            # ƏKS istiqamətdən kilidləyir (``raw_entry`` əlavə edən mutasiya çökür).
            cls.migrated_entry_only = Subject.objects.create(
                organization=cls.org, code="LRN107", name="Fəlsəfə", ects=2
            )
            # (b1) YALNIZ yekun bal.  LRN102 yekun daşıyır, amma imtahan balı da
            # daşıyır, ona görə orada ``raw_final`` budağı ``raw_exam``
            # tərəfindən KÖLGƏLƏNİR: məhz ``raw_final``-ı atan mutasiya sağ qalır.
            # Bu sətir onu təcrid edir.  ⚠️ Canlı datada YALNIZ yekun bal daşıyan
            # fakt bu gün YOXDUR (mapping-li 149,443 faktdan 0), yəni real risk
            # sıfırdır — sətir qaydanı, gələcək datanı deyil, KODU qoruyur.
            cls.migrated_final_only = Subject.objects.create(
                organization=cls.org, code="LRN108", name="Astronomiya", ects=3
            )

            program = Program.objects.create(
                organization=cls.org, code="LRNP", name="İxtisas", specialty_unit=cls.chair
            )
            curriculum = Curriculum.objects.create(organization=cls.org, program=program, admission_year=2023)
            for subject in (
                cls.migrated_done,
                cls.migrated_open,
                cls.native_done,
                cls.migrated_blank,
                cls.migrated_exam_only,
                cls.migrated_resit_only,
                cls.migrated_entry_only,
                cls.migrated_final_only,
            ):
                CurriculumSubject.objects.create(
                    organization=cls.org, curriculum=curriculum, subject=subject, semester_number=1
                )
            record = StudentAcademicRecord.objects.create(
                organization=cls.org,
                student=cls.student,
                program=program,
                curriculum=curriculum,
                group=cls.group,
                admission_year=2023,
            )
            services.enroll_mandatory_subjects(record=record, period=cls.period, semester_number=1)

            # Nəticəli iki fənn.  «Fizika» QƏSDƏN toxunulmamış qalır — semestri
            # davam edən köçürülmüş sətir məhz (b) halıdır.
            cls._grade(cls.migrated_done, datetime.date(2023, 10, 2), exam_score=45)
            cls._grade(cls.native_done, datetime.date(2023, 10, 9), exam_score=40)

            cls._fact(cls.migrated_done, source_pk=9001, entry="40", exam="45", final="85")
            cls._fact(cls.migrated_open, source_pk=9002, entry="40", exam="45", final="85")
            # (c) Sübut sətri var, amma HEÇ BİR bal daşımır — dəqiqləşdiriləsi
            # nəticə də, mənbə balı da yoxdur, ona görə qeyd susmalıdır.
            cls._fact(cls.migrated_blank, source_pk=9003)
            # (b2) YALNIZ imtahan balı — köçürülmüş faktların 85.8 %-i belədir.
            cls._fact(cls.migrated_exam_only, source_pk=9004, exam="52")
            # (b3) YALNIZ təkrar imtahan balı.
            cls._fact(cls.migrated_resit_only, source_pk=9005, resit="37")
            # (c2) YALNIZ giriş balı — nəticə ölçüsü deyil.
            cls._fact(cls.migrated_entry_only, source_pk=9006, entry="41")
            # (b1) YALNIZ yekun bal — ``raw_final`` budağını təcrid edir.
            cls._fact(cls.migrated_final_only, source_pk=9007, final="78")

    # ── Fikstur köməkçiləri ─────────────────────────────────────────────────

    @classmethod
    def _grade(cls, subject, first_lesson_day, *, exam_score):
        enrollment = cls.student.enrollments.get(offering__subject=subject)
        offering = enrollment.offering
        offering.instructor = cls.teacher
        offering.save(update_fields=["instructor"])
        for offset in range(4):
            lesson = gradebook.create_lesson(
                allow_past=True,
                offering=offering,
                date=first_lesson_day + datetime.timedelta(days=offset),
                kind=LessonKind.SEMINAR,
            )
            gradebook.save_marks(
                enforce_day=False,
                offering=offering,
                entries=[{"lesson_id": lesson.id, "enrollment_id": enrollment.id, "status": "present", "score": 10}],
                by_user=cls.teacher,
            )
        finals.set_exam_score(enrollment=enrollment, score=exam_score, by_user=cls.teacher)

    @classmethod
    def _fact(cls, subject, *, source_pk, entry="", exam="", resit="", final=""):
        """Bir sübut sətri — HƏR bal sahəsi AYRICA verilir.

        ⚠️ Sahələr qəsdən defolt BOŞDUR.  Əvvəlki fikstür bütün balları bir
        yerdə doldururdu, ona görə ``_has_source_result``-un ``or`` budaqları
        heç vaxt tək-tək işə düşmürdü: onu tək ``raw_final``-a endirən mutasiya
        42 testin hamısından sağ çıxırdı, halbuki real faktların yalnız 10.5 %-i
        yekun bal daşıyır.
        """
        enrollment = cls.student.enrollments.get(offering__subject=subject)
        with bypass_rls():
            return LegacyGradeFact.objects.create(
                organization=cls.org,
                enrollment=enrollment,
                source_system="myedu_mariadb",
                source_table="yekun",
                source_pk=source_pk,
                source_snapshot_sha256="a" * 64,
                source_row_hash=f"{source_pk:064x}",
                materialization_digest=f"{source_pk + 500:064x}",
                transform_version="rehearsal-v1",
                evidence_kind="summary",
                score_code="yekun",
                mapping_status="linked",
                source_enrollment_ref=f"jrn{source_pk:07d}:{source_pk}",
                entry_score_text=entry,
                exam_score_text=exam,
                resit_score_text=resit,
                final_score_text=final,
            )

    def _get(self, section):
        client = Client()
        client.force_login(self.student)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        return client.get(reverse("accounts:profile"), {"section": section})

    @staticmethod
    def _transcript_open():
        """Transkript səthini müvəqqəti AÇIR.

        ``STUDENT_TRANSCRIPT_SELF_SERVICE`` sahibin qərarı ilə bağlıdır
        (transkript ərizə pəncərəsindən verilir), ona görə bölmə RBAC-da
        siyahıya düşmür.  Şablon isə mövcuddur və bayraq açılan gün dərhal
        canlıya çıxacaq — qeydin ORADA da danışdığı indidən kilidlənir, əks
        halda səth yenidən susan vəziyyətdə açılardı.
        """
        from unittest import mock

        from apps.registrar import public as registrar_public

        return mock.patch.object(registrar_public, "STUDENT_TRANSCRIPT_SELF_SERVICE", True)

    # ── «Nəticələrim» (kart səthi) ──────────────────────────────────────────

    def test_my_results_shows_the_notice_on_the_migrated_result(self):
        resp = self._get("my-results")
        self.assertEqual(resp.status_code, 200)
        # (a) BİR dəfə — hər xanada yox: yalnız nəticəli köçürülmüş fənnin kartında.
        self.assertContains(resp, NOTICE, count=1)

    def test_my_results_speaks_when_the_source_has_a_score_but_the_screen_has_none(self):
        """KOR NÖQTƏ: ekranda nəticə yoxdur, sübutda bal var → qeyd DANIŞMALIDIR.

        Bu, «İmtahan Mərkəzinə müraciət et» deməyin ƏN ÇOX lazım olduğu haldır:
        əvvəl qeyd susurdu və mənbədəki bal yalnız qlif tooltip-ində görünürdü —
        mobil istifadəçinin ümumiyyətlə aça bilmədiyi yerdə.
        """
        resp = self._get("my-results")
        # Bu səth SƏHİFƏLƏNİR (səhifədə 6 kart), ona görə say birinci səhifəyə
        # düşən kor-nöqtə sətirlərinindir: LRN102, LRN105, LRN106.
        # ⚠️ ``raw_final`` budağını təcrid edən LRN108 ikinci səhifədədir —
        # onu səhifədən ASILI OLMAYAN
        # ``test_every_source_score_shape_opens_the_blind_spot_notice`` qoruyur
        # (o, qeydi səhifədən yox, birbaşa akademik qeyddən oxuyur).
        self.assertContains(resp, SOURCE_ONLY, count=3)

    def test_every_source_score_shape_opens_the_blind_spot_notice(self):
        """``_has_source_result``-un ÜÇ budağı da AYRICA yoxlanır.

        Miqyas: mapping-i olan 144,582 faktın 15,215-i (10.5 %) yekun bal
        daşıyır, 124,021-i (85.8 %) YALNIZ imtahan balı, 5,346-sı yalnız təkrar
        imtahan balıdır.  Yəni ``raw_exam``/``raw_resit`` budaqları real datanın
        ~90 %-ni daşıyır; onlar ayrıca kilidlənməsə bir sözlük reqressiya
        (``raw_final or raw_exam or raw_resit`` → ``raw_final``) qeydi həmin
        sətirlərdə SƏSSİZCƏ söndürərdi.  Ölçülüb: köhnə fikstürdə həmin mutasiya
        42 testin hamısından sağ çıxırdı.
        """
        from apps.registrar import transcript

        with bypass_rls():
            record = transcript.build_student_overall_record(student=self.student, organization=self.org)
        rows = {row["subject"].code: row for sem in record["semesters"] for row in sem["rows"]}

        for code, field in (("LRN108", "raw_final"), ("LRN105", "raw_exam"), ("LRN106", "raw_resit")):
            with self.subTest(code=code, field=field):
                mark = rows[code]["legacy"]
                self.assertTrue(mark[field], f"fikstür {field} budağını daşımır")
                self.assertTrue(
                    mark["source_only"],
                    f"{field} mənbə balı kor nöqtə sayılmır — qeyd bu sətirdə susardı",
                )
                self.assertTrue(mark["show_result_notice"])

        # Digər iki budaq bu sətirlərdə BOŞDUR — yəni test həqiqətən tək-tək
        # budağı ölçür, «hamısı dolu» fikstürün kölgəsində qalmır.
        self.assertEqual((rows["LRN105"]["legacy"]["raw_final"], rows["LRN105"]["legacy"]["raw_resit"]), ("", ""))
        self.assertEqual((rows["LRN106"]["legacy"]["raw_final"], rows["LRN106"]["legacy"]["raw_exam"]), ("", ""))

    def test_my_results_never_calls_a_missing_result_migrated(self):
        """İki cümlə QARIŞMIR: nəticəsi olmayan sətirdə «bu nəticə köçürülüb» yalandır."""
        html = self._get("my-results").content.decode()
        source_only_card = html[html.index("LRN102") : html.index("LRN103")]
        self.assertIn(SOURCE_ONLY, source_only_card)
        self.assertNotIn(NOTICE, source_only_card)

    def test_my_results_notice_names_origin_doubt_and_next_step(self):
        """Mətn üç şeyi deməlidir; biri düşsə tələbə nə edəcəyini bilməz."""
        resp = self._get("my-results")
        html = resp.content.decode()
        self.assertIn("köhnə sistemdən", html)
        self.assertIn("dəqiq olmaya bilər", html)
        self.assertIn("İmtahan Mərkəzinə müraciət", html)

    def test_my_results_notice_is_one_per_card_not_one_per_score_cell(self):
        """Sıxlıq: kartda dörd bal xanası var, qeyd BİR dəfədir."""
        html = self._get("my-results").content.decode()
        migrated_card = html[html.index("LRN101") : html.index("LRN102")]
        self.assertEqual(migrated_card.count("legacy-notice__text"), 1)
        self.assertGreater(migrated_card.count("result-academic-cell"), 1)

    def test_my_results_actually_loads_the_academic_stylesheet(self):
        """Sübut panelinin RƏNGİ yalnız fayl YÜKLƏNİRSƏ mənalıdır.

        ``my_results_academic.css`` yarandığı gündən (5086a02e) heç bir
        şablondan linklənməmişdi — 40 selektorun heç biri başqa CSS-də də
        yoxdur, yəni bütün `.result-academic-*` / `.result-legacy-*` markup-ı
        canlıda ÜSLUBSUZ render olunurdu.  Brauzerdə təsdiqləndi: panelin fonu
        `rgba(0,0,0,0)`, `--ems-danger-strong` xəbərdarlığı isə qara idi.

        Bu, 3-cü maddəni GÖRÜNMƏZ edirdi: «panel qırmızıdır → boz olsun»
        düzəlişi yüklənməyən faylda heç nəyi dəyişmirdi.  Rəng testləri faylın
        MƏTNİNİ oxuyur, ona görə onlar da bu boşluğu tuta bilmirdi — link
        ayrıca kilidlənir.
        """
        html = self._get("my-results").content.decode()
        self.assertIn(
            "my_results_academic.css",
            html,
            "«Nəticələrim» akademik kartının CSS-i yüklənmir — panelin rəngi ekranda tətbiq olunmur",
        )

    # ── «Ümumi tədris məlumatı» (cədvəl səthi) ──────────────────────────────

    def test_overall_academic_says_the_sentence_once_per_semester_not_once_per_row(self):
        """SIXLIQ qərarı kilidlənir.

        Brauzerdə A/B ölçülüb — hər iki variant EYNİ kod bazasından render
        olunub (1280 px, AZ, real köçürülmüş tələbə myedu.student.3373: 49 sətir, 8 semestr,
        46-sı nişanlı):

            A cari (semestr qeydi + qlif): sətir median  96.7 px,
              cədvəl 4,768 px, səhifə 6,452 px, cümlə  8 dəfə
            B rədd edilən (sətir qeydi):   sətir median 152.2 px,
              cədvəl 7,376 px, səhifə 8,716 px, cümlə 44 dəfə

        B tipik sətri +57 %, səhifəni +35 % şişirdirdi və eyni cümləni 44 dəfə
        təkrarlayırdı.  Tələbə mətni yenə EKRANDA oxuyur — tooltip-də deyil.
        """
        resp = self._get("overall-academic")
        self.assertEqual(resp.status_code, 200)
        # Fikstürdə bir semestr var → hər cümlə ən çoxu BİR dəfə.
        self.assertContains(resp, SEMESTER_CHECK, count=1)
        self.assertContains(resp, SEMESTER_MISSING, count=1)
        # Sətir-səviyyəli (tək nəticə) cümlələr cədvəldə HEÇ çıxmır.
        self.assertNotContains(resp, NOTICE)
        self.assertNotContains(resp, SOURCE_ONLY)

    def test_overall_academic_marks_every_migrated_row(self):
        """Semestr qeydi «nişanlı» deyir — nişan HƏR köçürülmüş sətirdə olmalıdır.

        Altı köçürülmüş sətir var (LRN101/102/104/105/106/107), yeni sistemin
        sətri (LRN103) nişansız qalır.  Nişan itsə, semestr qeydi hansı sətirdən
        danışdığını göstərə bilməzdi.
        """
        resp = self._get("overall-academic")
        self.assertContains(resp, '<span class="legacy-mark', count=7)

    def test_overall_academic_status_does_not_contradict_the_evidence(self):
        """Sübutda bal olan sətir «nəticə yazılmayıb» deməməlidir.

        Bu, kor nöqtənin ikinci üzüdür: status xanası tooltip-i təkzib edirdi
        (tooltip «Mənbədəki yekun bal: 85» yazarkən status «yazılmayıb» deyirdi).
        Fikstürdə semestr canlıdır, ona görə statusun özü «Davam edir»-dir;
        etiketin mətni isə ``legacy_grade_read``-də TƏK yerdə tərif olunur.
        """
        from apps.registrar import transcript

        with bypass_rls():
            record = transcript.build_student_overall_record(student=self.student, organization=self.org)
        rows = {row["subject"].code: row for sem in record["semesters"] for row in sem["rows"]}
        self.assertEqual(str(rows["LRN102"]["legacy"]["status_label"]), SOURCE_ONLY_STATUS)
        self.assertEqual(rows["LRN101"]["legacy"]["status_label"], "")

    # ── Görünmə qaydası ─────────────────────────────────────────────────────

    def test_row_without_a_result_and_without_a_source_score_gets_no_notice(self):
        """(c) Nə nəticə, nə mənbə balı → qeyd BOŞ xəbərdarlıq olardı."""
        from apps.registrar import transcript

        with bypass_rls():
            record = transcript.build_student_overall_record(student=self.student, organization=self.org)
        rows = {row["subject"].code: row for sem in record["semesters"] for row in sem["rows"]}

        blank_row = rows["LRN104"]
        self.assertIsNotNone(blank_row["legacy"], "köçürülmüş sətir nişanını itirməməlidir")
        self.assertFalse(blank_row["result"]["passed"] or blank_row["result"]["failed"])
        self.assertFalse(blank_row["legacy"]["show_result_notice"])

        # (c2) YALNIZ giriş balı da qeyd AÇMIR: giriş davamiyyət/kollokvium
        # toplusudur, köhnə sistemin «nəticə» ölçüsü deyil.  Bu, mənfi tərəfdən
        # kilidləyir — ``raw_entry``-ni ``_has_source_result``-a əlavə edən
        # mutasiya burada çökür.
        entry_only_row = rows["LRN107"]
        self.assertEqual(entry_only_row["legacy"]["raw_entry"], "41")
        self.assertFalse(entry_only_row["legacy"]["show_result_notice"])
        self.assertFalse(entry_only_row["legacy"]["source_only"])

        # (b) Eyni «nəticəsiz» sətir, amma mənbədə bal VAR → qeyd danışır.
        source_only_row = rows["LRN102"]
        self.assertFalse(source_only_row["result"]["passed"] or source_only_row["result"]["failed"])
        self.assertTrue(source_only_row["legacy"]["show_result_notice"])
        self.assertTrue(source_only_row["legacy"]["source_only"])

        done_row = rows["LRN101"]
        self.assertTrue(done_row["legacy"]["show_result_notice"])
        self.assertFalse(done_row["legacy"]["source_only"])

    def test_native_row_is_never_marked(self):
        """(d) Yeni sistemdə yazılmış bal köçürülmüş kimi göstərilməməlidir."""
        from apps.registrar import transcript

        with bypass_rls():
            record = transcript.build_student_overall_record(student=self.student, organization=self.org)
        rows = {row["subject"].code: row for sem in record["semesters"] for row in sem["rows"]}
        self.assertIsNone(rows["LRN103"]["legacy"])

    def test_permanent_red_legacy_warning_reaches_all_student_surfaces(self):
        """Sahibin daimi qırmızı qeydi üç tələbə səthində də itməz."""
        with self._transcript_open():
            for section in ("overall-academic", "my-transcript", "my-results"):
                with self.subTest(section=section):
                    resp = self._get(section)
                    self.assertEqual(resp.status_code, 200)
                    self.assertContains(resp, str(LEGACY_EXAM_CENTER_WARNING))
                    self.assertContains(
                        resp, "legacy-grade-warning" if section != "my-results" else "result-legacy-fact__score-warning"
                    )

    def test_transcript_speaks_like_the_other_two_surfaces(self):
        """ÜÇÜNCÜ SƏTH susmamalıdır.

        ``build_student_transcript`` semestr bayraqlarını hər bucket-ə onsuz da
        yazırdı, transkript şablonu isə onları atırdı: eyni tələbə «Ümumi tədris
        məlumatı»nda mətni oxuyur, transkriptdə isə yalnız qlif görürdü.
        """
        with self._transcript_open():
            resp = self._get("my-transcript")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, SEMESTER_CHECK, count=1)
        self.assertContains(resp, SEMESTER_MISSING, count=1)
        # Sətir qlifi qalır — cümlə hansı sətirlərdən danışdığını onunla göstərir.
        self.assertContains(resp, '<span class="legacy-mark', count=7)

    def test_exam_center_verification_clears_pending_status_but_keeps_legacy_warning(self):
        """VERIFIED gözləməni bitirir, daimi legacy-bal qeydini yox."""
        from apps.registrar import transcript

        for source_pk in (9001, 9002, 9003, 9004, 9005, 9006, 9007):
            fact = LegacyGradeFact.objects.get(source_pk=source_pk)
            with bypass_rls():
                LegacyGradeReview.objects.create(
                    organization=self.org,
                    fact=fact,
                    decision="verified",
                    reason_code="exam_center_verified",
                    note="Mənbə sənədi ilə yoxlanılıb.",
                    evidence_digest="d" * 64,
                    reviewed_by=self.owner,
                    reviewed_by_name="Rektor",
                )
        with bypass_rls():
            record = transcript.build_student_overall_record(student=self.student, organization=self.org)
        rows = {row["subject"].code: row for sem in record["semesters"] for row in sem["rows"]}
        for code in ("LRN101", "LRN102", "LRN105", "LRN106"):
            self.assertFalse(rows[code]["legacy"]["show_result_notice"])
            self.assertEqual(str(rows[code]["legacy"]["warning"]), str(LEGACY_EXAM_CENTER_WARNING))

        resp = self._get("overall-academic")
        self.assertNotContains(resp, SEMESTER_CHECK)
        self.assertNotContains(resp, SEMESTER_MISSING)
        # Daimi qırmızı legacy-bal qeydi və mənşə qlifi qalır.
        self.assertContains(resp, str(LEGACY_EXAM_CENTER_WARNING))
        self.assertContains(resp, '<span class="legacy-mark', count=7)
        self.assertContains(resp, str(LEGACY_BADGE_LABEL), count=14)

    # ── Səthlər arasında sürüşmə ────────────────────────────────────────────

    def test_both_surfaces_speak_about_the_same_rows(self):
        """İki səth eyni sətri biri susaraq, digəri danışaraq göstərməməlidir."""
        results = self._get("my-results").content.decode()
        overall = self._get("overall-academic").content.decode()
        # Kartda tək-nəticə cümlələri, cədvəldə onların semestr qarşılığı.
        self.assertIn(NOTICE, results)
        self.assertIn(SOURCE_ONLY, results)
        self.assertIn(SEMESTER_CHECK, overall)
        self.assertIn(SEMESTER_MISSING, overall)

    def test_the_two_surfaces_do_not_open_the_same_query_twice(self):
        """Xam faktlar «Nəticələrim» üçün İKİ dəfə sorğulanmır.

        Qeyd nişanını quran oxuma onsuz da bütün faktları gətirir; kart onları
        eyni oxumadan alır.  Sətirdə fakt siyahısı YOXDURSA, ikinci sorğu geri
        qayıdıb (N sətir üçün ikinci dəst) yenidən açılardı.

        ⚠️ Bu test SORĞUNU SAYIR, sadəcə nəticənin dolu olduğunu yoxlamır:
        faktların sətrə qoşulduğunu yoxlamaq təkrar sorğunu TUTMAZDI — ikinci
        dəst də eyni dolu nəticəni verərdi.

        ⚠️ Sayılan şey BÜTÜN legacy oxu dəstidir (fakt cədvəli + review
        prefetch-i), yalnız fakt cədvəli YOX.  Səbəb mutasiya ilə ölçüldü:
        ``legacy_grade_facts_for_enrollments`` hər çağırışda 1 fakt + 1 review
        sorğusu açır, ona görə təkrar çağırış fakt sayını 1-dən yalnız 2-yə
        qaldırır — «fakt ≤ 2» həddi təkrarı BURAXIRDI (mutasiya keçdi).
        Dəst bütövlükdə sayılanda təkrar 2 → 4 edir və test çökür.
        """
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        from apps.registrar import public

        request = type("R", (), {"user": self.student})()
        with bypass_rls():
            with CaptureQueriesContext(connection) as captured:
                data = public.student_academic_record_rows(request, organization=self.org)

        legacy_queries = [
            q["sql"]
            for q in captured.captured_queries
            if "registrar_legacygradefact" in q["sql"] or "registrar_legacygradereview" in q["sql"]
        ]
        self.assertEqual(
            len(legacy_queries),
            2,
            f"legacy oxu dəsti {len(legacy_queries)} sorğu açdı (gözlənilən 2: fakt + review):\n"
            + "\n".join(legacy_queries),
        )

        rows = {row["subject"].code: row for sem in data["semesters"] for row in sem["rows"]}
        self.assertEqual(len(rows["LRN101"]["legacy_grade_facts"]), 1)
        self.assertTrue(rows["LRN101"]["legacy_grade_review_required"])
        self.assertEqual(rows["LRN103"]["legacy_grade_facts"], [])


CSS_ROOT = pathlib.Path(settings.BASE_DIR)


def _rule_body(css_path, selector):
    """CSS faylından bir qaydanın gövdəsini çıxarır (sadə, iç-içə qayda yoxdur)."""

    text = (CSS_ROOT / css_path).read_text(encoding="utf-8")
    match = re.search(re.escape(selector) + r"\s*\{([^}]*)\}", text)
    assert match is not None, f"{selector} qaydası {css_path} faylında tapılmadı"
    return match.group(1)


class LegacyNoticeColourTest(TestCase):
    """Qeydin RƏNGİ — CSS faylının ÖZÜNDƏ yoxlanılır.

    ⚠️ Niyə render olunmuş HTML yox: qeydin sinfi (`legacy-notice`) rəng
    daşımır, rəng xarici CSS-dədir (layihə qaydası: inline CSS YOXDUR).  Əvvəlki
    test render-də sinif adının yanındakı ~150 simvolda «fail/danger/warning»
    axtarırdı — o parça həmin sözləri HEÇ VAXT saxlaya bilməzdi, yəni test
    rəngi ümumiyyətlə yoxlamırdı: `legacy_mark.css`-i qırmızıya çevirsən də
    yaşıl qalırdı.  İndi mənbə faylın özü oxunur (mutasiya ilə sınanıb).
    """

    NOTICE_CSS = "static/css/legacy_mark.css"
    PANEL_CSS = "apps/accounts/static/accounts/css/profile/sections/my_results_academic.css"

    #: Qadağan olunmuş ton ailələri və NİYƏ (bax `_legacy_grade_notice.html`).
    FORBIDDEN = ("--ems-danger", "--ems-warning", "#fee2e2", "#b91c1c", "#fff3cd", "#d99e13")

    def test_notice_uses_the_informative_blue_family(self):
        body = _rule_body(self.NOTICE_CSS, ".legacy-notice")
        self.assertIn("--ems-primary-50", body, "fon informativ mavi qalmalıdır")
        self.assertIn("--ems-primary-800", body, "mətn informativ mavi qalmalıdır")
        self.assertIn("--ems-primary-200", body, "haşiyə informativ mavi qalmalıdır")

    def test_legacy_grade_warning_is_red_on_all_surfaces(self):
        """Daimi legacy-bal bildirişi qırmızı palitradadır."""
        body = _rule_body(self.NOTICE_CSS, ".legacy-grade-warning")
        self.assertIn("--ems-danger-strong", body)

    def test_notice_never_borrows_the_failure_or_correction_palette(self):
        """QIRMIZI = «kəsilib», SARI = «auditli düzəliş» — ikisi də başqa mənadır."""
        for selector in (".legacy-notice", ".legacy-notice__icon"):
            body = _rule_body(self.NOTICE_CSS, selector)
            for token in self.FORBIDDEN:
                self.assertNotIn(token, body, f"{selector} qadağan tonu geyinib: {token}")

    def test_evidence_panel_is_not_red_next_to_the_blue_notice(self):
        """«Nəticələrim» kartında mavi qeydin ALTINDAKI panel qırmızı olmamalıdır.

        İkisi praktiki olaraq eyni şeyi deyir («bu bal köhnə sistemdəndir»), ona
        görə qırmızı panel qeydin öz rəng əsaslandırmasına zidd idi: qırmızı
        ekranda artıq «kəsilib» deməkdir.  Panel sübut qutusudur — neytral boz.
        """
        for selector in (
            ".result-legacy-grade",
            ".result-legacy-grade__summary",
            ".result-legacy-fact",
            # Gözləyən yoxlama UĞURSUZLUQ deyil — qırmızı «kəsilib» deməkdir.
            ".result-legacy-fact__review",
        ):
            body = _rule_body(self.PANEL_CSS, selector)
            for token in self.FORBIDDEN:
                self.assertNotIn(token, body, f"{selector} hələ də xəbərdarlıq tonundadır: {token}")

    def test_each_raw_score_warning_is_red(self):
        body = _rule_body(self.PANEL_CSS, ".result-legacy-fact__score-warning")
        self.assertIn("--ems-danger-strong", body)
