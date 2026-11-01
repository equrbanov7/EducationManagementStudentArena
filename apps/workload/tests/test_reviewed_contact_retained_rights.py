"""Retain reviewed legacy cohorts exactly; excluded active students gain no share."""

import json
from contextlib import ExitStack
from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import connection
from django.test import TestCase

from apps.registrar.models import Enrollment, JournalShare
from apps.workload.services.reviewed_chair_contacts import engine, retained_rights, state
from apps.workload.services.sbio235_state import RepairError
from apps.workload.tests.factories import TEACHER_PERMS, activate_member
from apps.workload.tests.test_reviewed_chair_contacts import ReviewedChairContactsTests as Fixture


class RetainedContactRightsTests(TestCase):
    setUpTestData = classmethod(Fixture.setUpTestData.__func__)
    setUp = Fixture.setUp
    run_repair = Fixture.run_repair
    apply = Fixture.apply

    def reviewed(self):
        pins, shares = {}, []
        for offering in self.offerings:
            enrolled = Enrollment.objects.get(offering=offering)
            for teacher, kind in ((self.new, "lecture"), (self.old, "seminar")):
                share = JournalShare.objects.create(
                    organization=self.org,
                    offering=offering,
                    teacher=teacher,
                    source="legacy",
                    kinds=[kind],
                    created_by=self.actor,
                    batch="reviewed-test-batch",
                )
                share.enrollments.add(enrolled)
                shares.append(share)
            raw = list(JournalShare.objects.filter(offering=offering).order_by("pk").values())
            links = list(
                JournalShare.enrollments.through.objects.filter(journalshare__offering=offering).order_by("pk").values()
            )
            es = list(
                Enrollment.objects.filter(pk=enrolled.pk).order_by("pk").values(*retained_rights.ENROLLMENT_FIELDS)
            )
            pins[str(offering.pk)] = {
                "shares": {str(s["id"]): retained_rights.sha(s) for s in raw},
                "through_sha256": retained_rights.sha(links),
                "selected_enrollments_sha256": retained_rights.sha(es),
            }
            extra = get_user_model().objects.create_user("excluded-" + str(offering.pk))
            activate_member(self.org, extra, "student", permissions=["grade.view"])
            Enrollment.objects.create(organization=self.org, offering=offering, student=extra)
        stack = self.enterContext(ExitStack())
        stack.enter_context(patch.object(retained_rights, "PINS", pins))
        return shares

    def test_apply_repeat_undo_preserve_legacy_record_and_selected_scope_exactly(self):
        shares = self.reviewed()
        ids = [s.pk for s in shares]
        before = list(JournalShare.objects.filter(pk__in=ids).order_by("pk").values())
        links = list(JournalShare.enrollments.through.objects.filter(journalshare_id__in=ids).order_by("pk").values())
        result = self.apply()
        self.assertEqual(self.run_repair(apply=True)["status"], "already_correct")
        self.assertFalse(JournalShare.objects.filter(source="workload").exists())
        self.assertEqual(list(JournalShare.objects.filter(pk__in=ids).order_by("pk").values()), before)
        self.assertEqual(
            list(JournalShare.enrollments.through.objects.filter(journalshare_id__in=ids).order_by("pk").values()),
            links,
        )
        undo = self.run_repair(undo=result["receipt"])
        self.run_repair(undo=result["receipt"], apply=True, expected_baseline=undo["baseline"])
        self.assertEqual(list(JournalShare.objects.filter(pk__in=ids).order_by("pk").values()), before)
        self.assertEqual(sum(s.enrollments.count() for s in shares), 4)

    def test_added_selected_student_and_changed_raw_provenance_fail_closed(self):
        shares = self.reviewed()
        extra = (
            Enrollment.objects.filter(offering=self.offerings[0])
            .exclude(pk__in=shares[0].enrollments.values("pk"))
            .get()
        )
        shares[0].enrollments.add(extra)
        with self.assertRaisesMessage(RepairError, "selected_scope_changed"):
            self.run_repair()
        shares[0].enrollments.remove(extra)
        JournalShare.objects.filter(pk=shares[0].pk).update(batch="unreviewed")
        with self.assertRaisesMessage(RepairError, "share_record_changed"):
            self.run_repair()

    def test_unreviewed_manual_or_additional_share_rejected(self):
        self.reviewed()
        stranger = get_user_model().objects.create_user("unexpected-contact-share")
        activate_member(self.org, stranger, "teacher", permissions=TEACHER_PERMS)
        JournalShare.objects.create(
            organization=self.org, offering=self.offerings[0], teacher=stranger, source="manual"
        )
        with self.assertRaisesMessage(RepairError, "share_set_changed"):
            self.run_repair()

    def test_later_enrollment_identity_blocks_repeat_and_undo(self):
        shares = self.reviewed()
        result = self.apply()
        Enrollment.objects.filter(pk=shares[0].enrollments.get().pk).update(status="dropped")
        with self.assertRaisesMessage(RepairError, "selected_enrollment_changed"):
            self.run_repair(undo=result["receipt"])

    def test_actual_command_keeps_retained_scope_in_both_rls_modes(self):
        shares = self.reviewed()
        self.org.slug = "qku"
        self.org.save(update_fields=["slug"])

        def invoke(**options):
            output = StringIO()
            call_command("repair_reviewed_chair_contacts", actor=self.actor.username, stdout=output, **options)
            return json.loads(output.getvalue())

        original = engine.run

        def checked(**options):
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT current_setting('app.current_org_id',true),current_setting('app.bypass_rls',true)"
                )
                self.assertEqual(cursor.fetchone(), (str(self.org.pk), "off"))
            return original(**options)

        with patch("apps.workload.management.commands.repair_reviewed_chair_contacts.run", side_effect=checked):
            for scoped in (False, True):
                with self.settings(RLS_TRANSACTION_SCOPED=scoped):
                    dry = invoke()
                    result = invoke(apply=True, expected_baseline=dry["baseline"])
                    undo = invoke(undo=result["receipt"])
                    invoke(undo=result["receipt"], apply=True, expected_baseline=undo["baseline"])
        self.assertEqual(sum(s.enrollments.count() for s in shares), 4)

    def test_late_failure_rolls_back_all_canonical_edits_with_legacy_pins(self):
        self.reviewed()
        before = state.snapshot(self.org, state.selection(""))[0]
        dry = self.run_repair()
        with patch.object(engine, "preserved", side_effect=RepairError("late_retained_failure")):
            with self.assertRaisesMessage(RepairError, "late_retained_failure"):
                self.run_repair(apply=True, expected_baseline=dry["baseline"])
        self.assertEqual(state.snapshot(self.org, state.selection(""))[0], before)


# The imported fixture class is support, not a second collection of its tests.
del Fixture
