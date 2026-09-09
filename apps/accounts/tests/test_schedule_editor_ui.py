"""«Cədvəl idarəetməsi» redaktoru + «Dərs cədvəli» — HTTP səviyyəsi.

Nəyi qoruyur (sahibin 2026-09-09 tələbləri)
-------------------------------------------
* bölmə TYUTORDA da açılır (rol pariteti) və slot OLMASA DA matris render olunur;
* boş xanadan slot yaratmaq, sürüşdürüb köçürmək, məcburi dəyişiklikdə toqquşan
  dərsi PARKLAMAQ (silmək YOX) və onu yenidən yerləşdirmək — hamısı TƏK JSON
  giriş nöqtəsindən (`accounts:schedule_editor_action`);
* tövsiyə yalnız boş hüceyrələri qaytarır;
* müəllim və tələbə yeni dərsi öz «Dərs cədvəli» ekranında EYNİ matrisdə görür;
* icazəsiz aktor 403 alır, heç nə sərt silinmir.
"""

from __future__ import annotations

import datetime
import json

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit
from apps.registrar import services
from apps.registrar.models import (
    AcademicStatus,
    Curriculum,
    CurriculumSubject,
    Program,
    ScheduleSlot,
    StudentAcademicRecord,
    Subject,
)
from core.constants import AcademicPeriodType, OrganizationType, OrgUnitType
from core.rls import bypass_rls

User = get_user_model()

PASSWORD = "StrongPass123!"
PROFILE = "accounts:profile"


@override_settings(UNIVERSITY_MODE=True)
class ScheduleEditorUIBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("sedui_owner", "sedui_owner@qku.edu.az", PASSWORD)
        with bypass_rls():
            cls.org = Organization.objects.create(
                name="SEDUI Univ",
                slug="sedui-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=cls.owner,
                status="active",
                is_active=True,
            )
            cls.faculty = OrgUnit.objects.create(
                organization=cls.org, name="Fakültə", slug="sedui-fac", unit_type=OrgUnitType.FACULTY
            )
            cls.speciality = OrgUnit.objects.create(
                organization=cls.org,
                parent=cls.faculty,
                name="İxtisas",
                slug="sedui-spec",
                unit_type=OrgUnitType.SPECIALTY,
            )
            cls.group = OrgUnit.objects.create(
                organization=cls.org,
                parent=cls.speciality,
                name="231A",
                slug="sedui-g1",
                unit_type=OrgUnitType.GROUP,
            )
            cls.group_b = OrgUnit.objects.create(
                organization=cls.org,
                parent=cls.speciality,
                name="231B",
                slug="sedui-g2",
                unit_type=OrgUnitType.GROUP,
            )
            cls.period = AcademicPeriod.objects.create(
                organization=cls.org,
                name="2025/2026 Payız",
                period_type=AcademicPeriodType.SEMESTER,
                academic_year="2025/2026",
                start_date=datetime.date.today() - datetime.timedelta(days=10),
                end_date=datetime.date.today() + datetime.timedelta(days=100),
                is_current=True,
            )
            cls.subject = Subject.objects.create(organization=cls.org, code="CS101", name="Proqramlaşdırma")

            cls.teacher = User.objects.create_user("sedui_teacher", "sedui_t@qku.edu.az", PASSWORD)
            cls.coordinator = User.objects.create_user("sedui_coord", "sedui_c@qku.edu.az", PASSWORD)
            cls.tutor = User.objects.create_user("sedui_tutor", "sedui_tu@qku.edu.az", PASSWORD)
            cls.student = User.objects.create_user("sedui_student", "sedui_s@qku.edu.az", PASSWORD)

            Membership.objects.create(
                user=cls.teacher,
                organization=cls.org,
                role=cls.org.roles.get(name="teacher"),
                is_primary=True,
                is_active=True,
            )
            Membership.objects.create(
                user=cls.coordinator,
                organization=cls.org,
                role=cls.org.roles.get(name="program_coordinator"),
                scope_unit=cls.speciality,
                is_primary=True,
                is_active=True,
            )
            Membership.objects.create(
                user=cls.tutor,
                organization=cls.org,
                role=cls.org.roles.get(name="tutor"),
                scope_unit=cls.speciality,
                is_primary=True,
                is_active=True,
            )
            Membership.objects.create(
                user=cls.student,
                organization=cls.org,
                role=cls.org.roles.get(name="student"),
                scope_unit=cls.group,
                is_primary=True,
                is_active=True,
            )
            cls.student.profile.organization = cls.org
            cls.student.profile.save(update_fields=["organization"])

            cls.program = Program.objects.create(organization=cls.org, code="SEDUI-CS", name="Kompüter elmləri")
            cls.curriculum = Curriculum.objects.create(organization=cls.org, program=cls.program, admission_year=2025)
            CurriculumSubject.objects.create(
                organization=cls.org, curriculum=cls.curriculum, subject=cls.subject, semester_number=1
            )
            StudentAcademicRecord.objects.create(
                organization=cls.org,
                student=cls.student,
                program=cls.program,
                curriculum=cls.curriculum,
                group=cls.group,
                admission_year=2025,
                status=AcademicStatus.ENROLLED,
            )
            cls.offering = services.get_or_create_offering(
                organization=cls.org, subject=cls.subject, period=cls.period, group=cls.group
            )
            cls.offering.instructor = cls.teacher
            cls.offering.save(update_fields=["instructor"])
            cls.offering_b = services.get_or_create_offering(
                organization=cls.org, subject=cls.subject, period=cls.period, group=cls.group_b
            )
            cls.offering_b.instructor = cls.teacher
            cls.offering_b.save(update_fields=["instructor"])

    def _client(self, user):
        client = Client()
        client.force_login(user)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        return client

    def _section(self, user, section="schedule-manage", **params):
        query = "&".join("%s=%s" % (key, value) for key, value in params.items())
        url = "%s?section=%s%s" % (reverse(PROFILE), section, ("&" + query) if query else "")
        return self._client(user).get(url)

    def _act(self, user, payload):
        return self._client(user).post(
            reverse("accounts:schedule_editor_action"),
            data=json.dumps(payload),
            content_type="application/json",
        )

    def _cell(self, **overrides):
        payload = {
            "action": "save",
            "group_id": str(self.group.id),
            "period_id": str(self.period.id),
            "subject_id": str(self.subject.id),
            "instructor_id": str(self.teacher.id),
            "weekday": 1,
            "time_slot": "10:10|11:40",
            "week_type": "all",
            "slot_kind": "lecture",
            "room": "",
        }
        payload.update(overrides)
        return payload


class AlwaysVisibleSectionTest(ScheduleEditorUIBase):
    def test_grid_renders_with_zero_slots(self):
        response = self._section(self.coordinator, sm_group=str(self.group.id))
        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        self.assertIn("smtx__table", body)
        self.assertIn("data-sedit-new", body)
        self.assertNotIn("smtx-card", body)

    def test_cell_dialog_is_rendered_with_the_group_plan_choices(self):
        body = self._section(self.coordinator, sm_group=str(self.group.id)).content.decode()
        # Dialoq + çekmecə + köçürmə təsdiqi eyni fraqmentdə render olunur.
        self.assertIn('id="seditCell"', body)
        self.assertIn('id="seditMove"', body)
        self.assertIn('id="seditParked"', body)
        # Fənn/müəllim seçiciləri layihə qaydası ilə (xam <select> YOX).
        self.assertIn("bootstrap-single-select--ems", body)
        self.assertIn('data-sedit-field="subject_id"', body)
        self.assertIn('data-sedit-field="instructor_id"', body)
        self.assertIn("CS101", body)

    def test_every_slot_change_goes_through_a_confirm_dialog(self):
        """Sahib (2026-09-09): «slot dəyişəndə hər zaman təsdiq istəsin … problem olmasa belə»."""
        body = self._section(self.coordinator, sm_group=str(self.group.id)).content.decode()
        self.assertIn('id="seditConfirm"', body)
        self.assertIn("data-sedit-confirm-ok", body)
        self.assertIn("data-sedit-confirm-summary", body)
        # Yaratma/redaktə və silmə üçün ayrı-ayrı izah mətnləri.
        self.assertIn("data-t-save", body)
        self.assertIn("data-t-delete", body)
        # Təsdiq JS-i xam `window.confirm` işlətmir.
        js_dir = settings.BASE_DIR / "apps/accounts/static/accounts/js"
        script = (js_dir / "schedule_editor.js").read_text(encoding="utf-8")
        helper = (js_dir / "schedule_editor_confirm.js").read_text(encoding="utf-8")
        self.assertNotIn("window.confirm", script)
        self.assertNotIn("window.confirm", helper)
        self.assertIn("askConfirm(cellSummary()", script)
        self.assertIn("window.EMSScheduleConfirm", script)

    def test_tutor_sees_the_same_editor_as_the_coordinator(self):
        response = self._section(self.tutor, sm_group=str(self.group.id))
        self.assertEqual(response.status_code, 200)
        self.assertIn("smtx__table", response.content.decode())

    def test_plain_teacher_has_no_access_to_the_editor(self):
        response = self._act(self.teacher, self._cell())
        self.assertEqual(response.status_code, 403)


class EditorActionTest(ScheduleEditorUIBase):
    def test_cell_dialog_creates_a_slot(self):
        response = self._act(self.coordinator, self._cell())
        self.assertEqual(response.status_code, 200, response.content)
        payload = response.json()
        self.assertTrue(payload["ok"])
        with bypass_rls():
            slot = ScheduleSlot.objects.get(pk=payload["slot"]["id"])
        self.assertEqual(slot.weekday, 1)
        self.assertEqual(slot.offering_id, self.offering.id)

    def test_move_reports_the_teacher_conflict_before_writing(self):
        with bypass_rls():
            ScheduleSlot.objects.create(
                organization=self.org,
                offering=self.offering_b,
                weekday=3,
                start_time=datetime.time(13, 35),
                end_time=datetime.time(15, 5),
            )
        created = self._act(self.coordinator, self._cell()).json()["slot"]
        response = self._act(
            self.coordinator,
            {
                "action": "move",
                "group_id": str(self.group.id),
                "period_id": str(self.period.id),
                "slot_id": created["id"],
                "weekday": 3,
                "time_slot": "13:35|15:05",
            },
        )
        self.assertEqual(response.status_code, 409)
        body = response.json()
        self.assertEqual(body["conflicts"][0]["kind"], "teacher")
        self.assertIn("231B", body["conflicts"][0]["message"])
        with bypass_rls():
            self.assertEqual(ScheduleSlot.objects.get(pk=created["id"]).weekday, 1)

    def test_forced_move_parks_the_other_slot_and_keeps_it_visible(self):
        with bypass_rls():
            blocker = ScheduleSlot.objects.create(
                organization=self.org,
                offering=self.offering_b,
                weekday=3,
                start_time=datetime.time(13, 35),
                end_time=datetime.time(15, 5),
            )
        created = self._act(self.coordinator, self._cell()).json()["slot"]
        response = self._act(
            self.coordinator,
            {
                "action": "move",
                "group_id": str(self.group.id),
                "period_id": str(self.period.id),
                "slot_id": created["id"],
                "weekday": 3,
                "time_slot": "13:35|15:05",
                "force": "1",
                "reason": "Dekanlığın sərəncamı ilə məcburi köçürmə",
            },
        )
        self.assertEqual(response.status_code, 200, response.content)
        with bypass_rls():
            blocker.refresh_from_db()
        self.assertTrue(blocker.is_parked)
        self.assertFalse(blocker.is_deleted)
        self.assertEqual(response.json()["parked"][0]["id"], str(blocker.pk))

        # Parklanmış dərs BAŞQA qrupundur, amma redaktorun CARİ görünüşündə
        # («231A») də görünməlidir — əks halda onu yenidən yerləşdirmək üçün
        # istifadəçi hansı qrupa keçəcəyini bilməzdi.
        panel = self._section(self.coordinator, sm_group=str(self.group.id)).content.decode()
        self.assertIn("sedit-parked__item", panel)
        self.assertIn("231B", panel)

    def test_suggestions_only_return_free_cells(self):
        created = self._act(self.coordinator, self._cell()).json()["slot"]
        response = self._act(
            self.coordinator,
            {
                "action": "suggest",
                "group_id": str(self.group.id),
                "period_id": str(self.period.id),
                "instructor_id": str(self.teacher.id),
            },
        )
        self.assertEqual(response.status_code, 200)
        rows = response.json()["suggestions"]
        self.assertTrue(rows)
        taken = [row for row in rows if row["weekday"] == 1 and row["time_slot"] == "10:10|11:40"]
        self.assertEqual(taken, [])
        self.assertTrue(created["id"])

    def test_delete_is_soft(self):
        created = self._act(self.coordinator, self._cell()).json()["slot"]
        response = self._act(
            self.coordinator,
            {
                "action": "delete",
                "group_id": str(self.group.id),
                "period_id": str(self.period.id),
                "slot_id": created["id"],
            },
        )
        self.assertEqual(response.status_code, 200)
        with bypass_rls():
            self.assertFalse(ScheduleSlot.objects.filter(pk=created["id"]).exists())
            self.assertTrue(ScheduleSlot.all_objects.get(pk=created["id"]).is_deleted)


class ReadOnlyScheduleTest(ScheduleEditorUIBase):
    """Müəllim və tələbə eyni matrisi (yalnız-oxu) görür — Task 3."""

    def _create(self):
        return self._act(self.coordinator, self._cell()).json()["slot"]

    def test_teacher_sees_the_new_slot_on_my_schedule(self):
        self._create()
        response = self._section(self.teacher, section="my-schedule")
        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        self.assertIn("smtx__table", body)
        self.assertIn("Proqramlaşdırma", body)

    def test_student_sees_the_new_slot_on_my_schedule(self):
        self._create()
        response = self._section(self.student, section="my-schedule")
        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        self.assertIn("smtx__table", body)
        self.assertIn("Proqramlaşdırma", body)

    def test_empty_schedule_still_renders_the_grid(self):
        response = self._section(self.student, section="my-schedule")
        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        self.assertIn("smtx__table", body)
        self.assertNotIn("smtx-card", body)
