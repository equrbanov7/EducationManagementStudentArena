"""Audit 2026-09-28 W3 — cədvəl yazıları ``pg_advisory_xact_lock(təşkilat, semestr)`` ilə seriyalaşır.

* ardıcıl iki cəhd: eyni müəllimin üst-üstə düşən ikinci slotu rədd olunur (kilid altında yoxlama);
* hər üç yazı yolu (idarə / redaktor / toplu dərc) kilidi yoxlamadan ƏVVƏL götürür;
* iki paralel tranzaksiya: ikincisi birincinin commit-inə qədər kilidi ala bilmir.
"""

from __future__ import annotations

import datetime
import threading
from unittest import mock

from django.contrib.auth import get_user_model
from django.db import connection, connections, transaction
from django.test import TestCase, TransactionTestCase, skipUnlessDBFeature

from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit
from apps.registrar import schedule, schedule_lock, services
from apps.registrar.models import ScheduleSlot, Subject
from core.constants import AcademicPeriodType, OrganizationType, OrgUnitType
from core.rls import bypass_rls

User = get_user_model()

T9 = datetime.time(9, 0)
T1030 = datetime.time(10, 30)
T10 = datetime.time(10, 0)
T1130 = datetime.time(11, 30)


class ScheduleLockKeyTest(TestCase):
    def test_key_is_stable_signed_bigint_and_scoped(self):
        key = schedule_lock.lock_key("org-a", "period-1")
        self.assertEqual(key, schedule_lock.lock_key("org-a", "period-1"))
        self.assertTrue(-(2**63) <= key < 2**63)
        self.assertNotEqual(key, schedule_lock.lock_key("org-a", "period-2"))
        self.assertNotEqual(key, schedule_lock.lock_key("org-b", "period-1"))

    def test_lock_outside_transaction_is_refused(self):
        if connection.vendor != "postgresql":
            self.skipTest("PostgreSQL advisory lock")
        with mock.patch.object(type(connection), "in_atomic_block", new=False, create=True):
            with self.assertRaises(RuntimeError):
                schedule_lock.lock_schedule("org", "period")


class ScheduleDoubleBookingTest(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("w3_owner", "w3_owner@qku.edu.az", "pw")
        with bypass_rls():
            self.org = Organization.objects.create(
                name="W3 Univ",
                slug="w3-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=self.owner,
                status="active",
                is_active=True,
            )
            self.group = OrgUnit.objects.create(
                organization=self.org, name="G1", slug="w3-g1", unit_type=OrgUnitType.GROUP
            )
            self.group2 = OrgUnit.objects.create(
                organization=self.org, name="G2", slug="w3-g2", unit_type=OrgUnitType.GROUP
            )
            self.period = AcademicPeriod.objects.create(
                organization=self.org,
                name="P",
                period_type=AcademicPeriodType.SEMESTER,
                academic_year="2024/2025",
                start_date="2024-09-01",
                end_date="2025-01-31",
                is_current=True,
            )
            self.teacher = User.objects.create_user("w3_teacher", "w3_teacher@qku.edu.az", "pw")
            Membership.objects.create(
                user=self.teacher,
                organization=self.org,
                role=self.org.roles.get(name="teacher"),
                is_primary=True,
                is_active=True,
            )
            math = Subject.objects.create(organization=self.org, code="W3M", name="Riyaziyyat")
            phys = Subject.objects.create(organization=self.org, code="W3P", name="Fizika")
            self.off1 = self._off(math, self.group)
            self.off2 = self._off(phys, self.group2)

    def _off(self, subject, group):
        off = services.get_or_create_offering(organization=self.org, subject=subject, period=self.period, group=group)
        off.instructor = self.teacher
        off.save(update_fields=["instructor"])
        return off

    def test_second_overlapping_teacher_slot_rejected_under_lock(self):
        with bypass_rls():
            with mock.patch.object(schedule_lock, "lock_schedule", wraps=schedule_lock.lock_schedule) as spy:
                schedule.create_slot(offering=self.off1, weekday=1, start_time=T9, end_time=T1030)
                with self.assertRaises(schedule.ScheduleConflict):
                    schedule.create_slot(offering=self.off2, weekday=1, start_time=T10, end_time=T1130)
            self.assertEqual(ScheduleSlot.objects.filter(offering__in=[self.off1, self.off2]).count(), 1)
        self.assertEqual(spy.call_count, 2)
        spy.assert_called_with(self.org.pk, self.period.pk)

    def test_manage_action_checks_under_lock(self):
        """İdarə yolu: toqquşma yoxlaması kilid götürüləndən SONRA gedir (atomik yoxla → yaz)."""
        from apps.registrar import schedule_manage, schedule_manage_actions

        order = []
        with (
            mock.patch.object(schedule_manage_actions, "_guard"),
            mock.patch.object(schedule_lock, "lock_schedule", side_effect=lambda *a: order.append("lock")) as lock_spy,
            mock.patch.object(
                schedule_manage,
                "check_slot",
                side_effect=lambda **kw: order.append("check") or {"_conflict": None, "teacher": "busy"},
            ),
        ):
            with self.assertRaises(schedule_manage_actions.ScheduleManageError):
                schedule_manage_actions.create_slot(
                    actor=self.owner,
                    organization=self.org,
                    offering=self.off2,
                    data={"weekday": "1", "time_slot": "", "start_time": "10:00", "end_time": "11:30"},
                )
        self.assertEqual(order, ["lock", "check"])
        lock_spy.assert_called_once_with(self.org.pk, self.period.pk)

    def test_publish_checks_conflicts_under_lock(self):
        from apps.registrar import schedule_publish

        # Dərc yalnız bitməmiş semestrə gedir (bitmiş semestr kilidə çatmadan rədd olunur).
        with bypass_rls():
            self.period.end_date = datetime.date.today() + datetime.timedelta(days=60)
            self.period.save(update_fields=["end_date"])
        order = []
        with (
            mock.patch.object(schedule_lock, "lock_schedule", side_effect=lambda *a: order.append("lock")),
            mock.patch.object(schedule_publish, "find_conflicts", side_effect=lambda **kw: order.append("check") or []),
            mock.patch("core.audit.log_action"),
        ):
            with bypass_rls():
                schedule_publish.publish_slots(
                    actor=self.owner,
                    organization=self.org,
                    period=self.period,
                    offering_ids=[],
                    slots=[],
                )
        self.assertEqual(order, ["lock", "check"])


@skipUnlessDBFeature("has_select_for_update")
class ScheduleLockConcurrencyTest(TransactionTestCase):
    """İki paralel tranzaksiya: B kilidi yalnız A commit edəndən sonra alır."""

    def test_second_transaction_waits_for_first(self):
        if connection.vendor != "postgresql":
            self.skipTest("PostgreSQL advisory lock")
        a_locked, a_release, b_acquired = threading.Event(), threading.Event(), threading.Event()
        errors = []

        def holder():
            try:
                with transaction.atomic():
                    schedule_lock.lock_schedule("org-x", "period-x")
                    a_locked.set()
                    a_release.wait(10)
            except Exception as exc:  # pragma: no cover — diaqnostika
                errors.append(exc)
            finally:
                connections.close_all()

        def waiter():
            try:
                a_locked.wait(10)
                with transaction.atomic():
                    schedule_lock.lock_schedule("org-x", "period-x")
                    b_acquired.set()
            except Exception as exc:  # pragma: no cover — diaqnostika
                errors.append(exc)
            finally:
                connections.close_all()

        first, second = threading.Thread(target=holder), threading.Thread(target=waiter)
        first.start()
        second.start()
        self.assertTrue(a_locked.wait(10))
        # A kilidi saxlayır — B gözləməlidir.
        self.assertFalse(b_acquired.wait(1.0))
        a_release.set()
        self.assertTrue(b_acquired.wait(10))
        first.join(10)
        second.join(10)
        self.assertEqual(errors, [])
