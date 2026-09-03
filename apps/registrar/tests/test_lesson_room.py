"""Yeni dərs yaradarkən KORPUS + OTAQ seçimi.

Korpus ayrıca model DEYİL — otağın öz ``building`` sahəsidir, ona görə korpus
yalnız otaq siyahısını daraldan UI süzgəcidir və POST-a yalnız otaq gedir.
Otaq reyestri ``exams.ExamRoom``-dur (təşkilatın yeganə org-scoped otaq
reyestri); ``Lesson.room`` ona sətir-ref FK ilə bağlanır.

Yoxlanılır:
* otaq seçilərək dərs yaradılır və dərsə yazılır;
* otaq MƏCBURİ deyil — boş buraxıla bilər (köhnə axın pozulmur);
* BAŞQA təşkilatın (və ya deaktiv) otağı qəbul edilmir — tenant sızması yoxdur;
* modal korpus/otaq seçimlərini və otaq JSON-unu render edir;
* redaktədə otaq dəyişdirilə və təmizlənə bilir.
"""

import datetime

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.exams.models import ExamRoom
from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit
from apps.registrar import gradebook, lesson_rooms, services
from apps.registrar.models import Lesson, Subject
from core.constants import AcademicPeriodType, OrganizationType, OrgUnitType
from core.rls import bypass_rls

User = get_user_model()


class LessonRoomTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("lr_owner", "lr_owner@qku.edu.az", "pw")
        with bypass_rls():
            cls.org = Organization.objects.create(
                name="LR Univ",
                slug="lr-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=cls.owner,
                status="active",
                is_active=True,
            )
            cls.other_org = Organization.objects.create(
                name="LR Other",
                slug="lr-other",
                org_type=OrganizationType.UNIVERSITY,
                owner=cls.owner,
                status="active",
                is_active=True,
            )
            cls.group = OrgUnit.objects.create(
                organization=cls.org, name="G1", slug="lr-g1", unit_type=OrgUnitType.GROUP
            )
            cls.period = AcademicPeriod.objects.create(
                organization=cls.org,
                name="2024/2025 Payız",
                period_type=AcademicPeriodType.SEMESTER,
                academic_year="2024/2025",
                start_date="2024-09-01",
                end_date="2025-01-31",
                is_current=True,
            )
            cls.subject = Subject.objects.create(organization=cls.org, code="CS101", name="Proqramlaşdırma")
            cls.teacher = User.objects.create_user("lr_teacher", "lr_teacher@qku.edu.az", "pw")
            Membership.objects.create(
                user=cls.teacher,
                organization=cls.org,
                role=cls.org.roles.get(name="teacher"),
                is_primary=True,
                is_active=True,
            )
            cls.offering = services.get_or_create_offering(
                organization=cls.org, subject=cls.subject, period=cls.period, group=cls.group
            )
            cls.offering.instructor = cls.teacher
            cls.offering.lesson_hours = 60
            cls.offering.save(update_fields=["instructor", "lesson_hours"])
            # İki korpus, üç otaq + bir deaktiv + bir yad təşkilat otağı.
            cls.room_a1 = ExamRoom.objects.create(
                organization=cls.org, name="101", code="A101", building="I korpus", capacity=30
            )
            cls.room_a2 = ExamRoom.objects.create(
                organization=cls.org, name="102", code="A102", building="I korpus", capacity=25
            )
            cls.room_b1 = ExamRoom.objects.create(
                organization=cls.org, name="201", code="B201", building="II korpus", capacity=40
            )
            cls.room_off = ExamRoom.objects.create(
                organization=cls.org, name="Köhnə", code="OLD", building="I korpus", is_active=False
            )
            cls.room_alien = ExamRoom.objects.create(
                organization=cls.other_org, name="999", code="X999", building="Yad korpus"
            )

    def _client(self, user):
        client = Client()
        client.force_login(user)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        return client

    def _post_lesson(self, client, **extra):
        from django.utils import timezone as _tz

        payload = {
            "action": "add_lesson",
            "lesson_date": _tz.localdate().isoformat(),
            "lesson_kind": "seminar",
            "lesson_hours": "2",
            "lesson_time": "08:30|10:00",
        }
        payload.update(extra)
        return client.post(reverse("registrar:journal_detail", args=[self.offering.id]), payload)

    # ── Yaradılış ────────────────────────────────────────────────────────────

    def test_lesson_created_with_room(self):
        resp = self._post_lesson(self._client(self.teacher), lesson_room=str(self.room_b1.id))
        self.assertEqual(resp.status_code, 302)
        with bypass_rls():
            lesson = Lesson.objects.get(offering=self.offering)
            self.assertEqual(lesson.room_id, self.room_b1.id)
            self.assertEqual(lesson.room.building, "II korpus")

    def test_room_is_optional(self):
        """Otaq MƏCBURİ deyil — köhnə axın (otaqsız dərs) pozulmur."""
        resp = self._post_lesson(self._client(self.teacher))
        self.assertEqual(resp.status_code, 302)
        with bypass_rls():
            self.assertIsNone(Lesson.objects.get(offering=self.offering).room_id)

    def test_blank_room_value_accepted(self):
        self._post_lesson(self._client(self.teacher), lesson_room="")
        with bypass_rls():
            self.assertIsNone(Lesson.objects.get(offering=self.offering).room_id)

    # ── Tenant / vəziyyət qapısı ─────────────────────────────────────────────

    def test_foreign_org_room_rejected(self):
        """Başqa təşkilatın otağı dərsə bağlanmır (tenant sızması qapısı)."""
        self._post_lesson(self._client(self.teacher), lesson_room=str(self.room_alien.id))
        with bypass_rls():
            self.assertIsNone(Lesson.objects.get(offering=self.offering).room_id)

    def test_inactive_room_rejected(self):
        self._post_lesson(self._client(self.teacher), lesson_room=str(self.room_off.id))
        with bypass_rls():
            self.assertIsNone(Lesson.objects.get(offering=self.offering).room_id)

    def test_garbage_room_id_rejected(self):
        self._post_lesson(self._client(self.teacher), lesson_room="not-a-uuid")
        with bypass_rls():
            self.assertIsNone(Lesson.objects.get(offering=self.offering).room_id)

    # ── Seçim siyahıları ─────────────────────────────────────────────────────

    def test_room_choices_exclude_inactive_and_foreign(self):
        with bypass_rls():
            rooms = lesson_rooms.lesson_room_choices(self.offering)
        ids = {r["id"] for r in rooms}
        self.assertEqual(ids, {str(self.room_a1.id), str(self.room_a2.id), str(self.room_b1.id)})
        self.assertNotIn(str(self.room_off.id), ids)
        self.assertNotIn(str(self.room_alien.id), ids)

    def test_building_choices_are_distinct_and_sorted(self):
        with bypass_rls():
            rooms = lesson_rooms.lesson_room_choices(self.offering)
            buildings = lesson_rooms.lesson_building_choices(rooms)
        self.assertEqual(buildings, ["I korpus", "II korpus"])

    # ── Modal render ─────────────────────────────────────────────────────────

    def test_modal_renders_building_and_room_selects(self):
        resp = self._client(self.teacher).get(reverse("registrar:journal_detail", args=[self.offering.id]))
        html = resp.content.decode()
        self.assertIn("data-jd-lesson-building", html)
        self.assertIn("data-jd-lesson-room", html)
        self.assertIn('name="lesson_room"', html)
        # Korpus seçimləri dolu, otaqlar isə JSON blokundan gəlir.
        self.assertIn("I korpus", html)
        self.assertIn('id="jd-lesson-rooms"', html)
        # Layihə qaydası: inline CSS/JS yoxdur — otaq datası json_script ilə gəlir.
        self.assertIn('type="application/json"', html)

    def test_modal_has_no_inline_script_or_style(self):
        resp = self._client(self.teacher).get(reverse("registrar:journal_detail", args=[self.offering.id]))
        html = resp.content.decode()
        # json_script `type="application/json"` verir — icra olunan skript deyil.
        self.assertNotIn("<script>", html)
        self.assertNotIn("<style>", html)

    # ── Redaktə ──────────────────────────────────────────────────────────────

    def test_update_lesson_changes_room(self):
        with bypass_rls():
            lesson = gradebook.create_lesson(
                offering=self.offering,
                date=datetime.date.today(),
                start_time=datetime.time(8, 30),
                end_time=datetime.time(10, 0),
                room=self.room_a1,
                created_by=self.teacher,
            )
            self.assertEqual(lesson.room_id, self.room_a1.id)
            gradebook.update_lesson(lesson=lesson, room=self.room_b1)
            lesson.refresh_from_db()
            self.assertEqual(lesson.room_id, self.room_b1.id)

    def test_update_lesson_can_clear_room(self):
        with bypass_rls():
            lesson = gradebook.create_lesson(
                offering=self.offering,
                date=datetime.date.today(),
                start_time=datetime.time(8, 30),
                end_time=datetime.time(10, 0),
                room=self.room_a1,
                created_by=self.teacher,
            )
            gradebook.update_lesson(lesson=lesson, room=None)
            lesson.refresh_from_db()
            self.assertIsNone(lesson.room_id)

    def test_update_lesson_without_room_kwarg_keeps_room(self):
        """``room`` verilməyəndə mövcud otaq OLDUĞU KİMİ qalır (None ≠ "dəyişmə")."""
        with bypass_rls():
            lesson = gradebook.create_lesson(
                offering=self.offering,
                date=datetime.date.today(),
                start_time=datetime.time(8, 30),
                end_time=datetime.time(10, 0),
                room=self.room_a1,
                created_by=self.teacher,
            )
            gradebook.update_lesson(lesson=lesson, topic="Yeni mövzu")
            lesson.refresh_from_db()
            self.assertEqual(lesson.room_id, self.room_a1.id)
            self.assertEqual(lesson.topic, "Yeni mövzu")
