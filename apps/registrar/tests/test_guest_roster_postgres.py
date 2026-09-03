"""«Alt qrupdan əlavə» provenansının DB-səviyyə qoruyucuları (yalnız PostgreSQL).

Django qatı onsuz da servis yolundan keçir; burada XAM yazının (``.update()``,
``objects.create()``) da kəsildiyi yoxlanılır — audit izi tətbiq qatını yan
keçərək dəyişdirilə bilməməlidir (migration 0056).
"""

from django.db import IntegrityError, connection, transaction

import pytest

from apps.registrar.models import Enrollment
from core.rls import bypass_rls

from .test_guest_roster import _GuestRosterBase

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(connection.vendor != "postgresql", reason="PostgreSQL triggers are required."),
]


class GuestSourceGroupGuardTests(_GuestRosterBase):
    def test_source_group_is_write_once(self):
        """Provenans bir dəfə yazılır — sonradan başqa qrupa «düzəldilə» bilməz."""
        self._drop_own_history(self.guest)
        with bypass_rls():
            from apps.registrar import guest_roster

            enrollment = guest_roster.add_guest_student(
                offering=self.offering, student=self.guest, by_user=self.coordinator
            )
            with self.assertRaises(IntegrityError):
                with transaction.atomic():
                    Enrollment.objects.filter(pk=enrollment.pk).update(source_group=self.group1)

    def test_source_group_cannot_be_cleared(self):
        self._drop_own_history(self.guest)
        with bypass_rls():
            from apps.registrar import guest_roster

            enrollment = guest_roster.add_guest_student(
                offering=self.offering, student=self.guest, by_user=self.coordinator
            )
            with self.assertRaises(IntegrityError):
                with transaction.atomic():
                    Enrollment.objects.filter(pk=enrollment.pk).update(source_group=None)

    def test_cross_organization_source_group_is_rejected(self):
        """Mənbə qrup tələbənin təşkilatına aid olmalıdır (same-org trigger)."""
        from apps.organizations.models import Organization, OrgUnit
        from core.constants import OrganizationType, OrgUnitType

        with bypass_rls():
            other_org = Organization.objects.create(
                name="GR Other",
                slug="gr-other",
                org_type=OrganizationType.UNIVERSITY,
                owner=self.owner,
                status="active",
                is_active=True,
            )
            foreign_group = OrgUnit.objects.create(
                organization=other_org, name="FG", slug="gr-fg", unit_type=OrgUnitType.GROUP
            )
            enrollment = self.host.enrollments.get(offering=self.offering)
            with self.assertRaises(IntegrityError):
                with transaction.atomic():
                    Enrollment.objects.filter(pk=enrollment.pk).update(source_group=foreign_group)
