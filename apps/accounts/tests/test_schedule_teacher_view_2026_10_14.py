"""«Cədvəl idarəetməsi» — müəllim görünüşündə redaktə + toqquşma siyasəti (sahib, 2026-10-14).

Sahibin tələbi: «müəllim seçiləndə də yerini dəyişmək olmalıdır; müəllimin dərsləri üst-üstə
düşərsə xəbərdarlıq versin (başqa qrupa dərsi var deyə); üstünə klik edəndə modal açılsın;
sürüşdürüb dəyişmək işləsin».

Nəyi qoruyur
------------
* müəllim görünüşü `schedule.manage` daşıyana REDAKTORDUR (yalnız-oxu banneri yoxdur, dialoqda
  «Qrup» sahəsi var); müəllimin ƏHATƏDƏN KƏNAR dərsi detal kartıdır (`data-sgx-slot`);
* `schedule.view` daşıyanda bölmə yalnız-oxudur, kart klikində detal modalı render olunur;
* toqquşma siyasəti: müəllim/auditoriya → `force` + səbəb (parklanır, audit səbəblə); QRUP →
  heç vaxt məcburi deyil (409 `group_conflict`); əhatədən KƏNAR toqquşma → minimal açıqlama
  («fənn · qrup»), `force_allowed=False`, məcburi cəhd 403;
* üst/alt həftə toqquşmur; EYNİ açılışın paralel laboratoriyası (fərqli müəllim) qrup toqquşması deyil;
* sürüklə-buraxın quru yoxlaması (`check_move`) heç nə yazmır.
"""

from __future__ import annotations

import datetime

from django.conf import settings

from apps.audit.models import AuditLog
from apps.organizations.models import Membership, OrgUnit
from apps.registrar import schedule_conflicts, services
from apps.registrar.models import ScheduleSlot, Subject
from core.constants import OrgUnitType
from core.rls import bypass_rls

from .test_schedule_editor_ui import ScheduleEditorUIBase, User

PASSWORD = "StrongPass123!"


class TeacherViewBase(ScheduleEditorUIBase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        with bypass_rls():
            cls.other_faculty = OrgUnit.objects.create(
                organization=cls.org, name="Fakültə 2", slug="sedtv-fac2", unit_type=OrgUnitType.FACULTY
            )
            cls.outside_group = OrgUnit.objects.create(
                organization=cls.org,
                parent=cls.other_faculty,
                name="999Z",
                slug="sedtv-out",
                unit_type=OrgUnitType.GROUP,
            )
            cls.physics = Subject.objects.create(organization=cls.org, code="FIZ9", name="Gizli Fizika")
            cls.outside_offering = services.get_or_create_offering(
                organization=cls.org, subject=cls.physics, period=cls.period, group=cls.outside_group
            )
            cls.outside_offering.instructor = cls.teacher
            cls.outside_offering.save(update_fields=["instructor"])
            cls.outside_slot = ScheduleSlot.objects.create(
                organization=cls.org,
                offering=cls.outside_offering,
                weekday=3,
                start_time=datetime.time(11, 50),
                end_time=datetime.time(13, 20),
                kind="lab",
                room="GIZLI-7",
            )
            cls.viewer = User.objects.create_user("sedtv_viewer", "sedtv_v@qku.edu.az", PASSWORD)
            Membership.objects.create(
                user=cls.viewer,
                organization=cls.org,
                role=cls.org.roles.get(name="vice_rector"),
                is_primary=True,
                is_active=True,
            )

    def _teacher_view(self, user):
        return self._section(user, sm_view="teacher", sm_teacher=str(self.teacher.pk)).content.decode()

    def _lecture(self, offering, weekday=1, start=(10, 10), end=(11, 40), **extra):
        with bypass_rls():
            return ScheduleSlot.objects.create(
                organization=self.org,
                offering=offering,
                weekday=weekday,
                start_time=datetime.time(*start),
                end_time=datetime.time(*end),
                **extra,
            )


class TeacherViewEditableTest(TeacherViewBase):
    def test_manager_gets_an_editor_in_teacher_view(self):
        own = self._lecture(self.offering)
        body = self._teacher_view(self.coordinator)
        self.assertNotIn("Müəllim görünüşü yalnız-oxudur", body)
        self.assertIn('data-view="teacher"', body)
        self.assertIn('data-teacher-id="%s"' % self.teacher.pk, body)
        self.assertIn('data-sedit-field="group_id"', body)
        self.assertIn('data-sedit-slot="%s"' % own.pk, body)
        self.assertIn("data-sedit-new", body)
        # Kartlar HTML5 `draggable` deyil — köçürmə pointer modulundadır.
        self.assertNotIn('draggable="true"', body)
        self.assertIn("schedule_editor_move.js", body)

    def test_out_of_scope_lesson_is_a_details_card_not_an_editable_one(self):
        body = self._teacher_view(self.coordinator)
        self.assertIn("Gizli Fizika", body)
        self.assertNotIn('data-sedit-slot="%s"' % self.outside_slot.pk, body)
        self.assertIn("data-sgx-slot", body)
        self.assertIn("data-sgx-modal", body)

    def test_view_only_holder_sees_details_modal_and_no_editor(self):
        body = self._teacher_view(self.viewer)
        self.assertIn("data-sedit-read-only", body)
        self.assertIn("data-sgx-modal", body)
        self.assertNotIn('id="seditCell"', body)
        self.assertNotIn("data-sedit-new", body)

    def test_view_only_holder_cannot_write(self):
        own = self._lecture(self.offering)
        response = self._act(
            self.viewer,
            {"action": "move", "slot_id": str(own.pk), "weekday": 2, "time_slot": "10:10|11:40"},
        )
        self.assertEqual(response.status_code, 403)

    def test_teacher_view_save_uses_the_dialog_group(self):
        response = self._act(self.coordinator, self._cell(group_id=str(self.group_b.id), weekday=4))
        self.assertEqual(response.status_code, 200, response.content)
        with bypass_rls():
            slot = ScheduleSlot.objects.get(pk=response.json()["slot"]["id"])
        self.assertEqual(slot.offering.group_id, self.group_b.id)

    def test_teacher_view_save_into_an_outside_group_is_refused(self):
        response = self._act(self.coordinator, self._cell(group_id=str(self.outside_group.id), weekday=4))
        self.assertEqual(response.status_code, 403)

    def test_my_schedule_card_still_opens_the_details_modal(self):
        self._lecture(self.offering)
        body = self._section(self.teacher, section="my-schedule").content.decode()
        self.assertIn("data-sgx-slot", body)
        self.assertIn("data-sgx-modal", body)


class ConflictPolicyTest(TeacherViewBase):
    def _move(self, slot, user=None, **extra):
        payload = {"action": "move", "slot_id": str(slot.pk), "weekday": 1, "time_slot": "10:10|11:40"}
        payload.update(extra)
        return self._act(user or self.coordinator, payload)

    def test_group_clash_is_refused_even_with_force(self):
        with bypass_rls():
            other_subject = Subject.objects.create(organization=self.org, code="MAT1", name="Riyaziyyat")
            other = services.get_or_create_offering(
                organization=self.org, subject=other_subject, period=self.period, group=self.group
            )
        blocker = self._lecture(other, kind="seminar")
        mover = self._lecture(self.offering, weekday=2)
        response = self._move(mover, force="1", reason="Dekanlığın sərəncamı ilə məcburi köçürmə")
        self.assertEqual(response.status_code, 409)
        body = response.json()
        self.assertEqual(body["error"], "group_conflict")
        self.assertEqual(body["conflicts"][0]["kind"], "group")
        self.assertFalse(body["conflicts"][0]["can_force"])
        with bypass_rls():
            blocker.refresh_from_db()
            mover.refresh_from_db()
        self.assertFalse(blocker.is_parked)
        self.assertEqual(mover.weekday, 2)

    def test_teacher_clash_needs_confirmation_and_is_audited(self):
        blocker = self._lecture(self.offering_b, kind="seminar")
        mover = self._lecture(self.offering, weekday=2)
        check = self._act(
            self.coordinator,
            {"action": "check_move", "slot_id": str(mover.pk), "weekday": 1, "time_slot": "10:10|11:40"},
        ).json()
        self.assertEqual([row["kind"] for row in check["conflicts"]], ["teacher"])
        self.assertTrue(check["force_allowed"])
        self.assertIn("231B", check["conflicts"][0]["message"])
        with bypass_rls():
            mover.refresh_from_db()
        self.assertEqual(mover.weekday, 2, "check_move heç nə yazmamalıdır")

        self.assertEqual(self._move(mover).status_code, 409)
        reason = "Auditoriya təmiri — dekanlığın sərəncamı"
        forced = self._move(mover, force="1", reason=reason)
        self.assertEqual(forced.status_code, 200, forced.content)
        with bypass_rls():
            blocker.refresh_from_db()
            mover.refresh_from_db()
            audit = AuditLog.objects.filter(resource_id=str(mover.pk), action="update").order_by("-created_at").first()
        self.assertTrue(blocker.is_parked)
        self.assertEqual(mover.weekday, 1)
        self.assertEqual(audit.reason, reason)
        self.assertTrue(audit.new_values["forced"])
        self.assertEqual(audit.new_values["parked_slot_ids"], [str(blocker.pk)])

    def test_out_of_scope_teacher_clash_is_redacted_and_cannot_be_forced(self):
        mover = self._lecture(self.offering, weekday=2)
        payload = {"action": "check_move", "slot_id": str(mover.pk), "weekday": 3, "time_slot": "11:50|13:20"}
        check = self._act(self.coordinator, payload).json()
        self.assertEqual(len(check["conflicts"]), 1)
        row = check["conflicts"][0]
        self.assertEqual(row["kind"], "teacher")
        self.assertFalse(row["in_scope"])
        self.assertFalse(check["force_allowed"])
        self.assertEqual(row["slot_id"], "")
        self.assertEqual(row["instructor"], "")
        self.assertEqual(row["room"], "")
        self.assertIn("FIZ9", row["message"])
        self.assertIn("999Z", row["message"])
        self.assertNotIn("GIZLI-7", row["message"])

        forced = self._move(
            mover, weekday=3, time_slot="11:50|13:20", force="1", reason="Kənar fakültəni sındırmaq cəhdi"
        )
        self.assertEqual(forced.status_code, 403)
        with bypass_rls():
            self.outside_slot.refresh_from_db()
        self.assertFalse(self.outside_slot.is_parked)
        self.assertNotIn("GIZLI-7", forced.content.decode())

    def test_upper_and_lower_weeks_do_not_clash_on_move(self):
        self._lecture(self.offering_b, kind="seminar", week_type="odd")
        mover = self._lecture(self.offering, weekday=2, week_type="even")
        check = self._act(
            self.coordinator,
            {"action": "check_move", "slot_id": str(mover.pk), "weekday": 1, "time_slot": "10:10|11:40"},
        ).json()
        self.assertEqual(check["conflicts"], [])
        self.assertEqual(self._move(mover).status_code, 200)

    def test_parallel_subgroup_labs_of_one_offering_are_not_a_group_clash(self):
        with bypass_rls():
            assistant = User.objects.create_user("sedtv_assist", "sedtv_a@qku.edu.az", PASSWORD)
            Membership.objects.create(
                user=assistant,
                organization=self.org,
                role=self.org.roles.get(name="teacher"),
                is_primary=True,
                is_active=True,
            )
            first = self._lecture(self.offering, kind="lab", room="L-1")
            found = schedule_conflicts.detect(
                organization=self.org,
                weekday=1,
                start_time=datetime.time(10, 10),
                end_time=datetime.time(11, 40),
                week_type="all",
                room="L-2",
                group_id=self.group.id,
                instructor_id=assistant.pk,
                period_id=self.period.id,
                subject_id=self.subject.id,
                kind="lab",
                offering_id=self.offering.id,
            )
            same_teacher = schedule_conflicts.detect(
                organization=self.org,
                weekday=1,
                start_time=datetime.time(10, 10),
                end_time=datetime.time(11, 40),
                week_type="all",
                room="L-2",
                group_id=self.group.id,
                instructor_id=self.teacher.pk,
                period_id=self.period.id,
                subject_id=self.subject.id,
                kind="lab",
                offering_id=self.offering.id,
            )
        self.assertEqual(found, [], "paralel alt qrup laboratoriyası toqquşma deyil")
        self.assertEqual({row["kind"] for row in same_teacher}, {"teacher", "group"})
        self.assertTrue(first.pk)


class MoveAssetsTest(TeacherViewBase):
    def test_move_module_is_ajax_safe_and_has_no_html5_drag(self):
        js_dir = settings.BASE_DIR / "apps/accounts/static/accounts/js"
        move = (js_dir / "schedule_editor_move.js").read_text(encoding="utf-8")
        editor = (js_dir / "schedule_editor.js").read_text(encoding="utf-8")
        self.assertIn("pointerdown", move)
        self.assertIn("check_move", move)
        self.assertIn("window.EMSDelegate", move)
        self.assertNotIn("dragstart", editor)
        self.assertIn("window.EMSScheduleEditor", editor)
