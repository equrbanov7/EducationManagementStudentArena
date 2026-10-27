"""Delta: tələbənin «ev» jurnalı (RİM 2026-10-27, MR-11/15) və legacy kod 2 = laboratoriya (MR-8/9).

Əvvəl ``(tələbə, fənn, dövr)`` üzrə «ilk emal olunan» jurnal qalib gəlirdi: paralel qrupun jurnalında yalnız qalıq
xanası olan (və ya passiv) jurnal tələbənin qeydiyyatını özünə çəkir, əsl jurnalın xanaları oraya 1–3 xanalı «fantom
dərs» kimi yazılırdı. İndi: aktiv, siyahıda, xanası çox olan jurnal evdir; əkiz/passiv jurnalın xanası ev açılışında
yalnız MÖVCUD dərsə düşür.
"""

import datetime as dt
from decimal import Decimal

from django.test import TestCase

from apps.legacy_import.services.delta.apply import execute
from apps.legacy_import.services.rehearsal_journal_lesson_kinds import cell_kind
from apps.organizations.models import OrgUnit
from apps.registrar.models import CourseOffering, Enrollment, Lesson, LessonMark
from core.rls import bypass_rls

from . import test_delta_apply as base
from .test_delta_apply import UNTIL, _bundle, _point

_SIBLING = {
    "id": 902,
    "name": "101 B",
    "speciality_id": 5,
    "department_id": 3,
    "start_year": 2026,
    "eyani_qiyabi": "Əyani",
    "bak_or_mag": "bak",
    "sector": "az",
    "kollec_or_uni": "University",
    "is_new": False,
}


def _twin_journal(*, active=1, students='["1"]', uniqid="twinB00001"):
    return {
        "id": 10,  # əsl jurnaldan (11) ƏVVƏL emal olunur
        "uniqid": uniqid,
        "lesson_id": 5,
        "teacher_id": 77,
        "groups_id": '["902"]',
        "students_id": students,
        "semestr": 14,
        "fake": 0,
        "sonra_sil": 0,
        "active": active,
        "fenn_saati": 45,
        "kredit": 5,
        "sillabus_id": None,
    }


class DeltaHomeJournalTests(TestCase):
    setUpTestData = classmethod(base.DeltaApplyTests.setUpTestData.__func__)

    @classmethod
    def _sibling(cls):
        with bypass_rls():
            return OrgUnit.objects.create(
                organization=cls.org, name="101 B", slug="d-g-b", unit_type="group", parent=cls.specialty
            )

    def _run(self, bundle, *, apply=True):
        with bypass_rls():
            return execute(
                organization=self.org, actor=self.actor, bundle=bundle, apply=apply, until=UNTIL, tag="delta-home"
            )

    def _bundle(self, journal, extra_points, extra_dates=()):
        bundle = _bundle()
        bundle["groups"].append(_SIBLING)
        bundle["journals"].insert(0, journal)
        bundle["points"] += extra_points
        bundle["lesson_dates"] += list(extra_dates)
        return bundle

    def test_twin_journal_processed_first_does_not_capture_the_student(self):
        sibling = self._sibling()
        journal = _twin_journal()
        bundle = self._bundle(
            journal,
            # Aysel paralel qrupun jurnalında: başqa saatda qalıq «qb» + B qrupunun dərsində bal.
            [
                _point(40, "1", "07", "13:35", "qb", uniqid=journal["uniqid"]),
                _point(41, "1", "06", "09:00", "9", uniqid=journal["uniqid"]),
            ],
            [{"id": 40, "journal_id": 10, "month": 10, "day": 7, "time": "13:35", "sem_muh": 0}],
        )
        run = self._run(bundle)
        with bypass_rls():
            own = CourseOffering.objects.get(organization=self.org, group=self.group, period=self.period)
            twin = CourseOffering.objects.get(organization=self.org, group=sibling, period=self.period)
            enrollments = Enrollment.objects.filter(student=self.existing, offering__period=self.period)
            self.assertEqual([e.offering_id for e in enrollments], [own.pk], "ev jurnalı (siyahı + çox xana) qalib")
            self.assertFalse(Lesson.objects.filter(offering=own, date=dt.date(2026, 10, 7)).exists(), "fantom yox")
            self.assertFalse(Lesson.objects.filter(offering=twin).exists())
            mark = LessonMark.objects.get(enrollment__student=self.existing, lesson__start_time=dt.time(9, 0))
            # Eyni tarix + saatdakı MÖVCUD dərsə düşən əkiz xana (J-V4: əsl jurnalın 8-i ilə eyni xana — mövcud qalır).
            self.assertEqual(mark.lesson.offering_id, own.pk)
            self.assertEqual(mark.score, Decimal("8"))
        self.assertEqual(run.counters["cell.cross_journal_skipped"], 1)
        self.assertEqual(run.counters["enrollment.twin_journal_to_home"], 1)
        again = self._run(bundle)
        self.assertEqual({k: v for k, v in again.counters.items() if k.startswith("written.")}, {})

    def test_inactive_journal_is_ignored_for_selection(self):
        self._sibling()
        journal = _twin_journal(active=0, students='["1","2"]', uniqid="oldB000001")
        bundle = self._bundle(journal, [_point(42, "1", "08", "11:50", "7", uniqid=journal["uniqid"])])
        run = self._run(bundle)
        with bypass_rls():
            offerings = set(
                Enrollment.objects.filter(student=self.existing, offering__period=self.period).values_list(
                    "offering__group__name", flat=True
                )
            )
            self.assertEqual(offerings, {"101 A"})
            self.assertFalse(Lesson.objects.filter(date=dt.date(2026, 10, 8)).exists())
        self.assertEqual(run.counters["enrollment.inactive_journal_to_home"], 2)
        self.assertEqual(run.counters["cell.cross_journal_skipped"], 1)

    def test_subgroup_lab_journal_still_merges_into_the_home_offering(self):
        """Tamamlayıcı jurnal (ana qrupun alt qrupu, legacy kod 2 = laboratoriya) əkiz SAYILMIR."""
        lab = {**_twin_journal(students='["2"]', uniqid="labA100001"), "id": 12, "groups_id": '["901"]'}
        bundle = _bundle()
        bundle["journals"].append(lab)
        bundle["points"].append({**_point(43, "2", "09", "15:15", "6", uniqid="labA100001"), "sem_muh": 2})
        bundle["lesson_dates"].append({"id": 43, "journal_id": 12, "month": 10, "day": 9, "time": "15:15"})
        run = self._run(bundle)
        with bypass_rls():
            lesson = Lesson.objects.get(date=dt.date(2026, 10, 9))
            self.assertEqual(lesson.kind, "lab")
            self.assertEqual(lesson.offering.group_id, self.group.pk)
            self.assertEqual(lesson.marks.get().score, Decimal("6"))
        self.assertEqual(run.counters.get("cell.cross_journal_skipped", 0), 0)


class LegacyLessonKindCodeTests(TestCase):
    def test_code_two_is_laboratory_and_three_stays_seminar(self):
        self.assertEqual(cell_kind(lab=0, sem_muh=2), "lab")
        self.assertEqual(cell_kind(lab=0, sem_muh=3), "seminar")
        self.assertEqual(cell_kind(lab=0, sem_muh=0), "seminar")
        self.assertEqual(cell_kind(lab=0, sem_muh=1), "lecture")
        self.assertEqual(cell_kind(lab=1, sem_muh=1), "lab")
