"""PostgreSQL database guards for component-scoped rubric evidence."""

from contextlib import contextmanager

from django.db import IntegrityError, connection, transaction

import pytest

from apps.registrar import rubrics
from apps.registrar.models import ComponentScore, CriterionScore, Rubric, RubricCriterion
from core.rls import bypass_rls

from .test_rubrics import RubricBaseTest

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(connection.vendor != "postgresql", reason="PostgreSQL triggers are required."),
]


class RubricDatabaseGuardTest(RubricBaseTest):
    def _rejects_sql(self, sql, params=()):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute(sql, params)
                    cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")
        with connection.cursor() as cursor:
            cursor.execute("SET CONSTRAINTS ALL DEFERRED")

    _PROBE_ROLE = "ems_guard_probe"
    # TRUNCATE ... CASCADE needs the TRUNCATE privilege on every table the
    # cascade reaches; criterion scores FK-reference the rubric criteria.
    _PROBE_TABLES = ("registrar_rubriccriterion", "registrar_criterionscore")

    def _drop_probe_role(self, cursor):
        cursor.execute(f"""
            DO $$
            BEGIN
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{self._PROBE_ROLE}') THEN
                    DROP OWNED BY {self._PROBE_ROLE};
                    DROP ROLE {self._PROBE_ROLE};
                END IF;
            END
            $$
            """)

    @contextmanager
    def _nonsuper_probe_role(self):
        with connection.cursor() as cursor:
            self._drop_probe_role(cursor)
            cursor.execute(f"CREATE ROLE {self._PROBE_ROLE}")
            cursor.execute(f"GRANT TRUNCATE ON TABLE {', '.join(self._PROBE_TABLES)} TO {self._PROBE_ROLE}")
        try:
            yield
        finally:
            with connection.cursor() as cursor:
                cursor.execute("RESET SESSION AUTHORIZATION")
                self._drop_probe_role(cursor)

    def _rejects_truncate_as_nonsuper(self, sql):
        # The guard waves superusers through (they could DROP the trigger
        # anyway) by checking session_user, which SET ROLE does not change.
        # Probe it under a guaranteed non-superuser role instead.
        with self._nonsuper_probe_role():
            with self.assertRaises(IntegrityError):
                with transaction.atomic():
                    with connection.cursor() as cursor:
                        cursor.execute(f"SET SESSION AUTHORIZATION {self._PROBE_ROLE}")
                        cursor.execute(sql)

    def _create_evidence(self):
        criterion = self.rubric.criteria.get(name="Məzmun")
        rubrics.save_criterion_scores(
            component=self.component,
            entries=[
                {
                    "criterion_id": str(criterion.id),
                    "enrollment_id": str(self.enrollment.id),
                    "points": "2",
                }
            ],
            by_user=self.teacher,
        )
        return criterion

    def test_coherence_guard_rejects_wrong_rubric_org_and_points(self):
        with bypass_rls():
            other_rubric = Rubric.objects.create(organization=self.org, name="PG other rubric")
            other_criterion = RubricCriterion.objects.create(
                organization=self.org,
                rubric=other_rubric,
                name="Other criterion",
                max_points=5,
            )
            cases = (
                {
                    "organization": self.org,
                    "component": self.component,
                    "criterion": other_criterion,
                    "enrollment": self.enrollment,
                    "points": 1,
                },
                {
                    "organization": self.org,
                    "component": self.component,
                    "criterion": self.rubric.criteria.first(),
                    "enrollment": self.enrollment,
                    "points": 99,
                },
            )
            for values in cases:
                with self.subTest(values=values), self.assertRaises(IntegrityError):
                    with transaction.atomic():
                        CriterionScore.objects.create(**values)

    def test_deferred_total_guard_rejects_missing_or_mismatched_rollup(self):
        with bypass_rls():
            criterion = self.rubric.criteria.first()
            with self.assertRaises(IntegrityError):
                with transaction.atomic():
                    CriterionScore.objects.create(
                        organization=self.org,
                        component=self.component,
                        criterion=criterion,
                        enrollment=self.enrollment,
                        points=1,
                    )
                    with connection.cursor() as cursor:
                        cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")
            with connection.cursor() as cursor:
                cursor.execute("SET CONSTRAINTS ALL DEFERRED")

            self._create_evidence()
            self._rejects_sql(
                "UPDATE registrar_componentscore SET score = %s WHERE component_id = %s AND enrollment_id = %s",
                [0, self.component.id, self.enrollment.id],
            )

    def test_component_score_alone_protects_component_identity_and_delete(self):
        with bypass_rls():
            ComponentScore.objects.create(
                organization=self.org,
                component=self.component,
                enrollment=self.enrollment,
                score=1,
                entered_by=self.teacher,
            )
            updates = (
                ("name = %s", ["Renamed"]),
                ("max_score = %s", [11]),
                ("rubric_id = NULL", []),
            )
            for assignment, values in updates:
                with self.subTest(assignment=assignment):
                    self._rejects_sql(
                        f"UPDATE registrar_assessmentcomponent SET {assignment} WHERE id = %s",
                        [*values, self.component.id],
                    )
            self._rejects_sql("DELETE FROM registrar_assessmentcomponent WHERE id = %s", [self.component.id])

    def test_scored_rubric_criterion_and_component_identity_is_immutable(self):
        with bypass_rls():
            criterion = self._create_evidence()
            operations = (
                (
                    "UPDATE registrar_rubriccriterion SET max_points = max_points + 1 WHERE id = %s",
                    [criterion.id],
                ),
                (
                    "UPDATE registrar_rubriccriterion SET name = %s WHERE id = %s",
                    ["Renamed criterion", criterion.id],
                ),
                ("UPDATE registrar_rubric SET name = %s WHERE id = %s", ["Renamed rubric", self.rubric.id]),
                ("DELETE FROM registrar_rubriccriterion WHERE id = %s", [criterion.id]),
                ("DELETE FROM registrar_rubric WHERE id = %s", [self.rubric.id]),
                ("DELETE FROM registrar_assessmentcomponent WHERE id = %s", [self.component.id]),
            )
            for sql, params in operations:
                with self.subTest(sql=sql):
                    self._rejects_sql(sql, params)
            self.assertTrue(CriterionScore.objects.filter(criterion=criterion, component=self.component).exists())

    def test_truncate_and_function_privileges_are_hardened(self):
        with bypass_rls():
            self._create_evidence()
            with connection.cursor() as cursor:
                cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")
                cursor.execute("SET CONSTRAINTS ALL DEFERRED")
            self._rejects_truncate_as_nonsuper("TRUNCATE registrar_rubriccriterion CASCADE")

        guarded_functions = {
            "registrar_guard_criterion_score_coherence",
            "registrar_assert_criterion_component_integrity",
            "registrar_assert_rubric_score_total",
            "registrar_guard_rubric_score_total",
            "registrar_guard_component_rubric_evidence",
            "registrar_guard_criterion_rubric_evidence",
            "registrar_guard_rubric_delete_with_evidence",
            "registrar_guard_rubric_evidence_no_truncate",
        }
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT p.proname, p.prosecdef, p.proconfig,
                       has_function_privilege('public', p.oid, 'EXECUTE')
                  FROM pg_catalog.pg_proc p
                  JOIN pg_catalog.pg_namespace n ON n.oid = p.pronamespace
                 WHERE n.nspname = 'public' AND p.proname = ANY(%s)
                """,
                [list(guarded_functions)],
            )
            rows = cursor.fetchall()
        self.assertEqual({row[0] for row in rows}, guarded_functions)
        for name, security_definer, config, public_execute in rows:
            with self.subTest(function=name):
                self.assertTrue(security_definer)
                self.assertIn("search_path=pg_catalog, public", config)
                self.assertFalse(public_execute)
