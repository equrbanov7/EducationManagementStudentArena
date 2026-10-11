"""«Jurnal təmizliyi» — QƏRARLAR, qərar jurnalı və CLI (sahib 2026-10-10).

Kilidlənən qaydalar:

* önizləmə heç nə yazmır; tətbiq ``enrolled → suspended`` / ``→ dropped`` edir, qeydiyyat SİLİNMİR, hər sətir
  qərar jurnalına (sübut + sha256) və audit-ə (``registrar.journal_hygiene``) düşür;
* önizləmədən sonra sətir dəyişibsə (yeni bal, status) tətbiq ``drift`` ilə rədd olunur — heç nə yazılmır;
* bir əməl ≤ 500 sətir, səbəb ≥ 20 simvol; məlumatlı ayrılmış sətir yalnız dondurula bilər;
* qərar jurnalı APPEND-ONLY: DB trigger-i UPDATE/DELETE-i bloklayır (yalnız bir dəfəlik geri qaytarma sahələri);
* «Bərpa et» əvvəlki statusu qaytarır, ikinci dəfə geri qaytarmaq olmur, statusu dəyişmiş sətir bloklanır;
* yalnız superadmin və ya təşkilat miqyaslı ``journal.correct``;
* CLI defolt DRY-RUN-dır; ``--apply`` səbəb və markersiz bazada ``--i-know-this-is-production`` istəyir.
"""

from __future__ import annotations

import io
import uuid

from django.core.exceptions import ValidationError
from django.core.management import CommandError, call_command
from django.db import IntegrityError, InternalError, connection, transaction
from django.test.utils import CaptureQueriesContext

from apps.audit.models import AuditLog
from apps.organizations.models import Membership
from apps.registrar import journal_hygiene as hygiene
from apps.registrar import journal_hygiene_actions as actions
from apps.registrar.models import AcademicStatus, Enrollment, JournalHygieneDecision
from core.rls import bypass_rls

from .journal_hygiene_fixture import REASON, HygieneBase, User

_DB_GUARD_ERRORS = (IntegrityError, InternalError)


class _ActionsBase(HygieneBase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        with bypass_rls():
            cls.expelled = cls.make_student("jh_x1", status=AcademicStatus.EXPELLED)
            cls.expelled2 = cls.make_student("jh_x2", status=AcademicStatus.EXPELLED)
            cls.left_row = cls.enroll(cls.expelled)
            cls.left_row2 = cls.enroll(cls.expelled2)
            ghost = cls._offering(cls.subject_c, cls.past)
            cls.empty_row = cls.enroll(cls.make_student("jh_e1"), ghost)
            cls.dean = User.objects.create_user("jh_dean", "jh_dean@qku.edu.az", "pw")
            Membership.objects.create(
                user=cls.dean,
                organization=cls.org,
                role=cls.org.roles.get(name="dean"),
                is_primary=True,
                is_active=True,
            )

    def _preview(self, category, ids, target, actor=None):
        with bypass_rls():
            return actions.preview(
                organization=self.org,
                actor=actor or self.owner,
                category=category,
                enrollment_ids=[str(pk) for pk in ids],
                target=target,
            )

    def _apply(self, category, ids, target, *, digest=None, reason=REASON, actor=None):
        digest = digest if digest is not None else self._preview(category, ids, target)["digest"]
        with bypass_rls():
            return actions.apply(
                organization=self.org,
                actor=actor or self.owner,
                category=category,
                enrollment_ids=[str(pk) for pk in ids],
                target=target,
                reason=reason,
                expected_digest=digest,
            )

    def _revert(self, decision_ids, reason=REASON):
        with bypass_rls():
            return actions.revert(
                organization=self.org, actor=self.owner, decision_ids=[str(pk) for pk in decision_ids], reason=reason
            )


class ApplyAndRevertTest(_ActionsBase):
    def test_preview_writes_nothing_and_reports_impact(self):
        data = self._preview(hygiene.LEFT, [self.left_row.pk, self.left_row2.pk], actions.TARGET_SUSPEND)
        self.assertEqual((data["rows"], data["journals"], data["students"], data["missing"]), (2, 1, 2, 0))
        self.assertTrue(data["can_apply"])
        self.assertEqual(len(data["digest"]), 64)
        self.assertEqual(self.status_of(self.left_row), Enrollment.Status.ENROLLED)
        self.assertFalse(JournalHygieneDecision.objects.exists())

    def test_suspend_left_students_then_revert(self):
        result = self._apply(hygiene.LEFT, [self.left_row.pk, self.left_row2.pk], actions.TARGET_SUSPEND)
        self.assertEqual(result["changed"], 2)
        self.assertEqual(self.status_of(self.left_row), Enrollment.Status.SUSPENDED)
        with bypass_rls():
            decisions = list(JournalHygieneDecision.objects.filter(batch=result["batch"]))
            self.assertTrue(Enrollment.objects.filter(pk=self.left_row.pk).exists())  # SİLİNMİR
            self.assertTrue(
                AuditLog.objects.filter(resource_type=actions.AUDIT_RESOURCE, resource_id=result["batch"]).exists()
            )
            # Artıq namizəd deyil — siyahıdan düşüb.
            self.assertFalse(hygiene.candidates(self.org, hygiene.LEFT).filter(pk=self.left_row.pk).exists())
        self.assertEqual(len(decisions), 2)
        decision = decisions[0]
        self.assertEqual((decision.from_status, decision.to_status), ("enrolled", "suspended"))
        self.assertEqual(decision.reason_code, hygiene.REASON_EXPELLED)
        self.assertEqual(decision.reason, REASON)
        self.assertEqual(len(decision.evidence_digest), 64)
        self.assertEqual(decision.decided_by, self.owner)

        reverted = self._revert([item.pk for item in decisions])
        self.assertEqual(reverted["reverted"], 2)
        self.assertEqual(self.status_of(self.left_row), Enrollment.Status.ENROLLED)
        with bypass_rls():
            decision.refresh_from_db()
        self.assertIsNotNone(decision.reverted_at)
        self.assertEqual(decision.revert_reason, REASON)
        with self.assertRaises(actions.HygieneError) as ctx:
            self._revert([decision.pk])  # ikinci dəfə olmaz
        self.assertEqual(ctx.exception.code, "not_revertable")

    def test_drop_empty_subject_and_revert(self):
        result = self._apply(hygiene.EMPTY, [self.empty_row.pk], actions.TARGET_DROP)
        self.assertEqual(result["changed"], 1)
        with bypass_rls():
            row = Enrollment.objects.get(pk=self.empty_row.pk)
            decision = JournalHygieneDecision.objects.get(enrollment=row)
        self.assertEqual(row.status, Enrollment.Status.DROPPED)
        self.assertIsNone(row.superseded_by_id)
        self.assertEqual(decision.category, hygiene.EMPTY)
        self.assertEqual(decision.reason_code, hygiene.SOURCE_NOT_IN_CURRICULUM)
        self._revert([decision.pk])
        self.assertEqual(self.status_of(self.empty_row), Enrollment.Status.ENROLLED)

    def test_empty_subject_cannot_be_suspended(self):
        with self.assertRaises(actions.HygieneError) as ctx:
            self._preview(hygiene.EMPTY, [self.empty_row.pk], actions.TARGET_SUSPEND)
        self.assertEqual(ctx.exception.code, "invalid_target")

    def test_left_row_with_data_can_only_be_suspended(self):
        with bypass_rls():
            self.mark(self.left_row)
        data = self._preview(hygiene.LEFT, [self.left_row.pk], actions.TARGET_DROP)
        self.assertFalse(data["can_apply"])
        self.assertEqual(data["blocked_total"], 1)
        self.assertEqual(data["evidence_totals"], {"marks": 1})
        with self.assertRaises(actions.HygieneError) as ctx:
            self._apply(hygiene.LEFT, [self.left_row.pk], actions.TARGET_DROP, digest=data["digest"])
        self.assertEqual(ctx.exception.code, "has_evidence")
        self.assertEqual(self.status_of(self.left_row), Enrollment.Status.ENROLLED)
        # Dondurmaq olar.
        self.assertEqual(self._apply(hygiene.LEFT, [self.left_row.pk], actions.TARGET_SUSPEND)["changed"], 1)

    def test_empty_left_row_may_be_dropped(self):
        self._apply(hygiene.LEFT, [self.left_row2.pk], actions.TARGET_DROP)
        self.assertEqual(self.status_of(self.left_row2), Enrollment.Status.DROPPED)


class GuardrailTest(_ActionsBase):
    def test_drift_after_preview_writes_nothing(self):
        ids = [self.left_row.pk, self.left_row2.pk]
        digest = self._preview(hygiene.LEFT, ids, actions.TARGET_SUSPEND)["digest"]
        with bypass_rls():
            self.mark(self.left_row2)  # önizləmədən sonra bal yazıldı
        with self.assertRaises(actions.HygieneError) as ctx:
            self._apply(hygiene.LEFT, ids, actions.TARGET_SUSPEND, digest=digest)
        self.assertEqual((ctx.exception.code, ctx.exception.status), ("drift", 409))
        self.assertEqual(self.status_of(self.left_row), Enrollment.Status.ENROLLED)
        self.assertFalse(JournalHygieneDecision.objects.exists())

    def test_row_that_stopped_being_a_candidate_is_drift(self):
        digest = self._preview(hygiene.EMPTY, [self.empty_row.pk], actions.TARGET_DROP)["digest"]
        with bypass_rls():
            self.mark(self.empty_row)  # artıq boş deyil
        with self.assertRaises(actions.HygieneError) as ctx:
            self._apply(hygiene.EMPTY, [self.empty_row.pk], actions.TARGET_DROP, digest=digest)
        self.assertEqual(ctx.exception.code, "drift")
        self.assertEqual(self.status_of(self.empty_row), Enrollment.Status.ENROLLED)

    def test_reason_batch_preview_and_selection_rules(self):
        with self.assertRaises(actions.HygieneError) as ctx:
            self._apply(hygiene.LEFT, [self.left_row.pk], actions.TARGET_SUSPEND, reason="qısa səbəb")
        self.assertEqual(ctx.exception.code, "reason_too_short")
        with self.assertRaises(actions.HygieneError) as ctx:
            self._apply(hygiene.LEFT, [self.left_row.pk], actions.TARGET_SUSPEND, digest="")
        self.assertEqual(ctx.exception.code, "preview_required")
        with self.assertRaises(actions.HygieneError) as ctx:
            self._preview(hygiene.LEFT, [uuid.uuid4() for _ in range(501)], actions.TARGET_SUSPEND)
        self.assertEqual(ctx.exception.code, "batch_too_large")
        with self.assertRaises(actions.HygieneError) as ctx:
            self._preview(hygiene.LEFT, ["not-a-uuid"], actions.TARGET_SUSPEND)
        self.assertEqual(ctx.exception.code, "empty_selection")
        # Namizəd olmayan id önizləmədə «missing» sayılır və tətbiqə buraxılmır.
        data = self._preview(hygiene.LEFT, [self.left_row.pk, self.empty_row.pk], actions.TARGET_SUSPEND)
        self.assertEqual((data["rows"], data["missing"], data["can_apply"]), (1, 1, False))
        self.assertEqual(self.status_of(self.left_row), Enrollment.Status.ENROLLED)

    def test_only_superadmin_or_org_wide_journal_correct(self):
        with self.assertRaises(actions.HygieneError) as ctx:
            self._preview(hygiene.LEFT, [self.left_row.pk], actions.TARGET_SUSPEND, actor=self.dean)
        self.assertEqual((ctx.exception.code, ctx.exception.status), ("permission_denied", 403))
        with bypass_rls():
            self.assertFalse(actions.can_apply(self.teacher, self.org))
            self.assertTrue(actions.can_apply(self.owner, self.org))

    def test_revert_is_blocked_when_status_changed_since(self):
        result = self._apply(hygiene.LEFT, [self.left_row.pk], actions.TARGET_SUSPEND)
        with bypass_rls():
            Enrollment.objects.filter(pk=self.left_row.pk).update(status=Enrollment.Status.ENROLLED)
        with self.assertRaises(actions.HygieneError) as ctx:
            self._revert(result["decision_ids"])
        self.assertEqual(ctx.exception.code, "revert_blocked")
        self.assertEqual(ctx.exception.details[0]["code"], "status_changed")

    def test_preview_query_count_does_not_grow_with_rows(self):
        def run(ids):
            with CaptureQueriesContext(connection) as ctx:
                self._preview(hygiene.LEFT, ids, actions.TARGET_SUSPEND)
            return sum(
                1
                for query in ctx.captured_queries
                if "set_config(" not in query["sql"] and "current_setting(" not in query["sql"]
            )

        one = run([self.left_row.pk])
        with bypass_rls():
            more = [self.enroll(self.make_student(f"jh_q{i}", status=AcademicStatus.EXPELLED)).pk for i in range(5)]
        self.assertEqual(run([self.left_row.pk, *more]), one)


class LedgerAppendOnlyTest(_ActionsBase):
    def setUp(self):
        result = self._apply(hygiene.LEFT, [self.left_row.pk], actions.TARGET_SUSPEND)
        with bypass_rls():
            self.decision = JournalHygieneDecision.objects.get(pk=result["decision_ids"][0])

    def _db_fails(self, fn):
        with self.assertRaises(_DB_GUARD_ERRORS), bypass_rls(), transaction.atomic():
            fn()

    def test_db_trigger_blocks_update_and_delete(self):
        queryset = JournalHygieneDecision.objects.filter(pk=self.decision.pk)
        self._db_fails(lambda: queryset.update(reason="Başqa səbəb yazılır — iz itməlidir."))
        self._db_fails(lambda: queryset.update(to_status="dropped"))
        self._db_fails(lambda: queryset.delete())
        # Geri qaytarma sahələri olmadan «reverted» qeyd etmək də olmaz (yarımçıq revert CHECK).
        self._db_fails(lambda: queryset.update(revert_reason="Səbəb var, amma vaxt yoxdur."))

    def test_model_layer_refuses_edits(self):
        self.decision.reason = "Başqa səbəb yazılır — iz itməlidir."
        with self.assertRaises(ValidationError):
            self.decision.save()
        with self.assertRaises(ValidationError):
            self.decision.delete()

    def test_one_time_revert_is_the_only_allowed_update(self):
        self._revert([self.decision.pk])
        queryset = JournalHygieneDecision.objects.filter(pk=self.decision.pk)
        self._db_fails(lambda: queryset.update(revert_reason="İkinci dəfə geri qaytarma cəhdi."))

    def test_actor_deletion_nulls_the_fk_but_keeps_the_name(self):
        with bypass_rls():
            actor = User.objects.create_superuser("jh_su_gone", "jh_su_gone@qku.edu.az", "pw")
            row = self.enroll(self.make_student("jh_x3", status=AcademicStatus.EXPELLED))
            result = self._apply(hygiene.LEFT, [row.pk], actions.TARGET_SUSPEND, actor=actor)
            actor.delete()
            decision = JournalHygieneDecision.objects.get(pk=result["decision_ids"][0])
        self.assertIsNone(decision.decided_by_id)
        self.assertEqual(decision.decided_by_name, "jh_su_gone")


class ReportCommandTest(_ActionsBase):
    def _call(self, *args):
        out = io.StringIO()
        call_command("journal_hygiene_report", "--organization", self.org.slug, *args, stdout=out)
        return out.getvalue()

    def test_dry_run_is_default_and_writes_nothing(self):
        output = self._call()
        self.assertIn("DRY-RUN", output)
        self.assertIn(str(self.left_row.pk), output)
        self.assertIn(str(self.empty_row.pk), output)
        self.assertEqual(self.status_of(self.left_row), Enrollment.Status.ENROLLED)
        self.assertFalse(JournalHygieneDecision.objects.exists())

    def test_apply_requires_reason_category_and_production_flag(self):
        with self.assertRaisesMessage(CommandError, "journal_hygiene_category_required"):
            self._call("--apply", "--reason", REASON)
        with self.assertRaisesMessage(CommandError, "journal_hygiene_target_not_disposable"):
            self._call("--apply", "--category", "left", "--reason", REASON)
        with self.assertRaisesMessage(CommandError, "journal_hygiene_reason_too_short"):
            self._call("--apply", "--category", "left", "--reason", "qısa", "--i-know-this-is-production")
        self.assertFalse(JournalHygieneDecision.objects.exists())

    def test_apply_per_category_with_guard_flag(self):
        output = self._call(
            "--apply", "--category", "left", "--code", "expelled", "--reason", REASON, "--i-know-this-is-production"
        )
        self.assertIn("YAZILDI: 2", output)
        self.assertEqual(self.status_of(self.left_row), Enrollment.Status.SUSPENDED)
        self.assertEqual(self.status_of(self.empty_row), Enrollment.Status.ENROLLED)  # yalnız seçilmiş kateqoriya
        self._call("--apply", "--category", "empty", "--reason", REASON, "--i-know-this-is-production")
        self.assertEqual(self.status_of(self.empty_row), Enrollment.Status.DROPPED)
        self.assertEqual(JournalHygieneDecision.objects.count(), 3)
