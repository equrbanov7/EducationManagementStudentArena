"""``infer_timetable_from_lessons`` — 2026-10-25 qaydaları (sahib: «jurnalı ÇOXLUQ olaraq yazdığı dərs saatlarına əsasən,
alt-üst həftə və s. hər şey nəzərə alınaraq dərs cədvəlini yarat»).

Dövr 6 həftə əvvəlki bazar ertəsi başlayır (1-ci həftə = üst/odd):

* B.c.a. 08:30 — A müəllimi «Dil-1(elementary)» məşğələsini G1 + G2-yə BİRGƏ keçir (birgə məşğələ = axın);
  həmin saatda B müəllimi G1-in «Dil-1(intermediate)» səviyyə qrupunu (paralel — qrup toqquşması deyil);
  A-nın G3-də bircə dəfə yazdığı «Kimya» dərsi axına QOŞULMUR (hədd altı);
* Ç. — C-nin G3 «Fizika» mühazirəsi: 1–3-cü həftə 11:30 (standartdan kənar), 4–6-cı 11:50 → bir slot 11:50–13:20;
* C.a. 10:10 — C-nin G3 «Fizika» seminarı 3 üst + 1 alt → üst (azlıq kompensasiya);
* B.e. 13:35 — D-nin G4 «Tarix» seminarı hər həftə (rəsmi cədvəldə «mühazirə» kimi var → ``exists_other_kind``);
  Cümə 15:15 — iki təsadüfi dərs → ``minority_slot``;
* B.c.a. 15:15 — E-nin G5 «Biologiya» mühazirəsi yalnız ötən həftə başlayıb → ``recent_start``;
* G6 «Hüquq» seminarı: F 1–2-ci həftə B.e. 10:10, sonra G (``Lesson.instructor``) Ç. 10:10 → köhnə ``teacher_changed``.
"""

from __future__ import annotations

import datetime
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit
from apps.registrar import schedule_conflicts, services, timetable_inference
from apps.registrar.models import Lesson, LessonKind, ScheduleSlot, SlotKind, Subject, WeekType
from core.constants import AcademicPeriodType, OrganizationType, OrgUnitType
from core.rls import bypass_rls

User = get_user_model()
T = datetime.time


def _counts(output: str) -> dict:
    counts = {}
    for line in output.splitlines():
        if line.startswith("timetable_infer: "):
            for pair in line.split(" ")[1:]:
                key, _sep, value = pair.partition("=")
                counts[key] = value
    return counts


class InferTimetableRulesTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        today = timezone.localdate()
        cls.start = today - datetime.timedelta(days=today.weekday() + 42)  # bazar ertəsi, 1-ci (üst) həftə
        owner = User.objects.create_user("itr_owner", "itr_owner@qku.edu.az", "pw")
        cls.t = {
            key: User.objects.create_user(f"itr.{key}", f"itr_{key}@qku.edu.az", "pw")
            for key in ("a", "b", "c", "d", "e", "f", "g")
        }
        with bypass_rls():
            cls.org = Organization.objects.create(
                name="ITR Univ",
                slug="itr-univ",
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
            role = cls.org.roles.get(name="teacher")
            for user in cls.t.values():
                Membership.objects.create(user=user, organization=cls.org, role=role, is_primary=True)
            groups = {
                index: OrgUnit.objects.create(
                    organization=cls.org, name=f"R{index}", slug=f"itr-g{index}", unit_type=OrgUnitType.GROUP
                )
                for index in range(1, 7)
            }
            subjects = {
                key: Subject.objects.create(organization=cls.org, code=f"ITR{index}", name=name)
                for index, (key, name) in enumerate(
                    (
                        ("elem", "Dil-1(elementary)"),
                        ("inter", "Dil-1 (intermediate)"),
                        ("chem", "Kimya"),
                        ("phys", "Fizika"),
                        ("hist", "Tarix"),
                        ("bio", "Biologiya"),
                        ("law", "Hüquq"),
                    )
                )
            }

            def offering(subject, group, teacher):
                row = services.get_or_create_offering(
                    organization=cls.org, subject=subjects[subject], period=cls.period, group=groups[group]
                )
                row.instructor = cls.t[teacher]
                row.save(update_fields=["instructor"])
                return row

            cls.o = {
                "elem1": offering("elem", 1, "a"),
                "elem2": offering("elem", 2, "a"),
                "inter1": offering("inter", 1, "b"),
                "chem3": offering("chem", 3, "a"),
                "phys3": offering("phys", 3, "c"),
                "hist4": offering("hist", 4, "d"),
                "bio5": offering("bio", 5, "e"),
                "law6": offering("law", 6, "f"),
            }

            def lessons(key, weekday, start, kind, weeks, instructor=None):
                for week in weeks:
                    Lesson.objects.create(
                        organization=cls.org,
                        offering=cls.o[key],
                        date=cls.start + datetime.timedelta(days=7 * (week - 1) + weekday - 1),
                        kind=kind,
                        start_time=start,
                        instructor=instructor,
                    )

            seminar, lecture = LessonKind.SEMINAR, LessonKind.LECTURE
            lessons("elem1", 2, T(8, 30), seminar, range(1, 7))
            lessons("elem2", 2, T(8, 30), seminar, range(1, 7))
            lessons("inter1", 2, T(8, 30), seminar, range(1, 7))
            lessons("chem3", 2, T(8, 30), seminar, (2,))
            lessons("phys3", 3, T(11, 30), lecture, (1, 2, 3))
            lessons("phys3", 3, T(11, 50), lecture, (4, 5, 6))
            lessons("phys3", 4, T(10, 10), seminar, (1, 2, 3, 5))
            lessons("hist4", 1, T(13, 35), seminar, range(1, 7))
            lessons("hist4", 5, T(15, 15), seminar, (2, 3))
            lessons("bio5", 2, T(15, 15), lecture, (6,))
            lessons("law6", 1, T(10, 10), seminar, (1, 2))
            lessons("law6", 3, T(10, 10), seminar, range(3, 7), instructor=cls.t["g"])
            cls.official = ScheduleSlot.objects.create(
                organization=cls.org,
                offering=cls.o["hist4"],
                weekday=1,
                start_time=T(13, 35),
                end_time=T(15, 5),
                kind=SlotKind.LECTURE,
            )

    def _call(self, *args) -> dict:
        out = StringIO()
        call_command(
            "infer_timetable_from_lessons", "--org", "itr-univ", "--period", "Payız 2026/2027", *args, stdout=out
        )
        return _counts(out.getvalue())

    def _slots(self, key):
        with bypass_rls():
            return list(
                ScheduleSlot.objects.filter(offering=self.o[key])
                .exclude(pk=self.official.pk)
                .order_by("weekday", "start_time")
                .values_list("weekday", "start_time", "end_time", "kind", "week_type", "instructor_id")
            )

    def test_dry_run_counts(self):
        counts = self._call()
        self.assertEqual(
            (counts["create"], counts["exists"], counts["conflict"], counts["superseded"], counts["below_threshold"]),
            ("7", "1", "0", "2", "1"),
        )
        self.assertEqual((counts["streams"], counts["stream_groups"], counts["snapped"]), ("1", "2", "3"))
        for reason in ("exists_other_kind", "minority_slot", "teacher_changed", "recent_start"):
            self.assertEqual(counts[f"reason_{reason}"], "1", reason)
        self.assertNotIn("reason_stream_mixed_subjects", counts)  # birdəfəlik «Kimya» axına yapışmır

    def test_apply_writes_expected_week(self):
        counts = self._call("--apply", "--i-know-this-is-production")
        self.assertEqual(counts["written"], "7")
        joint = (2, T(8, 30), T(10, 0), SlotKind.SEMINAR, WeekType.ALL, None)
        self.assertEqual(self._slots("elem1"), [joint])  # birgə məşğələ — iki qrup, bir saat
        self.assertEqual(self._slots("elem2"), [joint])
        self.assertEqual(self._slots("inter1"), [joint])  # səviyyə qrupu paralel
        self.assertEqual(self._slots("chem3"), [])
        self.assertEqual(
            self._slots("phys3"),
            [
                (3, T(11, 50), T(13, 20), SlotKind.LECTURE, WeekType.ALL, None),  # 11:30 → standart zəng
                (4, T(10, 10), T(11, 40), SlotKind.SEMINAR, WeekType.ODD, None),  # 3 üst + 1 alt → üst
            ],
        )
        self.assertEqual(self._slots("hist4"), [])  # B.e. rəsmi slot var (növ fərqli), Cümə azlıqdır
        self.assertEqual(self._slots("bio5"), [(2, T(15, 15), T(16, 45), SlotKind.LECTURE, WeekType.ALL, None)])
        self.assertEqual(
            self._slots("law6"), [(3, T(10, 10), T(11, 40), SlotKind.SEMINAR, WeekType.ALL, self.t["g"].pk)]
        )
        with bypass_rls():
            self.official.refresh_from_db()
        self.assertEqual(self.official.kind, SlotKind.LECTURE)  # mövcud slota toxunulmur
        self.assertEqual(self._call()["create"], "0")  # idempotent

    def test_flags_disable_rules(self):
        counts = self._call("--snap-minutes", "0", "--no-hours-cap", "--recent-days", "0")
        self.assertEqual(
            (counts["snapped"], counts.get("reason_minority_slot"), counts.get("reason_recent_start")),
            (
                "0",
                None,
                None,
            ),
        )

    def test_level_family_is_parallel_but_other_subject_clashes(self):
        self._call("--apply", "--i-know-this-is-production")
        with bypass_rls():
            other = Subject.objects.create(organization=self.org, code="ITR9", name="Riyaziyyat")
            kwargs = dict(
                organization=self.org,
                weekday=2,
                start_time=T(8, 30),
                end_time=T(10, 0),
                week_type=WeekType.ALL,
                group_id=self.o["elem1"].group_id,
                instructor_id=self.t["c"].pk,
                period_id=self.period.pk,
                kind=SlotKind.SEMINAR,
            )
            same_family = schedule_conflicts.detect(subject_id=self.o["inter1"].subject_id, **kwargs)
            unrelated = schedule_conflicts.detect(subject_id=other.pk, **kwargs)
        self.assertEqual(same_family, [])
        self.assertEqual([row["kind"] for row in unrelated], [schedule_conflicts.KIND_GROUP])


class InferenceRuleUnitsTest(SimpleTestCase):
    def test_snap_and_fallback_end(self):
        snap = timetable_inference.snap_to_bell
        self.assertEqual(snap(T(11, 30), None, 25), (T(11, 50), T(13, 20)))
        self.assertEqual(snap(T(10, 0), None, 25), (T(10, 10), T(11, 40)))
        self.assertEqual(snap(T(12, 40), None, 25), (T(12, 40), None))  # uzaqdır — olduğu kimi
        self.assertEqual(snap(T(11, 30), None, 0), (T(11, 30), None))
        self.assertEqual(timetable_inference.fallback_end(T(9, 0)), T(10, 30))
        self.assertEqual(timetable_inference.fallback_end(T(19, 0)), T(20, 20))

    @staticmethod
    def _unit(weekday, count, week_type=WeekType.ALL):
        start = datetime.date(2026, 9, 14) + datetime.timedelta(days=weekday - 1)
        days = {start + datetime.timedelta(days=7 * week) for week in range(count)}
        unit = timetable_inference.Unit(teacher_id=1, weekday=weekday, start=T(8, 30), kind=SlotKind.SEMINAR)
        unit.members, unit.week_type = {"o1": days}, week_type
        return unit

    def _budget(self, budgets):
        units = [self._unit(1, 6), self._unit(2, 5), self._unit(3, 2)]
        timetable_inference.apply_weekly_budget(units, budgets)
        return [unit.reason for unit in units]

    def test_weekly_budget_majority(self):
        self.assertEqual(self._budget({("o1", "seminar"): 1.0}), ["", "", "over_weekly_hours"])
        self.assertEqual(self._budget({("o1", "seminar"): 3.0}), ["", "", ""])
        self.assertEqual(self._budget({}), ["", "", "minority_slot"])
