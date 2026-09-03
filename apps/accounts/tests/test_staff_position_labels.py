"""«Üzv» doldurucusu + vəzifə etiketi zənciri.

İKİ MÜQAVİLƏ KİLİDLƏNİR:

1. **Vəzifəsiz istifadəçidə «Üzv» GÖRÜNMÜR.** ``member`` real vəzifə deyil —
   heç bir vəzifəsi olmayan hesabın defolt rolu (``UserProfile.role`` default).
   Onu tələbənin/müəllimin adının yanında etiket kimi yazmaq məzmunsuzdur.
   Rol idarəetmə səthlərində (seçim variantı kimi) isə qalmalıdır.

2. **Legacy vəzifə idxalı İCAZƏ VERMİR.** ``import_legacy_staff_positions``
   yalnız ``UserProfile.staff_position`` mətn sahəsini doldurur; rol/üzvlük
   toxunulmaz qalır və naməlum ``teacher_type`` kodu heç bir etiketə çevrilmir.
"""

from __future__ import annotations

import json
import tempfile
from io import StringIO
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.utils import translation

from core.staff_position import (
    is_placeholder_role_name,
    legacy_staff_category_label,
    resolve_position_label,
    visible_role_label,
)

from ..models import ProfileRole, UserProfile
from ..views.profile.context_builder import _build_effective_user_roles, _build_primary_position_label

User = get_user_model()


class StaffPositionKernelTest(TestCase):
    """`core.staff_position` — pure məntiq."""

    def test_member_is_placeholder(self):
        self.assertTrue(is_placeholder_role_name("member"))
        self.assertTrue(is_placeholder_role_name(" Member "))
        self.assertFalse(is_placeholder_role_name("teacher"))
        self.assertFalse(is_placeholder_role_name(""))

    def test_visible_role_label_blanks_placeholder(self):
        self.assertEqual(visible_role_label("member", "Member"), "")
        self.assertEqual(visible_role_label("member", "Üzv"), "")
        # PHASE21 U-2 (2026-09-03): seed-dəki dəyişməmiş İngiliscə "Dean" AZ-a
        # çevrilir (bax `core.roles.resolve_seeded_role_label`); admin fərqli
        # bir mətnə dəyişibsə (və ya heç bir etiket verilməyibsə) TOXUNULMUR.
        self.assertEqual(visible_role_label("dean", "Dean"), "Dekan")
        self.assertEqual(visible_role_label("dean", "Baş Dekan"), "Baş Dekan")
        # Etiket verilməyibsə ad özü qaytarılır — heç nə uydurulmur.
        self.assertEqual(visible_role_label("dean"), "dean")

    def test_position_chain_prefers_title_then_staff_position(self):
        self.assertEqual(
            resolve_position_label(title="Dekan", staff_position="İnzibati işçi", role_name="teacher"),
            "Dekan",
        )
        self.assertEqual(
            resolve_position_label(staff_position="İnzibati işçi", role_name="member", role_label="Member"),
            "İnzibati işçi",
        )
        self.assertEqual(resolve_position_label(role_name="teacher", role_label="Müəllim"), "Müəllim")

    def test_position_chain_is_empty_without_any_position(self):
        """Vəzifə yoxdursa BOŞLUQ — «Üzv» doldurucusu yazılmır."""
        self.assertEqual(resolve_position_label(role_name="member", role_label="Üzv"), "")
        self.assertEqual(resolve_position_label(), "")

    def test_legacy_category_label_is_translated(self):
        with translation.override("en"):
            self.assertEqual(str(legacy_staff_category_label("administrative")), "Administrative staff")
        with translation.override("ru"):
            self.assertEqual(str(legacy_staff_category_label("administrative")), "Административный сотрудник")
        self.assertIsNone(legacy_staff_category_label("teacher_type_1"))
        self.assertIsNone(legacy_staff_category_label(None))


class ProfileHeaderPlaceholderTest(TestCase):
    """Profil başlığı — vəzifəsiz hesabda nişan yoxdur."""

    def _profile(self, username, *, role, staff_position=""):
        user = User.objects.create_user(username, f"{username}@example.com", "StrongPass123!")
        profile = UserProfile.objects.get(user=user)
        profile.role = role
        profile.staff_position = staff_position
        profile.save(update_fields=["role", "staff_position", "updated_at"])
        return user, profile

    def test_member_role_produces_no_badge_and_no_label(self):
        user, profile = self._profile("sp_member", role=ProfileRole.MEMBER)
        roles = _build_effective_user_roles(user, profile)
        self.assertEqual(roles, [])
        self.assertEqual(_build_primary_position_label(profile, roles), "")

    def test_member_role_with_staff_position_shows_the_position(self):
        user, profile = self._profile("sp_member_pos", role=ProfileRole.MEMBER, staff_position="İnzibati işçi")
        roles = _build_effective_user_roles(user, profile)
        self.assertEqual(roles, [])
        self.assertEqual(_build_primary_position_label(profile, roles), "İnzibati işçi")

    def test_real_role_still_renders(self):
        user, profile = self._profile("sp_teacher", role=ProfileRole.TEACHER)
        roles = _build_effective_user_roles(user, profile)
        self.assertEqual([item["name"] for item in roles], [ProfileRole.TEACHER])
        self.assertTrue(_build_primary_position_label(profile, roles))

    def test_staff_position_wins_over_role_label(self):
        user, profile = self._profile("sp_dean", role=ProfileRole.TEACHER, staff_position="Dekan")
        roles = _build_effective_user_roles(user, profile)
        self.assertEqual(_build_primary_position_label(profile, roles), "Dekan")

    def test_member_role_is_still_selectable_in_role_management(self):
        """Doldurucu rol SEÇİM variantı kimi qalmalıdır — yalnız etiket gizlənir."""
        self.assertIn(ProfileRole.MEMBER, dict(ProfileRole.CHOICES))


class LegacyStaffPositionImportTest(TestCase):
    """`import_legacy_staff_positions` — etiket yazır, icazə vermir."""

    def setUp(self):
        self.admin_user = User.objects.create_user("lsp_admin", "lsp_admin@example.com", "StrongPass123!")
        self.plain_user = User.objects.create_user("lsp_plain", "lsp_plain@example.com", "StrongPass123!")
        self.filled_user = User.objects.create_user("lsp_filled", "lsp_filled@example.com", "StrongPass123!")
        filled = UserProfile.objects.get(user=self.filled_user)
        filled.staff_position = "Kafedra müdiri"
        filled.save(update_fields=["staff_position", "updated_at"])

    def _source(self, rows):
        handle = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8")
        json.dump(rows, handle, ensure_ascii=False)
        handle.close()
        self.addCleanup(lambda: Path(handle.name).unlink(missing_ok=True))
        return handle.name

    def _rows(self):
        return [
            {"username": "lsp_admin", "legacy_worker_id": 1, "inzibati": 1, "teacher_type": 1, "permits": ["dekan"]},
            {"username": "lsp_plain", "legacy_worker_id": 2, "inzibati": 0, "teacher_type": 2, "permits": []},
            {
                "username": "lsp_filled",
                "legacy_worker_id": 3,
                "inzibati": 1,
                "teacher_type": 3,
                "permits": ["kafedra"],
            },
            {"username": "lsp_missing", "legacy_worker_id": 4, "inzibati": 1, "teacher_type": 1, "permits": []},
        ]

    def _run(self, *, apply_changes=False):
        out = StringIO()
        args = ["import_legacy_staff_positions", "--source", self._source(self._rows())]
        if apply_changes:
            args.append("--apply")
        with translation.override("en"):
            call_command(*args, stdout=out)
        return out.getvalue()

    def test_dry_run_writes_nothing(self):
        output = self._run()
        self.assertIn("Dry run", output)
        self.assertIn("Positions to be written: 1", output)
        self.assertEqual(UserProfile.objects.get(user=self.admin_user).staff_position, "")

    def test_apply_writes_only_administrative_and_only_when_empty(self):
        self._run(apply_changes=True)
        self.assertEqual(UserProfile.objects.get(user=self.admin_user).staff_position, "İnzibati işçi")
        # inzibati=0 → heç nə yazılmır.
        self.assertEqual(UserProfile.objects.get(user=self.plain_user).staff_position, "")
        # Mövcud vəzifə ƏZİLMİR (additive).
        self.assertEqual(UserProfile.objects.get(user=self.filled_user).staff_position, "Kafedra müdiri")

    def test_roles_are_never_touched(self):
        before = {
            profile.user_id: profile.role
            for profile in UserProfile.objects.filter(user__in=[self.admin_user, self.plain_user, self.filled_user])
        }
        self._run(apply_changes=True)
        after = {
            profile.user_id: profile.role
            for profile in UserProfile.objects.filter(user__in=[self.admin_user, self.plain_user, self.filled_user])
        }
        self.assertEqual(before, after)
        self.assertEqual(set(after.values()), {ProfileRole.MEMBER})

    def test_teacher_type_is_reported_as_unknown_and_never_written(self):
        output = self._run(apply_changes=True)
        self.assertIn("UNKNOWN", output)
        self.assertIn("teacher_type=1: 2 people", output)
        self.assertIn("teacher_type=2: 1 people", output)
        self.assertIn("teacher_type=3: 1 people", output)
        positions = set(UserProfile.objects.values_list("staff_position", flat=True))
        self.assertFalse({value for value in positions if "teacher_type" in value})

    def test_permit_holders_are_listed_for_manual_confirmation(self):
        output = self._run()
        self.assertIn("MANUAL CONFIRMATION", output)
        self.assertIn("lsp_admin", output)
        self.assertIn("lsp_filled", output)

    def test_unmatched_rows_are_counted_not_crashed(self):
        output = self._run()
        self.assertIn("Matched accounts: 3", output)
        self.assertIn("Rows with no matching account: 1", output)

    def test_malformed_source_is_rejected_fail_closed(self):
        with self.assertRaises(CommandError):
            call_command("import_legacy_staff_positions", "--source", self._source({"not": "a list"}))
        with self.assertRaises(CommandError):
            call_command("import_legacy_staff_positions", "--source", self._source([{"inzibati": 1}]))
