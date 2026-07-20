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
