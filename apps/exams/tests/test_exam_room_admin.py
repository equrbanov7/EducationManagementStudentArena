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
from apps.exams.services.final_center import RoomAdminError, add_computer, can_supervise_session
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
