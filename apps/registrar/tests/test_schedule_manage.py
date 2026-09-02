"""Cədvəl idarəetməsi (`schedule.manage`) — icazə, əhatə, validasiya, yayım.

Nəyi qoruyur
------------
2026-09-a qədər cədvəl slotunu YALNIZ dərsi aparan müəllim əlavə edib silə
bilirdi (``journal_access.is_direct_editor``), proqram koordinatoru / dekanlıq /
RİM isə heç nə edə bilmirdi. İndi qapı kanonik ``schedule.manage`` açarındadır və
UNIT rollarında ``Membership.scope_unit`` alt-ağacı ilə məhdudlaşır.

Bu fayl həmin müqaviləni sabitləyir:

* koordinator ÖZ ixtisasında slot yaza bilir, BAŞQA fakültədə 403 alır;
* adi müəllim (açılışın müəllimi olsa belə) əlavə/silmədə 403 alır;
* RİM org-wide işləyir;
* saxlama-öncəsi validasiya (səhv saat, təkrar slot, qrup/müəllim/otaq
  konflikti) slotu YAZMADAN rədd edir;
* əməl audit sətri + tələbə/müəllim bildirişi yaradır.
"""

import datetime

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.notifications.models import InAppNotification
from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit
from apps.registrar import schedule, schedule_manage, services
from apps.registrar.models import Curriculum, Program, ScheduleSlot, StudentAcademicRecord, Subject
from core.constants import AcademicPeriodType, OrganizationType, OrgUnitType
from core.rls import bypass_rls

User = get_user_model()


class ScheduleManageBase(TestCase):
    """Fakültə → kafedra → ixtisas → qrup zənciri + iki ayrı fakültə."""

    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("smx_owner", "smx_owner@qku.edu.az", "pw")
        with bypass_rls():
            cls.org = Organization.objects.create(
                name="SMX Univ",
                slug="smx-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=cls.owner,
                status="active",
                is_active=True,
            )
            cls.faculty = OrgUnit.objects.create(
                organization=cls.org, name="Fakültə A", slug="smx-fac-a", unit_type=OrgUnitType.FACULTY
            )
            cls.speciality = OrgUnit.objects.create(
                organization=cls.org,
                parent=cls.faculty,
                name="İxtisas A",
                slug="smx-spec-a",
                unit_type=OrgUnitType.SPECIALTY,
            )
            cls.group = OrgUnit.objects.create(
                organization=cls.org,
                parent=cls.speciality,
                name="A-101",
                slug="smx-g-a101",
                unit_type=OrgUnitType.GROUP,
            )
            # İkinci fakültə — koordinatorun ƏHATƏSİNDƏN KƏNAR.
            cls.other_faculty = OrgUnit.objects.create(
                organization=cls.org, name="Fakültə B", slug="smx-fac-b", unit_type=OrgUnitType.FACULTY
            )
            cls.other_group = OrgUnit.objects.create(
                organization=cls.org,
                parent=cls.other_faculty,
                name="B-101",
                slug="smx-g-b101",
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
            cls.subject_b = Subject.objects.create(organization=cls.org, code="CS202", name="Alqoritmlər")

            cls.teacher = User.objects.create_user("smx_teacher", "smx_teacher@qku.edu.az", "pw")
            cls.coordinator = User.objects.create_user("smx_coord", "smx_coord@qku.edu.az", "pw")
            cls.rim = User.objects.create_user("smx_rim", "smx_rim@qku.edu.az", "pw")
            cls.student = User.objects.create_user("smx_student", "smx_student@qku.edu.az", "pw")

            Membership.objects.create(
                user=cls.teacher,
                organization=cls.org,
                role=cls.org.roles.get(name="teacher"),
                is_primary=True,
                is_active=True,
            )
            cls.coordinator_membership = Membership.objects.create(
                user=cls.coordinator,
                organization=cls.org,
                role=cls.org.roles.get(name="program_coordinator"),
                scope_unit=cls.speciality,
                is_primary=True,
                is_active=True,
            )
            Membership.objects.create(
                user=cls.rim,
                organization=cls.org,
                role=cls.org.roles.get(name="ikt_rehber"),
                is_primary=True,
                is_active=True,
            )
            Membership.objects.create(
                user=cls.student,
                organization=cls.org,
                role=cls.org.roles.get(name="student"),
                is_primary=True,
                is_active=True,
            )
            cls.student.profile.organization = cls.org
            cls.student.profile.save(update_fields=["organization"])

            cls.offering = services.get_or_create_offering(
                organization=cls.org, subject=cls.subject, period=cls.period, group=cls.group
            )
            cls.offering.instructor = cls.teacher
            cls.offering.save(update_fields=["instructor"])
            cls.offering_b = services.get_or_create_offering(
                organization=cls.org, subject=cls.subject_b, period=cls.period, group=cls.group
            )
            cls.offering_b.instructor = cls.teacher
            cls.offering_b.save(update_fields=["instructor"])
            cls.other_offering = services.get_or_create_offering(
                organization=cls.org, subject=cls.subject, period=cls.period, group=cls.other_group
            )

            program = Program.objects.create(organization=cls.org, code="CS", name="Kompüter elmləri")
            curriculum = Curriculum.objects.create(organization=cls.org, program=program, admission_year=2025)
            StudentAcademicRecord.objects.create(
                organization=cls.org,
                student=cls.student,
                program=program,
                curriculum=curriculum,
                group=cls.group,
                admission_year=2025,
            )

    def _client(self, user):
        client = Client()
        client.force_login(user)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        return client

    def _add_payload(self, offering=None, **overrides):
        payload = {
            "offering_id": str((offering or self.offering).id),
            "weekday": "2",
            "time_slot": "10:10|11:40",
            "room": "201",
            "week_type": "all",
            "slot_kind": "lecture",
        }
        payload.update(overrides)
        return payload

    def _post_add(self, user, **overrides):
        return self._client(user).post(reverse("registrar:schedule"), self._add_payload(**overrides))


class SchedulePermissionGateTest(ScheduleManageBase):
    """Kim slot yaza/silə bilir — rol adı yox, `schedule.manage` + əhatə."""

    def test_default_roles_carry_the_permission(self):
        for role_name in ("program_coordinator", "ikt_rehber", "dean", "chair_head"):
            role = self.org.roles.get(name=role_name)
            self.assertIn("schedule.manage", role.permissions, role_name)
        self.assertNotIn("schedule.manage", self.org.roles.get(name="teacher").permissions)

    def test_coordinator_in_scope_can_add(self):
        resp = self._post_add(self.coordinator)
        self.assertEqual(resp.status_code, 302)
        with bypass_rls():
            self.assertTrue(ScheduleSlot.objects.filter(offering=self.offering, weekday=2).exists())

    def test_coordinator_out_of_scope_is_denied(self):
        resp = self._post_add(self.coordinator, offering=self.other_offering)
        self.assertEqual(resp.status_code, 403)
        with bypass_rls():
            self.assertFalse(ScheduleSlot.objects.filter(offering=self.other_offering).exists())

    def test_plain_teacher_cannot_add_even_for_own_offering(self):
        resp = self._post_add(self.teacher)
        self.assertEqual(resp.status_code, 403)
        with bypass_rls():
            self.assertFalse(ScheduleSlot.objects.filter(offering=self.offering).exists())

    def test_plain_teacher_cannot_delete(self):
        with bypass_rls():
            slot = schedule.create_slot(
                offering=self.offering,
                weekday=1,
                start_time=datetime.time(9, 0),
                end_time=datetime.time(10, 30),
                room="101",
            )
        resp = self._client(self.teacher).post(reverse("registrar:schedule_slot_delete", args=[slot.id]))
        self.assertEqual(resp.status_code, 403)
        with bypass_rls():
            self.assertTrue(ScheduleSlot.objects.filter(pk=slot.pk).exists())

    def test_rim_is_org_wide(self):
        resp = self._post_add(self.rim, offering=self.other_offering)
        self.assertEqual(resp.status_code, 302)
        with bypass_rls():
            self.assertTrue(ScheduleSlot.objects.filter(offering=self.other_offering).exists())

    def test_coordinator_can_delete_in_scope(self):
        with bypass_rls():
            slot = schedule.create_slot(
                offering=self.offering,
                weekday=1,
                start_time=datetime.time(9, 0),
                end_time=datetime.time(10, 30),
            )
        resp = self._client(self.coordinator).post(reverse("registrar:schedule_slot_delete", args=[slot.id]))
        self.assertEqual(resp.status_code, 302)
        with bypass_rls():
            self.assertFalse(ScheduleSlot.objects.filter(pk=slot.pk).exists())

    def test_can_manage_helpers_are_fail_closed(self):
        self.assertTrue(schedule_manage.can_manage(self.coordinator, self.org))
        self.assertFalse(schedule_manage.can_manage(self.teacher, self.org))
        self.assertTrue(schedule_manage.can_manage_offering(self.coordinator, self.org, self.offering))
        self.assertFalse(schedule_manage.can_manage_offering(self.coordinator, self.org, self.other_offering))
        self.assertFalse(schedule_manage.can_manage_offering(self.teacher, self.org, self.offering))


class ScheduleValidationTest(ScheduleManageBase):
    """Saxlama-öncəsi validasiya — slot YAZILMADAN rədd olunur."""

    def _check(self, user, **overrides):
        return self._client(user).post(
            reverse("accounts:schedule_manage_check"),
            data=self._add_payload(**overrides),
        )

    def test_reversed_hours_are_rejected(self):
        resp = self._check(self.coordinator, time_slot="", start_time="12:00", end_time="11:00")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertFalse(body["ok"])
        self.assertIn("time_slot", body["errors"])

    def test_invalid_weekday_is_rejected(self):
        resp = self._check(self.coordinator, weekday="9")
        self.assertFalse(resp.json()["ok"])
        self.assertIn("weekday", resp.json()["errors"])

    def test_duplicate_slot_is_rejected(self):
        self._post_add(self.coordinator)
        resp = self._check(self.coordinator)
        self.assertFalse(resp.json()["ok"])
        self.assertIn("time_slot", resp.json()["errors"])

    def test_group_conflict_is_reported_with_reason(self):
        self._post_add(self.coordinator)
        # Eyni qrup + eyni gün, üst-üstə düşən vaxt, BAŞQA fənn.
        resp = self._check(
            self.coordinator, offering=self.offering_b, time_slot="", start_time="11:00", end_time="12:30"
        )
        body = resp.json()
        self.assertFalse(body["ok"])
        self.assertIn("conflict", body["errors"])
        self.assertEqual(body["conflict"]["subject_code"], "CS101")

    def test_room_conflict_across_groups(self):
        self._post_add(self.rim)
        resp = self._client(self.rim).post(
            reverse("accounts:schedule_manage_check"),
            data=self._add_payload(offering=self.other_offering, room="201"),
        )
        body = resp.json()
        self.assertFalse(body["ok"])
        self.assertIn("conflict", body["errors"])

    def test_past_period_is_closed_for_writing(self):
        with bypass_rls():
            past = AcademicPeriod.objects.create(
                organization=self.org,
                name="2023/2024 Payız",
                period_type=AcademicPeriodType.SEMESTER,
                academic_year="2023/2024",
                start_date=datetime.date(2023, 9, 1),
                end_date=datetime.date(2024, 1, 31),
            )
            past_offering = services.get_or_create_offering(
                organization=self.org, subject=self.subject, period=past, group=self.group
            )
        resp = self._check(self.coordinator, offering=past_offering)
        self.assertFalse(resp.json()["ok"])
        self.assertIn("period", resp.json()["errors"])

    def test_conflicting_slot_is_never_saved(self):
        self._post_add(self.coordinator)
        self._client(self.coordinator).post(
            reverse("registrar:schedule"),
            self._add_payload(offering=self.offering_b, time_slot="", start_time="11:00", end_time="12:30"),
        )
        with bypass_rls():
            self.assertEqual(ScheduleSlot.objects.filter(offering=self.offering_b).count(), 0)

    def test_check_endpoint_is_denied_for_a_plain_teacher(self):
        resp = self._check(self.teacher)
        self.assertEqual(resp.status_code, 403)


class SchedulePropagationTest(ScheduleManageBase):
    """Audit + bildiriş: dəyişiklik müəllimə və qrupun tələbələrinə gedir."""

    def test_add_writes_audit_and_notifies(self):
        from apps.audit.models import AuditLog

        # Bildiriş `transaction.on_commit`-dədir — TestCase daxilində commit
        # baş vermir, ona görə callback-lər açıq şəkildə icra edilir.
        with self.captureOnCommitCallbacks(execute=True):
            resp = self._client(self.coordinator).post(
                reverse("accounts:schedule_manage_action"),
                data={**self._add_payload(), "action": "add"},
            )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["ok"])
        with bypass_rls():
            self.assertTrue(AuditLog.objects.filter(action="create", resource_type="registrar.ScheduleSlot").exists())
            recipients = set(
                InAppNotification.objects.filter(metadata__event="schedule_changed").values_list(
                    "recipient_id", flat=True
                )
            )
        self.assertIn(self.teacher.id, recipients)
        self.assertIn(self.student.id, recipients)

    def test_delete_writes_audit_and_notifies(self):
        from apps.audit.models import AuditLog

        with bypass_rls():
            slot = schedule.create_slot(
                offering=self.offering,
                weekday=3,
                start_time=datetime.time(9, 0),
                end_time=datetime.time(10, 30),
            )
        with self.captureOnCommitCallbacks(execute=True):
            resp = self._client(self.coordinator).post(
                reverse("accounts:schedule_manage_action"),
                data={"action": "delete", "slot_id": str(slot.id)},
            )
        self.assertEqual(resp.status_code, 200)
        with bypass_rls():
            self.assertFalse(ScheduleSlot.objects.filter(pk=slot.pk).exists())
            self.assertTrue(AuditLog.objects.filter(action="delete", resource_type="registrar.ScheduleSlot").exists())
            self.assertTrue(
                InAppNotification.objects.filter(metadata__event="schedule_changed", metadata__removed=True).exists()
            )

    def test_action_endpoint_is_denied_for_a_plain_teacher(self):
        resp = self._client(self.teacher).post(
            reverse("accounts:schedule_manage_action"),
            data={**self._add_payload(), "action": "add"},
        )
        self.assertEqual(resp.status_code, 403)

    def test_unknown_action_is_rejected(self):
        resp = self._client(self.coordinator).post(
            reverse("accounts:schedule_manage_action"),
            data={"action": "explode"},
        )
        self.assertEqual(resp.status_code, 400)


class ScheduleSectionVisibilityTest(ScheduleManageBase):
    """Kabinet bölməsi: kim menyuda «Cədvəl idarəetməsi»ni görür."""

    def _fragment(self, user):
        return self._client(user).get(
            reverse("accounts:profile_section_fragment", kwargs={"section": "schedule-manage"})
        )

    def test_coordinator_sees_the_section(self):
        resp = self._fragment(self.coordinator)
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["ok"])

    def test_rim_sees_the_section(self):
        self.assertEqual(self._fragment(self.rim).status_code, 200)

    def test_teacher_does_not_see_the_section(self):
        self.assertEqual(self._fragment(self.teacher).status_code, 403)

    def test_student_does_not_see_the_section(self):
        self.assertEqual(self._fragment(self.student).status_code, 403)

    def test_student_my_schedule_stays_read_only(self):
        resp = self._client(self.student).get(reverse("registrar:schedule"))
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.context["schedule_can_manage"])

    def test_teacher_my_schedule_has_no_management_controls(self):
        resp = self._client(self.teacher).get(reverse("registrar:schedule"))
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.context["schedule_can_manage"])
        self.assertNotContains(resp, "data-sgx-open-add")
