"""
2026-09-14 (audit 2026-09-13, `findings/tests.md` §1 · F-T11) — final mərkəzi icazə qapıları.

Coverage cədvəlində 0 % olan qapılar:
* `final_center/permissions.py`: `ensure_can_manage_final_center`,
  `ensure_can_supervise_session`, `ensure_ticket_owner`;
* `services/access_policy.py`: `ensure_can_manage_exam_rooms`.

View-lar bu `ensure_*` funksiyalarını deyil, eyni `can_*` predikatlarını
(`center_org_or_403`, `get_center_session_or_404(for_supervision=True)`,
`_resolve_own_ticket`, `superadmin_exam_rooms`) çağırır — ona görə hər qapı
üçün (a) BİRBAŞA unit test (rol × təyinat × tenant konteksti) və (b) həmin
predikatı işlədən BİR HTTP test var: unit test qapının özünü, HTTP test isə
view-un məhz o qaydanı tətbiq etdiyini sübut edir.

Fikstur `test_final_center_flow._FlowBase`-dən miras alınır (zal + 127.0.0.1
kompüteri + PIN-li bilet) ki, IP qapısı və giriş sessiyası real axınla qurulsun.
"""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import PermissionDenied
from django.test import Client
from django.urls import reverse

from apps.accounts.models import ProfileRole
from apps.exams.models import ExamRoom
from apps.exams.services.access_policy import can_manage_exam_rooms, ensure_can_manage_exam_rooms
from apps.exams.services.final_center import (
    can_manage_final_center,
    can_supervise_session,
    ensure_can_manage_final_center,
    ensure_can_supervise_session,
    ensure_ticket_owner,
)
from apps.exams.tests.test_exam_center_policy import PASSWORD, _assign_user_to_org
from apps.exams.tests.test_final_center_flow import _FlowBase
from apps.organizations.models import Organization
from core.constants import OrganizationType

User = get_user_model()


class _GateBase(_FlowBase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        # Zala (oturuma yox) təyin olunmuş nəzarətçi — yeni model.
        cls.room_invigilator = User.objects.create_user("w2g_room_inv", "w2g_room_inv@test.az", PASSWORD)
        _assign_user_to_org(cls.room_invigilator, cls.org, ProfileRole.TEACHER, "teacher")
        cls.room.invigilators.add(cls.room_invigilator)
        # Başqa zala təyin olunmuş nəzarətçi — bu zalın oturumunu idarə edə bilməz.
        cls.other_room = ExamRoom.objects.create(
            organization=cls.org, name="Zal B", code="ZB", capacity=10, created_by=cls.center
        )
        cls.other_room_invigilator = User.objects.create_user("w2g_other_inv", "w2g_other_inv@test.az", PASSWORD)
        _assign_user_to_org(cls.other_room_invigilator, cls.org, ProfileRole.TEACHER, "teacher")
        cls.other_room.invigilators.add(cls.other_room_invigilator)
        # Köhnə (deprecated) oturum-səviyyəli heyət üzvü.
        cls.staff_member = User.objects.create_user("w2g_staff", "w2g_staff@test.az", PASSWORD)
        _assign_user_to_org(cls.staff_member, cls.org, ProfileRole.TEACHER, "teacher")
        # İKT Rəhbəri — zal infrastrukturunu idarə edən texniki super-operator.
        cls.ikt = User.objects.create_user("w2g_ikt", "w2g_ikt@test.az", PASSWORD)
        _assign_user_to_org(cls.ikt, cls.org, ProfileRole.MEMBER, "ikt_rehber")
        # Superadminin per-user bayraqla həvalə etdiyi zal idarəçisi.
        cls.room_admin = User.objects.create_user("w2g_room_admin", "w2g_room_admin@test.az", PASSWORD)
        _assign_user_to_org(cls.room_admin, cls.org, ProfileRole.TEACHER, "teacher")
        cls.room_admin.profile.can_manage_exam_rooms = True
        cls.room_admin.profile.save(update_fields=["can_manage_exam_rooms", "updated_at"])
        cls.root = User.objects.create_superuser("w2g_root", "w2g_root@test.az", PASSWORD)
        # Yad tenant — mərkəz rolu BAŞQA təşkilatdadır.
        cls.other_org = Organization.objects.create(
            name="W2G Other University",
            org_type=OrganizationType.UNIVERSITY,
            owner=cls.owner,
            status="active",
            is_active=True,
        )
        cls.foreign_center = User.objects.create_user("w2g_foreign_center", "w2g_fc@test.az", PASSWORD)
        _assign_user_to_org(cls.foreign_center, cls.other_org, ProfileRole.MEMBER, "exam_center_head")

    def setUp(self):
        super().setUp()
        self.session.staff.add(self.staff_member)
        # Rol bayraqları (is_exam_center və s.) aktiv təşkilat kontekstinə bağlıdır;
        # HTTP axınında bunu middleware qurur, unit testdə əl ilə veririk.
        for user in (
            self.center,
            self.invigilator,
            self.teacher,
            self.student,
            self.student2,
            self.room_invigilator,
            self.other_room_invigilator,
            self.staff_member,
            self.ikt,
            self.room_admin,
        ):
            user.set_active_organization_context(self.org)
        self.foreign_center.set_active_organization_context(self.other_org)


class EnsureCanManageFinalCenterTests(_GateBase):
    def test_center_and_superadmin_pass(self):
        ensure_can_manage_final_center(self.center)
        ensure_can_manage_final_center(self.root)
        self.assertTrue(can_manage_final_center(self.center))

    def test_supervisors_students_and_anonymous_are_denied(self):
        for user in (self.invigilator, self.room_invigilator, self.staff_member, self.teacher, self.student):
            with self.subTest(user=user.username):
                with self.assertRaises(PermissionDenied):
                    ensure_can_manage_final_center(user)
        with self.assertRaises(PermissionDenied):
            ensure_can_manage_final_center(AnonymousUser())

    def test_center_role_is_bound_to_active_tenant(self):
        """Mərkəz rolu yad tenant kontekstində heç nəyə çevrilmir (rol qlobal deyil)."""
        self.foreign_center.set_active_organization_context(self.other_org)
        ensure_can_manage_final_center(self.foreign_center)
        self.foreign_center.set_active_organization_context(self.org)
        with self.assertRaises(PermissionDenied):
            ensure_can_manage_final_center(self.foreign_center)

    def test_http_session_cancel_requires_manage_level(self):
        url = reverse("exams:exam_center_session_cancel", args=[self.session.pk])
        for user in (self.invigilator, self.room_invigilator, self.student):
            with self.subTest(user=user.username):
                self.assertEqual(self._client_for(user).post(url, {"reason": "w2"}).status_code, 403)
        response = self._client_for(self.center).post(url, {"reason": "w2"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("exams:exam_center_room_list"))


class EnsureCanSuperviseSessionTests(_GateBase):
    def test_center_room_invigilator_legacy_invigilator_and_staff_pass(self):
        for user in (self.center, self.root, self.room_invigilator, self.invigilator, self.staff_member):
            with self.subTest(user=user.username):
                ensure_can_supervise_session(user, self.session)
                self.assertTrue(can_supervise_session(user, self.session))

    def test_unassigned_teacher_other_room_invigilator_and_student_are_denied(self):
        for user in (self.teacher, self.other_room_invigilator, self.student):
            with self.subTest(user=user.username):
                with self.assertRaises(PermissionDenied):
                    ensure_can_supervise_session(user, self.session)
                self.assertFalse(can_supervise_session(user, self.session))

    def test_removing_room_assignment_revokes_access(self):
        self.room.invigilators.remove(self.room_invigilator)
        with self.assertRaises(PermissionDenied):
            ensure_can_supervise_session(self.room_invigilator, self.session)

    def test_http_session_monitor_follows_room_assignment(self):
        url = reverse("exams:exam_center_session_monitor", args=[self.session.pk])
        self.assertEqual(self._client_for(self.room_invigilator).get(url).status_code, 200)
        self.assertEqual(self._client_for(self.staff_member).get(url).status_code, 200)
        self.assertEqual(self._client_for(self.other_room_invigilator).get(url).status_code, 403)
        self.assertEqual(self._client_for(self.teacher).get(url).status_code, 403)


class EnsureTicketOwnerTests(_GateBase):
    def test_only_the_ticket_student_passes(self):
        ensure_ticket_owner(self.student, self.ticket)
        # Mərkəz və hətta superadmin biletin SAHİBİ deyil — qapı ciddi sahiblikdir.
        for user in (self.student2, self.center, self.invigilator, self.root):
            with self.subTest(user=user.username):
                with self.assertRaises(PermissionDenied):
                    ensure_ticket_owner(user, self.ticket)
        with self.assertRaises(PermissionDenied):
            ensure_ticket_owner(AnonymousUser(), self.ticket)

    def test_http_ticket_state_hides_existence_from_non_owner(self):
        url = reverse("exams:final_ticket_state", args=[self.ticket.pk])
        # Sahib, PIN girişindən keçmiş sessiya ilə → 200.
        client, _response = self._entry_client()
        self.assertEqual(client.get(url).status_code, 200)
        # Sahib, giriş sessiyasız → 403 (bilet onundur, amma credential nəsli yoxdur).
        self.assertEqual(self._client_for(self.student).get(url).status_code, 403)
        # Başqa tələbə → 404 (bilet mövcudluğu sızmır).
        self.assertEqual(self._client_for(self.student2).get(url).status_code, 404)


class EnsureCanManageExamRoomsTests(_GateBase):
    def test_superadmin_ikt_and_flagged_user_pass(self):
        for user in (self.root, self.ikt, self.room_admin):
            with self.subTest(user=user.username):
                ensure_can_manage_exam_rooms(user)
                self.assertTrue(can_manage_exam_rooms(user))

    def test_center_without_flag_teacher_student_and_anonymous_are_denied(self):
        for user in (self.center, self.teacher, self.invigilator, self.student):
            with self.subTest(user=user.username):
                with self.assertRaises(PermissionDenied):
                    ensure_can_manage_exam_rooms(user)
        with self.assertRaises(PermissionDenied):
            ensure_can_manage_exam_rooms(AnonymousUser())
        self.assertFalse(can_manage_exam_rooms(AnonymousUser()))

    def test_flag_is_revocable(self):
        self.room_admin.profile.can_manage_exam_rooms = False
        self.room_admin.profile.save(update_fields=["can_manage_exam_rooms", "updated_at"])
        self.room_admin.refresh_from_db()
        with self.assertRaises(PermissionDenied):
            ensure_can_manage_exam_rooms(self.room_admin)

    def test_http_exam_rooms_section_follows_the_gate(self):
        url = reverse("accounts:superadmin_exam_rooms")
        self.assertEqual(self._client_for(self.room_admin).get(url).status_code, 200)
        self.assertEqual(self._client_for(self.ikt).get(url).status_code, 200)
        for user in (self.center, self.teacher, self.student):
            with self.subTest(user=user.username):
                self.assertEqual(self._client_for(user).get(url).status_code, 403)
        anonymous = Client().get(url)
        self.assertEqual(anonymous.status_code, 302)
        self.assertIn("login", anonymous["Location"])
