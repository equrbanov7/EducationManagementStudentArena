"""«Fənləri birləşdir» — tətbiq: bütün FK-lar köçür, mənbə arxivlənir, audit + geri qaytarma (2026-10-19)."""

from __future__ import annotations

from decimal import Decimal

from django.apps import apps as django_apps

from apps.audit.models import AuditLog
from apps.registrar import subject_merge, subject_merge_apply, subject_merge_undo
from apps.registrar.models import CourseOffering, CurriculumSubject, ExamChanceGrant, Subject
from apps.registrar.models.curriculum_meta import PlanStatus
from apps.registrar.subject_merge_inventory import KEEP, M2M, RELATIONS
from core.rls import bypass_rls

from .subject_merge_fixture import REASON, SubjectMergeBase


def _attname(rel):
    return rel.model()._meta.get_field(rel.field).attname


class MergeApplyTest(SubjectMergeBase):
    def _merge(self, sources=None, **extra):
        sources = sources or [self.source]
        with bypass_rls():
            payload = subject_merge.preview(self.org, str(self.target.pk), [str(item.pk) for item in sources])
            result = subject_merge_apply.apply(
                organization=self.org,
                actor=self.office,
                target_ref=str(self.target.pk),
                source_refs=[str(item.pk) for item in sources],
                reason=REASON,
                expected_digest=payload["digest"],
                **extra,
            )
        return payload, result

    def test_every_relation_is_repointed_and_source_archived(self):
        built = self.build_full_source()
        payload, result = self._merge()
        self.assertTrue(payload["can_apply"], payload["blocking"])
        with bypass_rls():
            for rel in RELATIONS:
                model = rel.model()
                if rel.strategy == M2M:
                    through = model._meta.get_field(rel.field).remote_field.through
                    self.assertFalse(through.objects.filter(subject_id=self.source.pk).exists(), rel.key)
                    continue
                remaining = model._base_manager.filter(**{_attname(rel): self.source.pk}).count()
                if rel.strategy == KEEP:
                    self.assertEqual(remaining, 1, rel.key)  # dəyişməz tarixçə mənbədə qalır
                else:
                    self.assertEqual(remaining, 0, rel.key)
            self.assertEqual(
                set(built["group_both"].subjects.values_list("pk", flat=True)), {self.target.pk}
            )  # təkrar əlaqə çıxarıldı
            self.assertEqual(list(built["group_move"].subjects.values_list("pk", flat=True)), [self.target.pk])
            built["availability"].refresh_from_db()
            self.assertEqual(built["availability"].subject_priorities, {str(self.target.pk): 4})
            self.assertEqual(ExamChanceGrant.objects.get(pk=built["chance"].pk).subject_id, self.source.pk)
            source = Subject.objects.get(pk=self.source.pk)
        self.assertTrue(source.is_archived)
        self.assertFalse(source.is_active)
        self.assertEqual(source.archived_reason, "Birləşdirildi → QA-SM-T")
        self.assertEqual(source.archived_by_id, self.office.pk)
        self.assertTrue(Subject.objects.filter(pk=self.source.pk).exists())  # silinmir

    def test_offering_with_journal_evidence_moves_with_its_grades(self):
        """``registrar.0045`` sübut qoruyucusu birləşmədə DAR icazə ilə keçilir (``audit.0004``)."""
        offering = self.offering(self.source, self.group1)
        enrollment = self.enroll(offering, grade="35")
        self._merge()
        with bypass_rls():
            offering.refresh_from_db()
            self.assertEqual(offering.subject_id, self.target.pk)
            self.assertEqual(offering.enrollments.get().pk, enrollment.pk)
            grade = django_apps.get_model("registrar", "FinalGrade").objects.get(enrollment=enrollment)
            self.assertEqual(grade.exam_score, Decimal("35"))

    def test_audit_records_counts_and_ids_for_undo(self):
        built = self.build_full_source()
        _payload, result = self._merge()
        entry = AuditLog.objects.get(pk=result["audit_id"])
        self.assertEqual(entry.resource_type, subject_merge.AUDIT_RESOURCE)
        self.assertEqual(entry.reason, REASON)
        changes = entry.changes
        self.assertEqual(changes["counts"]["registrar.CourseOffering.subject"], 1)
        self.assertEqual(
            changes["moved"]["registrar.CourseOffering.subject"], {str(self.source.pk): [str(built["offering"].pk)]}
        )
        self.assertEqual(changes["counts"]["exams.StudentGroup.subjects:dropped"], 1)
        self.assertEqual(changes["locked_plans"], [str(built["approved_plan"].pk)])
        self.assertEqual(entry.user_id, self.office.pk)
        self.assertTrue(
            AuditLog.objects.filter(resource_type="registrar.subject_merge.source", resource_id=str(entry.pk)).exists()
        )

    def test_approved_plan_row_is_repointed_as_identity_fix(self):
        plan = self.plan(PlanStatus.APPROVED)
        row = self.plan_row(plan, self.source, semester=2, total_hours=150)
        payload, _result = self._merge()
        self.assertTrue(any("identiklik" in text for text in payload["info"]))
        with bypass_rls():
            row.refresh_from_db()
        self.assertEqual((row.subject_id, row.semester_number, row.total_hours), (self.target.pk, 2, 150))

    def test_draft_plan_conflict_keeps_target_row(self):
        plan = self.plan(PlanStatus.DRAFT)
        keep = self.plan_row(plan, self.target, semester=1)
        drop = self.plan_row(plan, self.source, semester=1)
        payload, result = self._merge()
        self.assertEqual(payload["resolvable_total"], 1)
        with bypass_rls():
            self.assertTrue(CurriculumSubject.objects.filter(pk=keep.pk, subject=self.target).exists())
            self.assertFalse(CurriculumSubject.objects.filter(pk=drop.pk).exists())
        snapshot = AuditLog.objects.get(pk=result["audit_id"]).changes["deleted_plan_rows"]
        self.assertEqual([item["id"] for item in snapshot], [str(drop.pk)])

    def test_several_sources_at_once(self):
        third = Subject.objects.create(organization=self.org, code="QA-SM-S2", name="VoIP  sistemləri", ects=6)
        self.offering(self.source, self.group1)
        self.offering(third, self.group2)
        payload, result = self._merge([self.source, third])
        self.assertTrue(any("Kredit fərqlidir" in text for text in payload["warnings"]))
        with bypass_rls():
            self.assertEqual(CourseOffering.objects.filter(subject=self.target).count(), 2)
            self.assertEqual(Subject.objects.filter(pk__in=[self.source.pk, third.pk], is_archived=True).count(), 2)
        self.assertEqual(result["counts"]["registrar.CourseOffering.subject"], 2)

    def test_digest_mismatch_writes_nothing(self):
        offering = self.offering(self.source, self.group1)
        with bypass_rls():
            payload = subject_merge.preview(self.org, str(self.target.pk), [str(self.source.pk)])
        self.offering(self.source, self.group2)  # önizləmədən sonra yeni sətir
        with bypass_rls(), self.assertRaises(subject_merge.MergeError) as caught:
            subject_merge_apply.apply(
                organization=self.org,
                actor=self.office,
                target_ref=str(self.target.pk),
                source_refs=[str(self.source.pk)],
                reason=REASON,
                expected_digest=payload["digest"],
            )
        self.assertEqual((caught.exception.code, caught.exception.status), ("drift", 409))
        with bypass_rls():
            offering.refresh_from_db()
            self.assertEqual(offering.subject_id, self.source.pk)
            self.assertFalse(Subject.objects.get(pk=self.source.pk).is_archived)

    def test_missing_digest_and_short_reason_are_rejected(self):
        with bypass_rls():
            for reason, digest, code in ((REASON, "", "preview_required"), ("qısa", "x", "reason_too_short")):
                with self.subTest(code=code), self.assertRaises(subject_merge.MergeError) as caught:
                    subject_merge_apply.apply(
                        organization=self.org,
                        actor=self.office,
                        target_ref=str(self.target.pk),
                        source_refs=[str(self.source.pk)],
                        reason=reason,
                        expected_digest=digest,
                    )
                self.assertEqual(caught.exception.code, code)

    def test_blocking_conflict_refuses_apply(self):
        self.offering(self.source, self.group1)
        self.offering(self.target, self.group1)
        with bypass_rls():
            payload = subject_merge.preview(self.org, str(self.target.pk), [str(self.source.pk)])
            self.assertFalse(payload["can_apply"])
            with self.assertRaises(subject_merge.MergeError) as caught:
                subject_merge_apply.apply(
                    organization=self.org,
                    actor=self.office,
                    target_ref=str(self.target.pk),
                    source_refs=[str(self.source.pk)],
                    reason=REASON,
                    expected_digest=payload["digest"],
                )
        self.assertEqual(caught.exception.code, "conflicts")
        self.assertFalse(Subject.objects.get(pk=self.source.pk).is_archived)


class MergeUndoTest(SubjectMergeBase):
    def _merge(self):
        with bypass_rls():
            payload = subject_merge.preview(self.org, str(self.target.pk), [str(self.source.pk)])
            return subject_merge_apply.apply(
                organization=self.org,
                actor=self.office,
                target_ref=str(self.target.pk),
                source_refs=[str(self.source.pk)],
                reason=REASON,
                expected_digest=payload["digest"],
            )

    def test_dry_run_then_apply_restores_everything(self):
        built = self.build_full_source()
        draft = self.plan(PlanStatus.DRAFT, year=2027, name="Qaralama")
        self.plan_row(draft, self.target, semester=1)
        dropped = self.plan_row(draft, self.source, semester=1, total_hours=120)
        result = self._merge()
        with bypass_rls():
            report = subject_merge_undo.undo(audit_id=result["audit_id"])
            self.assertEqual(report["issues"], [])
            self.assertFalse(report["applied"])
            self.assertTrue(Subject.objects.get(pk=self.source.pk).is_archived)  # dry-run heç nə saxlamadı
            report = subject_merge_undo.undo(audit_id=result["audit_id"], apply=True, reason=REASON)
            self.assertTrue(report["applied"], report["issues"])
            moved = AuditLog.objects.get(pk=result["audit_id"]).changes["moved"]
            self.assertTrue(moved)
            for key, rows in moved.items():
                rel = next(item for item in RELATIONS if item.key == key)
                ids = rows[str(self.source.pk)]
                on_source = rel.model()._base_manager.filter(pk__in=ids, **{_attname(rel): self.source.pk}).count()
                self.assertEqual(on_source, len(ids), key)
            source = Subject.objects.get(pk=self.source.pk)
            self.assertFalse(source.is_archived)
            self.assertTrue(source.is_active)
            self.assertEqual(source.archived_reason, "")
            restored = CurriculumSubject.objects.get(pk=dropped.pk)
            self.assertEqual((restored.subject_id, restored.total_hours), (self.source.pk, 120))
            self.assertEqual(
                set(built["group_both"].subjects.values_list("pk", flat=True)), {self.source.pk, self.target.pk}
            )
            built["availability"].refresh_from_db()
            self.assertEqual(built["availability"].subject_priorities, {str(self.source.pk): 4, str(self.target.pk): 2})
            again = subject_merge_undo.undo(audit_id=result["audit_id"])
        self.assertIn("Bu birləşmə artıq geri qaytarılıb", again["issues"])

    def test_undo_refuses_when_rows_changed_after_merge(self):
        offering = self.offering(self.source, self.group1)
        result = self._merge()
        other = Subject.objects.create(organization=self.org, code="QA-SM-Z", name="Z")
        with bypass_rls():
            CourseOffering.objects.filter(pk=offering.pk).update(subject=other)  # sübutsuz açılış — trigger keçir
            report = subject_merge_undo.undo(audit_id=result["audit_id"], apply=True, reason=REASON)
        self.assertFalse(report["applied"])
        self.assertTrue(any("başqa yerə" in issue for issue in report["issues"]))

    def test_undo_refuses_when_source_restored_manually(self):
        result = self._merge()
        Subject.objects.filter(pk=self.source.pk).update(is_archived=False, archived_reason="")
        with bypass_rls():
            report = subject_merge_undo.undo(audit_id=result["audit_id"])
        self.assertTrue(any("dəyişib" in issue for issue in report["issues"]))

    def test_unknown_audit_id(self):
        with bypass_rls(), self.assertRaises(subject_merge.MergeError):
            subject_merge_undo.undo(audit_id="00000000-0000-0000-0000-000000000000")
