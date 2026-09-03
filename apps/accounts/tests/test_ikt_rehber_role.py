"""İKT Rəhbəri (ikt_rehber) rolunun əsas davranışı — pure/unit səviyyə.

İki yük-daşıyan nöqtə: (1) rol alias həlli (org_admin + exam-center-head gücü),
(2) kollokvium bitmiş-semestr kilidini keçmə. Hər ikisi DB/middleware tələb etmir.
"""

from types import SimpleNamespace

from django.test import SimpleTestCase

from core.roles import ProfileRole


class IktRehberAliasTests(SimpleTestCase):
    def test_ikt_rehber_gets_admin_and_exam_center_head_aliases(self):
        aliases = ProfileRole.aliases_for_membership_role("ikt_rehber", level=88)
        # Öz adı + imtahan mərkəzi rəhbəri (is_exam_center/head) + org_admin (level≥80).
        self.assertIn("ikt_rehber", aliases)
        self.assertIn(ProfileRole.EXAM_CENTER_HEAD, aliases)
        self.assertIn(ProfileRole.ORG_ADMIN, aliases)

    def test_ikt_rehber_level_is_high_operator(self):
        # exam-center (85) üstündə, prorektor (90) altında — yüksək operator.
        self.assertEqual(ProfileRole.LEVELS[ProfileRole.IKT_REHBER], 88)


class KollokviumPastBypassTests(SimpleTestCase):
    def _past_period(self):
        return SimpleNamespace(is_past=True)

    def test_regular_user_blocked_on_past_period(self):
        from apps.accounts.views.kollokvium_windows import KollokviumAdminError, _reject_if_period_past

        user = SimpleNamespace(is_superuser=False, is_superadmin=False, is_ikt_rehber=False)
        with self.assertRaises(KollokviumAdminError):
            _reject_if_period_past(self._past_period(), user)

    def test_ikt_rehber_bypasses_past_period(self):
        from apps.accounts.views.kollokvium_windows import _reject_if_period_past

        user = SimpleNamespace(is_superuser=False, is_superadmin=False, is_ikt_rehber=True)
        # Heç bir exception atmamalıdır (İKT Rəhbəri bitmiş semestri düzəldə bilər).
        _reject_if_period_past(self._past_period(), user)


class IktRehberExamRoomPermissionTests(SimpleTestCase):
    """İKT Rəhbəri zal/kompüter infrastrukturunu idarə edə bilməlidir.

    Rolun öz tərifində `exam.*` var (organizations/default_roles.py), yəni
    imtahan mərkəzinin TAM səlahiyyətini daşıyır.
    """

    def _user(self, **flags):
        base = {
            "is_authenticated": True,
            "is_superuser": False,
            "is_superadmin": False,
            "is_ikt_rehber": False,
            "profile": SimpleNamespace(can_manage_exam_rooms=False),
        }
        base.update(flags)
        return SimpleNamespace(**base)

    def test_ikt_rehber_can_manage_exam_rooms(self):
        from apps.exams.services.access_policy import can_manage_exam_rooms

        self.assertTrue(can_manage_exam_rooms(self._user(is_ikt_rehber=True)))

    def test_plain_user_still_cannot(self):
        """Reqressiya qoruması: icazə genişlənməyib."""
        from apps.exams.services.access_policy import can_manage_exam_rooms

        self.assertFalse(can_manage_exam_rooms(self._user()))

    def test_per_user_delegation_flag_still_works(self):
        from apps.exams.services.access_policy import can_manage_exam_rooms

        user = self._user(profile=SimpleNamespace(can_manage_exam_rooms=True))
        self.assertTrue(can_manage_exam_rooms(user))

    def test_anonymous_denied(self):
        from apps.exams.services.access_policy import can_manage_exam_rooms

        self.assertFalse(can_manage_exam_rooms(self._user(is_authenticated=False, is_ikt_rehber=True)))


class IktRehberRegistrarConsoleTests(SimpleTestCase):
    """Sidebar linki ilə view icazəsi uyğunlaşmalıdır (əks halda link 404 verir)."""

    def test_console_uses_canonical_course_permission(self):
        from apps.registrar.console_views import REGISTRAR_MANAGE_PERMISSION

        self.assertEqual(REGISTRAR_MANAGE_PERMISSION, "course.edit")
