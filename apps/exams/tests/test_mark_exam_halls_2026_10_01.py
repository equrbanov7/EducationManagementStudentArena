"""``mark_exam_halls`` komandası, korpus/otaq uyğunlaşdırması və 0070 miqrasiyasının
data qaydası (sahib 2026-10-01: «B korpusunda 03, 28, 38-i imtahan zalı kimi nəzərə al»).
"""

import importlib
from datetime import timedelta
from io import StringIO

from django.apps import apps as django_apps
from django.contrib.auth import get_user_model
from django.core.management import CommandError, call_command
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from apps.exams.domain.final_center import ExamRoomComputer
from apps.exams.models import Exam, ExamAttempt, ExamRoom, ExamRoomSession
from apps.exams.services.final_center.hall_matching import (
    TIER_BASE_NUMBER,
    TIER_EXACT,
    TIER_NUMERIC,
    building_matches,
    match_room_tokens,
    parse_room_tokens,
    room_match_tier,
)
from apps.organizations.models import Organization
from core.constants import OrganizationType

User = get_user_model()


class HallMatchingTests(SimpleTestCase):
    def test_building_letter_matches_production_and_short_labels(self):
        for label in ("Korpus B (Yüksək texnologiyalar)", "Korpus B", "B", "B korpusu", "b binası"):
            with self.subTest(label=label):
                self.assertTrue(building_matches(label, "B"))
                self.assertTrue(building_matches(label, "Korpus B"))
        self.assertFalse(building_matches("Korpus C", "B"))
        self.assertFalse(building_matches("Korpus A (Biznes məktəbi)", "B"))
        self.assertTrue(building_matches("Korpus İ (İçərişəhər)", "I"))
        self.assertTrue(building_matches("Korpus B (Yüksək texnologiyalar)", "yuksek texnologiyalar"))
        self.assertTrue(building_matches("3", "3"))
        self.assertFalse(building_matches("", "B"))

    def test_room_tiers_and_leading_zeros(self):
        self.assertEqual(room_match_tier("28", "myedu-room-9", "28"), TIER_EXACT)
        self.assertEqual(room_match_tier("x", "MYEDU-ROOM-9", "myedu-room-9"), TIER_EXACT)
        self.assertEqual(room_match_tier("3", "c", "03"), TIER_NUMERIC)
        self.assertEqual(room_match_tier("03", "c", "3"), TIER_NUMERIC)
        self.assertEqual(room_match_tier("03/2", "c", "03"), TIER_BASE_NUMBER)
        self.assertIsNone(room_match_tier("31", "c", "3"))
        self.assertIsNone(room_match_tier("-101", "c", "101"))
        self.assertIsNone(room_match_tier("akt zalı", "c", "03"))

    def test_best_tier_wins_and_ties_are_ambiguous(self):
        class R:
            def __init__(self, name):
                self.name, self.code = name, f"c-{name}"

        rooms = [R("03"), R("03/2"), R("28A"), R("28B")]
        exact, ambiguous, missing = match_room_tokens(rooms, ["3", "28", "99"])
        self.assertEqual(exact.room.name, "03")
        self.assertEqual(exact.tier, TIER_NUMERIC)
        self.assertIsNone(ambiguous.room)
        self.assertTrue(ambiguous.ambiguous)
        self.assertIsNone(missing.room)
        self.assertFalse(missing.ambiguous)

    def test_parse_tokens(self):
        self.assertEqual(parse_room_tokens(" 03, 28 ,,38,03 "), ["03", "28", "38"])


class MarkExamHallsCommandTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        owner = User.objects.create_user("mh_owner", "mh_owner@test.az", "x")
        cls.org = Organization.objects.create(
            name="MH University", org_type=OrganizationType.UNIVERSITY, owner=owner, status="active", is_active=True
        )
        cls.slug = cls.org.slug
        building = "Korpus B (Yüksək texnologiyalar)"
        cls.r03 = ExamRoom.objects.create(
            organization=cls.org, name="03/2", code="myedu-room-4", building=building, is_exam_hall=False
        )
        cls.r28 = ExamRoom.objects.create(
            organization=cls.org, name="28", code="myedu-room-9", building=building, is_exam_hall=False
        )
        cls.r38 = ExamRoom.objects.create(
            organization=cls.org, name="38", code="myedu-room-11", building=building, is_exam_hall=False
        )
        cls.c38 = ExamRoom.objects.create(
            organization=cls.org, name="38", code="myedu-room-233", building="Korpus C", is_exam_hall=False
        )

    def _run(self, *args):
        out = StringIO()
        call_command("mark_exam_halls", "--org", self.slug, *args, stdout=out)
        return out.getvalue()

    def _flags(self):
        return dict(ExamRoom.objects.filter(organization=self.org).values_list("code", "is_exam_hall"))

    def test_dry_run_changes_nothing(self):
        before = self._flags()
        output = self._run("--building", "B", "--rooms", "03,28,38")
        self.assertEqual(self._flags(), before)
        self.assertIn("DRY-RUN", output)
        self.assertIn("dəyişən=3", output)
        self.assertIn("«03» ≈", output)

    def test_apply_marks_only_the_building_rooms_and_is_idempotent(self):
        output = self._run("--building", "B", "--rooms", "03,28,38", "--apply")
        self.assertIn("[APPLY] qeyd: dəyişən=3", output)
        flags = self._flags()
        self.assertTrue(flags["myedu-room-4"] and flags["myedu-room-9"] and flags["myedu-room-11"])
        self.assertFalse(flags["myedu-room-233"])  # C korpusundakı «38» toxunulmur
        AuditLog = django_apps.get_model("audit", "AuditLog")
        marked = AuditLog.objects.filter(reason="exam_hall_marked", resource_type="exam_room")
        self.assertEqual(marked.count(), 3)
        self.assertEqual(marked.first().changes.get("source"), "command")

        again = self._run("--building", "B", "--rooms", "03,28,38", "--apply")
        self.assertIn("dəyişən=0 dəyişməz=3", again)
        self.assertEqual(marked.count(), 3)

    def test_unmark_and_live_session_refusal(self):
        self._run("--building", "B", "--rooms", "28,38", "--apply")
        now = timezone.now()
        ExamRoomSession.objects.create(
            organization=self.org,
            room=self.r28,
            state="active",
            scheduled_start=now,
            scheduled_end=now + timedelta(hours=1),
        )
        output = self._run("--building", "B", "--rooms", "28,38", "--unmark", "--apply")
        self.assertIn("rədd=1", output)
        flags = self._flags()
        self.assertTrue(flags["myedu-room-9"])  # canlı oturum — çıxarılmadı
        self.assertFalse(flags["myedu-room-11"])

    def test_missing_and_unknown_building(self):
        output = self._run("--building", "B", "--rooms", "99")
        self.assertIn("tapılmadı=1", output)
        with self.assertRaises(CommandError) as ctx:
            self._run("--building", "Z", "--rooms", "03")
        self.assertIn("Korpus B (Yüksək texnologiyalar)", str(ctx.exception))
        with self.assertRaises(CommandError):
            call_command("mark_exam_halls", "--org", "no-such-org", "--building", "B", "--rooms", "03")


class MigrationDataRuleTests(TestCase):
    """0070: mövcud otaqlardan YALNIZ imtahan izi olanlar zal qalır."""

    def test_rooms_without_computers_sessions_or_attempts_become_plain(self):
        owner = User.objects.create_user("mg_owner", "mg_owner@test.az", "x")
        org = Organization.objects.create(
            name="MG University", org_type=OrganizationType.UNIVERSITY, owner=owner, status="active", is_active=True
        )
        with_pc = ExamRoom.objects.create(organization=org, name="PC", code="PC")
        ExamRoomComputer.objects.create(
            organization=org, room=with_pc, label="PC-1", mac_address="AA:BB:CC:DD:EE:01", is_active=False
        )
        with_session = ExamRoom.objects.create(organization=org, name="SS", code="SS")
        now = timezone.now()
        ExamRoomSession.objects.create(
            organization=org,
            room=with_session,
            state="ended",
            scheduled_start=now,
            scheduled_end=now + timedelta(hours=1),
        )
        with_attempt = ExamRoom.objects.create(organization=org, name="AT", code="AT")
        exam = Exam.objects.create(title="MG", author=owner, organization=org, exam_type="test")
        ExamAttempt.objects.create(exam=exam, user=owner, room=with_attempt)
        bare = ExamRoom.objects.create(organization=org, name="BR", code="BR")
        already_plain = ExamRoom.objects.create(organization=org, name="PL", code="PL", is_exam_hall=False)

        migration = importlib.import_module("apps.exams.migrations.0070_examroom_is_exam_hall")
        migration.classify_existing_rooms(django_apps, None)
        migration.classify_existing_rooms(django_apps, None)  # idempotent

        flags = dict(ExamRoom.objects.filter(organization=org).values_list("code", "is_exam_hall"))
        self.assertEqual(flags, {"PC": True, "SS": True, "AT": True, "BR": False, "PL": False})
        self.assertTrue(ExamRoom.objects.filter(pk=with_pc.pk, computers__isnull=False).exists())
        self.assertFalse(ExamRoom.objects.get(pk=bare.pk).is_exam_hall)
        self.assertFalse(ExamRoom.objects.get(pk=already_plain.pk).is_exam_hall)
