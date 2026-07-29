"""`seed_room_monitor_demo` + zallar səhifəsinin "Hazırda gedən imtahanlar" bölməsi.

Demo komandası zal monitorunu real yüklə göstərmək üçündür (2026-07-29):
qarışıq statuslu tələbələr + bir neçə fənn. Canlı siyahı isə köhnə "Oturumlar"
keçidinin yerinə gəlib.
"""

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import Client, TestCase
from django.urls import reverse

from apps.accounts.models import ProfileRole
from apps.exams.models import ExamRoom, ExamRoomComputer, FinalExamTicket
from apps.exams.tests.test_exam_center_policy import PASSWORD, _assign_user_to_org
from apps.organizations.models import Organization
from core.constants import OrganizationType

User = get_user_model()


class RoomMonitorDemoSeedTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("rmd_owner", "rmd_owner@test.az", PASSWORD)
        cls.org = Organization.objects.create(
            name="RMD University",
            org_type=OrganizationType.UNIVERSITY,
            owner=cls.owner,
            status="active",
            is_active=True,
        )
        cls.center = User.objects.create_user("rmd_center", "rmd_center@test.az", PASSWORD)
        _assign_user_to_org(cls.center, cls.org, ProfileRole.MEMBER, "exam_center")

        cls.room = ExamRoom.objects.create(
            organization=cls.org, name="Demo Zal", code="RMD-101", capacity=30, created_by=cls.owner
        )
        for seat in range(1, 6):
            ExamRoomComputer.objects.create(
                organization=cls.org,
                room=cls.room,
                label=f"PC-{seat:02d}",
                seat_number=seat,
                mac_address=f"AA:BB:CC:00:10:{seat:02d}",
                ip_address=f"10.0.10.{seat}",
                created_by=cls.owner,
            )

    def _seed(self):
        call_command("seed_room_monitor_demo", room="RMD-101", active=6, waiting=3, completed=2, removed=2)

    def test_seed_creates_mixed_statuses(self):
        self._seed()

        by_status = {
            status: FinalExamTicket.objects.filter(student__username__startswith="monitor_demo_", status=status).count()
            for status in ("active", "waiting", "ready", "completed", "removed")
        }
        self.assertEqual(by_status["active"], 6)
        self.assertEqual(by_status["waiting"] + by_status["ready"], 3)
        self.assertEqual(by_status["completed"], 2)
        self.assertEqual(by_status["removed"], 2)

    def test_seed_is_rerunnable(self):
        self._seed()
        self._seed()

        total = FinalExamTicket.objects.filter(student__username__startswith="monitor_demo_").count()
        self.assertEqual(total, 13)

    def test_snapshot_shows_active_students_with_violations(self):
        self._seed()
        from apps.exams.services.final_center import room_monitor_snapshot

        snap = room_monitor_snapshot(self.room)

        self.assertEqual(snap["counts"]["active"], 6)
        violated = [r for r in snap["students"] if r["violation_count"] > 0 and r["status"] == "active"]
        self.assertTrue(violated, msg="pozuntulu tələbə görünmür")

    def test_rooms_page_lists_running_exams_instead_of_sessions_link(self):
        self._seed()
        client = Client()
        client.force_login(self.center)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()

        response = client.get(reverse("exams:exam_center_room_list"))

        self.assertEqual(response.status_code, 200)
        # Köhnə "Oturumlar" səhifəsi tamamilə silinib — URL adı belə qalmayıb.
        self.assertNotContains(response, "/exams/center/sessions/?")
        # Canlı siyahı: hər üç fənn görünür, zal adı ilə.
        live = response.context["live_exams"]
        self.assertEqual(len(live), 3)
        self.assertContains(response, "Hazırda gedən imtahanlar")
        self.assertContains(response, "Riyaziyyat — Final imtahanı (Demo)")
        self.assertContains(response, "RMD-101")
        # Klik zal monitoruna aparır.
        self.assertContains(response, reverse("exams:exam_center_room_monitor", args=[self.room.pk]))
