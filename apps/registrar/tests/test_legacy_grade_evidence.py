"""Backend-agnostic contracts for immutable legacy-grade evidence."""

import hashlib
import zlib
from decimal import Decimal

from django.core.exceptions import ValidationError

from apps.organizations.models import Organization
from apps.registrar.models import (
    LegacyGradeArtifact,
    LegacyGradeArtifactKind,
    LegacyGradeEvidenceKind,
    LegacyGradeFact,
    LegacyGradeMappingStatus,
    LegacyGradeReview,
    LegacyGradeReviewDecision,
)
from apps.registrar.tests.test_corrections_bridge import _BaseJournalSetup
from core.constants import OrganizationType
from core.rls import bypass_rls

_SNAPSHOT = "a" * 64
_ROW_HASH = "b" * 64
_DIGEST = "c" * 64
_REVIEW_DIGEST = "d" * 64
_DEFAULT_ENROLLMENT = object()
_DEFAULT_MAPPING = object()


class LegacyGradeEvidenceModelTests(_BaseJournalSetup):
    def _artifact(self, *, source_pk=1, organization=None, payload=b"<table>test-only</table>"):
        return LegacyGradeArtifact.objects.create(
            organization=organization or self.org,
            source_system="myedu_mariadb",
            source_table="balvereqi_logs",
            source_pk=source_pk,
            source_snapshot_sha256=_SNAPSHOT,
            source_row_hash=_ROW_HASH,
            materialization_digest=_DIGEST,
            transform_version="legacy-grade-v1",
            artifact_kind=LegacyGradeArtifactKind.SCORE_SHEET_EXPORT,
            source_owner_ref="17",
            source_journal_ref="journal-1",
            source_exported_at_text="2023-08-14 10:00:00",
            payload_sha256=hashlib.sha256(payload).hexdigest(),
            payload_size_bytes=len(payload),
            payload_zlib=zlib.compress(payload, 9),
        )

    def _fact(
        self,
        *,
        source_pk=1,
        organization=None,
        enrollment=_DEFAULT_ENROLLMENT,
        mapping_status=_DEFAULT_MAPPING,
        mapping_issue_code=_DEFAULT_MAPPING,
        source_enrollment_ref="journal-1:student-1",
    ):
        resolved_enrollment = self.enrollment if enrollment is _DEFAULT_ENROLLMENT else enrollment
        resolved_status = (
            LegacyGradeMappingStatus.LINKED if resolved_enrollment is not None else LegacyGradeMappingStatus.UNRESOLVED
        )
        if mapping_status is not _DEFAULT_MAPPING:
            resolved_status = mapping_status
        resolved_issue = {
            LegacyGradeMappingStatus.LINKED: "",
            LegacyGradeMappingStatus.CONFLICT: "legacy_grade_fact_conflict",
            LegacyGradeMappingStatus.GROUP_MISMATCH: "legacy_grade_fact_group_mismatch",
            LegacyGradeMappingStatus.DISCARDED_SOURCE: "legacy_grade_fact_discarded_source",
            LegacyGradeMappingStatus.UNRESOLVED: "legacy_grade_fact_unresolved",
        }[resolved_status]
        if mapping_issue_code is not _DEFAULT_MAPPING:
            resolved_issue = mapping_issue_code
        return LegacyGradeFact.objects.create(
            organization=organization or self.org,
            enrollment=resolved_enrollment,
            source_system="myedudb",
            source_table="yekun",
            source_pk=source_pk,
            source_snapshot_sha256=_SNAPSHOT,
            source_row_hash=_ROW_HASH,
            materialization_digest=_DIGEST,
            transform_version="legacy-grade-v1",
            evidence_kind=LegacyGradeEvidenceKind.SUMMARY,
            mapping_status=resolved_status,
            mapping_issue_code=resolved_issue,
            source_student_ref="student-1",
            source_journal_ref="journal-1",
            source_enrollment_ref=source_enrollment_ref,
            entry_score_text="59",
            exam_score_text="58",
            final_score_text="117",
            entry_score=Decimal("59"),
            exam_score=Decimal("58"),
            final_score=Decimal("117"),
        )

    def _review(self, fact):
        return LegacyGradeReview.objects.create(
            organization=fact.organization,
            fact=fact,
            decision=LegacyGradeReviewDecision.VERIFIED,
            reason_code="exam_center_verified",
            note="Mənbə sənədi ilə yoxlanılıb.",
            evidence_digest=_REVIEW_DIGEST,
            reviewed_by=self.owner,
            reviewed_by_name=self.owner.get_full_name() or self.owner.username,
        )

    def _second_organization(self):
        owner = type(self.owner).objects.create_user(
            "legacy_evidence_owner_b",
            "legacy-evidence-owner-b@example.test",
            "pw",
        )
        with bypass_rls():
            return Organization.objects.create(
                name="Legacy evidence B",
                slug="legacy-evidence-b",
                org_type=OrganizationType.UNIVERSITY,
                owner=owner,
                status="active",
                is_active=True,
            )

    def test_raw_legacy_scores_are_preserved_without_clamping(self):
        with bypass_rls():
            fact = self._fact()

        self.assertEqual(fact.entry_score, Decimal("59"))
        self.assertEqual(fact.exam_score, Decimal("58"))
        self.assertEqual(fact.final_score, Decimal("117"))
        self.assertTrue(fact.requires_exam_center_review)

    def test_fact_instance_and_queryset_mutations_are_rejected(self):
        with bypass_rls():
            fact = self._fact()

        fact.final_score_text = "100"
        with self.assertRaisesRegex(ValidationError, "immutable"):
            fact.save(update_fields=["final_score_text"])
        with self.assertRaisesRegex(ValidationError, "cannot be deleted"):
            fact.delete()
        with self.assertRaisesRegex(ValidationError, "immutable"):
            LegacyGradeFact.objects.filter(pk=fact.pk).update(final_score_text="100")
        with self.assertRaisesRegex(ValidationError, "cannot be deleted"):
            LegacyGradeFact.objects.filter(pk=fact.pk).delete()

    def test_artifact_payload_is_exact_and_all_mutations_are_rejected(self):
        raw = "<table><td>tələbə</td><td>45</td></table>".encode()
        with bypass_rls():
            artifact = self._artifact(payload=raw)

        self.assertEqual(zlib.decompress(bytes(artifact.payload_zlib)), raw)
        self.assertEqual(artifact.payload_sha256, hashlib.sha256(raw).hexdigest())
        self.assertEqual(artifact.payload_size_bytes, len(raw))
        self.assertTrue(artifact.requires_exam_center_review)

        artifact.source_exported_at_text = "rewritten"
        with self.assertRaisesRegex(ValidationError, "immutable"):
            artifact.save(update_fields=["source_exported_at_text"])
        with self.assertRaisesRegex(ValidationError, "cannot be deleted"):
            artifact.delete()
        with self.assertRaisesRegex(ValidationError, "immutable"):
            LegacyGradeArtifact.objects.filter(pk=artifact.pk).update(source_owner_ref="18")
        with self.assertRaisesRegex(ValidationError, "cannot be deleted"):
            LegacyGradeArtifact.objects.filter(pk=artifact.pk).delete()

    def test_review_instance_and_queryset_mutations_are_rejected(self):
        with bypass_rls():
            review = self._review(self._fact())

        review.note = "rewritten"
        with self.assertRaisesRegex(ValidationError, "immutable"):
            review.save(update_fields=["note"])
        with self.assertRaisesRegex(ValidationError, "cannot be deleted"):
            review.delete()
        with self.assertRaisesRegex(ValidationError, "immutable"):
            LegacyGradeReview.objects.filter(pk=review.pk).update(note="rewritten")
        with self.assertRaisesRegex(ValidationError, "cannot be deleted"):
            LegacyGradeReview.objects.filter(pk=review.pk).delete()

    def test_review_requires_score_entry_permission_and_canonicalizes_actor_name(self):
        with bypass_rls():
            fact = self._fact(source_pk=3)

        with self.assertRaisesRegex(ValidationError, "səlahiyyəti yoxdur"):
            LegacyGradeReview.objects.create(
                organization=self.org,
                fact=fact,
                decision=LegacyGradeReviewDecision.VERIFIED,
                reason_code="unauthorized_review",
                evidence_digest=_REVIEW_DIGEST,
                reviewed_by=self.teacher,
                reviewed_by_name=self.owner.username,
            )

        # Backend-agnostic model testi middleware sessiyası yaratmır. PostgreSQL
        # actor-binding ayrıca raw/RLS testlərində yoxlanır; burada yalnız model
        # RBAC və canonical snapshot davranışını izolə edirik.
        with bypass_rls():
            review = LegacyGradeReview.objects.create(
                organization=self.org,
                fact=fact,
                decision=LegacyGradeReviewDecision.VERIFIED,
                reason_code="exam_center_verified",
                evidence_digest=_REVIEW_DIGEST,
                reviewed_by=self.owner,
                reviewed_by_name="spoofed-name",
            )
        self.assertEqual(review.reviewed_by_name, self.owner.get_full_name() or self.owner.username)

    def test_review_bulk_create_cannot_bypass_authorization(self):
        with bypass_rls():
            fact = self._fact(source_pk=4)
        review = LegacyGradeReview(
            organization=self.org,
            fact=fact,
            decision=LegacyGradeReviewDecision.VERIFIED,
            reason_code="bulk_bypass_attempt",
            evidence_digest=_REVIEW_DIGEST,
            reviewed_by=self.teacher,
            reviewed_by_name=self.teacher.username,
        )
        with self.assertRaisesRegex(ValidationError, "individually authorized"):
            LegacyGradeReview.objects.bulk_create([review])

    def test_model_validation_rejects_cross_organization_enrollment_and_fact(self):
        org_b = self._second_organization()
        with bypass_rls():
            fact = self._fact()
        fact.organization = org_b
        with self.assertRaisesRegex(ValidationError, "eyni təşkilata"):
            fact.full_clean()

        with bypass_rls():
            canonical_fact = self._fact(source_pk=2)
        review = LegacyGradeReview(
            organization=org_b,
            fact=canonical_fact,
            decision=LegacyGradeReviewDecision.DISPUTED,
            reason_code="organization_mismatch",
            evidence_digest=_REVIEW_DIGEST,
            reviewed_by=org_b.owner,
            reviewed_by_name=org_b.owner.username,
        )
        with self.assertRaisesRegex(ValidationError, "eyni təşkilata"):
            review.full_clean()
