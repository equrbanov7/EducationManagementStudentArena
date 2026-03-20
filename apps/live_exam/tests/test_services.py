"""
Serializer and transport tests for live_exam app.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import ProfileRole
from apps.exams.models import Exam
from apps.live_exam.models import LivePlayer, LiveSession
from apps.live_exam.serializers import serialize_player_identity, serialize_players, serialize_top
from apps.live_exam.transport import build_lobby_state_payload, build_reaction_event_payload
from apps.organizations.models import Organization
from core.constants import OrganizationType

User = get_user_model()


class LiveExamSerializerTransportTest(TestCase):
    def setUp(self):
        self.teacher = User.objects.create_user("service_teacher", "service@example.com", "StrongPass123!")
        self.teacher.profile.role = ProfileRole.TEACHER
        self.teacher.profile.save(update_fields=["role", "updated_at"])

        self.org = Organization.objects.create(
            name="Test Org",
            org_type=OrganizationType.SCHOOL,
            owner=self.teacher,
            status="active",
            is_active=True,
        )
        self.teacher.profile.organization = self.org
        self.teacher.profile.organization_type = self.org.org_type
        self.teacher.profile.save(update_fields=["organization", "organization_type", "updated_at"])

        self.exam = Exam.objects.create(
            title="Service Test Exam",
            slug="service-test-exam",
            author=self.teacher,
            is_active=True,
        )
        self.session = LiveSession.objects.create(exam=self.exam, host_user=self.teacher)
        self.player = LivePlayer.objects.create(
            session=self.session,
            nickname="Service Player",
            avatar_key="avatar_3",
            accessory_key="crown",
            client_id="service-player-client",
            score=15,
        )

    def test_serialize_player_identity_includes_accessory(self):
        payload = serialize_player_identity(self.player)
        self.assertEqual(payload["avatar_key"], "avatar_3")
        self.assertEqual(payload["accessory_key"], "crown")

    def test_serialize_players_includes_accessory(self):
        payload = serialize_players(self.session)
        self.assertEqual(payload[0]["avatar_key"], "avatar_3")
        self.assertEqual(payload[0]["accessory_key"], "crown")

    def test_serialize_top_includes_accessory(self):
        payload = serialize_top(self.session)
        self.assertEqual(payload[0]["score"], 15)
        self.assertEqual(payload[0]["accessory_key"], "crown")

    def test_build_lobby_state_payload_includes_accessory(self):
        payload = build_lobby_state_payload(self.session)
        self.assertEqual(payload["type"], "lobby_state")
        self.assertEqual(payload["players"][0]["accessory_key"], "crown")

    def test_build_reaction_event_payload_includes_player_identity(self):
        created_at = timezone.now()
        payload = build_reaction_event_payload(
            player=self.player,
            reaction_key="laugh",
            emoji="😂",
            created_at=created_at,
        )

        self.assertEqual(payload["type"], "reaction_event")
        self.assertEqual(payload["player"]["nickname"], "Service Player")
        self.assertEqual(payload["player"]["accessory_key"], "crown")
        self.assertEqual(payload["reaction_key"], "laugh")
        self.assertEqual(payload["emoji"], "😂")
        self.assertEqual(payload["created_at"], created_at.isoformat())
