"""Həqiqi miqrasiya: RLS, raw-SQL sərhədi, append-only sübut və paralel retry."""

import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from threading import Barrier
from types import SimpleNamespace

from django.db import IntegrityError, close_old_connections, connection, transaction
from django.test import RequestFactory

import pytest

from apps.registrar import absence_credit, gradebook
from apps.registrar.models import AbsenceCredit
from apps.registrar.tests.test_absence_credit import AbsenceCreditTests
from apps.registrar.tests.test_corrections_bridge import _BaseJournalSetup
from apps.registrar.tests.test_exam_score_sheet_invariants import build_tenant
from core.rls import bypass_rls

pytestmark = pytest.mark.postgres


class AbsenceCreditPostgresTests(AbsenceCreditTests):
    # Inherited behavior runs against the real migration/trigger as well.
    def raw_entry(self, **kwargs):
        values = dict(
            organization=self.org,
            enrollment=self.enrollment,
            actor=self.admin,
            hours=8,
            reason="DB səviyyəsində yoxlanan ümumi güzəşt",
            request_token=uuid.uuid4(),
            old_absence_hours=12,
            new_absence_hours=4,
        )
        values.update(kwargs)
        return AbsenceCredit.objects.create(**values)

    @contextmanager
    def app_role(self, organization):
        role = "credit_probe_" + uuid.uuid4().hex[:12]
        with connection.cursor() as cursor:
            cursor.execute(f"CREATE ROLE {role} NOSUPERUSER NOBYPASSRLS")
            cursor.execute(f"GRANT USAGE ON SCHEMA public TO {role}")
            cursor.execute(f"GRANT SELECT,INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA public TO {role}")
            cursor.execute(f"GRANT USAGE,SELECT ON ALL SEQUENCES IN SCHEMA public TO {role}")
            cursor.execute("SELECT set_config('app.bypass_rls', 'off', true)")
            cursor.execute("SELECT set_config('app.current_org_id', %s, true)", [str(organization.pk)])
            cursor.execute(f"SET LOCAL ROLE {role}")
            cursor.execute("SELECT rolsuper,rolbypassrls FROM pg_roles WHERE rolname=current_user")
            self.assertEqual(cursor.fetchone(), (False, False))
        try:
            yield
        finally:
            with connection.cursor() as cursor:
                cursor.execute("RESET ROLE")
                cursor.execute("SELECT set_config('app.bypass_rls', 'on', true)")
                cursor.execute(f"DROP OWNED BY {role}")
                cursor.execute(f"DROP ROLE {role}")

    def test_nonbypass_role_valid_write_foreign_read_and_cross_tenant_reference(self):
        other = build_tenant("credit-other-tenant")
        with self.app_role(self.org):
            credit = self.apply()
            self.assertEqual(AbsenceCredit.objects.count(), 1)
            with self.assertRaises(IntegrityError), transaction.atomic():
                self.raw_entry(enrollment=other.enrollments[0])
            with self.assertRaises(IntegrityError), transaction.atomic():
                self.raw_entry(organization=other.org)
        with self.app_role(other.org):
            self.assertFalse(AbsenceCredit.objects.filter(pk=credit.pk).exists())
        self.enrollment.refresh_from_db()
        self.assertEqual(self.enrollment.absence_hours, 4)

    def test_raw_sql_cannot_overcredit_rewrite_or_delete_evidence(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.raw_entry(hours=20, new_absence_hours=0)
        first = self.apply()
        with self.assertRaises(IntegrityError), transaction.atomic():
            AbsenceCredit.objects.filter(pk=first.pk).update(hours=2)
        with self.assertRaises(IntegrityError), transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute("DELETE FROM registrar_absencecredit WHERE id=%s", [first.pk])
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.raw_entry(reverses=first, hours=2, old_absence_hours=4, new_absence_hours=6)
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.raw_entry(old_absence_hours=12, new_absence_hours=4)
        self.assertEqual(AbsenceCredit.objects.count(), 1)


@pytest.mark.django_db(transaction=True)
def test_concurrent_identical_request_creates_one_credit_and_consistent_counter():
    fixture = SimpleNamespace()
    _BaseJournalSetup.setUp(fixture)
    for day in range(1, 7):
        _BaseJournalSetup._absent_lesson(fixture, day, hours=2)
    barrier, token = Barrier(2), uuid.uuid4()

    def worker():
        close_old_connections()
        try:
            request = RequestFactory().post("/")
            request.user, request.organization = fixture.admin, fixture.org
            barrier.wait(timeout=10)
            with bypass_rls():
                return absence_credit.adjust(
                    request=request,
                    offering=fixture.offering,
                    enrollment_id=fixture.enrollment.pk,
                    hours=8,
                    reason="Paralel eyni sorğunun təkrar göndərilməsi",
                    request_token=token,
                ).pk
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        ids = list(pool.map(lambda _: worker(), range(2)))
    assert ids[0] == ids[1]
    with bypass_rls():
        assert AbsenceCredit.objects.count() == 1
        fixture.enrollment.refresh_from_db()
        assert fixture.enrollment.absence_hours == 4
        assert gradebook.recompute_absence_hours(enrollment=fixture.enrollment) == 4
