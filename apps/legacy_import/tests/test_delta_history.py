"""Tarixi semestrlərin boşluq bərpası (``history`` / ``history_topics`` fazaları) — sintetik paket, real modellər.

Ledger (``LegacyEntityMap``) əvəzinə ``ledger_map`` saxta lüğətlə əvəzlənir — fazanın ledger-dən istifadəsi
(dilimlər, tələbə) eyni qalır, ledger cədvəlinin append-only qapıları bu testin mövzusu deyil.
"""

import datetime as dt
from contextlib import ExitStack
from decimal import Decimal
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.accounts.models import UserProfile
from apps.legacy_import.services.delta.apply import execute
from apps.legacy_import.services.delta.history import HistoryPhaseMismatch
from apps.legacy_import.services.delta.history_extract import parse_semesters
from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit
from apps.registrar.models import (
    AssessmentScheme,
    CourseOffering,
    Curriculum,
    Enrollment,
    FinalGrade,
    Lesson,
    LessonMark,
    Program,
    StudentAcademicRecord,
    Subject,
)
from core.constants import AcademicPeriodType, OrganizationType
from core.rls import bypass_rls

User = get_user_model()
UNTIL = dt.date(2026, 10, 25)
UQ = "histJRN0001"
UQ_QUARANTINE = "histJRN0002"
UQ_MERGED = "histJRN0000"  # cutover-də UQ ilə eyni açılışa birləşmiş ikinci legacy jurnal (sıra: UQ-dan ƏVVƏL)


def _point(pk, student, day, point, *, month="10", uniqid=UQ, time="09:00", excusable=0):
    return {
        "id": pk,
        "journal_uniqid": uniqid,
        "month_id": month,
        "day_number": day,
        "student_id": student,
        "point": point,
        "time": time,
        "excusable": excusable,
        "sem_muh": 2,
        "lab": 0,
        "update_counter": 1,
        "updated_at": None,
        "delta": "history",
    }


def _student(pk, first, last, group_id, *, azad=0, father="Ata"):
    return {
        "id": pk,
        "first_name": first,
        "last_name": last,
        "father_name": father,
        "fincode": "",
        "sex": 1,
        "gender": None,
        "birthday": "",
        "group_id": group_id,
        "speciality_id": 5,
        "entry_year": "2023",
        "azadedildi": azad,
        "education_level": "",
        "education_type": "Əyani",
        "payment_type": "",
        "is_new": False,
    }


def _group(pk, name, start_year):
    return {
        "id": pk,
        "name": name,
        "speciality_id": 5,
        "department_id": 3,
        "start_year": start_year,
        "eyani_qiyabi": "Əyani",
        "bak_or_mag": "bak",
        "sector": "az",
        "kollec_or_uni": "University",
        "is_new": False,
    }


def _bundle():
    journal = {
        "id": 31,
        "uniqid": UQ,
        "lesson_id": 5,
        "teacher_id": 77,
        "groups_id": '["900","901"]',
        "students_id": '["1","2","4"]',
        "semestr": 8,
        "fake": 0,
        "sonra_sil": 0,
        "active": 1,
        "fenn_saati": 30,
        "kredit": 5,
        "sillabus_id": 0,
    }
    quarantine = {**journal, "id": 32, "uniqid": UQ_QUARANTINE, "lesson_id": 6, "groups_id": '["999"]'}
    merged = {**journal, "id": 30, "uniqid": UQ_MERGED, "groups_id": '["900"]'}
    return {
        "snapshot": {"sha256": "1" * 64, "full_semesters": [], "history_semesters": [8], "phases": ["history"]},
        "periods": [{"id": 8, "name": "2024/2025 Payız", "type": "autumn", "is_current": 0}],
        "departments": [],
        "specialities": [],
        "groups": [_group(900, "201 A", 2020), _group(901, "201 B", 2020)],
        "subjects": [
            {"id": 5, "name": "Fizika", "lesson_code": "", "department_id": 3, "type": ""},
            {"id": 6, "name": "Kimya", "lesson_code": "", "department_id": 3, "type": ""},
        ],
        "workers": [],
        "students": [
            _student(1, "Kamal", "Mövcud", 901),
            _student(2, "Lalə", "Hesabsız", 900),
            _student(3, "Orxan", "Qayıb", 900),
            _student(4, "Səbinə", "Əkiz", 900),
        ],
        "journals": [],
        "lesson_dates": [],
        "points": [],
        "excuse_windows": [],
        "syllabi": [],
        "lesson_topics": [],
        "history": {
            "semesters": [8],
            "journals": [journal, quarantine, merged],
            "points": [
                _point(1, 1, "07", "8"),
                _point(2, 1, "14", "ie"),
                _point(3, 1, "", "71", month="im"),
                _point(4, 2, "07", "9"),
                _point(5, 2, "14", "qb", excusable=1),
                _point(6, 3, "07", "qb"),
                _point(7, 4, "07", "7"),
                _point(8, 1, "21", "6", uniqid=UQ_QUARANTINE),
                # Yalnız «qb»: yeni yazılış açmır, amma eyni qaçışda açılan yazılışa (eyni açılış) düşür.
                _point(9, 2, "28", "qb", uniqid=UQ_MERGED),
            ],
            "lesson_dates": [{"id": 1, "journal_id": 32, "month": 10, "day": 21, "time": "09:00", "sem_muh": 2}],
            "excuse_windows": [],
            "fin_counts": {},
            "lesson_topics": [
                {
                    "id": 1,
                    "journal_uniqid": UQ,
                    "month": 10,
                    "day": 7,
                    "times": "09:00",
                    "sem_muh": 2,
                    "room": 0,
                    "movzu": "Kinematika",
                    "semestr": 8,
                },
            ],
        },
    }


class HistoryPhaseTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.actor = User.objects.create_superuser("hist_actor", "hist-actor@example.test", "x")
        with bypass_rls():
            cls.org = Organization.objects.create(
                name="Hist Univ",
                slug="hist-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=cls.actor,
                status="active",
                is_active=True,
            )
            faculty = OrgUnit.objects.create(organization=cls.org, name="Fakültə", slug="h-fac", unit_type="faculty")
            specialty = OrgUnit.objects.create(
                organization=cls.org, name="Fizika ixtisası", slug="h-spec", unit_type="specialty", parent=faculty
            )
            cls.g900 = OrgUnit.objects.create(
                organization=cls.org,
                name="201 A",
                slug="h-g900",
                unit_type="group",
                parent=specialty,
                settings={"admission_year": 2020, "degree_level": "bachelor", "legacy": {"id": 900}},
            )
            cls.g901 = OrgUnit.objects.create(
                organization=cls.org,
                name="201 B",
                slug="h-g901",
                unit_type="group",
                parent=specialty,
                settings={"admission_year": 2020, "degree_level": "bachelor", "legacy": {"id": 901}},
            )
            cls.program = Program.objects.create(
                organization=cls.org, code="HFZ", name="Fizika", specialty_unit=specialty, degree_level="bachelor"
            )
            cls.curriculum = Curriculum.objects.create(organization=cls.org, program=cls.program, admission_year=2020)
            cls.period = AcademicPeriod.objects.create(
                organization=cls.org,
                name="Payız",
                academic_year="2024/2025",
                period_type=AcademicPeriodType.SEMESTER,
                start_date=dt.date(2024, 9, 15),
                end_date=dt.date(2025, 1, 31),
                is_current=False,
            )
            chair = OrgUnit.objects.create(
                organization=cls.org, name="Fizika kafedrası", slug="h-chair", unit_type="chair", parent=faculty
            )
            cls.physics = Subject.objects.create(organization=cls.org, code="QKU-5", name="Fizika", chair_unit=chair)
            cls.chemistry = Subject.objects.create(organization=cls.org, code="QKU-6", name="Kimya", chair_unit=chair)
            cls.o900 = CourseOffering.objects.create(
                organization=cls.org, subject=cls.physics, period=cls.period, group=cls.g900
            )
            cls.o901 = CourseOffering.objects.create(
                organization=cls.org, subject=cls.physics, period=cls.period, group=cls.g901
            )
            cls.other_chem = CourseOffering.objects.create(
                organization=cls.org, subject=cls.chemistry, period=cls.period, group=cls.g901
            )
            Lesson.objects.create(
                organization=cls.org,
                offering=cls.o900,
                date=dt.date(2024, 10, 28),
                kind="seminar",
                start_time=dt.time(9),
            )
            for offering in (cls.o900, cls.o901):
                AssessmentScheme.objects.create(
                    organization=cls.org, offering=offering, approval_status="approved", is_published=True
                )
                Lesson.objects.create(
                    organization=cls.org,
                    offering=offering,
                    date=dt.date(2024, 10, 7),
                    kind="seminar",
                    start_time=dt.time(9, 0),
                )
            student_role = cls.org.roles.get(name="student")
            alumni_role = cls.org.roles.get(name="alumni")
            # 201 A — məzun qrupu (alumni çoxluqdadır); 201 B — mövcud tələbə (ledger) burada.
            cls.kamal = cls._member("kamal.movcud", "Kamal", "Mövcud", alumni_role, cls.g901)
            cls.sebine = cls._member("sebine.ekiz", "Səbinə", "Əkiz", alumni_role, cls.g900)
            cls.orxan = cls._member("orxan.qayib", "Orxan", "Qayıb", alumni_role, cls.g900)
            cls._member("baska.mezun", "Başqa", "Məzun", alumni_role, cls.g900)
            cls._member("tek.telebe", "Tək", "Tələbə", student_role, cls.g901)
            # Səbinə: eyni fənn + dövr üzrə BAŞQA açılışda yazılış — əkiz, bərpa olunmamalıdır.
            twin_offering = CourseOffering.objects.create(
                organization=cls.org,
                subject=Subject.objects.create(organization=cls.org, code="QKU-50", name="Fizika", chair_unit=chair),
                period=cls.period,
                group=cls.g901,
            )
            Enrollment.objects.create(organization=cls.org, student=cls.sebine, offering=twin_offering)
            # Kamal: həmin dövrdə 201 B qrupunda (Kimya) yazılışı var — karantin jurnalının qrup sübutu.
            Enrollment.objects.create(organization=cls.org, student=cls.kamal, offering=cls.other_chem)

    @classmethod
    def _member(cls, username, first, last, role, group):
        user = User.objects.create_user(username, f"{username}@example.test", "x", first_name=first, last_name=last)
        UserProfile.objects.filter(user=user).update(patronymic="Ata")
        Membership.objects.create(user=user, organization=cls.org, role=role, is_primary=True, is_active=True)
        StudentAcademicRecord.objects.create(
            organization=cls.org,
            student=user,
            program=cls.program,
            curriculum=cls.curriculum,
            group=group,
            admission_year=2020,
            status="enrolled",
            is_active=True,
        )
        return user

    def _ledger(self):
        maps = {
            "student": {"1": str(self.kamal.pk), "3": str(self.orxan.pk), "4": str(self.sebine.pk)},
            "course_offering": {
                f"{UQ}:900": str(self.o900.pk),
                f"{UQ}:901": str(self.o901.pk),
                f"{UQ_MERGED}:900": str(self.o900.pk),
            },
            "group_unit": {"900": str(self.g900.pk), "901": str(self.g901.pk)},
            "lesson_subject": {"5": str(self.physics.pk), "6": str(self.chemistry.pk)},
        }

        def fake(_organization, entity_type, legacy_pks=None):
            found = maps.get(entity_type, {})
            if legacy_pks is None:
                return dict(found)
            keys = {str(key) for key in legacy_pks}
            return {key: value for key, value in found.items() if key in keys}

        return fake

    def _run(self, *, apply, bundle=None, phases=("history",)):
        fake = self._ledger()
        with ExitStack() as stack:
            for target in (
                "apps.legacy_import.services.delta.resolve.ledger_map",
                "apps.legacy_import.services.delta.people.ledger_map",
                "apps.legacy_import.services.delta.history_plan.ledger_map",
            ):
                stack.enter_context(mock.patch(target, fake))
            stack.enter_context(bypass_rls())
            return execute(
                organization=self.org,
                actor=self.actor,
                bundle=bundle or _bundle(),
                apply=apply,
                until=UNTIL,
                tag="hist-test",
                phases=phases,
            )

    def test_dry_run_counts_and_writes_nothing(self):
        run = self._run(apply=False)
        self.assertEqual(run.counters["history.pair.created"], 2)
        with bypass_rls():
            self.assertFalse(User.objects.filter(username="myedu.student.2").exists())
            self.assertFalse(Enrollment.objects.filter(offering=self.o901, student=self.kamal).exists())

    def test_apply_restores_gaps_into_closed_journals_and_rerun_is_noop(self):
        run = self._run(apply=True)
        with bypass_rls():
            # K9 / siyahıdakı tələbə: öz (SAR) qrupunun dilimi, bağlı jurnala yazılıb + yekun bal.
            kamal = Enrollment.objects.get(offering=self.o901, student=self.kamal)
            self.assertIsNone(kamal.source_group_id)
            mark = LessonMark.objects.get(enrollment=kamal, lesson__date=dt.date(2024, 10, 7))
            self.assertEqual((mark.status, mark.score), ("present", Decimal("8")))
            self.assertEqual(FinalGrade.objects.get(enrollment=kamal).exam_score, Decimal("71"))
            # 14 oktyabr dərsi yox idi — real xanası olan slot sintetik dərs kimi bərpa olunur.
            self.assertTrue(
                Lesson.objects.filter(offering=self.o901, date=dt.date(2024, 10, 14), is_legacy_synthesised=True)
            )
            # Hesabı olmayan keçmiş tələbə: arxiv (alumni, giriş bağlı) hesab + SAR + yazılış.
            lale = User.objects.get(username="myedu.student.2")
            self.assertEqual(lale.profile.access_state, UserProfile.AccessState.ARCHIVED)
            self.assertEqual(lale.profile.institutional_identifier, "2")
            self.assertTrue(lale.email.endswith("@placeholder.invalid"))
            self.assertFalse(lale.has_usable_password())
            self.assertEqual(StudentAcademicRecord.objects.get(student=lale).group_id, self.g900.pk)
            excused = LessonMark.objects.get(enrollment__student=lale, lesson__date=dt.date(2024, 10, 14))
            self.assertEqual(excused.status, "excused")
            merged = LessonMark.objects.get(enrollment__student=lale, lesson__date=dt.date(2024, 10, 28))
            self.assertEqual(merged.status, "absent")
            # Yalnız «qb» olan cüt və əkiz cüt bərpa olunmur.
            self.assertFalse(Enrollment.objects.filter(student=self.orxan, offering__subject=self.physics).exists())
            self.assertFalse(Enrollment.objects.filter(student=self.sebine, offering__subject=self.physics).exists())
            # Karantin jurnalı: tələbənin dövrdəki TƏK qrupu (201 B) → həmin qrupun Kimya açılışı (mövcud yazılış).
            chem = Enrollment.objects.get(student=self.kamal, offering=self.other_chem)
            self.assertTrue(LessonMark.objects.filter(enrollment=chem, score=Decimal("6")).exists())
        self.assertEqual(run.counters["history.pair.skipped.absent_only"], 1)
        self.assertEqual(run.counters["history.pair.skipped.twin_other_offering"], 1)
        self.assertEqual(run.counters["history.student.archived_created"], 1)
        again = self._run(apply=True)
        written = {k: v for k, v in again.counters.items() if k.startswith("written.") or ".touched." in k}
        self.assertEqual(written, {})
        self.assertEqual(again.counters["history.pair.existing"], 4)

    def test_quarantine_creates_locked_offering_when_missing(self):
        """Qrup sübutu olan, amma açılışı olmayan karantin cütü: açılış yaranır və J7 kimi KİLİDLƏNİR."""
        with bypass_rls():
            Enrollment.objects.filter(offering=self.other_chem).delete()
            CourseOffering.objects.filter(pk=self.other_chem.pk).delete()
        run = self._run(apply=True)
        with bypass_rls():
            created = CourseOffering.objects.get(subject=self.chemistry, group=self.g901, period=self.period)
            scheme = AssessmentScheme.objects.get(offering=created)
            self.assertEqual((scheme.approval_status, scheme.is_published), ("approved", True))
            enrollment = Enrollment.objects.get(offering=created, student=self.kamal)
            self.assertTrue(LessonMark.objects.filter(enrollment=enrollment, score=Decimal("6")).exists())
            self.assertFalse(Lesson.objects.get(offering=created).is_legacy_synthesised)
        self.assertEqual(run.counters["history.offering.created_locked"], 1)
        again = self._run(apply=True)
        self.assertEqual({k: v for k, v in again.counters.items() if k.startswith("written.")}, {})

    def test_same_person_with_two_legacy_rows_gets_one_archived_account(self):
        """Legacy-də eyni adamın iki sətri (ad + ata adı eyni) — bir arxiv hesabı; ikinci sətir ona bağlanır."""
        bundle = _bundle()
        bundle["students"].append(_student(5, "Lalə", "Hesabsız", 900))
        bundle["history"]["points"].append(_point(10, 5, "07", "10", uniqid=UQ_MERGED))
        run = self._run(apply=True, bundle=bundle)
        with bypass_rls():
            self.assertEqual(User.objects.filter(first_name="Lalə", last_name="Hesabsız").count(), 1)
            self.assertFalse(User.objects.filter(username="myedu.student.5").exists())
        self.assertEqual(run.counters["history.student.archived_created"], 1)
        self.assertEqual(run.counters["student.name"], 1)

    def test_history_topics_fill_blank_topic_in_closed_journal(self):
        run = self._run(apply=True, phases=("history_topics",))
        with bypass_rls():
            topic = Lesson.objects.get(offering=self.o900, date=dt.date(2024, 10, 7)).topic
        self.assertEqual(topic, "Kinematika")
        self.assertEqual(run.counters["history.topic.filled"], 2)
        again = self._run(apply=True, phases=("history_topics",))
        self.assertEqual(again.counters["history.topic.kept_existing"], 2)

    def test_history_bundle_refuses_regular_phases(self):
        with self.assertRaises(HistoryPhaseMismatch):
            self._run(apply=False, phases=("students", "history"))

    def test_parse_semesters(self):
        self.assertEqual(parse_semesters("1-3,7"), [1, 2, 3, 7])
        self.assertEqual(parse_semesters([2, "2"]), [2])
        with self.assertRaises(ValueError):
            parse_semesters("3-1")
