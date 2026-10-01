"""İmtahan zalı bayrağı (sahib 2026-10-01) — icazə, AJAX düyməsi, siyahı əhatəsi.

«İmtahan zalları yerində bütün otaqlar görünür» şikayəti: ``ExamRoom`` həm də
otaq reyestridir. İndi zal = ``is_exam_hall``; imtahan mərkəzinin zal siyahısı,
hesabat süzgəci və kabinet bölməsi yalnız zalları (+ canlı oturumlu otağı)
göstərir, zal təyin edə bilən «Hamısı» görünüşündə otağı zal kimi qeyd edir.
"""

import json
from datetime import timedelta

from django.apps import apps as django_apps
from django.contrib.auth import get_user_model
from django.test import Client, RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import ProfileRole
from apps.exams.domain.final_center import ExamRoomComputer
from apps.exams.models import ExamRoom, ExamRoomSession
from apps.exams.services.final_center.halls import (
    ERROR_ACTIVE_COMPUTERS,
    ERROR_LIVE_SESSION,
    ERROR_NEEDS_CONFIRM,
    ExamHallChangeError,
    can_designate_exam_halls,
    exam_hall_scope_q,
    set_exam_hall,
)
from apps.exams.tests.test_exam_center_policy import PASSWORD, _assign_user_to_org
from apps.organizations.models import Organization
from core.constants import OrganizationType

User = get_user_model()


def _audit(reason, room):
    AuditLog = django_apps.get_model("audit", "AuditLog")
    return AuditLog.objects.filter(reason=reason, resource_type="exam_room", resource_id=str(room.pk))


class _HallBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("hl_owner", "hl_owner@test.az", PASSWORD)
        cls.org = Organization.objects.create(
            name="HL University", org_type=OrganizationType.UNIVERSITY, owner=cls.owner, status="active", is_active=True
        )
        cls.other_org = Organization.objects.create(
            name="HL Other", org_type=OrganizationType.UNIVERSITY, owner=cls.owner, status="active", is_active=True
        )
        cls.head = User.objects.create_user("hl_head", "hl_head@test.az", PASSWORD)
        _assign_user_to_org(cls.head, cls.org, ProfileRole.MEMBER, "exam_center_head")
        cls.staff = User.objects.create_user("hl_staff", "hl_staff@test.az", PASSWORD)
        _assign_user_to_org(cls.staff, cls.org, ProfileRole.MEMBER, "exam_center_staff")
        cls.rim = User.objects.create_user("hl_rim", "hl_rim@test.az", PASSWORD)
        _assign_user_to_org(cls.rim, cls.org, ProfileRole.MEMBER, "ikt_rehber")
        cls.teacher = User.objects.create_user("hl_teacher", "hl_teacher@test.az", PASSWORD)
        _assign_user_to_org(cls.teacher, cls.org, ProfileRole.TEACHER, "teacher")
        cls.superadmin = User.objects.create_superuser("hl_super", "hl_super@test.az", PASSWORD)

        cls.hall = ExamRoom.objects.create(organization=cls.org, name="28", code="B-28", building="Korpus B")
        cls.plain = ExamRoom.objects.create(
            organization=cls.org, name="03/2", code="B-03", building="Korpus B", is_exam_hall=False
        )
        cls.plain_a = ExamRoom.objects.create(
            organization=cls.org, name="101", code="A-101", building="Korpus A", is_exam_hall=False
        )
        cls.foreign = ExamRoom.objects.create(
            organization=cls.other_org, name="Yad", code="Y-1", building="Korpus B", is_exam_hall=False
        )

    def _client(self, user, *, csrf=False):
        client = Client(enforce_csrf_checks=csrf)
        client.force_login(user)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        return client

    def _toggle(self, user, room, value, *, confirm=False):
        return self._client(user).post(
            reverse("exams:exam_center_room_exam_hall", args=[room.pk]),
            data=json.dumps({"is_exam_hall": value, "confirm": confirm}),
            content_type="application/json",
        )

    def _session(self, room, state):
        now = timezone.now()
        return ExamRoomSession.objects.create(
            organization=self.org,
            room=room,
            state=state,
            scheduled_start=now + timedelta(minutes=5),
            scheduled_end=now + timedelta(hours=2),
        )


class DesignatePermissionTests(_HallBase):
    def _in_org(self, user):
        # Rol yoxlaması sorğu middleware-inin qoyduğu aktiv təşkilatdan oxunur.
        fresh = User.objects.get(pk=user.pk)
        fresh._active_organization = self.org
        return fresh

    def test_managers_can_designate(self):
        for user in (self.head, self.rim, self.superadmin):
            with self.subTest(user=user.username):
                self.assertTrue(can_designate_exam_halls(self._in_org(user)))

    def test_flagged_room_manager_can_designate(self):
        user = User.objects.create_user("hl_flag", "hl_flag@test.az", PASSWORD)
        _assign_user_to_org(user, self.org, ProfileRole.MEMBER, "member")
        self.assertFalse(can_designate_exam_halls(self._in_org(user)))
        user.profile.can_manage_exam_rooms = True
        user.profile.save(update_fields=["can_manage_exam_rooms"])
        self.assertTrue(can_designate_exam_halls(self._in_org(user)))

    def test_staff_teacher_and_anonymous_cannot(self):
        from django.contrib.auth.models import AnonymousUser

        for user in (self._in_org(self.staff), self._in_org(self.teacher), AnonymousUser()):
            with self.subTest(user=str(user)):
                self.assertFalse(can_designate_exam_halls(user))


class ToggleEndpointTests(_HallBase):
    def test_head_marks_and_unmarks_with_audit(self):
        response = self._toggle(self.head, self.plain, True)
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["ok"] and body["changed"] and body["is_exam_hall"])
        self.assertEqual(body["hall_count"], 2)
        self.plain.refresh_from_db()
        self.assertTrue(self.plain.is_exam_hall)
        self.assertEqual(_audit("exam_hall_marked", self.plain).count(), 1)

        response = self._toggle(self.head, self.plain, False)
        self.assertEqual(response.status_code, 200)
        self.plain.refresh_from_db()
        self.assertFalse(self.plain.is_exam_hall)
        log = _audit("exam_hall_unmarked", self.plain).get()
        self.assertEqual(log.user_id, self.head.pk)
        self.assertEqual(log.new_values, {"is_exam_hall": False})

    def test_idempotent_mark_writes_no_audit(self):
        response = self._toggle(self.head, self.hall, True)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["changed"])
        self.assertFalse(_audit("exam_hall_marked", self.hall).exists())

    def test_forbidden_for_staff_and_teacher(self):
        for user in (self.staff, self.teacher):
            with self.subTest(user=user.username):
                response = self._toggle(user, self.plain, True)
                self.assertEqual(response.status_code, 403)
                self.assertFalse(response.json()["ok"])
        self.plain.refresh_from_db()
        self.assertFalse(self.plain.is_exam_hall)

    def test_other_org_room_is_404_for_head(self):
        response = self._toggle(self.head, self.foreign, True)
        self.assertEqual(response.status_code, 404)
        self.foreign.refresh_from_db()
        self.assertFalse(self.foreign.is_exam_hall)

    def test_superadmin_may_toggle_any_org(self):
        response = self._toggle(self.superadmin, self.foreign, True)
        self.assertEqual(response.status_code, 200)
        self.foreign.refresh_from_db()
        self.assertTrue(self.foreign.is_exam_hall)

    def test_csrf_is_enforced(self):
        client = self._client(self.head, csrf=True)
        url = reverse("exams:exam_center_room_exam_hall", args=[self.plain.pk])
        payload = json.dumps({"is_exam_hall": True})
        response = client.post(url, data=payload, content_type="application/json")
        self.assertEqual(response.status_code, 403)
        client.get(reverse("exams:exam_center_room_list"))  # csrftoken kukisi
        token = client.cookies["csrftoken"].value
        response = client.post(url, data=payload, content_type="application/json", HTTP_X_CSRFTOKEN=token)
        self.assertEqual(response.status_code, 200)

    def test_get_and_incomplete_body_rejected(self):
        url = reverse("exams:exam_center_room_exam_hall", args=[self.plain.pk])
        self.assertEqual(self._client(self.head).get(url).status_code, 405)
        response = self._client(self.head).post(url, data="{}", content_type="application/json")
        self.assertEqual(response.status_code, 400)

    def test_form_encoded_body_is_accepted(self):
        url = reverse("exams:exam_center_room_exam_hall", args=[self.plain.pk])
        response = self._client(self.head).post(url, {"is_exam_hall": "1"})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["is_exam_hall"])

    def test_refused_while_session_is_live(self):
        for state in ("entry_open", "active"):
            with self.subTest(state=state):
                session = self._session(self.hall, state)
                response = self._toggle(self.head, self.hall, False)
                self.assertEqual(response.status_code, 409)
                self.assertEqual(response.json()["code"], ERROR_LIVE_SESSION)
                self.assertFalse(response.json()["needs_confirm"])
                self.hall.refresh_from_db()
                self.assertTrue(self.hall.is_exam_hall)
                session.delete()

    def test_refused_while_active_computers_are_registered(self):
        ExamRoomComputer.objects.create(
            organization=self.org, room=self.hall, label="PC-1", mac_address="AA:BB:CC:DD:EE:01"
        )
        response = self._toggle(self.rim, self.hall, False)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["code"], ERROR_ACTIVE_COMPUTERS)
        ExamRoomComputer.objects.filter(room=self.hall).update(is_active=False)
        response = self._toggle(self.rim, self.hall, False)
        self.assertEqual(response.status_code, 200)

    def test_upcoming_session_needs_confirmation(self):
        session = self._session(self.hall, "prepared")
        response = self._toggle(self.head, self.hall, False)
        self.assertEqual(response.status_code, 409)
        self.assertTrue(response.json()["needs_confirm"])
        self.assertEqual(response.json()["code"], ERROR_NEEDS_CONFIRM)
        response = self._toggle(self.head, self.hall, False, confirm=True)
        self.assertEqual(response.status_code, 200)
        self.hall.refresh_from_db()
        self.assertFalse(self.hall.is_exam_hall)
        # Oturum toxunulmur — zal monitoru onun üçün açıq qalır (orphan yoxdur).
        session.refresh_from_db()
        self.assertEqual(session.state, "prepared")
        self.assertEqual(session.room_id, self.hall.pk)

    def test_service_refusal_raises_typed_error(self):
        self._session(self.hall, "active")
        with self.assertRaises(ExamHallChangeError) as ctx:
            set_exam_hall(self.hall, False, by=self.head)
        self.assertEqual(ctx.exception.code, ERROR_LIVE_SESSION)
        self.assertEqual(ctx.exception.usage.live, 1)


class ExamCenterRoomListTests(_HallBase):
    def _rooms(self, response):
        return [room.pk for group in response.context["building_groups"] for room in group["rooms"]]

    def test_default_scope_lists_only_exam_halls(self):
        response = self._client(self.head).get(reverse("exams:exam_center_room_list"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self._rooms(response), [self.hall.pk])
        self.assertEqual(response.context["kpi_rooms"], 1)
        self.assertContains(response, "data-exam-hall-toggle")

    def test_live_session_keeps_non_hall_room_visible(self):
        self._session(self.plain_a, "entry_open")
        response = self._client(self.head).get(reverse("exams:exam_center_room_list"))
        self.assertIn(self.plain_a.pk, self._rooms(response))

    def test_all_scope_groups_every_room_by_building_for_designators(self):
        response = self._client(self.head).get(reverse("exams:exam_center_room_list"), {"scope": "all"})
        groups = response.context["building_groups"]
        self.assertEqual([g["label"] for g in groups], ["Korpus A", "Korpus B"])
        korpus_b = groups[1]
        self.assertEqual([room.name for room in korpus_b["rooms"]], ["03/2", "28"])
        self.assertEqual((korpus_b["room_total"], korpus_b["hall_total"]), (2, 1))
        self.assertNotIn(self.foreign.pk, self._rooms(response))
        self.assertContains(response, "İmtahan zalı kimi qeyd et")

    def test_staff_cannot_switch_to_all_and_sees_no_toggle(self):
        response = self._client(self.staff).get(reverse("exams:exam_center_room_list"), {"scope": "all"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["active_scope"], "halls")
        self.assertEqual(self._rooms(response), [self.hall.pk])
        self.assertNotContains(response, "data-exam-hall-toggle")

    def test_building_filter_and_search_keep_scope(self):
        client = self._client(self.head)
        response = client.get(reverse("exams:exam_center_room_list"), {"scope": "all", "building": "Korpus A"})
        self.assertEqual(self._rooms(response), [self.plain_a.pk])
        self.assertIn("scope=all", response.context["pagination_query"])
        response = client.get(reverse("exams:exam_center_room_list"), {"q": "101"})
        self.assertEqual(self._rooms(response), [])

    def test_reports_room_filter_offers_halls_and_used_rooms_only(self):
        self._session(self.plain_a, "ended")
        response = self._client(self.head).get(reverse("exams:exam_center_reports"))
        self.assertEqual(response.status_code, 200)
        offered = {room.pk for room in response.context["rooms"]}
        self.assertEqual(offered, {self.hall.pk, self.plain_a.pk})

    def test_scope_q_is_join_free(self):
        self._session(self.hall, "active")
        self._session(self.hall, "entry_open")
        qs = ExamRoom.objects.filter(organization=self.org).filter(exam_hall_scope_q())
        self.assertEqual(list(qs.values_list("pk", flat=True)), [self.hall.pk])


class ProfileSectionScopeTests(_HallBase):
    def _section(self, user, **params):
        from apps.accounts.views.profile._sections.exam_rooms import build_exam_rooms_section

        request = RequestFactory().get("/", params)
        request.user = user
        section = {}
        build_exam_rooms_section(
            request,
            section,
            is_superadmin=False,
            active_organization=self.org,
            allowed_sections={"superadmin-exam-rooms"},
            active_section="superadmin-exam-rooms",
        )
        return section

    def test_default_shows_halls_and_all_shows_registry(self):
        section = self._section(self.rim)
        self.assertEqual([room.pk for room in section["rooms"]], [self.hall.pk])
        self.assertEqual(section["kpi_tiles"][0]["value"], 1)
        self.assertEqual(section["kpi_tiles"][0]["key"], "exam-halls")
        section = self._section(self.rim, xr_scope="all")
        self.assertEqual({room.pk for room in section["rooms"]}, {self.hall.pk, self.plain.pk, self.plain_a.pk})
        self.assertEqual([g["label"] for g in section["table_groups"]], ["Korpus A", "Korpus B"])
        self.assertEqual(section["table_groups"][1]["hall_total"], 1)

    def test_create_room_reads_the_hall_checkbox(self):
        client = self._client(self.superadmin)
        url = reverse("accounts:superadmin_exam_rooms")
        base = {"action": "create_room", "organization_id": str(self.org.pk), "capacity": "0", "computer_count": "0"}
        client.post(url, {**base, "name": "Sinif", "code": "S-1", "is_exam_hall_field": "1"})
        client.post(url, {**base, "name": "Zal", "code": "Z-1", "is_exam_hall_field": "1", "is_exam_hall": "1"})
        client.post(url, {**base, "name": "Köhnə", "code": "K-1"})
        flags = dict(ExamRoom.objects.filter(code__in=("S-1", "Z-1", "K-1")).values_list("code", "is_exam_hall"))
        self.assertEqual(flags, {"S-1": False, "Z-1": True, "K-1": True})
