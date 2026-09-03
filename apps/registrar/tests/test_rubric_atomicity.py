"""Atomic rubric scoring and evidence-retention regression tests."""

import datetime
import uuid
from decimal import Decimal
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.db.models.deletion import ProtectedError
from django.utils import timezone

from apps.registrar import gradebook, rubrics
from apps.registrar.models import (
    ApprovalStatus,
    AssessmentComponent,
    ComponentScore,
    CriterionScore,
)
from core.rls import bypass_rls

from .test_rubrics import RubricBaseTest


class RubricAtomicityTest(RubricBaseTest):
    def _entry(self, criterion, points):
        return {
            "criterion_id": str(criterion.id),
            "enrollment_id": str(self.enrollment.id),
            "points": points,
        }

    def _score_one_criterion(self):
        criterion = self.rubric.criteria.get(name="Məzmun")
        rubrics.save_criterion_scores(
            component=self.component,
            entries=[self._entry(criterion, "2")],
            by_user=self.teacher,
        )
        return criterion

    def test_same_rubric_is_independent_across_two_components(self):
        with bypass_rls():
            criterion = self.rubric.criteria.get(name="Məzmun")
            second = AssessmentComponent.objects.create(
                organization=self.org,
                offering=self.offering,
                rubric=self.rubric,
                name="İkinci layihə",
                max_score=10,
            )
            rubrics.save_criterion_scores(
                component=self.component,
                entries=[self._entry(criterion, "2")],
                by_user=self.teacher,
            )
            rubrics.save_criterion_scores(
                component=second,
                entries=[self._entry(criterion, "3")],
                by_user=self.teacher,
            )
            points = list(
                CriterionScore.objects.filter(criterion=criterion, enrollment=self.enrollment)
                .order_by("points")
                .values_list("points", flat=True)
            )
            first_grid = rubrics.get_rubric_grid(self.component)
            second_grid = rubrics.get_rubric_grid(second)

        self.assertEqual(points, [Decimal("2"), Decimal("3")])
        self.assertEqual(first_grid["rows"][0]["cells"][0]["points"], Decimal("2"))
        self.assertEqual(second_grid["rows"][0]["cells"][0]["points"], Decimal("3"))

    def test_invalid_late_entry_rolls_back_whole_batch(self):
        with bypass_rls():
            criteria = list(self.rubric.criteria.all())
            with self.assertRaises(ValidationError):
                rubrics.save_criterion_scores(
                    component=self.component,
                    entries=[
                        self._entry(criteria[0], "2"),
                        self._entry(criteria[1], "999"),
                    ],
                    by_user=self.teacher,
                )
            self.assertFalse(CriterionScore.objects.filter(component=self.component).exists())
            self.assertFalse(ComponentScore.objects.filter(component=self.component).exists())

    def test_negative_and_non_finite_points_are_rejected(self):
        with bypass_rls():
            criterion = self.rubric.criteria.first()
            for raw in ("-0.01", "NaN", "Infinity"):
                with self.subTest(raw=raw), self.assertRaises(ValidationError):
                    rubrics.save_criterion_scores(
                        component=self.component,
                        entries=[self._entry(criterion, raw)],
                        by_user=self.teacher,
                    )
            self.assertFalse(CriterionScore.objects.filter(component=self.component).exists())

    def test_duplicate_and_malformed_entries_have_stable_validation_error(self):
        with bypass_rls():
            criterion = self.rubric.criteria.first()
            entry = self._entry(criterion, "1")
            for entries in ([entry, entry.copy()], [object()]):
                with self.subTest(entries=entries), self.assertRaises(ValidationError) as caught:
                    rubrics.save_criterion_scores(
                        component=self.component,
                        entries=entries,
                        by_user=self.teacher,
                    )
                self.assertEqual(caught.exception.error_list[0].code, "criterion_score_batch_rejected")
            self.assertFalse(CriterionScore.objects.filter(component=self.component).exists())

    def test_locked_journal_rejects_instead_of_silent_success(self):
        with bypass_rls():
            criterion = self.rubric.criteria.first()
            scheme = gradebook.ensure_assessment_scheme(offering=self.offering)
            scheme.approval_status = ApprovalStatus.APPROVED
            scheme.is_published = True
            scheme.save(update_fields=["approval_status", "is_published"])
            with self.assertRaises(ValidationError) as caught:
                rubrics.save_criterion_scores(
                    component=self.component,
                    entries=[self._entry(criterion, "1")],
                    by_user=self.teacher,
                )
            self.assertEqual(caught.exception.error_list[0].code, "criterion_score_batch_rejected")
            self.assertFalse(CriterionScore.objects.filter(component=self.component).exists())

    def test_no_rubric_rejects_and_empty_valid_batch_is_noop(self):
        with bypass_rls():
            no_rubric = AssessmentComponent.objects.create(
                organization=self.org,
                offering=self.offering,
                name="Rubriksiz",
                max_score=10,
            )
            with self.assertRaises(ValidationError):
                rubrics.save_criterion_scores(component=no_rubric, entries=[], by_user=self.teacher)
            with patch("apps.registrar.gradebook_components.grade_audit.log_grade_changes") as audit:
                self.assertEqual(
                    rubrics.save_criterion_scores(component=self.component, entries=[], by_user=self.teacher),
                    0,
                )
            audit.assert_not_called()

    def test_expired_component_score_rolls_back_new_criterion_score(self):
        with bypass_rls():
            criterion = self.rubric.criteria.first()
            component_score = ComponentScore.objects.create(
                organization=self.org,
                component=self.component,
                enrollment=self.enrollment,
                score=0,
                entered_by=self.teacher,
            )
            ComponentScore.objects.filter(pk=component_score.pk).update(
                created_at=timezone.now() - datetime.timedelta(hours=3)
            )
            with self.assertRaises(ValidationError):
                rubrics.save_criterion_scores(
                    component=self.component,
                    entries=[self._entry(criterion, "1")],
                    by_user=self.teacher,
                )
            self.assertFalse(CriterionScore.objects.filter(component=self.component).exists())
            component_score.refresh_from_db()
            self.assertEqual(component_score.score, Decimal("0"))

    def test_audit_failure_rolls_back_criterion_and_component_scores(self):
        with bypass_rls():
            criterion = self.rubric.criteria.first()
            with (
                patch(
                    "apps.registrar.gradebook_components.grade_audit.log_grade_changes",
                    side_effect=RuntimeError("audit unavailable"),
                ),
                self.assertRaises(RuntimeError),
            ):
                rubrics.save_criterion_scores(
                    component=self.component,
                    entries=[self._entry(criterion, "1")],
                    by_user=self.teacher,
                )
            self.assertFalse(CriterionScore.objects.filter(component=self.component).exists())
            self.assertFalse(ComponentScore.objects.filter(component=self.component).exists())

    def test_strict_component_batch_rejects_and_rolls_back(self):
        with bypass_rls():
            entries = [
                {
                    "component_id": str(self.component.id),
                    "enrollment_id": str(self.enrollment.id),
                    "score": "2",
                },
                {
                    "component_id": str(uuid.uuid4()),
                    "enrollment_id": str(self.enrollment.id),
                    "score": "2",
                },
            ]
            with self.assertRaises(ValidationError):
                gradebook.save_component_scores(
                    offering=self.offering,
                    entries=entries,
                    by_user=self.teacher,
                    require_all=True,
                    fail_closed_audit=True,
                )
            self.assertFalse(ComponentScore.objects.filter(component=self.component).exists())

    def test_strict_component_values_and_shape_are_fail_closed(self):
        with bypass_rls():
            for raw_entry in (
                {
                    "component_id": str(self.component.id),
                    "enrollment_id": str(self.enrollment.id),
                    "score": "not-a-number",
                },
                {
                    "component_id": str(self.component.id),
                    "enrollment_id": str(self.enrollment.id),
                    "score": "11",
                },
                object(),
            ):
                with self.subTest(raw_entry=raw_entry), self.assertRaises(ValidationError):
                    gradebook.save_component_scores(
                        offering=self.offering,
                        entries=[raw_entry],
                        by_user=self.teacher,
                        require_all=True,
                        fail_closed_audit=True,
                    )
            self.assertFalse(ComponentScore.objects.filter(component=self.component).exists())

    def test_direct_rubric_definition_validation_is_fail_closed(self):
        bad_definitions = (
            None,
            [],
            [("", 1)],
            [("X", 0)],
            [("X", 1.5)],
            [("X", True)],
            [("X", 1), ("x", 2)],
            [("not-a-pair",)],
            [(f"C{i}", 1) for i in range(21)],
        )
        with bypass_rls():
            for criteria in bad_definitions:
                with self.subTest(criteria=criteria), self.assertRaises(ValidationError):
                    rubrics.save_rubric(
                        organization=self.org,
                        name="Etibarsız rubrik",
                        criteria=criteria,
                    )
            self.assertFalse(self.org.rubrics.filter(name="Etibarsız rubrik").exists())

    def test_rubric_and_criterion_identity_is_frozen_after_evidence(self):
        with bypass_rls():
            criterion = self._score_one_criterion()
            original = [(c.name, c.max_points) for c in self.rubric.criteria.all()]
            variants = (
                {"name": "Yeni rubrik adı", "criteria": original},
                {
                    "name": self.rubric.name,
                    "criteria": [(name, 5 if name == criterion.name else maximum) for name, maximum in original],
                },
                {
                    "name": self.rubric.name,
                    "criteria": [(name, maximum) for name, maximum in original if name != criterion.name],
                },
                {
                    "name": self.rubric.name,
                    "criteria": [
                        ("Məzmun-renamed" if name == criterion.name else name, maximum) for name, maximum in original
                    ],
                },
                {
                    "name": self.rubric.name,
                    "criteria": [("məzmun" if name == criterion.name else name, maximum) for name, maximum in original],
                },
            )
            for variant in variants:
                with self.subTest(variant=variant), self.assertRaises(ValidationError):
                    rubrics.save_rubric(
                        organization=self.org,
                        rubric=self.rubric,
                        description="",
                        **variant,
                    )
            self.rubric.refresh_from_db()
            criterion.refresh_from_db()
            self.assertEqual(self.rubric.name, "Layihə təqdimatı")
            self.assertEqual(criterion.name, "Məzmun")
            self.assertEqual(criterion.max_points, 4)

    def test_model_relations_protect_rubric_evidence(self):
        with bypass_rls():
            criterion = self._score_one_criterion()
            for target in (criterion, self.component, self.rubric):
                with self.subTest(target=target), self.assertRaises(ProtectedError):
                    target.delete()

    def test_component_score_evidence_blocks_component_mutation_and_delete(self):
        with bypass_rls():
            ComponentScore.objects.create(
                organization=self.org,
                component=self.component,
                enrollment=self.enrollment,
                score=1,
                entered_by=self.teacher,
            )
            another_rubric = rubrics.save_rubric(
                organization=self.org,
                name="Başqa rubrik",
                criteria=[("Meyar", 10)],
            )
            mutations = (
                {
                    "id": str(self.component.id),
                    "name": self.component.name,
                    "max_score": 11,
                    "rubric_id": str(self.rubric.id),
                },
                {
                    "id": str(self.component.id),
                    "name": self.component.name,
                    "max_score": self.component.max_score,
                    "rubric_id": str(another_rubric.id),
                },
            )
            for definition in mutations:
                with self.subTest(definition=definition), self.assertRaises(ValidationError):
                    gradebook.save_components(
                        offering=self.offering,
                        definitions=[definition],
                        by_user=self.teacher,
                    )
            remaining = gradebook.save_components(offering=self.offering, definitions=[], by_user=self.teacher)
            self.component.refresh_from_db()
            self.assertIn(self.component.id, {component.id for component in remaining})
            self.assertEqual(self.component.max_score, 10)
            self.assertEqual(self.component.rubric_id, self.rubric.id)
