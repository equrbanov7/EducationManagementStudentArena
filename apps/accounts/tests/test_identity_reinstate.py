"""Bərpa əmri ilə girişin açılması — sanksiyalanmış səthin qapıları.

Servis qatı (`people/movements.py::_require`) bərpa əmri üçün aktordan
`student.movement` + `people.manage_academic` cütlüyünü tələb edir. Bu fayl
DB qatındakı TƏKRAR qapını yoxlayır (accounts 0021,
`accounts_reinstate_student_identity`) — yəni servis yan keçilsə belə
`archived → active` keçidi bağlıdır. Postgres-siz mühitdə trigger/funksiya
yoxdur, ona görə həmin testlər `postgres` markeri ilə işarələnib.
"""

from django.contrib.auth import get_user_model
from django.db import DatabaseError, connection, transaction
from django.test import TestCase

import pytest

from apps.accounts.models import UserProfile
from apps.accounts.services.identity_access import IdentityAccessError
from apps.accounts.services.identity_reinstate import order_evidence_digest, reinstate_student_access
from apps.organizations.models import Membership, Organization
from core.constants import OrganizationType
from core.rls import bypass_rls

User = get_user_model()


class OrderDigestTests(TestCase):
    """Sübutun barmaq izi ƏMRDƏN çıxır — əmr dəyişsə digest də dəyişir."""

    def test_digest_is_stable_for_the_same_order(self):
        first = order_evidence_digest(order_number="R-141", order_date="2026-09-01", record_id=7, actor_id=3)
        second = order_evidence_digest(order_number=" R-141 ", order_date="2026-09-01", record_id=7, actor_id=3)
        self.assertEqual(first, second)
        self.assertRegex(first, r"^[0-9a-f]{64}$")

    def test_digest_changes_when_the_order_changes(self):
        base = order_evidence_digest(order_number="R-141", order_date="2026-09-01", record_id=7, actor_id=3)
        for changed in (
            order_evidence_digest(order_number="R-142", order_date="2026-09-01", record_id=7, actor_id=3),
            order_evidence_digest(order_number="R-141", order_date="2026-09-02", record_id=7, actor_id=3),
            order_evidence_digest(order_number="R-141", order_date="2026-09-01", record_id=8, actor_id=3),
            order_evidence_digest(order_number="R-141", order_date="2026-09-01", record_id=7, actor_id=4),
        ):
            self.assertNotEqual(base, changed)


class ReinstateGuardTests(TestCase):
    """Sübutsuz/formasız çağırışlar Python qatında da rədd olunur."""

    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("ri_owner", "ri_owner@qku.edu.az", "pw")
        with bypass_rls():
            cls.org = Organization.objects.create(
                name="RI Univ",
                slug="ri-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=cls.owner,
                status="active",
                is_active=True,
            )
            cls.student = User.objects.create_user("ri_student", "ri_student@qku.edu.az", "pw")
            Membership.objects.create(
                user=cls.student,
                organization=cls.org,
                role=cls.org.roles.get(name="student"),
                is_primary=True,
                is_active=True,
            )
            UserProfile.objects.filter(user=cls.student).update(
                organization=cls.org, access_state=UserProfile.AccessState.ARCHIVED
            )
            # Girişi AÇIQ qalan ikinci tələbə — «no-op» yolunu yoxlamaq üçün.
            # (Arxivlənmiş profili xam UPDATE ilə geri açmaq olmaz: trigger onu
            # məhz bunun üçün bloklayır, yəni fixture ayrı hesab tələb edir.)
            cls.open_student = User.objects.create_user("ri_open", "ri_open@qku.edu.az", "pw")
            Membership.objects.create(
                user=cls.open_student,
                organization=cls.org,
                role=cls.org.roles.get(name="student"),
                is_primary=True,
                is_active=True,
            )
            UserProfile.objects.filter(user=cls.open_student).update(organization=cls.org)

    def test_a_malformed_digest_is_refused(self):
        for digest in ("", "not-a-digest", "a" * 63, "z" * 64):
            with self.assertRaises(IdentityAccessError):
                reinstate_student_access(
                    user=self.student,
                    organization=self.org,
                    actor=self.owner,
                    evidence_digest=digest,
                )

    def test_an_already_open_account_is_a_noop(self):
        result = reinstate_student_access(
            user=self.open_student,
            organization=self.org,
            actor=self.owner,
            evidence_digest="b" * 64,
        )
        self.assertFalse(result.reopened)


@pytest.mark.postgres
class DatabaseGateTests(TestCase):
    """DB funksiyası servis qatından ASILI OLMADAN səlahiyyət cütlüyünü tələb edir."""

    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("rg_owner", "rg_owner@qku.edu.az", "pw")
        with bypass_rls():
            cls.org = Organization.objects.create(
                name="RG Univ",
                slug="rg-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=cls.owner,
                status="active",
                is_active=True,
            )
            cls.student = User.objects.create_user("rg_student", "rg_student@qku.edu.az", "pw")
            Membership.objects.create(
                user=cls.student,
                organization=cls.org,
                role=cls.org.roles.get(name="student"),
                is_primary=True,
                is_active=True,
            )
            UserProfile.objects.filter(user=cls.student).update(
                organization=cls.org, access_state=UserProfile.AccessState.ARCHIVED
            )
            # Tələbə rolu ilə aktor: `student.movement` DƏ, `people.manage_academic` DA yoxdur.
            cls.weak_actor = User.objects.create_user("rg_weak", "rg_weak@qku.edu.az", "pw")
            Membership.objects.create(
                user=cls.weak_actor,
                organization=cls.org,
                role=cls.org.roles.get(name="student"),
                is_primary=True,
                is_active=True,
            )
            UserProfile.objects.filter(user=cls.weak_actor).update(organization=cls.org)

    def setUp(self):
        if connection.vendor != "postgresql":
            self.skipTest("Bərpa funksiyası yalnız PostgreSQL-də mövcuddur")

    def test_an_actor_without_the_permission_pair_cannot_reopen_access(self):
        with self.assertRaises(DatabaseError):
            with transaction.atomic():
                reinstate_student_access(
                    user=self.student,
                    organization=self.org,
                    actor=self.weak_actor,
                    evidence_digest="c" * 64,
                )
        self.assertEqual(
            UserProfile.objects.get(user=self.student).access_state,
            UserProfile.AccessState.ARCHIVED,
        )

    def test_a_raw_update_still_cannot_reopen_access(self):
        """Trigger yerindədir: servisdən yan keçən xam UPDATE `42501` alır."""
        with self.assertRaises(DatabaseError):
            with transaction.atomic():
                UserProfile.objects.filter(user=self.student).update(access_state=UserProfile.AccessState.ACTIVE)
        self.assertEqual(
            UserProfile.objects.get(user=self.student).access_state,
            UserProfile.AccessState.ARCHIVED,
        )
