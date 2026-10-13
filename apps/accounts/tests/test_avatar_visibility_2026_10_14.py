"""Profil şəkli — sahib 2026-10-14 «profil şəkli marşrutu bağlansın» (`core.people_visibility.can_view_avatar`).

Ortaq təşkilat artıq kifayət deyil: tələbə başqa tələbənin şəklini yalnız qrup yoldaşıdırsa və ya eyni fənn
açılışında birlikdədirsə görür; müəllimin şəklini görür. Müəllim/heyət ortaq təşkilatda hamını görür.
Fikstur «Starosta» testlərindən götürülür (eyni qrup / başqa qrup / müəllim).
"""

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.test import TestCase, override_settings

from apps.accounts.models import UserProfile
from core.media_views import _check_avatar_access
from core.people_visibility import can_view_avatar, can_view_person

from .test_role_audit_b_lead_2026_10_13 import MyGroupSectionTest

TINY_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4"
    b"\x89\x00\x00\x00\rIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
)


@override_settings(UNIVERSITY_MODE=True)
class AvatarVisibilityTest(TestCase):
    setUpTestData = MyGroupSectionTest.__dict__["setUpTestData"]
    _user = MyGroupSectionTest.__dict__["_user"]
    _member = MyGroupSectionTest.__dict__["_member"]
    _record = MyGroupSectionTest.__dict__["_record"]

    def test_student_sees_classmate_but_not_other_group(self):
        self.assertTrue(can_view_avatar(self.lead, self.mate.pk))
        # Ortaq təşkilatdır (köhnə qayda icazə verirdi), amma qrup yoldaşı deyil və ortaq fənn yoxdur.
        self.assertTrue(can_view_person(self.lead, self.stranger.pk))
        self.assertFalse(can_view_avatar(self.lead, self.stranger.pk))

    def test_student_sees_teacher_and_teacher_sees_every_student(self):
        self.assertTrue(can_view_avatar(self.lead, self.teacher.pk))
        self.assertTrue(can_view_avatar(self.teacher, self.stranger.pk))
        self.assertTrue(can_view_avatar(self.dean, self.mate.pk))

    def test_self_always(self):
        self.assertTrue(can_view_avatar(self.stranger, self.stranger.pk))

    def test_shared_offering_counts_as_classmate(self):
        from apps.registrar.models import CourseOffering, Enrollment
        from core.rls import bypass_rls

        with bypass_rls():
            offering = CourseOffering.objects.filter(group=self.group).first()
            Enrollment.objects.create(organization=self.org, student=self.stranger, offering=offering)
        self.assertTrue(can_view_avatar(self.lead, self.stranger.pk))

    def test_route_and_media_checker_follow_the_rule(self):
        name = default_storage.save("avatars/avrule_stranger.png", ContentFile(TINY_PNG))
        try:
            UserProfile.objects.filter(user=self.stranger).update(avatar=name)
            self.assertFalse(_check_avatar_access(self.lead, name))
            self.assertTrue(_check_avatar_access(self.teacher, name))
            from django.test import Client
            from django.urls import reverse

            client = Client()
            client.force_login(self.lead)
            self.assertEqual(client.get(reverse("accounts:profile_avatar", args=[self.stranger.pk])).status_code, 404)
        finally:
            default_storage.delete(name)
