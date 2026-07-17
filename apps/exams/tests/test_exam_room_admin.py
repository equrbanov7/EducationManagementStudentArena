"""İmtahan zalı administrasiyası — kompüter/MAC, IP/MAC giriş qapısı, icazə, nəzarətçi."""

from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase, override_settings
from django.utils import timezone

from apps.accounts.models import ProfileRole
from apps.exams.domain.final_center import ExamRoomComputer
from apps.exams.models import ExamRoom, ExamRoomSession
from apps.exams.services.access_policy import can_manage_exam_rooms
from apps.exams.services.exam_center_gate import (
    org_computer_access_allowed,
    resolve_room_computer,
    room_ip_access_allowed,
)
from apps.exams.services.final_center import (
    RoomAdminError,
    add_computer,
    bulk_add_computers,
    can_supervise_session,
)
from apps.exams.tests.test_exam_center_policy import PASSWORD, _assign_user_to_org
from apps.organizations.models import Organization
from core.constants import OrganizationType

User = get_user_model()


class MacNormalizationTests(TestCase):
    def test_normalize_variants(self):
        for raw in ("aa-bb-cc-dd-ee-ff", "AABB.CCDD.EEFF", "aa:bb:cc:dd:ee:ff", "AABBCCDDEEFF"):
            self.assertEqual(ExamRoomComputer.normalize_mac(raw), "AA:BB:CC:DD:EE:FF")

    def test_invalid_length_raises(self):
        for bad in ("", "AA:BB", "zzzz", "AA:BB:CC:DD:EE"):
            with self.assertRaises(ValueError):
                ExamRoomComputer.normalize_mac(bad)


class _RoomBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("era_owner", "era_owner@test.az", PASSWORD)
        cls.org = Organization.objects.create(
            name="ERA University",
            org_type=OrganizationType.UNIVERSITY,
            owner=cls.owner,
            status="active",
            is_active=True,
        )
        cls.room = ExamRoom.objects.create(organization=cls.org, name="Zal A", code="ZA", capacity=25)


class AddComputerServiceTests(_RoomBase):
    def test_add_normalizes_and_persists(self):
        comp = add_computer(
            room=self.room, label="PC-01", mac="aa-bb-cc-dd-ee-01", ip_address="10.0.0.11", seat_number="1"
        )
        self.assertEqual(comp.mac_address, "AA:BB:CC:DD:EE:01")
        self.assertEqual(comp.organization_id, self.org.id)
        self.assertEqual(comp.seat_number, 1)

    def test_duplicate_mac_rejected(self):
        add_computer(room=self.room, label="PC-01", mac="AA:BB:CC:DD:EE:01")
        with self.assertRaises(RoomAdminError):
            add_computer(room=self.room, label="PC-02", mac="aa:bb:cc:dd:ee:01")

    def test_duplicate_seat_rejected(self):
        add_computer(room=self.room, label="PC-01", mac="AA:BB:CC:DD:EE:01", seat_number=1)
        with self.assertRaises(RoomAdminError):
            add_computer(room=self.room, label="PC-02", mac="AA:BB:CC:DD:EE:02", seat_number=1)

    def test_invalid_mac_rejected(self):
        with self.assertRaises(RoomAdminError):
            add_computer(room=self.room, label="PC-01", mac="not-a-mac")

    def test_same_mac_in_other_room_of_same_org_rejected_with_room_name(self):
        # «Əlavə etmişəm, amma görmürəm» bugı: MAC eyni təşkilatın BAŞQA zalında
        # qalıb — xəta hansı zalda olduğunu deməlidir.
        other_room = ExamRoom.objects.create(organization=self.org, name="Zal B2", code="ZB2")
        add_computer(room=other_room, label="PC-01", mac="AA:BB:CC:DD:EE:07")
        with self.assertRaises(RoomAdminError) as ctx:
            add_computer(room=self.room, label="PC-09", mac="aa-bb-cc-dd-ee-07")
        self.assertIn("Zal B2", str(ctx.exception))

    def test_same_mac_in_other_org_allowed(self):
        other_org = Organization.objects.create(
            name="ERA Other University",
            org_type=OrganizationType.UNIVERSITY,
            owner=self.owner,
            status="active",
            is_active=True,
        )
        foreign_room = ExamRoom.objects.create(organization=other_org, name="Yad zal", code="YZ")
        add_computer(room=foreign_room, label="PC-01", mac="AA:BB:CC:DD:EE:08")
        comp = add_computer(room=self.room, label="PC-08", mac="AA:BB:CC:DD:EE:08")
        self.assertEqual(comp.room, self.room)

    def test_update_rejects_mac_registered_in_other_room(self):
        from apps.exams.services.final_center import update_computer

        other_room = ExamRoom.objects.create(organization=self.org, name="Zal B3", code="ZB3")
        add_computer(room=other_room, label="PC-01", mac="AA:BB:CC:DD:EE:0A")
        comp = add_computer(room=self.room, label="PC-02", mac="AA:BB:CC:DD:EE:0B")
        with self.assertRaises(RoomAdminError) as ctx:
            update_computer(computer=comp, label="PC-02", mac="AA:BB:CC:DD:EE:0A")
        self.assertIn("Zal B3", str(ctx.exception))


class BulkAddComputersTests(_RoomBase):
    def _macs(self):
        return {c.mac_address: c for c in ExamRoomComputer.objects.filter(room=self.room)}

    def test_name_mac_seat_without_ip(self):
        """«AD, MAC, YER» — IP yazılmadan yer nömrəsi düzgün oxunur (əsas şikayət)."""
        created, errors = bulk_add_computers(
            room=self.room,
            text="PC-01, 00-23-24-F5-0C-FF, 1\nPC-02, 00-23-24-F5-88-3B, 2",
        )
        self.assertEqual(created, 2)
        self.assertEqual(errors, [])
        comps = self._macs()
        self.assertEqual(comps["00:23:24:F5:0C:FF"].seat_number, 1)
        self.assertFalse(comps["00:23:24:F5:0C:FF"].ip_address)
        self.assertEqual(comps["00:23:24:F5:88:3B"].seat_number, 2)

    def test_legacy_empty_ip_slot_before_seat_still_parses(self):
        """Köhnə «AD, MAC, , YER» sətri boş IP-slotuna baxmayaraq yeri düzgün oxuyur."""
        created, errors = bulk_add_computers(
            room=self.room,
            text="PC-01, 00-23-24-F5-0C-FF, , 1",
        )
        self.assertEqual(created, 1)
        self.assertEqual(errors, [])
        comp = self._macs()["00:23:24:F5:0C:FF"]
        self.assertEqual(comp.seat_number, 1)
        self.assertFalse(comp.ip_address)

    def test_seat_and_ip_autodetected_regardless_of_order(self):
        created, errors = bulk_add_computers(
            room=self.room,
            text="PC-01, AA:BB:CC:DD:EE:01, 3, 10.0.0.13\nPC-02, AA:BB:CC:DD:EE:02, 10.0.0.14, 4",
        )
        self.assertEqual(created, 2)
        self.assertEqual(errors, [])
        comps = self._macs()
        self.assertEqual(comps["AA:BB:CC:DD:EE:01"].seat_number, 3)
        self.assertEqual(comps["AA:BB:CC:DD:EE:01"].ip_address, "10.0.0.13")
        self.assertEqual(comps["AA:BB:CC:DD:EE:02"].seat_number, 4)
        self.assertEqual(comps["AA:BB:CC:DD:EE:02"].ip_address, "10.0.0.14")

    def test_name_and_mac_only(self):
        created, errors = bulk_add_computers(room=self.room, text="PC-01, AA:BB:CC:DD:EE:05")
        self.assertEqual(created, 1)
        self.assertEqual(errors, [])
        comp = self._macs()["AA:BB:CC:DD:EE:05"]
        self.assertIsNone(comp.seat_number)
        self.assertFalse(comp.ip_address)

    def test_missing_mac_line_reported_and_skipped(self):
        created, errors = bulk_add_computers(
            room=self.room,
            text="PC-01\nPC-02, AA:BB:CC:DD:EE:06, 7",
        )
        self.assertEqual(created, 1)
        self.assertEqual(len(errors), 1)
        self.assertIn("1", errors[0])


class DeleteRoomServiceTests(_RoomBase):
    def test_delete_room_without_sessions_removes_computers(self):
        from apps.exams.services.final_center import delete_room

        room = ExamRoom.objects.create(organization=self.org, name="Silinən zal", code="SZ")
        add_computer(room=room, label="PC-01", mac="AA:BB:CC:DD:EE:21")
        delete_room(room=room)
        self.assertFalse(ExamRoom.objects.filter(code="SZ").exists())
        self.assertFalse(ExamRoomComputer.objects.filter(mac_address="AA:BB:CC:DD:EE:21").exists())

    def test_delete_room_with_session_history_blocked(self):
        from apps.exams.services.final_center import delete_room

        room = ExamRoom.objects.create(organization=self.org, name="Tarixçəli zal", code="TZ")
        now = timezone.now()
        ExamRoomSession.objects.create(
            organization=self.org,
            room=room,
            scheduled_start=now - timedelta(hours=3),
            scheduled_end=now - timedelta(hours=1),
        )
        with self.assertRaises(RoomAdminError) as ctx:
            delete_room(room=room)
        self.assertIn("Tarixçəli zal", str(ctx.exception))
        self.assertTrue(ExamRoom.objects.filter(code="TZ").exists())


class SuperadminRoomViewTests(_RoomBase):
    """View qatı: delete_room action-u + vurğu (hl) parametrləri."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.superadmin = User.objects.create_superuser("era_admin", "era_admin@test.az", PASSWORD)

    def _client(self):
        from django.test import Client

        client = Client()
        client.force_login(self.superadmin)
        return client

    def test_delete_room_action_deletes_and_redirects(self):
        from django.urls import reverse

        room = ExamRoom.objects.create(organization=self.org, name="View zalı", code="VZ")
        response = self._client().post(
            reverse("accounts:superadmin_exam_rooms"),
            {"action": "delete_room", "organization_id": str(self.org.pk), "room_id": str(room.pk)},
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(ExamRoom.objects.filter(pk=room.pk).exists())

    def test_add_computer_action_appends_highlight(self):
        from django.urls import reverse

        response = self._client().post(
            reverse("accounts:superadmin_exam_rooms"),
            {
                "action": "add_computer",
                "organization_id": str(self.org.pk),
                "room_id": str(self.room.pk),
                "label": "HL-PC",
                "mac_address": "AA:BB:CC:DD:EE:31",
            },
        )
        self.assertEqual(response.status_code, 302)
        comp = ExamRoomComputer.objects.get(label="HL-PC")
        self.assertIn(f"hl_comp={comp.pk}", response["Location"])
        self.assertIn(f"#sar-room-{self.room.pk}", response["Location"])


class RoomIpGateTests(_RoomBase):
    def setUp(self):
        self.rf = RequestFactory()

    def test_no_registered_ips_allows(self):
        # Qeyd yoxdur → per-zal məhdudiyyət yoxdur.
        request = self.rf.get("/exams/final/", REMOTE_ADDR="203.0.113.9")
        self.assertTrue(room_ip_access_allowed(request, self.room))

    def test_matching_ip_allowed_mismatch_blocked(self):
        add_computer(room=self.room, label="PC-01", mac="AA:BB:CC:DD:EE:01", ip_address="10.0.0.11")
        ok = self.rf.get("/exams/final/", REMOTE_ADDR="10.0.0.11")
        bad = self.rf.get("/exams/final/", REMOTE_ADDR="10.0.0.99")
        self.assertTrue(room_ip_access_allowed(ok, self.room))
        self.assertFalse(room_ip_access_allowed(bad, self.room))

    def test_inactive_computer_ip_ignored(self):
        comp = add_computer(room=self.room, label="PC-01", mac="AA:BB:CC:DD:EE:01", ip_address="10.0.0.11")
        comp.is_active = False
        comp.save(update_fields=["is_active"])
        # Yeganə IP söndürülüb → qeydli IP yoxdur → icazəli (qlobal gate qərar verir).
        request = self.rf.get("/exams/final/", REMOTE_ADDR="10.0.0.99")
        self.assertTrue(room_ip_access_allowed(request, self.room))


@override_settings(EXAM_CLIENT_MAC_RESOLUTION="arp_agent")
class MacGateTests(_RoomBase):
    """MAC (arp_agent) rejimi: kompüter yoxlamaları IP yox, MAC ilə aparılır."""

    MAC = "C8:D3:FF:B3:89:50"

    def setUp(self):
        self.rf = RequestFactory()
        self.request = self.rf.get("/exams/final/", REMOTE_ADDR="10.0.3.66")

    def _with_client_mac(self, mac):
        return mock.patch(
            "apps.exams.services.exam_center_gate.resolve_client_mac",
            return_value=mac,
        )

    def test_registered_mac_allowed_ip_irrelevant(self):
        # IP DB-dəki ilə uyğun DEYİL — MAC rejimində bunun əhəmiyyəti yoxdur.
        add_computer(room=self.room, label="PC-01", mac=self.MAC, ip_address="10.0.99.99")
        with self._with_client_mac(self.MAC):
            self.assertTrue(room_ip_access_allowed(self.request, self.room))
            room, comp = resolve_room_computer(self.request, self.org)
        self.assertEqual(room, self.room)
        self.assertEqual(comp.mac_address, self.MAC)

    def test_unregistered_mac_blocked(self):
        add_computer(room=self.room, label="PC-01", mac=self.MAC)
        with self._with_client_mac("AA:AA:AA:AA:AA:01"):
            self.assertFalse(room_ip_access_allowed(self.request, self.room))
            self.assertEqual(resolve_room_computer(self.request, self.org), (None, None))

    def test_unresolvable_mac_fail_closed(self):
        # Agent əlçatmaz / kənar müştəri (ARP qeydi yoxdur) → giriş rədd.
        add_computer(room=self.room, label="PC-01", mac=self.MAC)
        with self._with_client_mac(None):
            self.assertFalse(room_ip_access_allowed(self.request, self.room))
            self.assertEqual(resolve_room_computer(self.request, self.org), (None, None))
            self.assertFalse(org_computer_access_allowed(self.request, self.org))

    def test_org_gate_matches_mac(self):
        add_computer(room=self.room, label="PC-01", mac=self.MAC)
        with self._with_client_mac(self.MAC):
            self.assertTrue(org_computer_access_allowed(self.request, self.org))
        with self._with_client_mac("AA:AA:AA:AA:AA:01"):
            self.assertFalse(org_computer_access_allowed(self.request, self.org))

    def test_org_gate_open_when_no_computers(self):
        # Org-da qeydli kompüter yoxdursa biletsiz yol mövcud davranışda qalır.
        with self._with_client_mac(None):
            self.assertTrue(org_computer_access_allowed(self.request, self.org))
        self.assertTrue(org_computer_access_allowed(self.request, None))


class RoomIsolationAndMonitorTests(_RoomBase):
    """Biletsiz cəhdlərin zal möhürü: otaq izolyasiyası + zal monitoru sətirləri."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        from datetime import timedelta

        from django.utils import timezone

        from apps.exams.models import Exam

        cls.room_b = ExamRoom.objects.create(organization=cls.org, name="Zal B", code="ZB", capacity=25)
        now = timezone.now()
        cls.exam = Exam.objects.create(
            title="İzolyasiya Final",
            author=cls.owner,
            organization=cls.org,
            exam_type="test",
            exam_type_extended="final",
            is_active=True,
            total_duration_minutes=60,
            start_datetime=now - timedelta(minutes=5),
            end_datetime=now + timedelta(hours=2),
        )
        cls.student = User.objects.create_user("era_iso_student", "era_iso@test.az", PASSWORD)

    def _attempt(self, status="in_progress", room=None, computer=None, user=None):
        from apps.exams.models import ExamAttempt

        attempt = ExamAttempt.objects.create(
            user=user or self.student, exam=self.exam, status=status, room=room, room_computer=computer
        )
        if status != "in_progress":
            from django.utils import timezone

            attempt.finished_at = timezone.now()
            attempt.save(update_fields=["finished_at"])
        return attempt

    def test_same_exam_across_multiple_rooms_allowed(self):
        # 2026-07: otaq izolyasiyası ləğv edildi — eyni imtahan bir neçə zalda
        # keçirilə bilər. Bir tələbə zal A-da başlasa belə, zal B-də qeydli
        # kompüterdən giriş bloklanmır (MAC/IP gate + PIN + cəhd limiti idarə edir).
        self._attempt(room=self.room)  # zal A-da canlı cəhd
        from apps.exams.services.final_center.monitor import room_monitor_snapshot

        # Zal B monitoru öz tələbələrini göstərir — imtahan A-ya bağlanmır.
        snapshot_b = room_monitor_snapshot(self.room_b)
        self.assertEqual(snapshot_b["counts"]["active"], 0)

    def test_room_monitor_snapshot_includes_ticketless_attempts(self):
        from apps.exams.services.final_center.monitor import room_monitor_snapshot

        comp = add_computer(room=self.room, label="PC-01", mac="AA:BB:CC:DD:EE:01", seat_number=2)
        other_student = User.objects.create_user("era_iso_student2", "era_iso2@test.az", PASSWORD)
        self._attempt(room=self.room, computer=comp)
        self._attempt(status="submitted", room=self.room, user=other_student)

        snapshot = room_monitor_snapshot(self.room)
        rows = {r["username"]: r for r in snapshot["students"]}
        self.assertIn("era_iso_student", rows)
        live_row = rows["era_iso_student"]
        self.assertEqual(live_row["status"], "active")
        self.assertEqual(live_row["seat"], 2)
        self.assertIsNone(live_row["ticket_id"])
        self.assertEqual(live_row["exam_title"], "İzolyasiya Final")
        self.assertEqual(rows["era_iso_student2"]["status"], "completed")
        self.assertEqual(snapshot["counts"]["active"], 1)
        self.assertEqual(snapshot["counts"]["completed"], 1)
        self.assertEqual(snapshot["counts"]["total"], 2)
        # Canlı imtahan üçün psevdo-oturum çipi (filter seçimləri üçün).
        chip_ids = [s["session_id"] for s in snapshot["sessions"]]
        self.assertIn(f"exam-{self.exam.pk}", chip_ids)

    def test_other_room_snapshot_does_not_show_foreign_attempts(self):
        from apps.exams.services.final_center.monitor import room_monitor_snapshot

        self._attempt(room=self.room)
        snapshot_b = room_monitor_snapshot(self.room_b)
        self.assertEqual(snapshot_b["students"], [])
        self.assertEqual(snapshot_b["counts"]["total"], 0)


class OrgGateIpModeTests(_RoomBase):
    """ "off" (IP) rejimində org-səviyyə qapı IP ilə işləyir."""

    def setUp(self):
        self.rf = RequestFactory()

    def test_ip_mode_matches_registered_ip(self):
        add_computer(room=self.room, label="PC-01", mac="AA:BB:CC:DD:EE:01", ip_address="10.0.0.11")
        ok = self.rf.get("/exams/final/", REMOTE_ADDR="10.0.0.11")
        bad = self.rf.get("/exams/final/", REMOTE_ADDR="10.0.0.99")
        self.assertTrue(org_computer_access_allowed(ok, self.org))
        self.assertFalse(org_computer_access_allowed(bad, self.org))


class ManageRoomsPermissionTests(_RoomBase):
    def test_superuser_can(self):
        su = User.objects.create_superuser("era_su", "era_su@test.az", PASSWORD)
        self.assertTrue(can_manage_exam_rooms(su))

    def test_flagged_profile_can(self):
        user = User.objects.create_user("era_flag", "era_flag@test.az", PASSWORD)
        user.profile.can_manage_exam_rooms = True
        user.profile.save(update_fields=["can_manage_exam_rooms"])
        user.refresh_from_db()
        self.assertTrue(can_manage_exam_rooms(user))

    def test_plain_user_cannot(self):
        user = User.objects.create_user("era_plain", "era_plain@test.az", PASSWORD)
        self.assertFalse(can_manage_exam_rooms(user))


class RoomInvigilatorSupervisionTests(_RoomBase):
    def test_room_invigilator_supervises_all_room_sessions(self):
        teacher = User.objects.create_user("era_teacher", "era_teacher@test.az", PASSWORD)
        _assign_user_to_org(teacher, self.org, ProfileRole.TEACHER, "teacher")
        now = timezone.now()
        session = ExamRoomSession.objects.create(
            organization=self.org,
            room=self.room,
            scheduled_start=now + timedelta(minutes=5),
            scheduled_end=now + timedelta(hours=2),
        )
        # Nəzarətçi hələ təyin olunmayıb → idarə edə bilməz.
        self.assertFalse(can_supervise_session(teacher, session))
        # Zala təyin olunanda zaldakı bütün oturumları idarə edir.
        self.room.invigilators.add(teacher)
        self.assertTrue(can_supervise_session(teacher, session))
