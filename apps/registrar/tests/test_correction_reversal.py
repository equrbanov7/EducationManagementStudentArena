"""Service-level guarantees for the append-only correction reversal ledger."""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import RequestFactory

from apps.organizations.models import Membership
from apps.registrar import (
    correction_reversals,
    corrections,
    gradebook_components,
    item_corrections,
    journal_extras,
)
from apps.registrar.models import (
    ComponentScoreCorrection,
    CorrectionField,
    CorrectionReason,
    CorrectionReversal,
    JournalCorrection,
    SelfWorkCorrection,
    SelfWorkMark,
)
from apps.registrar.tests.test_corrections_bridge import _BaseJournalSetup, _pdf
from core.rls import bypass_rls

User = get_user_model()


class CorrectionReversalLedgerTests(_BaseJournalSetup):
    def _apply_grade(self, mark, score, note="ledger"):
        return corrections.apply_correction(
            mark=mark,
            field=CorrectionField.SCORE,
            new_score=score,
            reason=CorrectionReason.TECHNICAL,
            note=note,
            document=_pdf(),
            by_user=self.admin,
        )

    def _login_corrector(self):
        self.client.force_login(self.admin)
        session = self.client.session
        session["active_organization"] = self.org.slug
        session.save()

    def _revert_url(self):
        return f"/jurnal/duzelis/{self.offering.id}/sil/"

    def test_http_requires_exact_correction_id_and_does_not_mutate(self):
        _lesson, mark = self._seminar_mark(13, 3)
        with bypass_rls():
            self._apply_grade(mark, 7)
        self._login_corrector()

        response = self.client.post(
            self._revert_url(),
            data={"type": "grade", "mark_id": str(mark.pk)},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 409)
        mark.refresh_from_db()
        self.assertEqual(mark.score, 7)
        self.assertFalse(CorrectionReversal.objects.exists())

    def test_duplicate_exact_http_retry_is_idempotent(self):
        _lesson, mark = self._seminar_mark(14, 3)
        with bypass_rls():
            correction = self._apply_grade(mark, 7)
        self._login_corrector()
        payload = {
            "type": "grade",
            "mark_id": str(mark.pk),
            "correction_id": str(correction.pk),
        }

        first = self.client.post(self._revert_url(), data=payload, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        second = self.client.post(self._revert_url(), data=payload, HTTP_X_REQUESTED_WITH="XMLHttpRequest")

        self.assertEqual((first.status_code, second.status_code), (200, 200))
        self.assertTrue(first.json()["ok"])
        self.assertTrue(second.json()["ok"])
        self.assertEqual(CorrectionReversal.objects.filter(journal_correction=correction).count(), 1)
        mark.refresh_from_db()
        self.assertEqual(mark.score, 3)

    def test_stale_modal_id_cannot_reverse_a_newer_correction(self):
        _lesson, mark = self._seminar_mark(15, 3)
        with bypass_rls():
            older = self._apply_grade(mark, 6, "older")
            mark.refresh_from_db()
            newer = self._apply_grade(mark, 9, "newer")
        self._login_corrector()

        response = self.client.post(
            self._revert_url(),
            data={
                "type": "grade",
                "mark_id": str(mark.pk),
                "correction_id": str(older.pk),
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 409)
        mark.refresh_from_db()
        self.assertEqual(mark.score, 9)
        self.assertFalse(CorrectionReversal.objects.exists())
        self.assertTrue(JournalCorrection.objects.filter(pk=newer.pk).exists())

    def test_apply_audit_failure_rolls_back_domain_and_evidence(self):
        _lesson, mark = self._seminar_mark(16, 3)
        with bypass_rls(), patch.object(corrections, "log_action", side_effect=RuntimeError("audit down")):
            with self.assertRaisesRegex(RuntimeError, "audit down"):
                self._apply_grade(mark, 8)

        mark.refresh_from_db()
        self.assertEqual(mark.score, 3)
        self.assertFalse(JournalCorrection.objects.exists())

    def test_reversal_audit_failure_rolls_back_value_and_ledger(self):
        _lesson, mark = self._seminar_mark(17, 3)
        with bypass_rls():
            correction = self._apply_grade(mark, 8)
        with (
            bypass_rls(),
            patch.object(correction_reversals, "log_action", side_effect=RuntimeError("audit down")),
        ):
            with self.assertRaisesRegex(RuntimeError, "audit down"):
                corrections.revert_last_grade_correction(
                    mark=mark,
                    by_user=self.admin,
                    correction_id=correction.pk,
                )

        mark.refresh_from_db()
        self.assertEqual(mark.score, 8)
        self.assertFalse(CorrectionReversal.objects.exists())
        self.assertTrue(JournalCorrection.objects.filter(pk=correction.pk).exists())

    def test_item_audit_failure_rolls_back_mark_and_evidence(self):
        with bypass_rls():
            topic = journal_extras.add_selfwork_topic(offering=self.offering, title="audit rollback")
        with bypass_rls(), patch.object(item_corrections, "log_action", side_effect=RuntimeError("audit down")):
            with self.assertRaisesRegex(RuntimeError, "audit down"):
                item_corrections.apply_selfwork_correction(
                    offering=self.offering,
                    topic=topic,
                    enrollment=self.enrollment,
                    new_done=True,
                    reason=CorrectionReason.TECHNICAL,
                    note="rollback",
                    document=_pdf(),
                    by_user=self.admin,
                )

        self.assertFalse(SelfWorkMark.objects.filter(topic=topic, enrollment=self.enrollment).exists())
        self.assertFalse(SelfWorkCorrection.objects.exists())

    def test_reversal_uses_real_actor_without_copying_pii(self):
        _lesson, mark = self._seminar_mark(18, 3)
        with bypass_rls():
            correction = self._apply_grade(mark, 8)
        request = RequestFactory().post("/")
        request.user = self.admin
        request.is_view_as = True
        request.real_user = self.owner
        request.view_as_mode = "student"

        with bypass_rls():
            corrections.revert_last_grade_correction(
                mark=mark,
                by_user=self.admin,
                request=request,
                correction_id=correction.pk,
            )

        reversal = CorrectionReversal.objects.get(journal_correction=correction)
        self.assertEqual(reversal.reverted_by_id, self.owner.pk)
        self.assertEqual(reversal.reverted_by_ref, str(self.owner.pk))
        self.assertEqual(reversal.reason_code, "operator_revert")
        field_names = {field.name for field in CorrectionReversal._meta.fields}
        self.assertFalse(field_names & {"name", "username", "email", "full_name"})

    def test_direct_service_rejects_inactive_or_cross_tenant_actor(self):
        _lesson, mark = self._seminar_mark(25, 3)
        with bypass_rls():
            correction = self._apply_grade(mark, 8)
            outsider = User.objects.create_user("reversal_sqlite_outsider", password="pw")
            inactive = User.objects.create_user("reversal_sqlite_inactive", password="pw", is_active=False)
            Membership.objects.create(
                organization=self.org,
                user=inactive,
                role=self.org.roles.get(name="member"),
                is_active=True,
            )

            for actor in (outsider, inactive):
                with self.subTest(actor=actor.pk), self.assertRaises(ValidationError):
                    corrections.revert_last_grade_correction(
                        mark=mark,
                        by_user=actor,
                        correction_id=correction.pk,
                    )

        mark.refresh_from_db()
        self.assertEqual(mark.score, 8)
        self.assertFalse(CorrectionReversal.objects.exists())

    def test_correction_and_reversal_instance_history_is_immutable(self):
        _lesson, mark = self._seminar_mark(19, 3)
        with bypass_rls():
            correction = self._apply_grade(mark, 8)
            corrections.revert_last_grade_correction(
                mark=mark,
                by_user=self.admin,
                correction_id=correction.pk,
            )
        reversal = CorrectionReversal.objects.get(journal_correction=correction)

        correction.note = "rewritten"
        with self.assertRaises(ValidationError):
            correction.save()
        with self.assertRaises(ValidationError):
            correction.delete()
        reversal.reason_code = "rewritten"
        with self.assertRaises(ValidationError):
            reversal.save()
        with self.assertRaises(ValidationError):
            reversal.delete()

    def test_correction_backed_selfwork_topic_delete_is_graceful(self):
        with bypass_rls():
            topic = journal_extras.add_selfwork_topic(offering=self.offering, title="protected")
            correction = item_corrections.apply_selfwork_correction(
                offering=self.offering,
                topic=topic,
                enrollment=self.enrollment,
                new_done=True,
                reason=CorrectionReason.TECHNICAL,
                note="evidence",
                document=_pdf(),
                by_user=self.admin,
            )
            self.assertFalse(journal_extras.delete_selfwork_topic(topic=topic))

        topic.refresh_from_db()
        self.assertTrue(SelfWorkCorrection.objects.filter(pk=correction.pk).exists())

    def test_correction_backed_component_delete_is_graceful(self):
        with bypass_rls():
            component = list(journal_extras.ensure_kollokviums(self.offering))[0]
            correction = item_corrections.apply_component_correction(
                component=component,
                enrollment=self.enrollment,
                new_score=7,
                reason=CorrectionReason.TECHNICAL,
                note="evidence",
                document=_pdf(),
                by_user=self.admin,
            )
            remaining = gradebook_components.save_components(
                offering=self.offering,
                definitions=[],
                by_user=self.admin,
            )

        self.assertIn(component.pk, {row.pk for row in remaining})
        self.assertTrue(ComponentScoreCorrection.objects.filter(pk=correction.pk).exists())
