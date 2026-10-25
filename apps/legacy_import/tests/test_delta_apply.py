"""Köhnə sistem DELTA tətbiqi — uçdan-uca (sintetik paket, real modellər və DB qapıları).

Yoxlanılır: dry-run heç nə yazmır; tətbiq çatışmayanı yaradır (FİN-siz müəllim, tələbə, alt qrup,
açılış, qeydiyyat, dərs, xana, təsdiqlənmiş sillabus, təkrar imtahan); yeni sistemin mövcud dəyəri
ÜZƏRİNƏ YAZILMIR; ikinci qaçış 0 yazı verir (idempotent).
"""

import datetime as dt
import os
import stat
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase

from apps.accounts.models import UserProfile
from apps.audit.models import AuditLog
from apps.legacy_import.services.delta.apply import BATCH_RESOURCE, execute
from apps.legacy_import.services.delta.bundle import BundleError, read_bundle, write_bundle
from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit
from apps.registrar.models import (
    CourseOffering,
    Curriculum,
    Enrollment,
    Lesson,
    LessonMark,
    Program,
    StudentAcademicRecord,
    Subject,
)
from apps.syllabus.models import Syllabus
from core.constants import AcademicPeriodType, OrganizationType
from core.rls import bypass_rls

User = get_user_model()
UNTIL = dt.date(2026, 10, 21)


def _bundle(**overrides):
    data = {
        "snapshot": {"sha256": "0" * 64, "full_semesters": [14], "since": "2026-08-01"},
        "periods": [{"id": 14, "name": "2026/2027 Payız", "type": "autumn", "is_current": 1}],
        "departments": [],
        "specialities": [],
        "groups": [
            {
                "id": 900,
                "name": "101 A",
                "speciality_id": 5,
                "department_id": 3,
                "start_year": 2026,
                "eyani_qiyabi": "Əyani",
                "bak_or_mag": "bak",
                "sector": "az",
                "kollec_or_uni": "University",
                "is_new": False,
            },
            {
                "id": 901,
                "name": "101 A1",
                "speciality_id": 5,
                "department_id": 3,
                "start_year": 2026,
                "eyani_qiyabi": "Əyani",
                "bak_or_mag": "bak",
                "sector": "az",
                "kollec_or_uni": "University",
                "is_new": True,
            },
        ],
        "subjects": [{"id": 5, "name": "Riyaziyyat", "lesson_code": "", "department_id": 3, "type": ""}],
        "workers": [
            {
                "id": 77,
                "first_name": "Kamran",
                "last_name": "Delta",
                "father_name": "Vüqar",
                "department_id": 3,
                "teacher_type": 1,
                "inzibati": 0,
                "kollec_or_uni": "University",
            }
        ],
        "students": [
            {
                "id": 1,
                "first_name": "Aysel",
                "last_name": "Mövcud",
                "father_name": "Tural",
                "fincode": "AAA1111",
                "sex": 2,
                "gender": None,
                "birthday": "",
                "group_id": 900,
                "speciality_id": 5,
                "entry_year": "2026",
                "azadedildi": 0,
                "education_level": "Bakalavr",
                "education_type": "Əyani",
                "payment_type": "Ödənişli",
                "is_new": True,
            },
            {
                "id": 2,
                "first_name": "Nicat",
                "last_name": "Yenizadə",
                "father_name": "Orxan",
                "fincode": "BBB2222",
                "sex": 0,
                "gender": "Kişi",
                "birthday": "2007-05-04",
                "group_id": 901,
                "speciality_id": 5,
                "entry_year": "2026",
                "azadedildi": 0,
                "education_level": "Bakalavr",
                "education_type": "Əyani",
                "payment_type": "Dövlət Sifarişi",
                "is_new": True,
            },
            {
                "id": 3,
                "first_name": "Azad",
                "last_name": "Edilmiş",
                "father_name": "",
                "fincode": "",
                "sex": 1,
                "gender": None,
                "birthday": "",
                "group_id": 900,
                "speciality_id": 5,
                "entry_year": "2026",
                "azadedildi": 1,
                "education_level": "",
                "education_type": "",
                "payment_type": "",
                "is_new": True,
            },
        ],
        "journals": [
            {
                "id": 11,
                "uniqid": "abcDEF1234",
                "lesson_id": 5,
                "teacher_id": 77,
                "groups_id": '["900"]',
                "students_id": '["1","2","3"]',
                "semestr": 14,
                "fake": 0,
                "sonra_sil": 0,
                "active": 1,
                "fenn_saati": 45,
                "kredit": 5,
                "sillabus_id": 500,
            },
        ],
        "lesson_dates": [
            {"id": 21, "journal_id": 11, "month": 10, "day": 6, "time": "09:00", "sem_muh": 2},
            {"id": 22, "journal_id": 11, "month": 10, "day": 6, "time": "10:30", "sem_muh": 2},
            {"id": 23, "journal_id": 11, "month": 11, "day": 10, "time": "09:00", "sem_muh": 2},
        ],
        "points": [
            _point(1, "1", "06", "09:00", "8"),
            _point(2, "2", "06", "09:00", "qb"),
            _point(3, "1", "06", "10:30", "ie"),
            _point(4, "2", "06", "10:30", "ie"),
            _point(5, "1", "10", "09:00", "ie", month="11"),
            _point(6, "1", "06", "09:00", "6", counter=0),  # J-V4: köhnə təkrar uduzur
            _point(7, "2", "", "", "55", month="im2", uniqid="oldJOURNAL"),
        ],
        "excuse_windows": [],
        "syllabi": [
            {
                "id": 500,
                "uniqid": "syl500",
                "lesson_id": 5,
                "teacher_id": 77,
                "ders_saati": 45,
                "language": "az",
                "active": 1,
                "is_new": True,
                "is_changed": False,
                "week": [
                    {
                        "id": 1,
                        "uniqid": "syl500",
                        "movzu": "Giri&ccedil;",
                        "muh_saat": "2",
                        "sem_saat": "2",
                        "praktiki_saat": "",
                        "lab_saat": "",
                        "qeyd": "",
                    }
                ],
                "sections": {"sillabus_tesviri_ve_meqsedi": [[1, "Təsvir"]]},
            },
        ],
    }
    data.update(overrides)
    return data


def _point(pk, student, day, time, point, *, month="10", counter=1, uniqid="abcDEF1234"):
    return {
        "id": pk,
        "journal_uniqid": uniqid,
        "month_id": month,
        "day_number": day,
        "student_id": int(student),
        "point": point,
        "time": time,
        "excusable": 0,
        "sem_muh": 2,
        "lab": 0,
        "update_counter": counter,
        "updated_at": None,
        "delta": "full",
    }


class DeltaApplyTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.actor = User.objects.create_superuser("delta_actor", "delta-actor@example.test", "x")
        with bypass_rls():
            cls.org = Organization.objects.create(
                name="Delta Univ",
                slug="delta-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=cls.actor,
                status="active",
                is_active=True,
            )
            faculty = OrgUnit.objects.create(organization=cls.org, name="Fakültə", slug="d-fac", unit_type="faculty")
            cls.specialty = OrgUnit.objects.create(
                organization=cls.org, name="Riyaziyyat ixtisası", slug="d-spec", unit_type="specialty", parent=faculty
            )
            cls.group = OrgUnit.objects.create(
                organization=cls.org,
                name="101 A",
                slug="d-g",
                unit_type="group",
                parent=cls.specialty,
                settings={"admission_year": 2026},
            )
            cls.program = Program.objects.create(
                organization=cls.org, code="DRY", name="Riyaziyyat", specialty_unit=cls.specialty
            )
            Curriculum.objects.create(organization=cls.org, program=cls.program, admission_year=2026)
            cls.period = AcademicPeriod.objects.create(
                organization=cls.org,
                name="Payız",
                academic_year="2026/2027",
                period_type=AcademicPeriodType.SEMESTER,
                start_date=dt.date(2026, 9, 15),
                end_date=dt.date(2027, 1, 31),
                is_current=True,
            )
            cls.chair = OrgUnit.objects.create(
                organization=cls.org, name="Riyaziyyat kafedrası", slug="d-chair", unit_type="chair", parent=faculty
            )
            Subject.objects.create(organization=cls.org, code="QKU-5", name="Riyaziyyat", chair_unit=cls.chair)
            cls.existing = User.objects.create_user(
                "aysel.movcud", "a@example.test", "x", first_name="Aysel", last_name="Mövcud"
            )
            UserProfile.objects.filter(user=cls.existing).update(fin="AAA1111")
            Membership.objects.create(
                user=cls.existing,
                organization=cls.org,
                role=cls.org.roles.get(name="student"),
                is_primary=True,
                is_active=True,
            )
            StudentAcademicRecord.objects.create(
                organization=cls.org,
                student=cls.existing,
                program=cls.program,
                curriculum=Curriculum.objects.get(program=cls.program),
                group=cls.group,
                admission_year=2026,
                status="enrolled",
                is_active=True,
            )

    def _run(self, *, apply, bundle=None):
        with bypass_rls():
            return execute(
                organization=self.org,
                actor=self.actor,
                bundle=bundle or _bundle(),
                apply=apply,
                until=UNTIL,
                tag="delta-test",
            )

    def test_dry_run_writes_nothing(self):
        run = self._run(apply=False)
        self.assertEqual(run.counters["written.marks"], 4)
        with bypass_rls():
            self.assertFalse(CourseOffering.objects.filter(organization=self.org).exists())
            self.assertFalse(User.objects.filter(username__startswith="nicat").exists())
            self.assertFalse(AuditLog.objects.filter(resource_type=BATCH_RESOURCE).exists())

    def test_apply_creates_missing_and_second_run_is_noop(self):
        run = self._run(apply=True)
        with bypass_rls():
            offering = CourseOffering.objects.get(organization=self.org, group=self.group, period=self.period)
            self.assertEqual(offering.lesson_hours, 45)
            teacher = offering.instructor
            self.assertIsNotNone(teacher, "FİN-siz müəllim yaradılıb və açılışa yazılıb")
            self.assertIsNone(teacher.profile.fin)
            self.assertFalse(teacher.has_usable_password())
            created = User.objects.get(profile__institutional_identifier="2")
            self.assertFalse(created.has_usable_password())
            self.assertTrue(created.email.endswith("@placeholder.invalid"))
            subgroup = OrgUnit.objects.get(organization=self.org, slug="myedu-grp-901")
            self.assertEqual(subgroup.settings["parent_group"], str(self.group.pk))
            guest = Enrollment.objects.get(offering=offering, student=created)
            self.assertEqual(guest.source_group_id, subgroup.pk)
            self.assertTrue(Enrollment.objects.filter(offering=offering, student=self.existing).exists())
            self.assertFalse(User.objects.filter(last_name="Edilmiş").exists(), "azad edilmiş tələbə yaradılmır")
            lessons = Lesson.objects.filter(offering=offering).order_by("start_time")
            self.assertEqual([lesson.start_time for lesson in lessons], [dt.time(9, 0), dt.time(10, 30)])
            self.assertEqual({lesson.kind for lesson in lessons}, {"seminar"})
            score = LessonMark.objects.get(lesson=lessons[0], enrollment__student=self.existing)
            self.assertEqual((score.status, score.score), ("present", Decimal("8")))
            absent = LessonMark.objects.get(lesson=lessons[0], enrollment=guest)
            self.assertEqual(absent.status, "absent")
            guest.refresh_from_db()
            self.assertEqual(guest.absence_hours, 2)
            syllabus = Syllabus.objects.get(organization=self.org, offering=offering)
            self.assertEqual(syllabus.approved_version.status, "approved")
            self.assertEqual(syllabus.approved_version.approval_source, "migration")
            self.assertTrue(AuditLog.objects.filter(resource_type=BATCH_RESOURCE, resource_id="delta-test").exists())
            # «Mənim dərs yüküm»: kafedranın tapşırığında sətir + müəllim bölgüsü (təsdiqlənmiş sənəd).
            from apps.workload.models import TeacherAssignment

            assignments = TeacherAssignment.objects.filter(teacher=teacher, row__subject__code="QKU-5")
            self.assertEqual({a.activity for a in assignments}, {"lecture", "seminar"})
            self.assertIn(assignments[0].row.task.status, ("distributed", "amended"))
            self.assertEqual(sum(TeacherAssignment.objects.filter(teacher=teacher).values_list("hours", flat=True)), 45)
        self.assertEqual(run.counters["lesson.future_skipped"], 1)
        self.assertEqual(run.counters["final.resit.enrollment_unresolved"], 1)
        again = self._run(apply=True)
        written = {key: value for key, value in again.counters.items() if key.startswith(("written.", "touched."))}
        self.assertEqual(written, {})
        self.assertEqual(again.counters["mark.same"], 4)

    def test_legacy_lesson_date_without_cells_is_not_materialised(self):
        """Köhnə sistemdə əlavə olunub heç nə yazılmayan gün jurnalda TAM BOŞ sütun yaratmır."""
        bundle = _bundle()
        bundle["lesson_dates"].append(
            {"id": 24, "journal_id": 11, "month": 10, "day": 8, "time": "09:00", "sem_muh": 2}
        )
        run = self._run(apply=True, bundle=bundle)
        with bypass_rls():
            offering = CourseOffering.objects.get(organization=self.org, group=self.group, period=self.period)
            self.assertFalse(Lesson.objects.filter(offering=offering, date=dt.date(2026, 10, 8)).exists())
            self.assertEqual(Lesson.objects.filter(offering=offering).count(), 2)
        self.assertEqual(run.counters["lesson.empty_not_created"], 1)
        self.assertEqual(run.counters["lesson.created"], 2)
        again = self._run(apply=True, bundle=bundle)
        self.assertEqual({k: v for k, v in again.counters.items() if k.startswith("written.")}, {})

    def test_same_name_with_other_patronymic_is_another_person_and_is_created(self):
        """Sistemdə eyni ad-soyadlı, amma ata adı fərqli (başqa qrupda) tələbə var — legacy tələbə ayrıca yaradılır."""
        with bypass_rls():
            namesake = User.objects.create_user(
                "nicat.yenizade", "ny@example.test", "x", first_name="Nicat", last_name="Yenizadə"
            )
            UserProfile.objects.filter(user=namesake).update(patronymic="Elşən")
            Membership.objects.create(
                user=namesake, organization=self.org, role=self.org.roles.get(name="student"), is_active=True
            )
        run = self._run(apply=True)
        self.assertEqual(run.counters["student.name_other_person"], 1)
        with bypass_rls():
            created = User.objects.get(profile__institutional_identifier="2")
            self.assertNotEqual(created.pk, namesake.pk)
            self.assertTrue(LessonMark.objects.filter(enrollment__student=created).exists())
            self.assertFalse(Enrollment.objects.filter(student=namesake).exists())

    def test_ambiguous_namesake_is_created_only_with_explicit_flag(self):
        """Adaş eyni qrupdadır, ata adı yoxdur → ambiqü; ``snapshot.create_ambiguous`` ilə yeni hesab yaranır."""
        with bypass_rls():
            namesake = User.objects.create_user(
                "nicat.y2", "n2@example.test", "x", first_name="Nicat", last_name="Yenizadə"
            )
            Membership.objects.create(
                user=namesake, organization=self.org, role=self.org.roles.get(name="student"), is_active=True
            )
            UserProfile.objects.filter(user=namesake).update(birth_date=dt.date(2001, 1, 1))
        bundle = _bundle()
        bundle["students"][1]["father_name"] = ""
        first = self._run(apply=False, bundle=bundle)
        self.assertEqual(first.counters["student.name_ambiguous.no_patronymic_other_group"], 1)
        bundle["snapshot"] = {**bundle["snapshot"], "create_ambiguous": True}
        run = self._run(apply=True, bundle=bundle)
        self.assertEqual(run.counters["student.ambiguous_created"], 1)
        with bypass_rls():
            created = User.objects.get(profile__institutional_identifier="2")
        self.assertNotEqual(created.pk, namesake.pk)
        self.assertIn(("student_ambiguous_created", "Yenizadə Nicat", "1"), run.name_rows)

    def test_new_absent_only_column_is_not_created(self):
        """Yeni legacy sütununda YALNIZ «qb» varsa dərs yaradılmır (boş/«qb»-only sütun təmizliyi ilə eyni qayda)."""
        bundle = _bundle()
        bundle["points"] += [_point(20, "1", "13", "09:00", "qb"), _point(21, "2", "13", "09:00", "qb")]
        run = self._run(apply=True, bundle=bundle)
        with bypass_rls():
            offering = CourseOffering.objects.get(organization=self.org, group=self.group, period=self.period)
            self.assertFalse(Lesson.objects.filter(offering=offering, date=dt.date(2026, 10, 13)).exists())
        self.assertEqual(run.counters["lesson.absent_only_not_created"], 1)
        self.assertEqual(run.counters["mark.absent_only_lesson_skipped"], 2)
        again = self._run(apply=True, bundle=bundle)
        self.assertEqual({k: v for k, v in again.counters.items() if k.startswith("written.")}, {})

    def test_lesson_topics_fill_only_blank_and_rerun_is_stable(self):
        """Köhnə dərs tarixinin sillabus mövzusu dərsə yazılır; müəllimin yazdığı mövzuya toxunulmur."""
        self._run(apply=True)
        with bypass_rls():
            offering = CourseOffering.objects.get(organization=self.org, group=self.group, period=self.period)
            Lesson.objects.filter(offering=offering, start_time=dt.time(10, 30)).update(topic="Müəllimin mövzusu")
        from apps.exams.models import ExamRoom

        with bypass_rls():
            room = ExamRoom.objects.create(organization=self.org, name="204", code="myedu-room-5", building="1")
        bundle = _bundle(
            lesson_topics=[
                {
                    "id": 1,
                    "journal_uniqid": "abcDEF1234",
                    "month": 10,
                    "day": 6,
                    "times": "09:00",
                    "movzu": " Giriş  ",
                    "room": 5,
                },
                {"id": 2, "journal_uniqid": "abcDEF1234", "month": 10, "day": 6, "times": "10:30", "movzu": "Başqa"},
                {"id": 3, "journal_uniqid": "abcDEF1234", "month": 10, "day": 9, "times": "09:00", "movzu": "Yoxdur"},
                {"id": 4, "journal_uniqid": "unknownJRN", "month": 10, "day": 6, "times": "09:00", "movzu": "X"},
            ]
        )
        run = self._run(apply=True, bundle=bundle)
        with bypass_rls():
            topics = dict(Lesson.objects.filter(offering=offering).values_list("start_time", "topic"))
        self.assertEqual(topics, {dt.time(9, 0): "Giriş", dt.time(10, 30): "Müəllimin mövzusu"})
        with bypass_rls():
            self.assertEqual(Lesson.objects.get(offering=offering, start_time=dt.time(9, 0)).room_id, room.pk)
        self.assertEqual(run.counters["room.filled"], 1)
        self.assertEqual(run.counters["topic.filled"], 1)
        self.assertEqual(run.counters["topic.kept_existing"], 1)
        self.assertEqual(run.counters["topic.lesson_unmatched"], 1)
        self.assertEqual(run.counters["topic.offering_unresolved"], 1)
        again = self._run(apply=True, bundle=bundle)
        self.assertEqual({k: v for k, v in again.counters.items() if k.startswith(("written.", "touched."))}, {})

    def test_teacher_lesson_absorbs_legacy_slot_and_rerun_is_stable(self):
        """Müəllimin yeni sistemdə açdığı eyni gün dərsi bir legacy slotunu udur; ikinci qaçış eyni nəticə."""
        with bypass_rls():
            offering = CourseOffering.objects.create(
                organization=self.org, subject=Subject.objects.get(code="QKU-5"), period=self.period, group=self.group
            )
            Lesson.objects.create(
                organization=self.org,
                offering=offering,
                date=dt.date(2026, 10, 6),
                kind="seminar",
                start_time=dt.time(13, 0),
                created_by=self.actor,
            )
        self._run(apply=True)
        with bypass_rls():
            times = sorted(Lesson.objects.filter(offering=offering).values_list("start_time", flat=True))
        self.assertEqual(times, [dt.time(10, 30), dt.time(13, 0)], "09:00 slotu müəllimin 13:00 dərsinə düşüb")
        again = self._run(apply=True)
        self.assertEqual({k: v for k, v in again.counters.items() if k.startswith("written.")}, {})

    def test_empty_own_group_duplicate_is_released_into_subgroup_row(self):
        """Tələbə legacy-də alt qrup jurnalındadır; öz qrupunun eyni fənn jurnalındakı BOŞ sətri tarixçəyə keçir."""
        self._run(apply=True)
        with bypass_rls():
            created = User.objects.get(profile__institutional_identifier="2")
            subgroup = OrgUnit.objects.get(organization=self.org, slug="myedu-grp-901")
            record = StudentAcademicRecord.objects.get(student=created)
            self.assertEqual(record.group_id, subgroup.pk)
            own = CourseOffering.objects.create(
                organization=self.org, subject=Subject.objects.get(code="QKU-5"), period=self.period, group=subgroup
            )
            duplicate = Enrollment.objects.create(organization=self.org, student=created, offering=own)
        run = self._run(apply=True)
        with bypass_rls():
            duplicate.refresh_from_db()
            guest = Enrollment.objects.get(student=created, source_group=subgroup)
        self.assertEqual((duplicate.status, duplicate.superseded_by_id), ("dropped", guest.pk))
        self.assertEqual(run.counters["dedupe.released"], 1)
        self.assertEqual(self._run(apply=True).counters["dedupe.released"], 0)

    def test_existing_values_are_never_overwritten(self):
        self._run(apply=True)
        with bypass_rls():
            offering = CourseOffering.objects.get(organization=self.org, group=self.group, period=self.period)
            mark = LessonMark.objects.get(lesson__start_time=dt.time(9, 0), enrollment__student=self.existing)
            LessonMark.objects.filter(pk=mark.pk).update(score=Decimal("3"))
            other = User.objects.create_user("other_teacher", "o@example.test", "x")
            Membership.objects.create(
                user=other, organization=self.org, role=self.org.roles.get(name="teacher"), is_active=True
            )
            CourseOffering.objects.filter(pk=offering.pk).update(instructor=other)
        run = self._run(apply=True)
        with bypass_rls():
            mark.refresh_from_db()
            offering.refresh_from_db()
        self.assertEqual(mark.score, Decimal("3"))
        self.assertEqual(offering.instructor_id, other.pk)
        self.assertEqual(run.counters["mark.conflict_kept"], 1)
        self.assertEqual(run.counters["offering.instructor_conflict_kept"], 1)


class DeltaBundleTests(TestCase):
    def test_round_trip_is_private_and_versioned(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "delta.json.gz")
            write_bundle(path, _bundle())
            self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o600)
            self.assertEqual(read_bundle(path)["journals"][0]["uniqid"], "abcDEF1234")
            broken = _bundle()
            del broken["points"]
            with self.assertRaises(BundleError):
                write_bundle(path, broken)

    def test_command_refuses_digest_mismatch(self):
        import tempfile

        from django.core.management.base import CommandError

        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "delta.json.gz")
            write_bundle(path, _bundle())
            with self.assertRaises(CommandError):
                call_command("legacy_delta_apply", "--bundle", path, "--expected-sha256", "f" * 64)
