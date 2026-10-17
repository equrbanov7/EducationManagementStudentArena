"""«Uyğun vaxtlar» + otaq tövsiyəsi (``registrar.schedule_suggest``, sahib 2026-10-17).

Nəyi qoruyur
------------
* şəbəkə üst/alt həftə paritetinə hörmət edir (üst həftə dərsi alt həftəni bloklamır);
* rejimlər: «hər ikisi» yalnız ortaq boş, «müəllim üçün» qrupu məşğul xananı da, «qrup üçün»
  müəllimi məşğul xananı da təklif edir; statuslar ``detect`` ilə eynidir;
* qısa siyahı qrupun dərsi olan günə bitişik xananı yeni gündən əvvəl qoyur;
* otaqlar: kiçik otaq sonda (xəbərdarlıqla), qrupun korpusu əvvəl, ən kiçik uyğun otaq əvvəl,
  laboratoriya dərsinə laboratoriya; tutulmuş otaq təklif olunmur; tutum məlum deyilsə bayraq;
* axın (birləşmiş mühazirə): qrup sayları cəmlənir, axının otağı məşğul sayılmır;
* HTTP: icazəsiz 403, əhatədən kənar qrup 403, naməlum semestr 404; sorğu sayı slot sayından asılı deyil.
"""

from __future__ import annotations

from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.exams.models import ExamRoom
from apps.organizations.models import Membership, OrgUnit
from apps.registrar import schedule_suggest, services
from apps.registrar.models import Enrollment, ScheduleSlot, SlotKind, WeekType
from apps.registrar.tests.test_schedule_slot_instructor import User, _t
from apps.registrar.tests.test_schedule_slot_instructor_editor import _EditorBase
from core.constants import OrgUnitType
from core.rls import bypass_rls

MONDAY_2 = (1, "10:10|11:40")


def _cell(result, weekday, time_slot):
    return next(row for row in result["cells"] if row["weekday"] == weekday and row["time_slot"] == time_slot)


class _SuggestBase(_EditorBase):
    code = "ssg"

    @classmethod
    def _students(cls, offering, count, tag):
        for index in range(count):
            student = User.objects.create_user(f"{cls.code}_{tag}{index}", f"{cls.code}_{tag}{index}@qku.edu.az", "pw")
            Membership.objects.create(
                user=student,
                organization=cls.org,
                role=cls.org.roles.get(name="student"),
                is_primary=True,
                is_active=True,
            )
            Enrollment.objects.create(organization=cls.org, student=student, offering=offering)

    @classmethod
    def _room(cls, name, capacity, building="Korpus B", notes=""):
        return ExamRoom.objects.create(
            organization=cls.org,
            name=name,
            code=f"{cls.code}-{name}".lower(),
            building=building,
            capacity=capacity,
            notes=notes,
            is_exam_hall=False,
        )

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        with bypass_rls():
            cls.org.settings = {
                **(cls.org.settings or {}),
                "campuses": [{"building": "Korpus B", "units": ["İxtisas"]}],
            }
            cls.org.save(update_fields=["settings"])
            cls._students(cls.offering, 25, "a")  # 231A — 25 tələbə
            for name, capacity, building, notes in (
                ("Böyük", 60, "Korpus B", ""),
                ("Uyğun", 30, "Korpus B", ""),
                ("Kiçik", 10, "Korpus B", ""),
                ("Uzaq", 30, "Korpus A", ""),
                ("Naməlum", 0, "Korpus B", ""),
                ("Lab-1", 30, "Korpus B", "Laboratoriya"),
            ):
                cls._room(name, capacity, building, notes)

    def _plan(self, **overrides):
        params = {
            "organization": self.org,
            "group": self.groups[0],
            "period_id": self.period.pk,
            "teacher_id": self.teacher_a.pk,
            "subject_id": self.subject.pk,
            "kind": SlotKind.SEMINAR,
            "week_type": WeekType.ALL,
            "offering_id": self.offering.pk,
        }
        params.update(overrides)
        with bypass_rls():
            return schedule_suggest.plan(**params)


class GridTest(_SuggestBase):
    code = "ssgg"

    def test_odd_week_lesson_does_not_block_the_even_week(self):
        with bypass_rls():
            self._slot(self.offering_c, week_type=WeekType.ODD)  # A-nın 231C dərsi, üst həftə
        even = _cell(self._plan(week_type=WeekType.EVEN), *MONDAY_2)
        odd = _cell(self._plan(week_type=WeekType.ODD), *MONDAY_2)
        every = _cell(self._plan(week_type=WeekType.ALL), *MONDAY_2)
        self.assertEqual(even["status"], schedule_suggest.STATUS_FREE)
        self.assertTrue(even["suggested"])
        self.assertEqual(odd["status"], schedule_suggest.STATUS_TEACHER)
        self.assertEqual(every["status"], schedule_suggest.STATUS_TEACHER)
        self.assertFalse(every["suggested"])
        self.assertTrue(every["reasons"])  # səbəb mətni (detect ilə eyni)

    def test_modes_change_which_cells_are_suggested(self):
        with bypass_rls():
            group_busy = services.get_or_create_offering(
                organization=self.org, subject=self.subject_b, period=self.period, group=self.groups[0]
            )
            group_busy.instructor = self.teacher_b
            group_busy.save(update_fields=["instructor"])
            self._slot(group_busy)  # B.e. 10:10 — qrup məşğul (B-nin dərsi)
            self._slot(self.offering_c, weekday=2)  # Ç.a. 10:10 — müəllim A məşğul (231C)
        teacher_cell, group_cell = (2, "10:10|11:40"), MONDAY_2
        both = self._plan()
        for_teacher = self._plan(mode=schedule_suggest.MODE_TEACHER)
        for_group = self._plan(mode=schedule_suggest.MODE_GROUP)
        self.assertEqual(_cell(both, *group_cell)["status"], schedule_suggest.STATUS_GROUP)
        self.assertEqual(_cell(both, *teacher_cell)["status"], schedule_suggest.STATUS_TEACHER)
        self.assertFalse(_cell(both, *group_cell)["suggested"])
        self.assertFalse(_cell(both, *teacher_cell)["suggested"])
        self.assertTrue(_cell(for_teacher, *group_cell)["suggested"])  # müəllim boşdur
        self.assertFalse(_cell(for_teacher, *teacher_cell)["suggested"])
        self.assertTrue(_cell(for_group, *teacher_cell)["suggested"])  # qrup boşdur
        self.assertFalse(_cell(for_group, *group_cell)["suggested"])
        self.assertEqual(for_group["mode"], schedule_suggest.MODE_GROUP)

    def test_top_list_prefers_compact_days(self):
        with bypass_rls():
            self._slot(self.offering, weekday=3, start="10:10", end="11:40", kind=SlotKind.LECTURE)
        top = self._plan(exclude_ids=())["top"]
        first = top[0]
        # Çərşənbə — qrupun artıq dərsi var; 08:30 və ya 11:50 bitişikdir (yeni gündən əvvəl).
        self.assertEqual(first["weekday"], 3)
        self.assertIn(first["time_slot"], {"08:30|10:00", "11:50|13:20"})
        self.assertTrue(all(row["status"] in ("free", "room") for row in top))
        self.assertLessEqual(len(top), schedule_suggest.TOP_LIMIT)


class RoomTest(_SuggestBase):
    code = "ssgr"

    def _rooms(self, **overrides):
        return self._plan(weekday=1, time_slot="10:10|11:40", **overrides)["rooms"]

    def test_capacity_then_campus_then_smallest_fitting(self):
        rooms = self._rooms()
        labels = [row["label"] for row in rooms["rows"]]
        self.assertEqual(rooms["size"], 25)
        self.assertEqual(labels[:2], ["Uyğun", "Böyük"])  # 30 < 60, hər ikisi Korpus B
        self.assertLess(labels.index("Naməlum"), labels.index("Uzaq"))  # öz korpusu başqa korpusdan əvvəl
        self.assertLess(labels.index("Uzaq"), labels.index("Kiçik"))  # kiçik otaq ən sonda
        small = next(row for row in rooms["rows"] if row["label"] == "Kiçik")
        self.assertIs(small["fits"], False)
        far = next(row for row in rooms["rows"] if row["label"] == "Uzaq")
        self.assertFalse(far["same_campus"])
        self.assertTrue(rooms["capacity_known"])
        self.assertEqual(self._plan()["campus"], "Korpus B")

    def test_lab_lessons_get_labs_and_busy_rooms_are_skipped(self):
        with bypass_rls():
            self._slot(self.offering_b, room="Uyğun")  # B.e. 10:10 «Uyğun» tutulub (başqa qrup)
        lab = self._rooms(kind=SlotKind.LAB)
        seminar = self._rooms()
        self.assertEqual(lab["rows"][0]["label"], "Lab-1")
        self.assertNotIn("Uyğun", [row["label"] for row in seminar["rows"]])
        self.assertEqual(seminar["rows"][0]["label"], "Böyük")
        busy = self._rooms(room="uyğun")
        self.assertTrue(busy["current_busy"])

    def test_unknown_capacity_is_flagged(self):
        with bypass_rls():
            ExamRoom.objects.filter(organization=self.org).update(capacity=0)
        rooms = self._rooms()
        self.assertFalse(rooms["capacity_known"])
        self.assertTrue(all(row["fits"] is None for row in rooms["rows"]))

    def test_joint_lecture_sums_group_sizes_and_keeps_the_stream_room(self):
        with bypass_rls():
            partner = services.get_or_create_offering(
                organization=self.org, subject=self.subject, period=self.period, group=self.groups[1]
            )
            partner.instructor = self.teacher_a
            partner.save(update_fields=["instructor"])
            self._students(partner, 20, "b")
            self._slot(partner, kind=SlotKind.LECTURE, room="Böyük")  # axın: A, SI101, 231B
        result = self._plan(kind=SlotKind.LECTURE, weekday=1, time_slot="10:10|11:40")
        rooms = result["rooms"]
        self.assertEqual(rooms["size"], 45)
        self.assertEqual(rooms["joint_groups"], ["231B"])
        self.assertEqual(rooms["stream_room"], "Böyük")
        self.assertEqual(rooms["rows"][0]["label"], "Böyük")  # 45 nəfərə yalnız 60-lıq sığır
        self.assertEqual(_cell(result, *MONDAY_2)["status"], schedule_suggest.STATUS_FREE)  # axın toqquşma deyil
        mismatch = self._plan(kind=SlotKind.LECTURE, room="Uyğun")
        self.assertEqual(_cell(mismatch, *MONDAY_2)["status"], schedule_suggest.STATUS_ROOM)


class EndpointTest(_SuggestBase):
    code = "ssge"

    def _body(self, **overrides):
        data = {**self._payload(), "action": "plan", "mode": "both"}
        data.update(overrides)
        return data

    def test_plan_endpoint_returns_grid_and_rooms(self):
        response = self._act(self.coordinator, self._body())
        self.assertEqual(response.status_code, 200, response.content)
        data = response.json()
        self.assertTrue(data["ok"])
        self.assertEqual(len(data["cells"]), 6 * len(data["periods"]))
        self.assertEqual(data["rooms"]["size"], 25)
        self.assertEqual(data["group_size"], 25)

    def test_permission_and_scope(self):
        outsider = User.objects.create_user(f"{self.code}_out", f"{self.code}_out@qku.edu.az", "pw")
        with bypass_rls():
            far = OrgUnit.objects.create(
                organization=self.org, name="Uzaq fakültə", slug=f"{self.code}-far", unit_type=OrgUnitType.FACULTY
            )
            far_group = OrgUnit.objects.create(
                organization=self.org, parent=far, name="999X", slug=f"{self.code}-999x", unit_type=OrgUnitType.GROUP
            )
        self.assertEqual(self._act(outsider, self._body()).status_code, 403)
        self.assertEqual(self._act(self.coordinator, self._body(group_id=str(far_group.pk))).status_code, 403)
        missing = self._act(self.coordinator, self._body(period_id="00000000-0000-0000-0000-000000000000"))
        self.assertEqual(missing.status_code, 404)
        self.assertEqual(self._act(self.coordinator, self._body(period_id="abc")).status_code, 404)

    def test_query_count_does_not_grow_with_slots(self):
        import json

        from django.urls import reverse

        client = self._client(self.coordinator)
        url = reverse("accounts:schedule_editor_action")

        def count():
            with CaptureQueriesContext(connection) as ctx:
                response = client.post(url, data=json.dumps(self._body()), content_type="application/json")
            self.assertEqual(response.status_code, 200, response.content)
            return len(ctx.captured_queries)

        count()  # isinmə: sessiya / profil keşləri
        before = count()
        with bypass_rls():
            for weekday in range(1, 6):
                self._slot(self.offering_c, weekday=weekday, start="13:35", end="15:05", room="Böyük")
                self._slot(self.offering_b, weekday=weekday, start="08:30", end="10:00", room="Uyğun")
        after = count()
        self.assertEqual(before, after)
        self.assertLessEqual(after, 30)

    def test_slot_being_edited_does_not_block_itself(self):
        with bypass_rls():
            slot = self._slot(self.offering, kind=SlotKind.SEMINAR, room="Uyğun")
        data = self._act(self.coordinator, self._body(slot_id=str(slot.pk), room="Uyğun")).json()
        self.assertEqual(_cell(data, *MONDAY_2)["status"], schedule_suggest.STATUS_FREE)
        self.assertIn("Uyğun", [row["label"] for row in data["rooms"]["rows"]])

    def test_rendered_dialog_has_the_planner(self):
        from django.urls import reverse

        url = "%s?section=schedule-manage&sm_group=%s" % (reverse("accounts:profile"), self.groups[0].pk)
        html = self._client(self.coordinator).get(url).content.decode()
        self.assertIn("data-sedit-plan", html)
        self.assertIn('data-sedit-plan-mode="teacher"', html)
        self.assertIn("schedule_editor_planner.js", html)
        self.assertNotIn("data-sedit-suggest-open", html)


def test_week_parity_helper_is_the_conflict_engine():
    """Şəbəkə öz parite qaydasını YAZMIR — ``schedule_conflicts.week_types_overlap``-i işlədir."""
    slot = ScheduleSlot(weekday=1, start_time=_t("10:10"), end_time=_t("11:40"), week_type=WeekType.ODD)
    assert schedule_suggest._overlaps(slot, 1, _t("10:10"), _t("11:40"), WeekType.EVEN) is False
    assert schedule_suggest._overlaps(slot, 1, _t("10:10"), _t("11:40"), WeekType.ALL) is True
