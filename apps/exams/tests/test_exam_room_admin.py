"""İmtahan zalı administrasiyası — kompüter/MAC, IP giriş qapısı, icazə, nəzarətçi."""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase
from django.utils import timezone

from apps.accounts.models import ProfileRole
from apps.exams.domain.final_center import ExamRoomComputer
from apps.exams.models import Exam, ExamRoom, ExamRoomSession
from apps.exams.services.access_policy import can_manage_exam_rooms
from apps.exams.services.exam_center_gate import room_ip_access_allowed
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
        exam = Exam.objects.create(
            title="ERA Final",
            author=self.owner,
            organization=self.org,
            exam_type="test",
            exam_type_extended="final",
            is_active=True,
            total_duration_minutes=60,
        )
        now = timezone.now()
        session = ExamRoomSession.objects.create(
            organization=self.org,
            exam=exam,
            room=self.room,
            scheduled_start=now + timedelta(minutes=5),
            scheduled_end=now + timedelta(hours=2),
        )
        # Nəzarətçi hələ təyin olunmayıb → idarə edə bilməz.
        self.assertFalse(can_supervise_session(teacher, session))
        # Zala təyin olunanda zaldakı bütün oturumları idarə edir.
        self.room.invigilators.add(teacher)
        self.assertTrue(can_supervise_session(teacher, session))
