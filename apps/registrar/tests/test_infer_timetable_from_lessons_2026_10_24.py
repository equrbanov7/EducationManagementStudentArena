"""``infer_timetable_from_lessons`` — keçirilmiş dərslərdən canlı cədvəl slotları (sahib 2026-10-24).

Dövr 6 həftə əvvəlki bazar ertəsi başlayır (1-ci həftə = üst/odd). Müəllim ``T``:

* B.e. 08:30 — «Fizika» mühazirəsi 3 qrupa BİRLİKDƏ (axın), 1–6-cı həftələr, otaq «A-101» → 3 slot, hər həftə;
* Ç.a. 10:10 — G1 seminarı yalnız üst (1, 3, 5), G2 seminarı yalnız alt (2, 4, 6) həftələrdə → odd / even;
* Ç. 11:50 — G3 seminarı hər həftə → all;
* C.a. 13:35 — G1 seminarı bircə dəfə (2-ci həftə) → hədd altı, slot yox;
* Cümə 08:30 — G1 mühazirəsi 3 dəfə, amma G1-in həmin saatda başqa müəllimlə mövcud slotu var → toqquşma.
"""

from __future__ import annotations

import csv
import datetime
import pathlib
import re
import tempfile
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import CommandError, call_command
from django.test import TestCase
from django.utils import timezone

from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit
from apps.registrar import services, timetable_inference
from apps.registrar.models import Lesson, LessonKind, ScheduleSlot, SlotKind, Subject, WeekType
from core.constants import AcademicPeriodType, OrganizationType, OrgUnitType
from core.rls import bypass_rls

User = get_user_model()
T = datetime.time
WORKFLOW = pathlib.Path(__file__).resolve().parents[3] / ".github" / "workflows" / "prod-data-ops.yml"


class InferTimetableFromLessonsTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        today = timezone.localdate()
        cls.start = today - datetime.timedelta(days=today.weekday() + 42)  # bazar ertəsi, 1-ci (üst) həftə
        cls.owner = User.objects.create_user("itt_owner", "itt_owner@qku.edu.az", "pw")
        cls.teacher = User.objects.create_user("itt.teacher", "itt_teacher@qku.edu.az", "pw")
        cls.other = User.objects.create_user("itt.other", "itt_other@qku.edu.az", "pw")
        with bypass_rls():
            cls.org = Organization.objects.create(
                name="ITT Univ",
                slug="itt-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=cls.owner,
                status="active",
                is_active=True,
            )
            cls.period = AcademicPeriod.objects.create(
                organization=cls.org,
                name="Payız",
                period_type=AcademicPeriodType.SEMESTER,
                academic_year="2026/2027",
                start_date=cls.start,
                end_date=today + datetime.timedelta(days=60),
                is_current=True,
            )
            for user in (cls.teacher, cls.other):
                Membership.objects.create(
                    user=user, organization=cls.org, role=cls.org.roles.get(name="teacher"), is_primary=True
                )
            cls.groups = [
                OrgUnit.objects.create(
                    organization=cls.org, name=f"23{i} K", slug=f"itt-23{i}k", unit_type=OrgUnitType.GROUP
                )
                for i in (1, 2, 3)
            ]
            physics = Subject.objects.create(organization=cls.org, code="ITT101", name="Fizika")
            history = Subject.objects.create(organization=cls.org, code="ITT102", name="Tarix")
            cls.offerings = []
            for group in cls.groups:
                offering = services.get_or_create_offering(
                    organization=cls.org, subject=physics, period=cls.period, group=group
                )
                offering.instructor = cls.teacher
                offering.save(update_fields=["instructor"])
                cls.offerings.append(offering)
            g1, g2, g3 = cls.offerings
            cls.history = services.get_or_create_offering(
                organization=cls.org, subject=history, period=cls.period, group=cls.groups[0]
            )
            cls.history.instructor = cls.other
            cls.history.save(update_fields=["instructor"])
            room = cls.org.exam_rooms.create(name="A-101", code="RA101", building="Korpus A", is_active=True)

            def lessons(offering, weekday, start, end, kind, weeks, room=None):
                for week in weeks:
                    Lesson.objects.create(
                        organization=cls.org,
                        offering=offering,
                        date=cls.start + datetime.timedelta(days=7 * (week - 1) + weekday - 1),
                        kind=kind,
                        start_time=start,
                        end_time=end,
                        room=room,
                    )

            for offering in cls.offerings:
                lessons(offering, 1, T(8, 30), T(10, 0), LessonKind.LECTURE, range(1, 7), room=room)
            lessons(g1, 2, T(10, 10), T(11, 40), LessonKind.SEMINAR, (1, 3, 5))
            lessons(g2, 2, T(10, 10), T(11, 40), LessonKind.SEMINAR, (2, 4, 6))
            lessons(g3, 3, T(11, 50), T(13, 20), LessonKind.SEMINAR, range(1, 7))
            lessons(g1, 4, T(13, 35), T(15, 5), LessonKind.SEMINAR, (2,))
            lessons(g1, 5, T(8, 30), T(10, 0), LessonKind.LECTURE, (1, 2, 3))
            # Cədvəldən kənar (kompensasiya) dərsi — sayılır, amma slot üçün işlənmir.
            Lesson.objects.create(
                organization=cls.org,
                offering=g2,
                date=cls.start + datetime.timedelta(days=5),
                kind=LessonKind.SEMINAR,
                start_time=T(15, 15),
                end_time=T(16, 45),
                off_schedule_reason="Kompensasiya",
            )
            cls.blocking = ScheduleSlot.objects.create(
                organization=cls.org,
                offering=cls.history,
                weekday=5,
                start_time=T(8, 30),
                end_time=T(10, 0),
                kind=SlotKind.LECTURE,
            )

    def _call(self, *args) -> str:
        out = StringIO()
        call_command(
            "infer_timetable_from_lessons", "--org", "itt-univ", "--period", "Payız 2026/2027", *args, stdout=out
        )
        return out.getvalue()

    @staticmethod
    def _counts(output: str) -> dict:
        counts = {}
        for line in output.splitlines():
            if line.startswith("timetable_infer: "):
                for pair in line.split(" ")[1:]:
                    key, _sep, value = pair.partition("=")
                    counts[key] = value
        return counts

    def _slots(self, **filters):
        with bypass_rls():
            return list(
                ScheduleSlot.objects.filter(organization=self.org, **filters)
                .exclude(pk=self.blocking.pk)
                .select_related("offering")
                .order_by("weekday", "start_time", "offering__group__name")
            )

    def test_dry_run_writes_nothing_and_prints_only_counts(self):
        output = self._call()
        self.assertEqual(self._slots(), [])
        counts = self._counts(output)
        self.assertEqual(counts["mode"], "dry_run")
        # 3 axın qrupu + G1 odd + G2 even + G3 all = 6 yaradılacaq; Cümə mühazirəsi toqquşur; C.a. hədd altı.
        self.assertEqual(counts["create"], "6")
        self.assertEqual(counts["conflict"], "1")
        self.assertEqual(counts["below_threshold"], "1")
        self.assertEqual(counts["streams"], "1")
        self.assertEqual(counts["stream_groups"], "3")
        self.assertEqual(counts["off_schedule"], "1")
        self.assertEqual(counts["reason_clash_group"], "1")
        for username in ("itt.teacher", "itt.other", "itt_owner", "231 K", "Fizika"):
            self.assertNotIn(username, output)
        for line in output.splitlines():
            self.assertRegex(line, r"^timetable_infer: [a-z_]+=[0-9a-z_-]+( [a-z_]+=[0-9a-z_-]+)*$")

    def test_apply_creates_weekly_upper_lower_and_one_stream(self):
        output = self._call("--apply", "--i-know-this-is-production")
        self.assertEqual(self._counts(output)["written"], "6")
        g1, g2, g3 = self.offerings
        stream = self._slots(weekday=1)
        self.assertEqual([slot.offering_id for slot in stream], [g1.pk, g2.pk, g3.pk])
        for slot in stream:  # axın bölünmür: eyni gün/saat/həftə/otaq, eyni müəllim, mühazirə
            self.assertEqual(
                (slot.start_time, slot.end_time, slot.week_type, slot.kind, slot.room),
                (T(8, 30), T(10, 0), WeekType.ALL, SlotKind.LECTURE, "A-101"),
            )
            self.assertIsNone(slot.instructor_id)  # jurnal sahibi = müəllim → NULL
        tuesday = {slot.offering_id: slot for slot in self._slots(weekday=2)}
        self.assertEqual(tuesday[g1.pk].week_type, WeekType.ODD)
        self.assertEqual(tuesday[g2.pk].week_type, WeekType.EVEN)
        self.assertEqual({slot.kind for slot in tuesday.values()}, {SlotKind.SEMINAR})
        # Seminarın öz otağı yoxdur → müəllimin ən çox yazdığı otaq (2026-10-25 qaydası).
        self.assertEqual(tuesday[g1.pk].room, "A-101")
        (wednesday,) = self._slots(weekday=3)
        self.assertEqual((wednesday.offering_id, wednesday.week_type), (g3.pk, WeekType.ALL))
        self.assertEqual(self._slots(weekday=4), [])  # birdəfəlik dərs
        self.assertEqual(self._slots(weekday=5), [])  # toqquşma — mövcud slot qalır, yenisi yox
        with bypass_rls():
            self.assertTrue(ScheduleSlot.objects.filter(pk=self.blocking.pk, is_deleted=False).exists())

    def test_rerun_is_idempotent(self):
        self._call("--apply", "--i-know-this-is-production")
        counts = self._counts(self._call("--apply", "--i-know-this-is-production"))
        self.assertEqual((counts["create"], counts["exists"], counts["written"]), ("0", "6", "0"))
        self.assertEqual(len(self._slots()), 6)

    def test_existing_slot_not_duplicated_or_changed(self):
        g3 = self.offerings[2]
        with bypass_rls():
            existing = ScheduleSlot.objects.create(
                organization=self.org,
                offering=g3,
                weekday=3,
                start_time=T(11, 50),
                end_time=T(13, 20),
                kind=SlotKind.SEMINAR,
                room="B-7",
            )
        counts = self._counts(self._call("--apply", "--i-know-this-is-production"))
        self.assertEqual((counts["create"], counts["exists"]), ("5", "1"))
        (wednesday,) = self._slots(weekday=3)
        self.assertEqual((wednesday.pk, wednesday.room), (existing.pk, "B-7"))

    def test_teacher_conflict_skips_whole_stream(self):
        """Axının bir qrupu toqquşursa bütün axın yazılmır (yarımçıq axın yaranmır)."""
        with bypass_rls():
            group = OrgUnit.objects.create(
                organization=self.org, name="239 X", slug="itt-239x", unit_type=OrgUnitType.GROUP
            )
            other_subject = Subject.objects.create(organization=self.org, code="ITT109", name="Kimya")
            busy = services.get_or_create_offering(
                organization=self.org, subject=other_subject, period=self.period, group=group
            )
            busy.instructor = self.teacher
            busy.save(update_fields=["instructor"])
            ScheduleSlot.objects.create(
                organization=self.org,
                offering=busy,
                weekday=1,
                start_time=T(8, 30),
                end_time=T(10, 0),
                kind=SlotKind.LECTURE,
            )
        counts = self._counts(self._call("--apply", "--i-know-this-is-production"))
        self.assertEqual(counts["reason_clash_teacher"], "3")
        self.assertEqual(self._slots(weekday=1, offering__group__in=self.groups), [])

    def test_teacher_filter_and_threshold(self):
        counts = self._counts(self._call("--teacher", "itt.other"))
        self.assertEqual((counts["lessons"], counts["units"], counts["create"]), ("0", "0", "0"))
        counts = self._counts(self._call("--min-occurrences", "4"))
        # Ç.a. üst/alt seminarlar (3 tarix) və Cümə (3 tarix) indi hədd altıdır; axın + G3 (6 tarix) qalır.
        self.assertEqual(counts["create"], "4")

    def test_report_csv_and_errors(self):
        with tempfile.TemporaryDirectory() as folder:
            path = pathlib.Path(folder) / "tt.csv"
            self._call("--report", str(path))
            with path.open(encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
        self.assertEqual(len(rows), 8)
        stream_rows = [row for row in rows if row["weekday"] == "1"]
        self.assertEqual({row["stream_size"] for row in stream_rows}, {"3"})
        self.assertEqual({row["teacher"] for row in stream_rows}, {"itt.teacher"})
        with self.assertRaises(CommandError):
            self._call("--teacher", "yoxdur")
        with self.assertRaises(CommandError):
            self._call("--date-from", "2026-13-01")
        with self.assertRaisesMessage(CommandError, "timetable_infer_target_not_disposable"):
            self._call("--apply")  # real (markersiz) baza — açıq təsdiq lazımdır
        self.assertEqual(self._slots(), [])


class MovedClassLatestWinsTest(TestCase):
    """«Sonuncu qalib»: B.e. 08:30 (1–4-cü həftə) → B.e. 10:10 (5–8-ci həftə) köçürülüb — yalnız 10:10 yazılır;
    başqa qrupun B.e. + C.a. mühazirələri (aralıqlar kəsişir) hər ikisi qalır."""

    @classmethod
    def setUpTestData(cls):
        today = timezone.localdate()
        cls.start = today - datetime.timedelta(days=today.weekday() + 63)  # 9 həftə əvvəl, 1-ci (üst) həftə
        owner = User.objects.create_user("mv_owner", "mv_owner@qku.edu.az", "pw")
        cls.teacher = User.objects.create_user("mv.teacher", "mv_teacher@qku.edu.az", "pw")
        with bypass_rls():
            cls.org = Organization.objects.create(
                name="MV Univ",
                slug="mv-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=owner,
                status="active",
                is_active=True,
            )
            cls.period = AcademicPeriod.objects.create(
                organization=cls.org,
                name="Payız",
                period_type=AcademicPeriodType.SEMESTER,
                academic_year="2026/2027",
                start_date=cls.start,
                end_date=today + datetime.timedelta(days=60),
                is_current=True,
            )
            Membership.objects.create(
                user=cls.teacher, organization=cls.org, role=cls.org.roles.get(name="teacher"), is_primary=True
            )
            subject = Subject.objects.create(organization=cls.org, code="MV101", name="Riyaziyyat")
            offerings = []
            for index in (1, 2):
                group = OrgUnit.objects.create(
                    organization=cls.org, name=f"24{index} M", slug=f"mv-24{index}m", unit_type=OrgUnitType.GROUP
                )
                offering = services.get_or_create_offering(
                    organization=cls.org, subject=subject, period=cls.period, group=group
                )
                offering.instructor = cls.teacher
                offering.save(update_fields=["instructor"])
                offerings.append(offering)
            cls.moved, cls.twice = offerings

            def lessons(offering, weekday, start, end, weeks):
                for week in weeks:
                    Lesson.objects.create(
                        organization=cls.org,
                        offering=offering,
                        date=cls.start + datetime.timedelta(days=7 * (week - 1) + weekday - 1),
                        kind=LessonKind.LECTURE,
                        start_time=start,
                        end_time=end,
                    )

            lessons(cls.moved, 1, T(8, 30), T(10, 0), range(1, 5))
            lessons(cls.moved, 1, T(10, 10), T(11, 40), range(5, 9))
            lessons(cls.twice, 1, T(13, 35), T(15, 5), range(1, 9))
            lessons(cls.twice, 4, T(13, 35), T(15, 5), range(1, 9))

    def test_moved_class_superseded_overlapping_kept(self):
        out = StringIO()
        call_command(
            "infer_timetable_from_lessons",
            "--org",
            "mv-univ",
            "--period",
            "Payız 2026/2027",
            "--apply",
            "--i-know-this-is-production",
            stdout=out,
        )
        counts = InferTimetableFromLessonsTest._counts(out.getvalue())
        self.assertEqual((counts["create"], counts["superseded"], counts["reason_moved_later"]), ("3", "1", "1"))
        with bypass_rls():
            moved = list(ScheduleSlot.objects.filter(offering=self.moved).values_list("weekday", "start_time"))
            twice = set(ScheduleSlot.objects.filter(offering=self.twice).values_list("weekday", "start_time"))
        self.assertEqual(moved, [(1, T(10, 10))])
        self.assertEqual(twice, {(1, T(13, 35)), (4, T(13, 35))})


class ParityRuleTest(TestCase):
    def test_decide_week_type(self):
        decide = timetable_inference.decide_week_type
        self.assertEqual(decide(3, 0), WeekType.ODD)
        self.assertEqual(decide(0, 2), WeekType.EVEN)
        self.assertEqual(decide(3, 3), WeekType.ALL)
        self.assertEqual(decide(1, 2), WeekType.ALL)
        self.assertEqual(decide(2, 5), WeekType.ALL)
        # 2026-10-25 çoxluq qaydası: azlıq paritet ≤ 25 % → kompensasiya, çoxluq qalib.
        self.assertEqual(decide(1, 3), WeekType.EVEN)
        self.assertEqual(decide(3, 1), WeekType.ODD)
        self.assertEqual(decide(2, 1), WeekType.ALL)
        self.assertEqual(decide(1, 3, 0.2), WeekType.ALL)
        self.assertEqual(decide(0, 0), "")


class InferTimetableWorkflowTest(TestCase):
    def test_workflow_whitelists_command_and_filters_counts(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("          - infer_timetable_from_lessons\n", text)
        pattern = re.search(r"grep -E '(\^timetable_infer: [^']+)'", text).group(1)
        self.assertRegex("timetable_infer: create=6 exists=0 conflict=1", pattern)
        self.assertRegex("timetable_infer: mode=dry_run from=2026-09-15 to=2026-10-24", pattern)
        self.assertNotRegex("timetable_infer: teacher=Ad Soyad", pattern)
