"""Cədvəl redaktoru — «Dərsi aparan müəllim» seçimi (bölünmüş tədris, 2026-09-25).

Nəyi qoruyur
------------
* siyahı yalnız bu açılışı APARA BİLƏNLƏRDİR: jurnal sahibi («Jurnal sahibi» sətri), dərs yükü
  bölgüsünün müəllimləri (ləğv edilmiş tapşırıq xaric), jurnalda dərs aparmış müəllimlər;
* seçim SERVERDƏ yoxlanır — ixtiyari / aktiv üzvlüyü olmayan müəllim 400, heç nə yazılmır;
* jurnal sahibinin özü seçiləndə NULL saxlanır; sürüklə-burax override-ı saxlayır;
* toqquşma slotun müəllimi ilə ölçülür; bildiriş slotun müəlliminə də gedir;
* HTTP səthi (`slot_teachers`, `check`) fail-closed; redaktor seçicini layihə komponenti ilə
  render edir; qrup görünüşünün sorğu sayı override-dan asılı deyil.
"""

from __future__ import annotations

import json

from django.db import connection
from django.test import override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.notifications.models import InAppNotification
from apps.organizations.models import Membership, OrgUnit
from apps.registrar import schedule_conflicts, schedule_editor
from apps.registrar import schedule_editor_actions as editor
from apps.registrar.models import CourseOffering, Lesson, ScheduleSlot, SlotKind
from apps.registrar.tests.test_schedule_slot_instructor import SlotInstructorBase as _SlotInstructorBase
from apps.registrar.tests.test_schedule_slot_instructor import User, _t
from apps.workload.constants import Activity, TaskStatus
from apps.workload.models import TeacherAssignment, TeachingTask, TeachingTaskRow
from core.constants import OrgUnitType
from core.rls import bypass_rls


@override_settings(UNIVERSITY_MODE=True)
class _EditorBase(_SlotInstructorBase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        with bypass_rls():
            cls.chair = OrgUnit.objects.create(
                organization=cls.org,
                parent=cls.faculty,
                name="Kafedra",
                slug=f"{cls.code}-chair",
                unit_type=OrgUnitType.CHAIR,
            )
            cls.coordinator = User.objects.create_user(f"{cls.code}_coord", f"{cls.code}_c@qku.edu.az", "pw")
            Membership.objects.create(
                user=cls.coordinator,
                organization=cls.org,
                role=cls.org.roles.get(name="program_coordinator"),
                scope_unit=cls.speciality,
                is_primary=True,
                is_active=True,
            )

    def _assign(self, teacher, *, subject=None, activity=Activity.SEMINAR, status=TaskStatus.DRAFT):
        # Bir kafedranın bir ildə TƏK tapşırığı var (`uniq_teaching_task_year_chair`) — statusa görə kafedra.
        chair = self.chair
        if status != TaskStatus.DRAFT:
            chair = OrgUnit.objects.create(
                organization=self.org,
                parent=self.faculty,
                name=f"Kafedra ({status})",
                slug=f"{self.code}-chair-{status}",
                unit_type=OrgUnitType.CHAIR,
            )
        task, _created = TeachingTask.objects.get_or_create(
            organization=self.org, chair=chair, academic_year="2026/2027", defaults={"status": status}
        )
        row = TeachingTaskRow.objects.create(
            organization=self.org,
            task=task,
            period=self.period,
            subject=subject or self.subject,
            lecture_plan=30,
            lecture_total=30,
            seminar_plan=30,
            seminar_total=30,
            total_hours=60,
        )
        row.groups.set([self.groups[0]])
        return TeacherAssignment.objects.create(
            organization=self.org, row=row, teacher=teacher, activity=activity, hours=30
        )

    def _payload(self, **overrides):
        data = {
            "group_id": str(self.groups[0].pk),
            "period_id": str(self.period.pk),
            "subject_id": str(self.subject.pk),
            "instructor_id": str(self.teacher_a.pk),
            "weekday": "1",
            "time_slot": "10:10|11:40",
            "week_type": "all",
            "slot_kind": SlotKind.SEMINAR,
            "room": "",
        }
        data.update(overrides)
        return data

    def _save(self, **overrides):
        return editor.save_cell(
            actor=self.coordinator,
            organization=self.org,
            group=self.groups[0],
            period=self.period,
            data=self._payload(**overrides),
        )

    def _act(self, user, payload):
        return self._client(user).post(
            reverse("accounts:schedule_editor_action"), data=json.dumps(payload), content_type="application/json"
        )


class PickerChoicesTest(_EditorBase):
    code = "sipick"

    def test_only_teachers_who_may_teach_the_offering_are_offered(self):
        with bypass_rls():
            self._assign(self.teacher_b)  # bölgü: seminar
            self._assign(self.teacher_c, status=TaskStatus.CANCELLED)  # ləğv edilmiş tapşırıq — sayılmır
            Lesson.objects.create(
                organization=self.org,
                offering=self.offering,
                date=self.today,
                kind=SlotKind.SEMINAR,
                hours=2,
                instructor=self.teacher_d,  # jurnalda dərs aparıb
            )
            options = schedule_editor.slot_teacher_options(
                organization=self.org,
                group=self.groups[0],
                period=self.period,
                subject_id=str(self.subject.pk),
                instructor_id="",
            )
        self.assertEqual(options["owner"], {"id": str(self.teacher_a.pk), "name": "Aytən Əliyeva"})
        self.assertEqual([row["id"] for row in options["teachers"]], [str(self.teacher_b.pk), str(self.teacher_d.pk)])

    def test_new_cell_is_computed_in_memory_without_creating_an_offering(self):
        with bypass_rls():
            self._assign(self.teacher_b, subject=self.subject_b)
            before = CourseOffering.objects.count()
            options = schedule_editor.slot_teacher_options(
                organization=self.org,
                group=self.groups[0],
                period=self.period,
                subject_id=str(self.subject_b.pk),
                instructor_id=str(self.teacher_c.pk),
            )
            after = CourseOffering.objects.count()
            broken = schedule_editor.slot_teacher_options(
                organization=self.org, group=self.groups[0], period=self.period, subject_id="abc"
            )
        self.assertEqual(options["owner"]["id"], str(self.teacher_c.pk))
        self.assertEqual([row["id"] for row in options["teachers"]], [str(self.teacher_b.pk)])
        self.assertEqual(before, after)
        self.assertEqual(broken, {"owner": None, "teachers": []})


class ServerValidationTest(_EditorBase):
    code = "sival"

    def test_random_teacher_is_refused_and_nothing_is_written(self):
        with bypass_rls():
            before = ScheduleSlot.objects.count()
            for raw in (str(self.teacher_c.pk), "abc"):
                with self.assertRaises(schedule_editor.CellError) as caught:
                    self._save(slot_instructor_id=raw)
                self.assertEqual(caught.exception.status, 400)
                self.assertIn("slot_instructor_id", caught.exception.errors)
            after = ScheduleSlot.objects.count()
        self.assertEqual(before, after)

    def test_invalid_choice_on_a_new_subject_creates_no_offering(self):
        with bypass_rls():
            before = CourseOffering.objects.count()
            with self.assertRaises(schedule_editor.CellError) as caught:
                self._save(
                    subject_id=str(self.subject_b.pk),
                    instructor_id=str(self.teacher_c.pk),
                    slot_instructor_id=str(self.teacher_d.pk),
                )
            after = CourseOffering.objects.count()
        self.assertIn("slot_instructor_id", caught.exception.errors)
        self.assertEqual(before, after)

    def test_allowed_teacher_is_stored_and_the_owner_choice_stays_null(self):
        with bypass_rls():
            self._assign(self.teacher_b)
            result = self._save(slot_instructor_id=str(self.teacher_b.pk))
            owner_row = self._save(slot_instructor_id=str(self.teacher_a.pk), weekday="2")["slot"]
            slot = ScheduleSlot.objects.select_related("offering").get(pk=result["slot"]["id"])
            owner_slot = ScheduleSlot.objects.get(pk=owner_row["id"])
        self.assertEqual(slot.instructor_id, self.teacher_b.pk)
        self.assertEqual(slot.offering.instructor_id, self.teacher_a.pk)  # jurnal sahibliyi toxunulmur
        self.assertEqual(result["slot"]["slot_instructor_id"], str(self.teacher_b.pk))
        self.assertEqual(result["slot"]["teacher"], "Bəhruz Həsənov")
        self.assertEqual(result["slot"]["instructor"], "Aytən Əliyeva")
        self.assertIsNone(owner_slot.instructor_id)
        self.assertEqual(owner_row["teacher"], "Aytən Əliyeva")

    def test_teacher_without_an_active_membership_is_refused(self):
        with bypass_rls():
            self._assign(self.teacher_b)
            Membership.objects.filter(organization=self.org, user=self.teacher_b).update(is_active=False)
            with self.assertRaises(schedule_editor.CellError) as caught:
                schedule_editor.resolve_slot_instructor(
                    offering=self.offering, data={"slot_instructor_id": str(self.teacher_b.pk)}
                )
        self.assertIn("slot_instructor_id", caught.exception.errors)

    def test_move_keeps_the_assistant(self):
        with bypass_rls():
            self._assign(self.teacher_b)
            created = self._save(slot_instructor_id=str(self.teacher_b.pk))["slot"]
            slot = editor.get_slot(self.org, created["id"])
            editor.move_slot(
                actor=self.coordinator,
                organization=self.org,
                slot=slot,
                data={"weekday": 3, "time_slot": "13:35|15:05"},
            )
            slot.refresh_from_db()
        self.assertEqual((slot.weekday, slot.start_time), (3, _t("13:35")))
        self.assertEqual(slot.instructor_id, self.teacher_b.pk)

    def test_conflict_is_measured_for_the_assistant_and_the_assistant_is_notified(self):
        with bypass_rls():
            self._assign(self.teacher_b)
            self._slot(self.offering_b, weekday=1)  # B həmin saatda öz qrupundadır (231B)
            with self.assertRaises(schedule_editor.CellError) as caught:
                self._save(slot_instructor_id=str(self.teacher_b.pk))
            # Jurnal sahibi A həmin saatda boşdur — seminarı A aparsa toqquşma yoxdur.
            self._save(slot_instructor_id="")
            self._save(slot_instructor_id=str(self.teacher_b.pk), weekday="4")
            notified = InAppNotification.objects.filter(
                recipient=self.teacher_b, metadata__event="schedule_changed"
            ).count()
        self.assertEqual(caught.exception.code, "conflict")
        self.assertEqual(caught.exception.status, 409)
        self.assertEqual(caught.exception.extra["conflicts"][0]["kind"], schedule_conflicts.KIND_TEACHER)
        self.assertEqual(notified, 1)


class EditorHttpTest(_EditorBase):
    code = "sihttp"

    def test_slot_teachers_action_and_server_side_check(self):
        with bypass_rls():
            self._assign(self.teacher_b)
        base = {"group_id": str(self.groups[0].pk), "period_id": str(self.period.pk)}
        listing = self._act(self.coordinator, {**base, "action": "slot_teachers", "subject_id": str(self.subject.pk)})
        refused = self._act(
            self.coordinator, {**self._payload(slot_instructor_id=str(self.teacher_c.pk)), "action": "check"}
        )
        allowed = self._act(
            self.coordinator, {**self._payload(slot_instructor_id=str(self.teacher_b.pk)), "action": "check"}
        )
        denied = self._act(self.teacher_a, {**base, "action": "slot_teachers", "subject_id": str(self.subject.pk)})
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(listing.json()["owner"]["id"], str(self.teacher_a.pk))
        self.assertEqual([row["id"] for row in listing.json()["teachers"]], [str(self.teacher_b.pk)])
        self.assertEqual(refused.status_code, 400)
        self.assertIn("slot_instructor_id", refused.json()["errors"])
        self.assertEqual(allowed.status_code, 200)
        self.assertTrue(allowed.json()["ok"])
        self.assertEqual(denied.status_code, 403)

    def _section(self):
        url = "%s?section=schedule-manage&sm_group=%s" % (reverse("accounts:profile"), self.groups[0].pk)
        return self._client(self.coordinator).get(url)

    def test_editor_renders_the_picker_and_the_effective_teacher(self):
        with bypass_rls():
            self._slot(self.offering, weekday=2, kind=SlotKind.SEMINAR, instructor=self.teacher_b)
        body = self._section().content.decode()
        self.assertIn('data-sedit-field="slot_instructor_id"', body)
        self.assertIn('id="sedit-slot-teacher"', body)
        self.assertIn("data-owner-label=", body)
        self.assertIn(f'data-slot-instructor-id="{self.teacher_b.pk}"', body)
        self.assertIn('data-slot-instructor-name="Bəhruz Həsənov"', body)
        self.assertIn('data-teacher="Bəhruz Həsənov"', body)
        # Layihə komponenti (xam <select> yox): seçici `bootstrap-single-select--ems` sarğısındadır.
        wrapper = body.split('id="sedit-slot-teacher"')[0][-240:]
        self.assertIn("bootstrap-single-select--ems", wrapper)

    def test_group_view_queries_do_not_grow_with_overrides(self):
        with bypass_rls():
            slots = [self._slot(self.offering, weekday=day, kind=SlotKind.SEMINAR) for day in (1, 2, 3)]
        self._section()  # isinmə
        with CaptureQueriesContext(connection) as plain:
            self._section()
        with bypass_rls():
            ScheduleSlot.objects.filter(pk__in=[slot.pk for slot in slots]).update(instructor=self.teacher_b)
        with CaptureQueriesContext(connection) as overridden:
            response = self._section()
        self.assertContains(response, 'data-teacher="Bəhruz Həsənov"')
        self.assertEqual(len(overridden), len(plain))
