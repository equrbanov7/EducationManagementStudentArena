"""Sahib 2026-10-23: profil aktivləşdiriləndə RİM-ə bildiriş + RİM mərkəzində aktivləşdirmə sayı.

* ``email_verified`` False → True (ilk giriş OTP-si / parol bərpası) → RİM üzvlərinə (``ikt_rehber`` /
  ``rim_staff``) bildiriş: kim, növ, yekun say; keçid RİM mərkəzində həmin şəxsi axtarır.
* Artıq təsdiqli hesab (RİM parolu sıfırlayıb, istifadəçi yeni parol qurur) — yeni aktivləşdirmə DEYİL.
* «Sistem tənzimləmələri» açarı söndürüləndə bildiriş yoxdur.
* RİM mərkəzinin KPI sırası: cəmi + tələbə / müəllim / əməkdaş, «aktiv» = e-poçt təsdiqli VƏ ilkin parolda deyil.
"""

from __future__ import annotations

import re
from urllib.parse import unquote

from django.apps import apps
from django.core import mail
from django.test import Client, override_settings
from django.urls import reverse

from apps.accounts.forms.otp import mark_self_service_password_set
from apps.accounts.services.rim.activation import KEY_NOTIFY, activation_counts
from apps.notifications.models import InAppNotification
from core import runtime_settings

from .test_rim_center import RimCenterTestBase, add_member, make_user

NEW_PASSWORD = "MyBrandNewPass789!"


def _activate(user, *, verified=True, initial=False):
    profile = user.profile
    profile.email_verified = verified
    profile.password_change_required = initial
    profile.save(update_fields=["email_verified", "password_change_required", "updated_at"])


def _activation_notes():
    return InAppNotification.objects.filter(metadata__kind="profile_activated")


class RimActivationBase(RimCenterTestBase):
    def setUp(self):
        super().setUp()
        self.student = make_user("aysel.quliyeva", first="Aysel", last="Quliyeva", organization=self.org)
        add_member(self.student, self.org, self.student_role)
        self.clerk = make_user("kamran.staff", first="Kamran", last="Rəhimov", organization=self.org)
        add_member(self.clerk, self.org, self.staff_role)
        for user in (self.operator, self.teacher, self.namesake, self.higher, self.student, self.clerk):
            _activate(user, verified=False, initial=True)
        _activate(self.operator)


class ActivationCountsTests(RimActivationBase):
    def test_counts_per_kind_and_total(self):
        _activate(self.teacher)
        _activate(self.student)
        # E-poçtu təsdiqli, amma RİM parolu sıfırlayıb (ilkin parolda) — aktiv sayılmır.
        _activate(self.namesake, verified=True, initial=True)
        counts = activation_counts(self.org)
        # operator (ikt_rehber) + clerk (department_head) + higher (vice_rector) = heyət.
        self.assertEqual(counts["staff"], {"done": 1, "total": 3, "pct": 33.3})
        self.assertEqual(counts["teacher"], {"done": 1, "total": 2, "pct": 50.0})
        self.assertEqual(counts["student"], {"done": 1, "total": 1, "pct": 100.0})
        self.assertEqual(counts["total"]["done"], 3)
        self.assertEqual(counts["total"]["total"], 6)

    def test_blocked_and_archived_are_not_counted(self):
        self.student.is_active = False
        self.student.save(update_fields=["is_active"])
        self.assertEqual(activation_counts(self.org)["student"]["total"], 0)

    def test_no_organization_gives_zeros(self):
        self.assertEqual(activation_counts(None)["total"], {"done": 0, "total": 0, "pct": 0.0})


class ActivationNotificationTests(RimActivationBase):
    def test_self_service_reset_notifies_rim_members(self):
        with self.captureOnCommitCallbacks(execute=True):
            mark_self_service_password_set(self.student)
        notes = list(_activation_notes())
        self.assertEqual([note.recipient_id for note in notes], [self.operator.pk])
        note = notes[0]
        self.assertIn("Aysel Quliyeva", note.title)
        self.assertIn("Tələbə · @aysel.quliyeva", note.message)
        # Yekun say aktivləşdirənin özünü də sayır (bildiriş commit-dən sonra yazılır).
        self.assertIn("Cəmi aktivləşdirən: 2 / 6", note.message)
        self.assertIn("tələbə 1 / 1", note.message)
        # Keçid təşkilat açarı ilə sarılır (``/organizations/switch/<slug>/?next=…``) — hədəf RİM axtarışıdır.
        self.assertIn("section=rim-center&rim_q=aysel.quliyeva", unquote(note.link))
        self.assertEqual(note.organization_id, self.org.pk)

    def test_already_verified_account_is_not_a_new_activation(self):
        _activate(self.student, verified=True, initial=True)
        with self.captureOnCommitCallbacks(execute=True):
            mark_self_service_password_set(self.student)
        self.assertFalse(_activation_notes().exists())

    def test_switch_is_registered_in_login_group(self):
        spec = runtime_settings.SPECS[KEY_NOTIFY]
        self.assertEqual((spec.group, spec.kind), ("login", "bool"))
        self.assertTrue(runtime_settings.get_bool(KEY_NOTIFY))

    @override_settings(RUNTIME_SETTINGS_ENABLED=True)
    def test_switch_off_sends_nothing(self):
        apps.get_model("accounts", "RuntimeSetting").objects.update_or_create(key=KEY_NOTIFY, defaults={"value": False})
        runtime_settings.invalidate()
        try:
            with self.captureOnCommitCallbacks(execute=True):
                mark_self_service_password_set(self.student)
        finally:
            runtime_settings.invalidate()
        self.assertFalse(_activation_notes().exists())

    def test_rim_member_activating_self_gets_no_self_notification(self):
        _activate(self.operator, verified=False, initial=True)
        with self.captureOnCommitCallbacks(execute=True):
            mark_self_service_password_set(self.operator)
        self.assertFalse(_activation_notes().exists())

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_first_login_otp_flow_notifies(self):
        client = Client()
        client.force_login(self.teacher)
        url = reverse("accounts:set_initial_password")
        client.post(url, {"action": "send_otp", "email": "elvin.yeni@example.com"})
        code = re.search(r"\b(\d{6})\b", mail.outbox[-1].body).group(1)
        with self.captureOnCommitCallbacks(execute=True):
            response = client.post(
                url, {"action": "set_password", "code": code, "password1": NEW_PASSWORD, "password2": NEW_PASSWORD}
            )
        self.assertEqual(response.status_code, 302)
        self.teacher.profile.refresh_from_db()
        self.assertTrue(self.teacher.profile.email_verified)
        note = _activation_notes().get()
        self.assertEqual(note.recipient_id, self.operator.pk)
        self.assertIn("Müəllim · @myedu.worker.772", note.message)


class RimCenterActivationTilesTests(RimActivationBase):
    def test_tiles_and_prefilled_search(self):
        _activate(self.student)
        self.login_operator()
        response = self.client.get(reverse("accounts:profile"), {"section": "rim-center", "rim_q": "aysel.quliyeva"})
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn("PROFİLİNİ AKTİVLƏŞDİRİB", html)
        self.assertIn("6 nəfərdən", html)
        self.assertIn("TƏLƏBƏ", html)
        self.assertIn('value="aysel.quliyeva"', html)
