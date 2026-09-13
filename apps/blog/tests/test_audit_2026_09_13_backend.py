"""Backend auditi 2026-09-13 — F-07 (blog moderasiyası atomik deyildi).

``teacher_moderate_post`` / ``review_post`` post statusunu yazıb SONRA
``PostApprovalLog`` yaradırdı; ``ATOMIC_REQUESTS`` söndürülü olduğu üçün ikinci
yazı sınanda post «gizlədilmiş, amma qərar jurnalı olmayan» vəziyyətdə qalırdı.
İndi cüt ``transaction.atomic`` içindədir — jurnal sınarsa status da geri alınır.
"""

from __future__ import annotations

from unittest import mock

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import ProfileRole
from apps.blog.models import Category, Post, PostApprovalLog
from apps.blog.tests.test_views import _assign_user_to_org
from apps.organizations.models import Organization
from core.constants import OrganizationType

User = get_user_model()


class ModerationAtomicTest(TestCase):
    def setUp(self):
        cache.clear()
        self.superadmin = User.objects.create_superuser("mod_atomic_sa", "mod_atomic_sa@example.com", "pw")
        self.teacher = User.objects.create_user("mod_atomic_teacher", "mod_atomic_t@example.com", "pw")
        self.organization = Organization.objects.create(
            name="Mod Atomic Org",
            slug="mod-atomic-org",
            org_type=OrganizationType.COURSE_CENTER,
            owner=self.teacher,
        )
        from apps.organizations.cabinet_modules import set_module_enabled

        set_module_enabled(self.organization, "posts", True)
        _assign_user_to_org(self.teacher, self.organization, ProfileRole.TEACHER)
        self.category = Category.objects.create(name="Mod Atomic", slug="mod-atomic")
        self.post = Post.objects.create(
            author=self.teacher,
            title="Atomic Post",
            content="Content",
            is_published=True,
            category=self.category,
        )
        self.client.force_login(self.superadmin)
        session = self.client.session
        session["active_organization"] = self.organization.slug
        session.save()

    def test_deactivate_rolls_back_when_approval_log_fails(self):
        with mock.patch.object(PostApprovalLog.objects, "create", side_effect=RuntimeError("log boom")):
            with self.assertRaises(RuntimeError):
                self.client.post(
                    reverse("teacher_moderate_post", args=[self.post.id]),
                    {"action": "deactivate", "feedback": "Səbəb"},
                )
        self.post.refresh_from_db()
        self.assertTrue(self.post.is_published)
        self.assertEqual(self.post.approval_feedback, "")
        self.assertFalse(PostApprovalLog.objects.filter(post=self.post).exists())

    def test_deactivate_still_writes_both_rows(self):
        response = self.client.post(
            reverse("teacher_moderate_post", args=[self.post.id]),
            {"action": "deactivate", "feedback": "Səbəb"},
        )
        self.assertEqual(response.status_code, 302)
        self.post.refresh_from_db()
        self.assertFalse(self.post.is_published)
        self.assertEqual(PostApprovalLog.objects.filter(post=self.post).count(), 1)

    def test_reactivate_rolls_back_when_approval_log_fails(self):
        Post.objects.filter(pk=self.post.pk).update(is_published=False)
        with mock.patch.object(PostApprovalLog.objects, "create", side_effect=RuntimeError("log boom")):
            with self.assertRaises(RuntimeError):
                self.client.post(reverse("teacher_moderate_post", args=[self.post.id]), {"action": "reactivate"})
        self.post.refresh_from_db()
        self.assertFalse(self.post.is_published)
        self.assertFalse(PostApprovalLog.objects.filter(post=self.post).exists())
