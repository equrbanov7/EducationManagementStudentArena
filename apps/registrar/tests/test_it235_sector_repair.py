"""Bounded sector recovery uses canonical transfers and preserves marked history."""

from contextlib import ExitStack
from unittest.mock import patch

from apps.accounts.models import UserProfile
from apps.organizations.models import Membership
from apps.registrar import it235_sector_repair as repair
from apps.registrar.models import StudentAcademicRecord
from core.rls import bypass_rls

from .test_transfer import GroupTransferTest, User


class SectorRepairTest(GroupTransferTest):
    def test_bounded_dry_apply_repeat_and_old_mark_preserved(self):
        with bypass_rls(), ExitStack() as stack:
            self.owner.is_superuser = True
            self.owner.save(update_fields=["is_superuser"])
            self.group2.settings = {"sector": "en"}
            self.group2.save(update_fields=["settings"])
            second = User.objects.create_user("sector_second")
            Membership.objects.create(
                user=second, organization=self.org, role=self.org.roles.get(name="student"), is_active=True
            )
            StudentAcademicRecord.objects.create(
                organization=self.org,
                student=second,
                program=self.program,
                curriculum=self.curriculum,
                group=self.group1,
                admission_year=2024,
            )
            for user, old_id, patronymic in ((self.student, "9049", "Ramin"), (second, "9086", "Anar")):
                UserProfile.objects.update_or_create(
                    user=user,
                    defaults={"organization": self.org, "institutional_identifier": old_id, "patronymic": patronymic},
                )
            for key, value in {
                "ORG": str(self.org.pk),
                "SOURCE": str(self.group1.pk),
                "TARGET": str(self.group2.pk),
                "PEOPLE": {self.student.pk: ("9049", "Ramin"), second.pk: ("9086", "Anar")},
            }.items():
                stack.enter_context(patch.object(repair, key, value))
            self._add_history()
            result = repair.run(organization=self.org, user=self.owner)
            self.assertEqual(result["pending"], 2)
            self.record.refresh_from_db()
            self.assertEqual(self.record.group_id, self.group1.pk)
            repair.run(organization=self.org, user=self.owner, apply=True, expected_baseline=result["baseline"])
            self.record.refresh_from_db()
            self.assertEqual(self.record.group_id, self.group2.pk)
            self.assertEqual(repair.run(organization=self.org, user=self.owner)["pending"], 0)
