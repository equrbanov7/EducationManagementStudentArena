"""Köçürmə: bu semestr köhnə sistemdə jurnal yazan, yeni sistemdə müəllim üzvlüyü SÖNÜLÜ olan hesab
(``legacy_loads.restore_teacher_role``) — sönülü üzvlük aktiv kafedradadırsa bərpa olunur, başqa heç nə."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.organizations.models import Membership
from apps.workload.services.legacy_loads import restore_teacher_role

from .factories import activate_member, make_org, make_structure

User = get_user_model()


class RestoreTeacherRoleTests(TestCase):
    def setUp(self):
        self.org = make_org("wl-restore")
        self.unit = make_structure(self.org, code="RST")
        self.actor = User.objects.create_user("restore_actor", "ra@x.test", "pw")
        self.teacher = User.objects.create_user("restore_t", "rt@x.test", "pw")
        activate_member(self.org, self.teacher, "teacher", scope_unit=self.unit["chair"])
        Membership.objects.filter(user=self.teacher).update(is_active=False)

    def test_inactive_membership_in_active_chair_is_restored(self):
        chair = restore_teacher_role(organization=self.org, user=self.teacher, actor_user=self.actor)
        self.assertEqual(chair, self.unit["chair"])
        self.assertTrue(Membership.objects.get(user=self.teacher, scope_unit=chair).is_active)
        # Artıq aktiv müəllim üzvlüyü var → təkrar çağırış heç nə etmir.
        self.assertIsNone(restore_teacher_role(organization=self.org, user=self.teacher, actor_user=self.actor))

    def test_inactive_chair_is_not_revived(self):
        self.unit["chair"].is_active = False
        self.unit["chair"].save(update_fields=["is_active"])
        self.assertIsNone(restore_teacher_role(organization=self.org, user=self.teacher, actor_user=self.actor))
        self.assertFalse(Membership.objects.get(user=self.teacher).is_active)

    def test_user_without_any_teacher_membership_is_untouched(self):
        other = User.objects.create_user("restore_none", "rn@x.test", "pw")
        self.assertIsNone(restore_teacher_role(organization=self.org, user=other, actor_user=self.actor))
        self.assertFalse(Membership.objects.filter(user=other).exists())
